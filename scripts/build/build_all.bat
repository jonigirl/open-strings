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

echo Step 2: Building executable...
if /I "%1"=="--sign" (
    echo   Using Certum USB token - ensure token is plugged in.
    uv run python scripts\build\build_exe.py --sign
) else (
    uv run python scripts\build\build_exe.py --self-sign
)
if errorlevel 1 (
    set "FAIL_MSG=Failed to build executable"
    goto :fail
)
echo   - Executable created
echo.

echo Step 3: Verifying onedir build...
if not exist "dist\OpenStrings\" (
    set "FAIL_MSG=Build folder not found at dist\OpenStrings\"
    goto :fail
)
echo   - Build folder exists: OK
if /I "%1"=="--sign" (
    pwsh -NoProfile -NonInteractive -Command "if ((Get-AuthenticodeSignature -LiteralPath 'dist\OpenStrings\OpenStrings.exe').Status -ne 'Valid') { exit 1 }"
    if errorlevel 1 (
        set "FAIL_MSG=dist\OpenStrings\OpenStrings.exe signature is not valid"
        goto :fail
    )
    echo   - Executable signature: Valid
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
        set "FAIL_MSG=Installer creation failed"
        goto :fail
    )
    echo   - Installer created successfully!
    if /I "%1"=="--sign" (
        echo.
        echo Step 4b: Signing installer...
        for %%f in (dist\OpenStrings-*-Setup.exe) do (
            uv run python scripts\build\build_exe.py --sign-file "%%f"
            if errorlevel 1 (
                set "FAIL_MSG=Installer signing failed: %%f"
                goto :fail
            )
            pwsh -NoProfile -NonInteractive -Command "if ((Get-AuthenticodeSignature -LiteralPath '%%f').Status -ne 'Valid') { exit 1 }"
            if errorlevel 1 (
                set "FAIL_MSG=Installer signature is not valid: %%f"
                goto :fail
            )
            echo   - Installer signature: Valid
        )
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
exit /b 0

:: Exits inside ( ) blocks can return 0 when the script is run via cmd /c, so all failures jump here.
:fail
echo ERROR: !FAIL_MSG!
pause
exit /b 1
