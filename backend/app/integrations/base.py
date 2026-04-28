import functools
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable

logger = logging.getLogger(__name__)

K8S_NAMESPACE_PREFIX = "kubeai-"


def with_retry(max_retries: int = 3, backoff_base: float = 1.0):
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
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
            raise last_exception

        return wrapper

    return decorator


class BaseIntegration(ABC):
    @abstractmethod
    def health_check(self) -> bool: ...
