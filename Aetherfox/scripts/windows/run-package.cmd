@ECHO OFF
SETLOCAL
REM Aether: mach package --full. Staged binaries land in obj-aether\dist.
REM
REM Usage: scripts\windows\run-package.cmd

CALL "%~dp0_env.cmd"
IF ERRORLEVEL 1 EXIT /B 1

ECHO [aether] packaging...
"%MOZILLABUILD%\start-shell.bat" -no-start -defterm -c ^
  "cd '%SRC_POSIX%' && MOZCONFIG='%MOZCONFIG_POSIX%' MACH_HIDE_DEV_DRIVE_SUGGESTION=1 python3 mach --no-interactive package"
EXIT /B %ERRORLEVEL%