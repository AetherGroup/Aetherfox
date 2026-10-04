@ECHO OFF
SETLOCAL
REM Aether: mach configure --full. Only needed if mozconfig.windows changes.
REM `mach build` runs configure automatically when the objdir is stale.
REM
REM Usage: scripts\windows\run-configure.cmd

CALL "%~dp0_env.cmd"
IF ERRORLEVEL 1 EXIT /B 1

ECHO [aether] configuring...
"%MOZILLABUILD%\start-shell.bat" -no-start -defterm -c ^
  "cd '%SRC_POSIX%' && MOZCONFIG='%MOZCONFIG_POSIX%' MACH_HIDE_DEV_DRIVE_SUGGESTION=1 python3 mach --no-interactive configure"
EXIT /B %ERRORLEVEL%