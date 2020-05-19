# Unbounded Thread Pool

Implementation of python's [`concurrent.futures.Executor`] that creates new threads on demand 
and stops them if they are not needed anymore. 

It is designed to allow infinite recursive submitting of tasks, so the following code works properly, 
despite creating of 10k threads:

```python
from unbounded_thread_pool import UnboundedThreadPoolExecutor

with UnboundedThreadPoolExecutor() as executor:
    def factorial(n: int):
        if n == 0 or n == 1:
            return 1
        else:
            return executor.submit(factorial, n - 1).result() * n
    print(factorial(10000))
```

# Installation

```
pip install unbounded_thread_pool
```

# Requirements

- Python (3.6, 3.7, 3.8)

# Usage 

`UnboundedThreadPoolExecutor` supports the following constructor parameters:
- `name: str`: Name of executor, all thread names are prefixed with it.
Default is `UnboundedThreadPoolExecutor`. 
- `max_thread_idle_time: float`: How many seconds idling worker thread should live.
Default is `30` seconds.

For more details about methods check official python docs about [`concurrent.futures.Executor`].

# Usage with `asyncio`

When you write a lot of sync code that calls async code and vice versa (for example, if you use
[asgiref] `sync_to_async` and `async_to_sync`) default asyncio executor can stuck. It happens 
in case you have the following code flow:

async code ---> sync code (1) ---> async code ---> sync code(2)

Here the second (2) sync code requires free worker to be available in thread pool, but 
thread pool can be already exhausted by the first (1) sync code. This causes deadlock, 
as (1) waits for (2), while (2) waits for (1) to free thread pool. To eliminate this issue, 
you can use `UnboundedThreadPoolExecutor`:
 
```python
loop = asyncio.get_running_loop()
loop.set_default_executor(UnboundedThreadPoolExecutor(name='AsyncioExecutor'))
```

---

[`concurrent.futures.Executor`]: https://hub.docker.com/r/kartoza/postgis/
[asgiref]: https://github.com/django/asgiref#function-wrappers
