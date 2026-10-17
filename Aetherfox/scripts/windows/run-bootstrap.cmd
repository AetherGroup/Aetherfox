@ECHO OFF
SETLOCAL
REM Aether: mach bootstrap for a full (non-artifact) build.
REM Installs the toolchains into %%USERPROFILE%%\.mozbuild.
REM Only needed once per machine. Takes ~20 minutes.
REM
REM Usage: scripts\windows\run-bootstrap.cmd

CALL "%~dp0_env.cmd"
IF ERRORLEVEL 1 EXIT /B 1

ECHO [aether] bootstrapping (this installs clang, rust, nasm, nsis)...
"%MOZILLABUILD%\start-shell.bat" -no-start -defterm -c ^
  "cd '%SRC_POSIX%' && MOZCONFIG='%MOZCONFIG_POSIX%' MACH_HIDE_DEV_DRIVE_SUGGESTION=1 python3 mach --no-interactive bootstrap --application-choice browser"
EXIT /B %ERRORLEVEL%