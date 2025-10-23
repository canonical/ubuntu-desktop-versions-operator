# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Integration test helpers and utilities."""

import functools
import logging
import time

APP_NAME = "ubuntu-desktop-versions"


def retry(retry_num, retry_sleep_sec):
    """Retry decorator for flaky operations.

    Args:
        retry_num: Number of times to retry
        retry_sleep_sec: Seconds to sleep between retries
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for i in range(retry_num):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    if i >= retry_num - 1:
                        raise Exception(f"Exceeded {retry_num} retries") from exc
                    logging.error(
                        "func %s failure %d/%d: %s", func.__name__, i + 1, retry_num, exc
                    )
                    time.sleep(retry_sleep_sec)

        return wrapper

    return decorator
