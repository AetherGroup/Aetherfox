@ECHO OFF
SETLOCAL
REM Aether: mach build --full. Takes 1-3 hours from scratch.
REM Equivalent to running scripts/build.py, but inside MozillaBuild's shell.
REM
REM Usage: scripts\windows\run-build.cmd

CALL "%~dp0_env.cmd"
IF ERRORLEVEL 1 EXIT /B 1

ECHO [aether] building (1-3 h on first run)...
"%MOZILLABUILD%\start-shell.bat" -no-start -defterm -c ^
  "cd '%SRC_POSIX%' && MOZCONFIG='%MOZCONFIG_POSIX%' MACH_HIDE_DEV_DRIVE_SUGGESTION=1 python3 mach --no-interactive build"
EXIT /B %ERRORLEVEL%