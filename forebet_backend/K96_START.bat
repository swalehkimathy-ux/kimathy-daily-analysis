@echo off
title K96 PICKS - Server (USIFUNGE dirisha hili)
cd /d "%~dp0"
set PY=py
where py >nul 2>nul
if errorlevel 1 set PY=python
%PY% --version >nul 2>nul
if errorlevel 1 goto NO_PY

rem -- zima K96 ya zamani iliyobaki kwenye port 8777 (ingeonyesha GUI ya zamani / black screen)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8777" ^| findstr "LISTENING"') do (
    echo Nazima server ya zamani PID %%a ...
    taskkill /F /T /PID %%a >nul 2>&1
)

%PY% -u gui_server.py
if errorlevel 1 goto CRASH
exit /b 0

:NO_PY
echo [ERROR] Python haipo au haiko kwenye PATH. Endesha kwanza INSTALL_K96.bat
echo         au pakua Python: https://www.python.org/downloads - tick "Add python.exe to PATH"
pause
exit /b 1

:CRASH
echo.
echo [ERROR] K96 PICKS imesimama. Soma ujumbe hapo juu.
echo         Mara nyingi suluhisho: endesha INSTALL_K96.bat kisha jaribu tena.
pause
exit /b 1
