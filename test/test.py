import threading
import time
from unittest import TestCase

from unbounded_thread_pool import pool

# Following variable is used for hard-coded sleeps
_EPSILON = 0.0001


class UnboundPoolTests(TestCase):

    def setUp(self) -> None:
        self.executor = pool.UnboundedThreadPoolExecutor()

    def tearDown(self) -> None:
        self.executor.shutdown(wait=True)

    def test_run_single_func(self):
        done = False

        def func():
            nonlocal done
            time.sleep(_EPSILON)
            done = True

        future = self.executor.submit(func)
        future.result()
        self.assertTrue(done)

    def test_future_contain_proper_result(self):
        def func():
            return 42

        future = self.executor.submit(func)
        self.assertTrue(future.result(), 42)

    def test_exception_is_propogated(self):
        def func():
            raise KeyError

        future = self.executor.submit(func)
        with self.assertRaises(KeyError):
            future.result()

    def test_executor_passes_parameters(self):
        passed_args = None
        passed_kwargs = None

        def func(*args, **kwargs):
            nonlocal passed_args, passed_kwargs
            passed_args = args
            passed_kwargs = kwargs

        future = self.executor.submit(func, 1, 2, 3, foo=4, bar='5')
        future.result()
        self.assertEqual(passed_args, (1, 2, 3))
        self.assertEqual(passed_kwargs, dict(foo=4, bar='5'))

    def test_running_many_small_tasks(self):
        done = set()

        def func(index):
            nonlocal done
            time.sleep(_EPSILON)
            done.add(index)

        for _ in self.executor.map(func, range(100)):
            pass

        self.assertEqual(done, set(range(100)))

    def test_not_executed_if_cancelled(self):
        called = False

        def func():
            nonlocal called
            called = True

        while True:
            future = self.executor.submit(func)
            if future.cancel():
                time.sleep(10 * _EPSILON)
                self.assertFalse(called)
                break
            else:
                future.result()
                called = False

    def test_all_thread_are_destroyed_after_max_thread_idle_time(self):

        def noop():
            time.sleep(_EPSILON)
            pass

        with pool.UnboundedThreadPoolExecutor(max_thread_idle_time=0.2) as executor:
            initial_count = threading.active_count()
            for _ in range(10):
                executor.submit(noop)

            time.sleep(0.2 + 0.1)  # Sleep additional time to allow threads to be cleaned out

            self.assertEqual(initial_count, threading.active_count())

    def test_recursive_submits_works_properly(self):
        max_recursion = 5000

        def func(level: int):
            if level == 0:
                return 0
            else:
                return self.executor.submit(func, level - 1).result() + 1

        future = self.executor.submit(func, max_recursion)
        self.assertTrue(future.result(), max_recursion)

    def test_all_thread_are_destroyed_after_shutdown(self):
        initial_count = threading.active_count()

        def noop():
            time.sleep(_EPSILON)
            pass

        with pool.UnboundedThreadPoolExecutor(max_thread_idle_time=30) as executor:
            for _ in range(10):
                executor.submit(noop)

        self.assertEqual(initial_count, threading.active_count())

    def test_race_condition_of_thread_cleaning_and_task_submition(self):
        time_delta = 0.2
        iterations = 10
        tasks_in_iteration = 10

        done = 0

        def func():
            nonlocal done
            time.sleep(_EPSILON)
            done += 1

        with pool.UnboundedThreadPoolExecutor(name='in test', max_thread_idle_time=time_delta) as executor:
            for _ in range(iterations):
                for _ in range(tasks_in_iteration):
                    executor.submit(func)
                time.sleep(time_delta)

            self.assertEqual(done, iterations * tasks_in_iteration)


