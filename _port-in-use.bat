@echo off
set "CHECK_PORT=%~1"
if "%CHECK_PORT%"=="" exit /b 1

set "PORT_IN_USE=0"
set "PORT_PID="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /i "LISTENING" ^| findstr ":%CHECK_PORT% "') do (
  set "PORT_IN_USE=1"
  set "PORT_PID=%%a"
  goto :done
)
:done
exit /b 0
