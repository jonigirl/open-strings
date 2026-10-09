"""Build the pinned Windows DataForge exporter without redistributing game data."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

UPSTREAM_URL = "https://github.com/dolkensp/unp4k.git"
UPSTREAM_COMMIT = "b492ab14d26280c6ec91c4365ff0faf5f3e24a6b"
TOOL_VERSION = "v4.0.87-os1"
FRAMEWORK = "net9.0"
RUNTIME = "win-x64"
ASSET_NAME = f"unforge-openstrings-{TOOL_VERSION}-{RUNTIME}.zip"
TEMPLATES = Path(__file__).with_name("unforge")
DEFAULT_OUTPUT = Path(tempfile.gettempdir()) / "openstrings-tools" / TOOL_VERSION


def run(*command, cwd=None):
    subprocess.run(command, cwd=cwd, check=True)


def build(output: Path, source: Path | None = None) -> Path:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"Build output already exists: {output}")
    output.mkdir(parents=True)
    checkout = output / "source"
    if source is None:
        run("git", "init", str(checkout))
        run("git", "fetch", "--depth=1", UPSTREAM_URL, UPSTREAM_COMMIT, cwd=checkout)
        run("git", "checkout", "--detach", "FETCH_HEAD", cwd=checkout)
    else:
        run("git", "clone", "--no-hardlinks", "--no-checkout", str(source.resolve()), str(checkout))
        run("git", "checkout", "--detach", UPSTREAM_COMMIT, cwd=checkout)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=checkout, text=True).strip()
    if revision != UPSTREAM_COMMIT:
        raise RuntimeError("Upstream revision does not match the pinned commit")
    run("git", "apply", "--check", str(TEMPLATES / "parser.patch"), cwd=checkout)
    run("git", "apply", str(TEMPLATES / "parser.patch"), cwd=checkout)
    shutil.copy2(TEMPLATES / "RecordExporter.cs", checkout / "src" / "unforge" / "RecordExporter.cs")
    for name in ("unforge", "unforge.cli"):
        project = checkout / "src" / name / f"{name}.csproj"
        tree = ET.parse(project)
        target = tree.find("./PropertyGroup/TargetFrameworks")
        target.tag = "TargetFramework"
        target.text = FRAMEWORK
        tree.write(project, encoding="utf-8", xml_declaration=True)
    publish = output / "publish"
    run(
        "dotnet",
        "publish",
        str(checkout / "src" / "unforge.cli" / "unforge.cli.csproj"),
        "-c",
        "Release",
        "-r",
        RUNTIME,
        "--self-contained",
        "true",
        "-p:PublishSingleFile=true",
        "-p:IncludeNativeLibrariesForSelfExtract=true",
        "-p:PublishTrimmed=false",
        "-o",
        str(publish),
    )
    shutil.copy2(checkout / "LICENSE.txt", publish / "LICENSE.txt")
    project_root = Path(__file__).resolve().parents[2]
    shutil.copy2(project_root / "LICENSE", publish / "OPENSTRINGS-LICENSE.txt")
    shutil.copy2(project_root / "NOTICE.md", publish / "NOTICE.md")
    build_info = {
        "toolVersion": TOOL_VERSION,
        "upstreamCommit": UPSTREAM_COMMIT,
        "patchSha256": hashlib.sha256((TEMPLATES / "parser.patch").read_bytes()).hexdigest(),
        "exporterSha256": hashlib.sha256((TEMPLATES / "RecordExporter.cs").read_bytes()).hexdigest(),
        "framework": FRAMEWORK,
        "runtime": RUNTIME,
    }
    (publish / "build-info.json").write_text(json.dumps(build_info, indent=2), encoding="utf-8")
    artifact = output / ASSET_NAME
    with zipfile.ZipFile(artifact, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(publish.iterdir()):
            if path.is_file() and path.suffix != ".pdb":
                info = zipfile.ZipInfo(path.name, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, path.read_bytes())
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "size": artifact.stat().st_size,
                **build_info,
            },
            indent=2,
        )
    )
    return artifact


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--source", type=Path, help="Existing official Git checkout; only the pinned commit is used")
    options = parser.parse_args()
    build(options.output, options.source)
