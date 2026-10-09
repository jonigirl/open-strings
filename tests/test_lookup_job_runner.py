"""Tests for the concurrent lookup/generator job runner in generate_enhancements_ini.

Covers exception retries, the lookup concurrency cap, and content-based cache
invalidation. Exception retries do not recover native process crashes.
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


@pytest.mark.parametrize("name", ["scitem_lookups", "blueprint_pools", "reputation", "component_tag_fallbacks"])
@pytest.mark.parametrize("changed_input", ["xml", "localization", "patch", "added_xml", "removed_xml"])
def test_lookup_cache_tracks_actual_inputs(gen_module, tmp_path, name, changed_input):
    import os

    records = tmp_path / "raw" / "libs" / "foundry" / "records"
    records.mkdir(parents=True)
    xml = records / "example.xml"
    xml.write_text('<Record value="A"/>', encoding="utf-8")
    identity = tmp_path / gen_module.DATAFORGE_IDENTITY_FILE
    identity.write_text('{"patch_fingerprint":"A"}', encoding="utf-8")
    (tmp_path / ".p4k_mtime").write_text("unchanged", encoding="utf-8")
    loc = {"item_name": "Item A", "item_desc": "Size: 1"}
    calls = []

    def builder():
        calls.append(True)
        return len(calls)

    def lookup():
        return gen_module._cached_lookup(
            tmp_path, name, builder, dependency_key=gen_module._dataforge_cache_key(tmp_path, loc)
        )

    assert lookup() == 1
    assert lookup() == 1
    if changed_input in {"xml", "patch"}:
        path = xml if changed_input == "xml" else identity
        before = path.stat()
        path.write_text(path.read_text(encoding="utf-8").replace('"A"', '"B"'), encoding="utf-8")
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        assert path.stat().st_size == before.st_size
    elif changed_input == "localization":
        loc["item_name"] = "Item B"
        loc["item_desc"] = "Size: 2"
    elif changed_input == "added_xml":
        (records / "added.xml").write_text("<Record/>", encoding="utf-8")
    else:
        xml.unlink()
    assert lookup() == 2
    assert lookup() == 2
