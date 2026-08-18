from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def minimal_forge_fixture(tmp_path):
    """Create minimal DataForge structure for integration testing."""
    forge_dir = tmp_path / "dataforge"
    records = forge_dir / "raw" / "libs" / "foundry" / "records"
    records.mkdir(parents=True, exist_ok=True)

    # Create minimal required directory structure
    (records / "entities" / "scitem").mkdir(parents=True, exist_ok=True)
    (records / "entities" / "spaceships").mkdir(parents=True, exist_ok=True)

    return forge_dir


@pytest.fixture
def minimal_base_ini(tmp_path):
    """Create minimal base.ini for testing."""
    ini_file = tmp_path / "base.ini"
    ini_file.write_text("test_key=test_value\nanother_key=another_value\n", encoding="utf-8")
    return ini_file


def test_pipeline_rejects_incomplete_facade(minimal_base_ini, minimal_forge_fixture, tmp_path):
    """The incomplete facade must fail rather than silently generate no output."""
    # Defer import so the script module loads properly
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.utils.enhancement_pipeline import EnhancementPipeline

    output_dir = tmp_path / "output"

    # Create and run pipeline
    pipeline = EnhancementPipeline(
        forge_dir=minimal_forge_fixture,
        base_ini_path=minimal_base_ini,
        output_dir=output_dir,
    )

    with pytest.raises(RuntimeError, match="not implemented"):
        pipeline.run()


def test_pipeline_rejects_categories_without_generation(minimal_base_ini, minimal_forge_fixture, tmp_path):
    """Category selection cannot make the incomplete facade appear functional."""
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.utils.enhancement_pipeline import EnhancementPipeline

    output_dir = tmp_path / "output"

    # Request only specific categories
    pipeline = EnhancementPipeline(
        forge_dir=minimal_forge_fixture,
        base_ini_path=minimal_base_ini,
        output_dir=output_dir,
        categories={"ship_descs"},
    )

    with pytest.raises(RuntimeError, match="not implemented"):
        pipeline.run()
