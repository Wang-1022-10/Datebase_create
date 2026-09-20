@echo off
chcp 65001 >nul
setlocal EnableExtensions

set "ROOT=%~dp0.."
if exist "%~dp0_env.bat" call "%~dp0_env.bat"
if exist "%ROOT%\scripts\_env.bat" call "%ROOT%\scripts\_env.bat"

set "BACKEND=%ROOT%\backend"
set "SQL=%ROOT%\backend\src\main\resources\db\signal_osm_seed.sql"
set "IMPORT_PS1=%ROOT%\scripts\import-sql.ps1"

where mvn >nul 2>&1 || (
  echo ERROR: 未找到 Maven ^(mvn^)。请安装 Maven 并把 bin 加入 PATH。
  echo 或在 IDEA 自带终端中运行本脚本。
  exit /b 1
)

dir /b "%ROOT%\net\*.pbf" >nul 2>&1 || (
  echo ERROR: net\ 下没有 *.osm.pbf
  exit /b 1
)

echo [1/2] 扫描 OSM 生成 signal_osm_seed.sql ...
pushd "%BACKEND%"
call mvn -q compile exec:java "-Dexec.mainClass=com.driving.tools.OsmSignalSqlGenerator"
set "GEN_ERR=%ERRORLEVEL%"
popd
if not "%GEN_ERR%"=="0" exit /b %GEN_ERR%

if /i not "%~1"=="sql-only" (
  echo [2/2] 导入 MySQL ...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%IMPORT_PS1%" -SqlFile "%SQL%"
  if errorlevel 1 exit /b 1
)

echo 完成: %SQL%
exit /b 0
