"""Tests for the concurrent lookup/generator job runner in generate_enhancements_ini.

Covers the retry-on-SystemError behaviour added after real-world reports of
`SystemError: error return without exception set` from CPython's C-accelerated
XML parser under memory pressure, and the lower concurrency cap applied to
DataForge lookup building specifically.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "generate_enhancements_ini.py"


@pytest.fixture(scope="module")
def gen_module():
    spec = importlib.util.spec_from_file_location("generate_enhancements_job_runner_test", _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_run_jobs_with_retry_returns_all_results(gen_module):
    jobs = {"a": lambda: 1, "b": lambda: 2, "c": lambda: 3}
    results = gen_module._run_jobs_with_retry(jobs, max_workers=2, thread_name_prefix="test")
    assert results == {"a": 1, "b": 2, "c": 3}


def test_run_jobs_with_retry_recovers_from_system_error(gen_module):
    """A job that fails once with SystemError succeeds on the serial retry."""
    calls = {"count": 0}

    def flaky():
        calls["count"] += 1
        if calls["count"] == 1:
            raise SystemError("error return without exception set")
        return "recovered"

    jobs = {"flaky": flaky, "stable": lambda: "ok"}
    results = gen_module._run_jobs_with_retry(jobs, max_workers=2, thread_name_prefix="test")
    assert results == {"flaky": "recovered", "stable": "ok"}
    assert calls["count"] == 2


def test_run_jobs_with_retry_propagates_persistent_failure(gen_module):
    """If the serial retry also fails, the exception is not swallowed."""

    def always_fails():
        raise SystemError("still broken")

    jobs = {"broken": always_fails}
    with pytest.raises(SystemError, match="still broken"):
        gen_module._run_jobs_with_retry(jobs, max_workers=1, thread_name_prefix="test")


def test_lookup_max_workers_caps_concurrency(gen_module):
    """Lookup building must stay capped below the generator's general worker count."""
    assert gen_module.LOOKUP_MAX_WORKERS <= 3
