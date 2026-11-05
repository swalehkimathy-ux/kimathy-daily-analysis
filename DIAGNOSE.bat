@echo off
REM ============================================================================
REM  KIMATHY - KIPIMO CHA VYANZO
REM  Endesha hii mara moja baada ya usakinishaji, au wakati wowote injini
REM  inapotoa "NO QUALIFIED ACCUMULATOR" na wewe unataka kujua sababu.
REM ============================================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
    echo [KOSA] Python haipatikani. Sakinisha Python 3.10+ kwanza.
    pause
    exit /b 1
)

%PY% -m kimathy.diagnose
echo.
pause
endlocal
