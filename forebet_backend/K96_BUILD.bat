@echo off
rem ================================================================
rem   K96 PICKS - ONE-CLICK FULL BUILD (Electron desktop app)
rem   Needs: Node.js + Electron Builder  *  Python 3.10+  *  internet
rem   Steps: npm install -> electron-builder -> NSIS installer
rem ================================================================
chcp 65001 >nul
cd /d %~dp0
title K96 PICKS BUILDER

echo.
echo  === K96 PICKS - FULL DESKTOP BUILD =======================
echo.

rem -- 0. .env.local haifungwi ndani ya installer; weka resources\backend baada ya install.
if exist ".env.local" goto ENV_OK
echo   [0/5] .env.local haipo hapa; baada ya install, tengeneza resources\backend\.env.local.
goto ENV_DONE
:ENV_OK
echo   [0/5] .env.local ipo locally; builder haitai-copy. Weka copy resources\backend baada ya install.
:ENV_DONE

rem -- 1. Node.js ---------------------------------------------------
where node >nul 2>nul
if errorlevel 1 goto NONODE
echo   [1/5] Node.js ......... OK

rem -- 2. Python ----------------------------------------------------
where python >nul 2>nul
if errorlevel 1 goto NOPY
echo   [2/5] Python .......... OK

rem -- 3. pip deps ---------------------------------------------------
echo   [3/5] pip install -r requirements.txt ...
pip install -r requirements.txt --quiet
if errorlevel 1 goto PIPFAIL
echo         OK

rem -- 4. npm install ------------------------------------------------
echo   [4/5] npm install (electron + builder) ...
pushd electron
call npm install --silent
if errorlevel 1 goto NPMFAIL
echo         OK

rem -- 5. electron-builder -------------------------------------------
echo   [5/5] electron-builder (NSIS installer) ...
call npx electron-builder --win --x64
if errorlevel 1 goto EBFAIL
popd

echo.
echo  ============================================================
echo   IMEMALIZIKA!  Installer yako iko hapa:
echo     %CD%\dist_electron\K96 PICKS Setup 2.8.6.exe
echo.
echo   Install -> Start menu + Desktop "K96 PICKS" ni icon yako.
echo  ============================================================
pause
exit /b 0

:NONODE
echo   [X] Node.js haiko kwenye PATH. Install: https://nodejs.org
pause & exit /b 1

:NOPY
echo   [X] Python haiko kwenye PATH. Install: https://python.org
echo       Kumbuka tick: "Add Python to PATH" wakati wa install.
pause & exit /b 1

:PIPFAIL
echo   [X] pip imeshindwa. Angalia internet kisha rudia.
popd >nul 2>nul
pause & exit /b 1

:NPMFAIL
echo   [X] npm imeshindwa. Angalia internet / antivirus block kisha rudia.
popd
pause & exit /b 1

:EBFAIL
echo   [X] electron-builder imeshindwa. Soma log yake hapo juu.
popd
pause & exit /b 1
