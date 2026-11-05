@echo off
REM ============================================================================
REM  KIMATHY SMART BETTING ENGINE - kitufe kimoja (Windows)
REM  Bonyeza mara mbili. Faili la Excel litaenda kwenye folda ya Downloads.
REM ============================================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ============================================================
echo   KIMATHY SMART BETTING ENGINE
echo ============================================================
echo.

REM --- tafuta Python ---
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
    echo [KOSA] Python haipatikani kwenye PC hii.
    echo Sakinisha Python 3.10+ kutoka https://www.python.org/downloads/
    echo Hakikisha unaweka alama ya "Add Python to PATH" wakati wa usakinishaji.
    echo.
    pause
    exit /b 1
)

REM --- vyanzo (mara ya kwanza tu) ---
%PY% -c "import curl_cffi, bs4, openpyxl" >nul 2>nul
if errorlevel 1 (
    echo [SETUP] Inasakinisha vyanzo vinavyohitajika kwa mara ya kwanza...
    %PY% -m pip install --upgrade pip
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [KOSA] Usakinishaji wa vyanzo umeshindwa.
        pause
        exit /b 1
    )
)

REM --- endesha injini ---
%PY% -m kimathy.run %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo [OK] Uendeshaji umekamilika. Angalia folda ya Downloads.
) else (
    echo [ONYO] Uendeshaji umekamilika kwa onyo au kosa - code %RC%.
)
echo.
pause
endlocal
