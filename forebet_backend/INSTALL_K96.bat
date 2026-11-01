@echo off
title K96 PICKS - Kusakinisha (endesha mara MOJA tu)
cd /d "%~dp0"
echo ==========================================================
echo    K96 PICKS v2.8.4 - One-Click Setup
echo ==========================================================
echo.

set PY=py
where py >nul 2>nul
if errorlevel 1 set PY=python
%PY% --version >nul 2>nul
if errorlevel 1 goto NO_PY

echo [1/3] Python imepatikana:
%PY% --version
echo.

echo [2/3] Kupakua dependencies (curl_cffi, beautifulsoup4, playwright...) - subiri dakika 1-3...
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto PIP_FAIL

echo.
echo [3/3] Kupakua browser ya Playwright (Chromium) - inahitajika kupita Cloudflare ya Forebet...
%PY% -m playwright install chromium
if errorlevel 1 goto PW_FAIL

echo.
echo [+] Kuweka icon "K96 PICKS" kwenye Desktop (inafungua K96_START.bat)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut($d + '\K96 PICKS.lnk'); $s.TargetPath='%~dp0K96_START.bat'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0logo_k96.ico'; $s.Save()"
if errorlevel 1 echo [WARN] Icon haikuwekwa - tumia K96_START.bat moja kwa moja.

echo.
echo ==========================================================
echo    [OK] IMEKAMILIKA. Kuanzia sasa fungua app kwa:
echo      icon "K96 PICKS" kwenye Desktop  (au K96_START.bat)
echo    Kukagua Supabase:  TEST_CONNECTION.bat
echo ==========================================================
pause
exit /b 0

:NO_PY
echo [ERROR] Python haipo au haiko kwenye PATH.
echo         Pakua: https://www.python.org/downloads  (weka tick "Add python.exe to PATH")
pause
exit /b 1

:PIP_FAIL
echo [ERROR] pip install imeshindwa - hakikisha internet iko sawa (zima VPN/proxy kama ipo) kisha jaribu tena.
pause
exit /b 1

:PW_FAIL
echo [WARN] Playwright Chromium haikusakinishwa. App itafanya kazi, lakini Forebet ikiweka Cloudflare
echo        scraper haitaweza kufungua browser. Endesha tena: %PY% -m playwright install chromium
pause
exit /b 0
