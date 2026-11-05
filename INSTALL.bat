@echo off
REM ============================================================================
REM  KIMATHY SMART BETTING ENGINE - USAKINISHAJI (mara moja tu)
REM  Inasakinisha: vyanzo vya Python + browser ya Playwright (ya kupita Cloudflare)
REM ============================================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ============================================================
echo   KIMATHY - USAKINISHAJI
echo ============================================================
echo.

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
    echo [KOSA] Python haipatikani kwenye PC hii.
    echo.
    echo   1) Pakua Python 3.10+ : https://www.python.org/downloads/
    echo   2) Wakati wa usakinishaji WEKA ALAMA ya "Add Python to PATH"
    echo   3) Rudia hapa na uendeshe INSTALL.bat tena
    echo.
    pause
    exit /b 1
)

echo [1/3] Inasasisha pip...
%PY% -m pip install --upgrade pip

echo.
echo [2/3] Inasakinisha vyanzo vya Python...
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
    echo [KOSA] Usakinishaji wa vyanzo umeshindwa.
    pause
    exit /b 1
)

echo.
echo [3/3] Inapakua browser ya Playwright (ya kupita Cloudflare)...
%PY% -m playwright install chromium
if errorlevel 1 (
    echo [ONYO] Playwright haikusakinishwa. Injini itaendelea, lakini
    echo        Forebet inaweza kuzuiliwa. Jaribu:  %PY% -m playwright install chromium
)

echo.
echo ============================================================
echo   USAKINISHAJI UMEKAMILIKA
echo.
echo   Hatua inayofuata:  bonyeza DIAGNOSE.bat
echo   Kila siku:         bonyeza RUN_KIMATHY.bat
echo ============================================================
echo.
pause
endlocal
