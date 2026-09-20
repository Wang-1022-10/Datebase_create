@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>&1 || (
  echo ERROR: 未找到 python
  pause
  exit /b 1
)

echo 生成模拟 SQL ...
python generate_seed_sql.py
if errorlevel 1 pause & exit /b 1

echo 写入 demo.db ...
python init_demo_db.py
if errorlevel 1 pause & exit /b 1

echo.
echo 示例: python longitudinal_idm.py --db demo.db
pause
