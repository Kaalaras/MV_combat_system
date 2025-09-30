"""Project-wide pytest configuration hooks."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Generator

import pytest

pytest_plugins = ("pytest_asyncio",)


_original_fixture = pytest.fixture


def _wrap_fixture_function(func: Callable[..., Any]) -> Callable[..., Any]:
    if asyncio.iscoroutinefunction(func):
        def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return asyncio.run_coroutine_threadsafe(func(*args, **kwargs), loop).result()
            return loop.run_until_complete(func(*args, **kwargs))

        return _sync_wrapper
    return func


def fixture(*fixture_args: Any, **fixture_kwargs: Any):
    """Patched ``pytest.fixture`` supporting async fixture functions transparently."""

    if fixture_args and callable(fixture_args[0]) and not fixture_kwargs:
        func = _wrap_fixture_function(fixture_args[0])
        return _original_fixture(func)

    def decorator(func: Callable[..., Any]):
        wrapped = _wrap_fixture_function(func)
        return _original_fixture(*fixture_args, **fixture_kwargs)(wrapped)

    return decorator


pytest.fixture = fixture


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Provide a single asyncio event loop for the entire test session."""

    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()

