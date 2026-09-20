@echo off
rem Sets: VEHICLE_ROOT, BACKEND_DIR, FRONTEND_URL, BACKEND_PORT, FRONTEND_PORT, PYTHON_EXE, PY_LAUNCHER

if not defined VEHICLE_ROOT set "VEHICLE_ROOT=%~dp0.."
pushd "%VEHICLE_ROOT%" 2>nul || (
  echo ERROR: Cannot enter project directory: %VEHICLE_ROOT%
  exit /b 1
)
set "VEHICLE_ROOT=%CD%"
popd

set "BACKEND_DIR=%VEHICLE_ROOT%\backend"
set "FRONTEND_URL=http://127.0.0.1:5500/frontend/"
set "BACKEND_PORT=5050"
set "FRONTEND_PORT=5500"

set "PYTHON_EXE="
for /f "delims=" %%P in ('where python 2^>nul') do (
  if not defined PYTHON_EXE (
    echo %%P | findstr /i "WindowsApps" >nul
    if errorlevel 1 set "PYTHON_EXE=%%P"
  )
)

set "PY_LAUNCHER="
if not defined PYTHON_EXE (
  where py >nul 2>&1 && set "PY_LAUNCHER=1"
)

exit /b 0
