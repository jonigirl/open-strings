# Build Instructions for Open Strings

## Quick Start

**Build executable (recommended):**

```bash
uv run python scripts/build/build_exe.py
```

**Certum-signed executable and installer:**

```powershell
.\scripts\build\build_all.bat --sign
```

---

## Prerequisites

### Required Software

1. **Python 3.12+** and **UV** (`https://docs.astral.sh/uv/getting-started/installation/`) — required
2. **PyInstaller** — installed automatically by `uv sync`
3. **Inno Setup 6** — required for the installer
4. **Windows SDK signing tools and Certum token** — required for `--sign`

### Download Inno Setup (Optional)

For creating the installer, download from: https://jrsoftware.org/isdl.php

- Install the Unicode version
- Default installation is fine

---

## Step 0 (Optional): Exclude User Data

The executable does not bundle user cache data. Do not include the DataForge cache in a
distribution: its protected `pristine/` and `raw/` layers are created at runtime from the
user's installed `Data.p4k`.

---

## Step 1: Build the Executable

Run the build script from the project root:

```bash
uv run python scripts/build/build_exe.py
```

This will:

- Clean previous builds
- Package the application into an onedir bundle
- Include all necessary data files
- Create `dist/OpenStrings/OpenStrings.exe`

**Testing the build:**

```bash
dist\OpenStrings\OpenStrings.exe
```

---

## Step 2: Create the Installer (Recommended)

### Option A: Using build_all.bat (Automated)

```bash
cd scripts/build
build_all.bat
```

This runs both build_exe.py and Inno Setup automatically.

### Option B: Using Inno Setup GUI

1. Open Inno Setup Compiler
2. File → Open → Select `installer.iss` (in project root)
3. Build → Compile
4. The installer will be created under `dist/`

### Option C: Using Command Line

```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

The installer will be created as:

```
dist/OpenStrings-{VERSION}-Setup.exe
```

---

## Step 3: Test the Installer

1. Run the installer: `dist/OpenStrings-{VERSION}-Setup.exe`
2. Follow the installation wizard
3. Test the installed application:
   - Launch the app
   - Click "Extract DataForge from P4K" to load data
   - Edit some strings
   - Apply to game
   - Check that files are in the right location

---

## Code Signing

`build_all.bat --sign` signs the onedir executable and installer using the Certum
token. Enter the token PIN directly in its signing dialog, never in build arguments.
Check both artifacts with `Get-AuthenticodeSignature` after building.

The default build creates a temporary self-signed certificate for the executable;
it does not separately sign the installer. Windows trust warnings are expected.

The top-level `dist/OpenStrings.exe` is an intermediate copy, not the signed
executable packaged in the installer. Test `dist/OpenStrings/OpenStrings.exe`.

## Patched Extraction Tool

The patched unforge package is a separate release asset, not a game-data bundle.
Build it with an installed .NET 9 SDK:

```powershell
uv run python scripts/build/build_unforge.py
```

The helper checks out the pinned upstream revision, applies the maintained patch,
and produces a self-contained Windows package with the original MIT notice,
the project GPL license, and the distribution notice. The matching release tag
contains the modifications; `build-info.json` records the upstream revision.
Users do not need to install .NET. The build prints the artifact path and SHA-256.

The package must match the digest pinned in `src/utils/tools_manager.py`. Rebuilding
or signing its contents can change that digest; verify and update the pin before
packaging the app. Upload the exact package with the matching release before making
the installer available. Do not silently fall back to the unpatched exporter.

For an unpublished local smoke installer, bundle the verified package so installation
can recover even if an upgrade removes the existing tool cache:

```powershell
$env:OPENSTRINGS_UNFORGE_PACKAGE = "C:\BuildAssets\patched-unforge.zip"
.\scripts\build\build_all.bat --sign
```

The executable builder also accepts `--unforge-package PATH`. It checks the pinned
digest before building and places the ZIP in `dist/OpenStrings/tools/`, which the
installer includes. At runtime the app checks the digest again before installing
the bundled extractor. Missing upstream unp4k is still downloaded normally.

Archive existing build folders if they need to be preserved;
the application build scripts otherwise clean `build/` and `dist/`.

---

The installer includes:

- ✅ Main executable (`OpenStrings.exe`)
- ✅ Application help, fonts, and patch definitions (no extracted game data)
- ✅ Start menu shortcuts
- ✅ User config setup

---

## File Sizes (Approximate)

- **Application folder**: includes Python, PyQt6, supporting files, and the bundled tool ZIP
- **Installer**: approximately 100 MB with the patched extractor bundled; sizes vary by build

---

## Version Update Checklist

For future versions:

1. Update version in:
   - `VERSION.TXT` (e.g., `1.3.0`) — this is the single source of truth; `installer.iss` reads it via ISPP
   - `pyproject.toml` — `version = "..."` field
   - `uv.lock` — refresh with `uv lock` after changing the project version
   - `CHANGELOG.md` — rename `[Unreleased]` to `[X.Y.Z] - YYYY-MM-DD` and add a new `[X.Y.Z]` diff link at the bottom

2. Rebuild:

   ```bash
   cd scripts/build
   build_all.bat
   ```

3. Test installer and executable

4. Create release notes

5. Tag in git:

   ```bash
   git tag -a v0.2.0 -m "Release v0.2.0"
   git push origin v0.2.0
   ```

6. Create GitHub release with:
   - Release notes
   - Installer executable
   - Matching digest-pinned patched unforge ZIP

---

## Troubleshooting

### "PyInstaller not found"

```powershell
uv sync
```

### "Module not found" errors

Make sure all dependencies are installed:

```powershell
uv sync
```

### Executable is too large

This is normal for PyQt6 applications. PyInstaller bundles the entire Python runtime and all libraries (60-100MB is standard).

### Inno Setup not found

Install from: https://jrsoftware.org/isdl.php

Or compile the installer manually by:

1. Opening `installer.iss` in Inno Setup Compiler
2. Clicking Build → Compile

---

**Ready to build!** Run `build_all.bat` or follow the steps above.
