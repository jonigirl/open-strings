@echo off
setlocal enabledelayedexpansion
:: Always run from the project root regardless of where this script is invoked from
cd /d "%~dp0..\.." 

echo ========================================
echo Open Strings - Build Script
echo ========================================
echo.

echo Step 1: Cleaning old builds...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist
echo   - Old builds removed
echo.

echo Step 2: Building executable (self-signed)...
uv run python scripts\build\build_exe.py --self-sign
if errorlevel 1 (
    echo ERROR: Failed to build executable
    pause
    exit /b 1
)
echo   - Executable created
echo.

echo Step 3: Verifying onedir build...
if exist "dist\OpenStrings\" (
    echo   - Build folder exists: OK
) else (
    echo   - ERROR: Build folder not found at dist\OpenStrings\
    pause
    exit /b 1
)
echo.

echo Step 4: Creating installer (requires Inno Setup)...
set ISCC=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"  set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe

if "%ISCC%"=="" (
    echo WARNING: Inno Setup not found
    echo Skipping installer creation
    echo You can install Inno Setup from: https://jrsoftware.org/isdl.php
    echo Or create the installer manually by opening installer.iss
) else (
    "%ISCC%" installer.iss
    if errorlevel 1 (
        echo WARNING: Installer creation failed
        echo You can create it manually with Inno Setup
    ) else (
        echo   - Installer created successfully!
    )
)
echo.

echo ========================================
echo Build Complete!
echo ========================================
echo.
echo Outputs:
for %%f in (dist\OpenStrings-*-Setup.exe) do (
    echo   [OK] Installer: %%f
)
echo.
echo Next steps:
echo   1. Test the installer: dist\OpenStrings-*-Setup.exe
echo   2. Distribute the installer.
echo.
pause
