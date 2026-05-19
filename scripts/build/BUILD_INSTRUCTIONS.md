# Build Instructions for Open Strings

## Quick Start

**Build executable (recommended):**

```bash
uv run python scripts/build/build_exe.py
```

**Build everything (executable + installer):**

```bash
cd scripts/build
build_all.bat
```

---

## Prerequisites

### Required Software

1. **Python 3.12+** and **UV** (`https://docs.astral.sh/uv/getting-started/installation/`) — required
2. **PyInstaller** — installed automatically by `uv sync`

### Download Inno Setup (Optional)

For creating the installer, download from: https://jrsoftware.org/isdl.php

- Install the Unicode version
- Default installation is fine

---

## Step 0 (Optional): Clean Cache for Distribution

If distributing to users, optionally clean the DataForge cache to reduce user data size:

```bash
uv run python scripts/build/clean_cache_for_distribution.py
```

This removes the `raw/` DataForge extraction (keeping the filtered `libs/` which has all necessary stats data).
Users can regenerate raw/ if needed by re-extracting their P4K.

**Note:** The executable doesn't bundle user cache data - it's created at runtime. This script is only
useful if you've manually included cache in any distribution package.

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
- Create `dist/OpenStrings-{VERSION}/OpenStrings.exe`

**Testing the build:**

```bash
dist\OpenStrings-{VERSION}\OpenStrings.exe
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
4. The installer will be created in project root

### Option C: Using Command Line

```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

The installer will be created in the project root as:

```
OpenStrings-{VERSION}-Setup.exe
```

---

## Step 3: Test the Installer

1. Run the installer: `OpenStrings-{VERSION}-Setup.exe`
2. Follow the installation wizard
3. Test the installed application:
   - Launch the app
   - Click "Extract DataForge from P4K" to load data
   - Edit some strings
   - Apply to game
   - Check that files are in the right location

---

## Code Signing

Builds are always self-signed automatically — no configuration needed.

A temporary self-signed certificate is created in your Windows cert store and used to sign the executable. The installer is not separately signed. SmartScreen will still show an "Unknown Publisher" warning (this is expected for self-signed builds).

No environment variables, prompts, or flags are required.

---

The installer includes:

- ✅ Main executable (`OpenStrings.exe`)
- ✅ Data files (default global.ini)
- ✅ Start menu shortcuts
- ✅ User config setup

---

## File Sizes (Approximate)

- **Executable**: ~60-100 MB (includes Python runtime, PyQt6, and all dependencies)
- **Installer**: ~30-50 MB (compressed)

---

## Version Update Checklist

For future versions:

1. Update version in:
   - `VERSION.TXT` (e.g., `1.3.0`) — this is the single source of truth; `installer.iss` reads it via ISPP
   - `pyproject.toml` — `version = "..."` field
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
   - Standalone executable

---

## Troubleshooting

### "PyInstaller not found"

```bash
.venv\Scripts\pip install pyinstaller
```

### "Module not found" errors

Make sure all dependencies are installed:

```bash
.venv\Scripts\pip install -r requirements.txt
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
