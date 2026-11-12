@echo off
chcp 65001 >nul
rem 重置秒杀数据基线（跑 -m miaosha_write 前执行）
rem 等价于：python -m tools seed --stock 10
rem 数据库账号密码不再写在本文件里，见 data/env.local.yaml 或环境变量 MIAOSHA_DB_PASSWORD
cd /d %~dp0

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m tools seed %*
) else (
    python -m tools seed %*
)

if errorlevel 1 (
    echo.
    echo [失败] 重置未完成，先运行 python -m tools doctor 检查依赖
    pause
)
