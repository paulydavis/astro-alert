@echo off
REM Build AstroAlert.exe for Windows using PyInstaller.
REM Usage: double-click build.bat, or run from a command prompt.

echo =^> Installing / upgrading PyInstaller...
pip install --quiet --upgrade pyinstaller
if %ERRORLEVEL% neq 0 (
    echo ERROR: pip install failed. Make sure Python is on your PATH.
    pause
    exit /b 1
)

echo =^> Cleaning previous build...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

echo =^> Building AstroAlert.exe...
pyinstaller AstroAlert.spec
if %ERRORLEVEL% neq 0 (
    echo ERROR: PyInstaller failed. See output above.
    pause
    exit /b 1
)

echo.
echo Build complete: dist\AstroAlert.exe
echo.
echo To install:
echo   Copy dist\AstroAlert.exe anywhere you like and double-click it.
echo   Optionally create a shortcut on your Desktop.
echo.
echo Note: Windows SmartScreen may warn about an unsigned app.
echo   Click "More info" then "Run anyway" to proceed.
echo.
pause
