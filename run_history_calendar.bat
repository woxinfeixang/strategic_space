@echo off
echo Starting Historical Economic Calendar Workflow...

REM 定义项目根目录 (脚本将在此目录下运行)
set "PROJECT_DIR=E:\Programming\strategic_space"
REM 定义虚拟环境路径
set "VENV_PATH=%PROJECT_DIR%\.venv"
REM 定义要运行的 Python 脚本的相对路径
set "SCRIPT_PATH=economic_calendar\tasks\run_history_workflow.py"

REM 切换到项目根目录
cd /d "%PROJECT_DIR%"
if %errorlevel% neq 0 (
    echo ERROR: Failed to change directory to %PROJECT_DIR%
    goto :eof
)
echo Current directory: %cd%

REM 检查虚拟环境是否存在
if not exist "%VENV_PATH%\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found at %VENV_PATH%
    goto :eof
)

REM 激活虚拟环境
echo Activating virtual environment...
call "%VENV_PATH%\Scripts\activate.bat"
if %errorlevel% neq 0 (
    echo ERROR: Failed to activate virtual environment.
    goto :eof
)

REM 检查 Python 脚本是否存在
if not exist "%SCRIPT_PATH%" (
    echo ERROR: Python script not found at %SCRIPT_PATH%
    goto :eof
)

REM 运行 Python 脚本
echo Running Python script: %SCRIPT_PATH%
REM 使用虚拟环境中的 Python 运行脚本
python "%SCRIPT_PATH%"

if %errorlevel% neq 0 (
    echo ERROR: Python script execution failed.
) else (
    echo Python script finished successfully.
)

echo Workflow finished.

REM 如果需要手动运行时看到输出，可以取消下面这行的注释
pause

:eof 