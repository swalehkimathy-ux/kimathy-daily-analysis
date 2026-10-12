@echo off
REM ============================================================
REM KIMATHY DAILY ANALYSIS - Prepare the Android project and open Android Studio
REM Double-click this file after extracting the ZIP.
REM ============================================================
setlocal EnableExtensions
cd /d "%~dp0"
echo Project folder: %CD%
echo.

if not exist "package.json" (
  echo ERROR: package.json is missing. Extract the complete ZIP first.
  goto :err
)

where node >nul 2>nul
if errorlevel 1 (
  echo ERROR: Node.js is not installed. Install Node.js 22 LTS, version 22.12 or newer.
  goto :err
)
where npm >nul 2>nul
if errorlevel 1 (
  echo ERROR: npm was not found. Reinstall Node.js with npm included.
  goto :err
)
node -e "const [major,minor]=process.versions.node.split('.').map(Number);if(!(major>22||(major===22&&minor>=12)))process.exit(1)"
if errorlevel 1 (
  echo ERROR: Use Node.js 22.12 or newer.
  echo Node.js 22 LTS is recommended.
  goto :err
)

echo Node.js version:
node --version
echo.
echo ==^> [1/5] Installing the locked project dependencies...
if exist "package-lock.json" (
  call npm ci
) else (
  call npm install
)
if errorlevel 1 goto :err

echo.
echo ==^> [2/5] Preparing the private dashboard for Android...
call npm run build
if errorlevel 1 goto :err

if not exist "android\app\build.gradle" (
  echo.
  echo ==^> Android platform files are missing; creating them now...
  call npx cap add android
  if errorlevel 1 goto :err
)

echo.
echo ==^> [3/5] Syncing the web app into the Android project...
call npx cap sync android
if errorlevel 1 goto :err

echo.
echo ==^> [4/5] Opening Android Studio...
call npx cap open android
if errorlevel 1 goto :err

echo.
echo ============================================================
echo Preparation is complete. In Android Studio:
echo   1. Wait for Gradle Sync to finish.
echo   2. Choose Build ^> Build Bundle(s) / APK(s) ^> Build APK(s).
echo   3. Install the debug APK on your phone for testing.
echo.
echo Debug APK path:
echo   android\app\build\outputs\apk\debug\app-debug.apk
echo ============================================================
echo.
pause
exit /b 0

:err
echo.
echo Preparation stopped. Read the error above and check README_ANDROID.md.
pause
exit /b 1
