@echo off
setlocal

rem Resolve the project root from this launcher's location, not the current directory.
for %%I in ("%~dp0..") do set "PROJECT_DIR=%%~fI"
set "ROBOT_EXE=%PROJECT_DIR%\.venv-windows\Scripts\robot.exe"
set "BOT_FILE=%PROJECT_DIR%\rpa\bots\overdue_reminder_bot.robot"
set "RESULTS_DIR=%PROJECT_DIR%\rpa\results"

if not defined LIBRARY_ADMIN_EMAIL (
    echo ERROR: LIBRARY_ADMIN_EMAIL is not set.
    exit /b 2
)
if not defined LIBRARY_ADMIN_PASSWORD (
    echo ERROR: LIBRARY_ADMIN_PASSWORD is not set.
    exit /b 2
)
if not exist "%ROBOT_EXE%" (
    echo ERROR: Robot executable not found: "%ROBOT_EXE%"
    exit /b 3
)
if not exist "%BOT_FILE%" (
    echo ERROR: Robot bot not found: "%BOT_FILE%"
    exit /b 4
)

"%ROBOT_EXE%" --outputdir "%RESULTS_DIR%" "%BOT_FILE%"
set "ROBOT_EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %ROBOT_EXIT_CODE%
