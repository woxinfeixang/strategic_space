@echo off
:: 设置UTF-8编码以解决乱码问题
chcp 65001 >nul
title MT5历史数据更新

:: 设置Python环境变量以支持UTF-8
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set PYTHONLEGACYWINDOWSSTDIO=1

:: 检查是否有silent参数
set SILENT_MODE=0
if "%1"=="silent" set SILENT_MODE=1

if %SILENT_MODE%==0 (
    echo ======================================
    echo    MT5历史数据更新工具
    echo ======================================
    echo 正在更新历史数据，请等待...
    echo.
)

:: 切换到脚本所在的父目录（模块根目录的父目录）
cd /d "%~dp0..\..\..\"

:: 运行历史数据更新
python -m market_price_data.scripts.data_updater history

:: 根据返回值和静默模式决定行为
if %errorlevel% equ 0 (
    if %SILENT_MODE%==0 (
        echo.
        echo 历史数据更新成功完成！
        echo.
        echo 按任意键退出...
        pause >nul
    ) else (
        exit /b 0
    )
) else (
    if %SILENT_MODE%==0 (
        echo.
        echo 历史数据更新过程中出现错误，请查看日志获取详细信息。
        echo.
        echo 按任意键退出...
        pause >nul
    )
    exit /b 1
) 