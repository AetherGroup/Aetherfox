@ECHO OFF
REM Aether: shared setup for the MozillaBuild wrappers.
REM Sourced by run-bootstrap.cmd, run-configure.cmd, run-build.cmd and
REM run-package.cmd. Not meant to be run directly.
REM
REM Every path is derived from this file's own location, so the repository can
REM live anywhere on disk.

SET "REPO=%~dp0..\.."
SET "SRC=%REPO%\..\firefox-src"
REM The worktree cannot be named firefox-src when the path has to stay short:
REM "C:\firefox-src\" is already 15 characters of prefix, and with the real tree
REM that yields 230-character paths, past the ~224 mozmake tolerates (the libxul
REM link then fails with a bogus "No rule to make target"). Any path ending in
REM \firefox-src\ is unworkable, which is why FIREFOX_SRC can point the wrappers
REM at a short worktree such as C:\fs. See docs/BUILD.md.
IF DEFINED FIREFOX_SRC SET "SRC=%FIREFOX_SRC%"
SET "MOZCONFIG_FILE=%REPO%\mozconfig.windows"

IF NOT DEFINED MOZILLABUILD SET "MOZILLABUILD=C:\mozilla-build"

IF NOT EXIST "%MOZILLABUILD%\start-shell.bat" (
  ECHO [aether] MozillaBuild not found at "%MOZILLABUILD%".
  ECHO [aether] Install it from https://ftp.mozilla.org/pub/mozilla/libraries/win32/MozillaBuildSetup-Latest.exe
  ECHO [aether] or point MOZILLABUILD at an existing install.
  EXIT /B 1
)

IF NOT EXIST "%SRC%\mach" (
  ECHO [aether] No Firefox checkout at "%SRC%".
  ECHO [aether] Run: python scripts\sync.py
  EXIT /B 1
)

REM MSYS2 needs POSIX-style paths inside the shell. cygpath writes to a temp
REM file rather than a FOR /F pipe, because cmd misparses a quoted executable
REM path inside backticks.
SET "CYGPATH_OUT=%TEMP%\aether-cygpath.txt"

"%MOZILLABUILD%\msys2\usr\bin\cygpath.exe" -u "%SRC%" > "%CYGPATH_OUT%"
SET /P SRC_POSIX=<"%CYGPATH_OUT%"

"%MOZILLABUILD%\msys2\usr\bin\cygpath.exe" -u "%MOZCONFIG_FILE%" > "%CYGPATH_OUT%"
SET /P MOZCONFIG_POSIX=<"%CYGPATH_OUT%"

DEL /Q "%CYGPATH_OUT%"