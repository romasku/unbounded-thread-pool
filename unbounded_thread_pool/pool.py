import atexit
import logging
import queue
import threading
import weakref
from concurrent.futures import Executor, Future
from dataclasses import dataclass
from threading import Thread
from typing import Callable, Union, Type, List

logger = logging.getLogger(__name__)


@dataclass
class PoolState:
    # Special class to hold all Poll data. It is safe to have strong reference on it
    max_thread_idle_time: float
    name: str

    queue: "queue.Queue[Union[Type[DieTask], TaskItem]]"
    resurrector_event: threading.Event
    shutting_down: bool = False
    die_task_reached: bool = False


@dataclass
class TaskItem:
    future: Future
    func: Callable
    args: tuple
    kwargs: dict

    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
        except BaseException as exc:
            self.future.set_exception(exc)
            # Break a reference cycle with the exception 'exc'
            self = None
        else:
            self.future.set_result(result)


class DieTask:
    # Used to notify Worker that it should exit
    pass


class _WorkerThread(Thread):

    def __init__(self, name: str, pool_state: PoolState):
        super().__init__(name=name, daemon=True)
        self.pool_state = pool_state

    class StopException(Exception):
        pass

    def main_loop(self):
        try:
            task = self.pool_state.queue.get(timeout=self.pool_state.max_thread_idle_time)
        except queue.Empty:
            raise self.StopException()  # We were idle for `max_thread_idle_time`, so we should exit now
        else:
            if task is DieTask:
                self.pool_state.queue.put(task)
                self.pool_state.die_task_reached = True
                raise self.StopException()
            elif task.future.set_running_or_notify_cancel():
                task.run()

    def run(self) -> None:
        logger.info(f'WorkerThread {self.name} starting')
        try:
            while True:
                self.main_loop()
        except self.StopException:
            logger.info(f'WorkerThread {self.name} shutting down')


class _ResurrectorThread(Thread):
    base_timeout = 0.01
    max_timeout = 2

    _worker_threads_id: int
    threads: List[_WorkerThread]

    def __init__(self, name: str, pool_state: PoolState):
        super().__init__(name=name, daemon=True)
        self._worker_threads_id = 1
        self.threads = []
        self.pool_state = pool_state

    def run(self) -> None:
        logger.info(f'ResurrectorThread {self.name} starting')
        timeout = self.base_timeout
        while not self.pool_state.die_task_reached:
            if not self.pool_state.queue.empty():
                # This means that there are more tasks then workers
                worker_thread = _WorkerThread(
                    name=f'{self.pool_state.name}WorkerThread {self._worker_threads_id}',
                    pool_state=self.pool_state,
                )
                self.threads.append(worker_thread)
                worker_thread.start()
                self._worker_threads_id += 1
                timeout = self.base_timeout
            else:
                timeout = min(timeout * 2, self.max_timeout)

            if self.pool_state.resurrector_event.wait(timeout=timeout):
                self.pool_state.resurrector_event.clear()

        for thread in self.threads:
            thread.join()
        logger.info(f'ResurrectorThread {self.name} shutting down')


def _atexit_handler(executor_ref):
    executor = executor_ref()
    if executor and not executor.state.shutting_down:
        executor.shutdown(wait=True)


class UnboundedThreadPoolExecutor(Executor):
    state: PoolState
    _resurrector_thread: _ResurrectorThread
    _shutdown_lock: threading.Lock

    def __init__(self, name: str = 'UnboundedThreadPoolExecutor', max_thread_idle_time: float = 30):
        self.state = PoolState(
            name=name,
            max_thread_idle_time=max_thread_idle_time,
            queue=queue.Queue(),
            resurrector_event=threading.Event(),
        )
        self._resurrector_thread = _ResurrectorThread(
            name=f'{name}ResurrectorThread',
            pool_state=self.state,
        )
        self._resurrector_thread.start()
        self._shutdown_lock = threading.Lock()

        atexit.register(_atexit_handler, weakref.ref(self))

    def submit(*args, **kwargs):
        # Copy-pasted from concurrent.futures.thread.ThreadPoolExecutor
        # this is required to support passing fn both as args and kwarg
        if len(args) >= 2:
            self, fn, *args = args
        elif not args:
            raise TypeError("descriptor 'submit' of 'ThreadPoolExecutor' object "
                            "needs an argument")
        elif 'fn' in kwargs:
            fn = kwargs.pop('fn')
            self, *args = args
            import warnings
            warnings.warn("Passing 'fn' as keyword argument is deprecated",
                          DeprecationWarning, stacklevel=2)
        else:
            raise TypeError('submit expected at least 1 positional argument, '
                            'got %d' % (len(args) - 1))
        with self._shutdown_lock:
            if self.state.shutting_down:
                raise RuntimeError('cannot schedule new futures after shutdown')
            future = Future()
            self.state.queue.put(TaskItem(future, fn, args, kwargs))
            self.state.resurrector_event.set()
            return future

    def __del__(self):
        # If there is no reference, there can be no race with .submit call
        self.state.shutting_down = True
        self.state.queue.put(DieTask)
        self.state.resurrector_event.set()

    def shutdown(self, wait=True):
        with self._shutdown_lock:
            self.state.shutting_down = True
            self.state.queue.put(DieTask)
            self.state.resurrector_event.set()

        if wait:
            self._resurrector_thread.join()

