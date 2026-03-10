@echo off
chcp 65001 >nul
title OpenClaw 启动器

echo ========================================
echo      OpenClaw 自动启动程序
echo ========================================
echo.

:: 激活conda环境
call conda activate openclaw

:: 检查是否激活成功
if %errorlevel% neq 0 (
    echo [❌] 激活环境失败！请检查：
    echo     1. Conda是否正确安装
    echo     2. openclaw环境是否存在
    echo     3. 运行：conda info --envs 查看环境
    pause
    exit /b 1
)

echo [✅] Conda环境激活成功：openclaw
echo.

:: 执行Python程序
echo [🚀] 正在启动 OpenClaw Desk...
python main.py

:: 如果程序退出，暂停显示信息
echo.
echo [程序已退出]
pause