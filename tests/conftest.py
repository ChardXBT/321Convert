import threading

import pytest

import app as app_module
from core import config, runner


@pytest.fixture(autouse=True)
def _inline_isolation(monkeypatch):
    """Fast in-process conversions plus clean rate-limit/semaphore state."""
    monkeypatch.setattr(config, "CONVERSION_ISOLATION", "inline")
    monkeypatch.setattr(
        runner,
        "_SEMAPHORE",
        threading.BoundedSemaphore(config.MAX_CONCURRENT_CONVERSIONS),
    )
    app_module.rate_limit_hits.clear()
    yield
    app_module.rate_limit_hits.clear()


@pytest.fixture()
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()
