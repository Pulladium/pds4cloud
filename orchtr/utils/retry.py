import time
from collections.abc import Callable, Iterable
from typing import TypeVar

T = TypeVar("T")


class NonRetryableError(Exception):
    """Raise for permanent failures that must not be retried."""


def retry_call(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    delays: Iterable[float] = (0.0, 1.0),
    sleep_fn: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, BaseException, float], None] | None = None,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    give_up_on: tuple[type[BaseException], ...] = (NonRetryableError,),
) -> T:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    delay_values = list(delays)
    last_exc: BaseException | None = None

    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except give_up_on:
            raise
        except retry_on as exc:
            last_exc = exc
            if attempt >= attempts:
                raise

            delay = delay_values[min(attempt - 1, len(delay_values) - 1)] if delay_values else 0.0
            if on_retry is not None:
                on_retry(attempt, exc, delay)
            if delay > 0:
                sleep_fn(delay)
        except Exception as exc:
            raise

    raise RuntimeError("retry_call exhausted without exception") from last_exc
