import logging
import queue
import threading
from concurrent.futures import Executor, Future
from dataclasses import dataclass
from threading import Thread
from typing import Callable, Union, Type

logger = logging.getLogger(__name__)


@dataclass
class TaskItem:
    future: Future
    func: Callable
    args: tuple
    kwargs: dict


class DieTask:
    # Used to notify Worker that it should exit
    pass


class _PoolThead(Thread):

    def __init__(self, name: str, executor: 'UnboundedThreadPoolExecutor'):
        super().__init__(name=name)
        self.executor = executor


class _WorkerThread(_PoolThead):

    def run(self) -> None:
        logger.info(f'WorkerThread {self.name} starting')
        try:
            self.executor.active_count += 1
            while True:
                try:
                    task = self.executor._queue.get(timeout=self.executor.max_thread_idle_time)
                except queue.Empty:
                    return  # We were idle for `max_thread_idle_time`, so we should exit now
                else:
                    if task is DieTask:
                        return
                    elif not task.future.set_running_or_notify_cancel():
                        continue
                    else:
                        result = task.func(*task.args, **task.kwargs)
                        task.future.set_result(result)
        finally:
            self.executor.active_count -= 1
            logger.info(f'WorkerThread {self.name} shutting down')


class _ResurrectorThread(_PoolThead):
    base_timeout = 0.01
    max_timeout = 2

    _worker_threads_id = 1
    threads = []

    def __init__(self, name: str, executor: 'UnboundedThreadPoolExecutor'):
        super().__init__(name=name, executor=executor)
        self._worker_threads_id = 1
        self.threads = []

    def run(self) -> None:
        logger.info(f'ResurrectorThread {self.name} starting')
        timeout = self.base_timeout
        while not self.executor._shutting_down:
            if not self.executor._queue.empty():
                # This means that there are more tasks then workers
                worker_thread = _WorkerThread(
                    name=f'{self.executor.name}WorkerThread {self._worker_threads_id}',
                    executor=self.executor,
                )
                self.threads.append(worker_thread)
                worker_thread.start()
                self._worker_threads_id += 1
                timeout = self.base_timeout
            else:
                timeout = min(timeout * 2, self.max_timeout)
            if self.executor._resurrector_event.wait(timeout=timeout):
                self.executor._resurrector_event.clear()

        for thread in self.threads:
            thread.join()
        logger.info(f'ResurrectorThread {self.name} shutting down')


class UnboundedThreadPoolExecutor(Executor):
    active_count: int = 0
    max_thread_idle_time: float
    name: str

    _queue: "queue.Queue[Union[Type[DieTask], TaskItem]]"
    _shutting_down: bool = False
    _resurrector_event: threading.Event

    def __init__(self, name: str = 'UnboundedThreadPoolExecutor', max_thread_idle_time: float = 30):
        self.name = name
        self.max_thread_idle_time = max_thread_idle_time
        self._queue = queue.Queue()
        self._resurrector_event = threading.Event()
        self._resurrector_thread = _ResurrectorThread(
            name=f'{self.name}ResurrectorThread',
            executor=self,
        )
        self._resurrector_thread.start()

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
        future = Future()
        self._queue.put(TaskItem(future, fn, args, kwargs))
        self._resurrector_event.set()
        return future

    def shutdown(self, wait=True):
        self._shutting_down = True
        for _ in range(self.active_count):
            self._queue.put(DieTask)
        self._resurrector_event.set()

        if wait:
            self._resurrector_thread.join()

