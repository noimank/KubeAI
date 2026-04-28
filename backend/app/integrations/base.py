import functools
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

K8S_NAMESPACE_PREFIX = "kubeai-"


def with_retry(max_retries: int = 3, backoff_base: float = 1.0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: BaseException | None = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    wait = backoff_base * (2 ** (attempt - 1))
                    logger.warning(
                        "K8s operation %s failed (attempt %d/%d): %s",
                        func.__name__,
                        attempt,
                        max_retries,
                        e,
                    )
                    if attempt < max_retries:
                        import time

                        time.sleep(wait)
            assert last_exception is not None
            raise last_exception

        return wrapper

    return decorator


class BaseIntegration(ABC):
    @abstractmethod
    def health_check(self) -> bool: ...
