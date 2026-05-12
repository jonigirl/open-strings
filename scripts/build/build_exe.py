"""
Build script for creating Open Strings executable

Usage:
    python build_exe.py              # build and self-sign
    python build_exe.py --self-sign  # same as above (explicit)

Self-signed certs provide integrity verification only.
SmartScreen will still warn "Unknown Publisher" — that is expected.
"""

import argparse
import glob
import importlib.util
import os
import shutil
import subprocess
import sys

import PyInstaller.__main__

# ---------------------------------------------------------------------------
# Code-signing helpers
# ---------------------------------------------------------------------------


def find_signtool() -> str | None:
    """Return path to signtool.exe, checking PATH then common Windows SDK locations."""
    found = shutil.which("signtool")
    if found:
        return found
    env_path = os.environ.get("SIGNTOOL_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path
    # Search Windows SDK bin dirs, newest version first
    patterns = [
        r"C:\Program Files (x86)\Windows Kits\10\bin\10.*\x64\signtool.exe",
        r"C:\Program Files\Windows Kits\10\bin\10.*\x64\signtool.exe",
    ]
    candidates: list[str] = []
    for pattern in patterns:
        candidates.extend(glob.glob(pattern))
    candidates.sort(reverse=True)
    return candidates[0] if candidates else None


# ---------------------------------------------------------------------------
# Self-signing helpers
# ---------------------------------------------------------------------------

_SELF_SIGN_SUBJECT = "CN=Open Strings (Self-Signed Build)"
_SELF_SIGN_STORE = "Cert:\\CurrentUser\\My"


def create_self_signed_cert() -> tuple[str, None]:
    """Create a code-signing cert in the current user's cert store via PowerShell.

    Returns (thumbprint, None).  The cert is valid for 2 years.
    """
    print("  Creating self-signed certificate...")
    ps_create = (
        f"$cert = New-SelfSignedCertificate "
        f"-Type CodeSigningCert "
        f"-Subject '{_SELF_SIGN_SUBJECT}' "
        f"-CertStoreLocation '{_SELF_SIGN_STORE}' "
        f"-NotAfter (Get-Date).AddYears(2) "
        f"-HashAlgorithm SHA256; "
        f"Write-Output $cert.Thumbprint"
    )
    # Use pwsh (PowerShell 7).
    ps_exe = "pwsh"
    result = subprocess.run(
        [ps_exe, "-NoProfile", "-NonInteractive", "-Command", ps_create],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stdout + result.stderr).strip()
        raise RuntimeError(f"New-SelfSignedCertificate failed:\n{detail}")

    lines = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
    if not lines:
        detail = result.stderr.strip()
        raise RuntimeError(
            "New-SelfSignedCertificate produced no output."
            + (f"\n{detail}" if detail else "")
            + "\nThis usually means the current user lacks permission to write to the "
            "certificate store. Try running the build as Administrator, or use "
            "--sign with a PFX file instead."
        )
    thumb = lines[-1]
    if not thumb:
        raise RuntimeError("Could not read thumbprint from New-SelfSignedCertificate output.")
    print(f"  - Certificate created (thumbprint: {thumb[:16]}...)")

    return thumb, None


def run_self_sign(file_path: str) -> None:
    """Create a self-signed cert and sign *file_path*; exits with code 1 on failure."""
    signtool = find_signtool()
    if not signtool:
        print(
            "ERROR: signtool.exe not found.\n"
            "  Install the Windows 10/11 SDK, add signtool to PATH, or set SIGNTOOL_PATH."
        )
        sys.exit(1)
    try:
        thumb, _ = create_self_signed_cert()
        # Self-signed certs have no trusted timestamp authority — sign without /tr
        cmd = [
            signtool,
            "sign",
            "/sha1",
            thumb,
            "/fd",
            "SHA256",
            "/d",
            "Open Strings",
            file_path,
        ]
        print(f"  Signing (self-signed): {os.path.basename(file_path)}")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            detail = (res.stdout + res.stderr).strip()
            raise RuntimeError(f"signtool failed:\n{detail}")
        print("  - Signed OK (self-signed — SmartScreen warning will still appear)")
    except (OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(description="Build Open Strings executable.")
parser.add_argument(
    "--self-sign",
    action="store_true",
    default=True,
    help="Build and self-sign with a new temporary self-signed cert (default).",
)
args = parser.parse_args()

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

# Get the project directory
project_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(os.path.dirname(project_dir))

# Add src to path for imports
sys.path.insert(0, os.path.join(root_dir, "src"))

# Get version from VERSION.TXT
version_file = os.path.join(root_dir, "VERSION.TXT")
with open(version_file) as f:
    current_version = f.read().strip()

print(f"\n{'=' * 60}")
print(f"Building version: {current_version}")
print(f"{'=' * 60}\n")

# Clean previous builds
print("Cleaning old builds...")
for folder in ["build", "dist"]:
    path = os.path.join(root_dir, folder)
    if os.path.exists(path):
        shutil.rmtree(path)
        print(f"  - Removed {folder}/")

print()

# Build using spec file from repo root
print("Building --onedir version (for installer)...")
print()

os.chdir(root_dir)

# Generate PE version resource
gen_script = os.path.join(project_dir, "gen_version_info.py")
spec = importlib.util.spec_from_file_location("gen_version_info", gen_script)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.generate(root_dir)
print("  - version_info.txt generated")
print()

try:
    PyInstaller.__main__.run(["OpenStrings.spec"])
    print(f"\n{'=' * 60}")
    print("Build successful!")
    print(f"{'=' * 60}")
    print("Executable: dist/OpenStrings/OpenStrings.exe")
    print()
except Exception as e:
    print(f"\nError building executable: {e}")
    sys.exit(1)

exe_path = os.path.join(root_dir, "dist", "OpenStrings", "OpenStrings.exe")
if not os.path.isfile(exe_path):
    print(f"WARNING: built exe not found at expected path: {exe_path}")
else:
    print("Self-signing executable...")
    run_self_sign(exe_path)
    print()
