@echo off
REM Batch script to run the historical market data update once.
REM It activates the specified conda environment before running the Python script.

echo Activating Python environment (conda base) and running history update...

REM --- Method 1: Using 'conda run' (Recommended for scripting) ---
REM Ensure 'base' is the correct name of your conda environment where
REM the project dependencies (pandas, MetaTrader5, omegaconf, etc.) are installed.
conda run -n base python -m market_price_data.scripts.run_data_service --history-once
REM Check the exit code of the previous command (optional)
if %errorlevel% neq 0 (
    echo ERROR: Python script failed with exit code %errorlevel%
    REM pause
    exit /b %errorlevel%
)

REM --- Method 2: Using 'conda activate' (Alternative, might be less reliable in scheduled tasks) ---
REM Make sure the path to conda.bat is correct for your system.
REM set CONDA_ACTIVATE_PATH=C:\Users\YourUsername\anaconda3\Scripts\conda.bat
REM if not exist "%CONDA_ACTIVATE_PATH%" (
REM     echo ERROR: Cannot find conda activate script at %CONDA_ACTIVATE_PATH%
REM     echo Please update the path in the batch script.
REM     pause
REM     exit /b 1
REM )
REM call "%CONDA_ACTIVATE_PATH%" activate base
REM if %errorlevel% neq 0 ( echo ERROR: Failed to activate conda environment 'base'. & pause & exit /b 1 )
REM python -m market_price_data.scripts.run_data_service --history-once
REM set SCRIPT_ERRORLEVEL=%errorlevel%
REM call "%CONDA_ACTIVATE_PATH%" deactivate
REM if %SCRIPT_ERRORLEVEL% neq 0 (
REM     echo ERROR: Python script failed with exit code %SCRIPT_ERRORLEVEL%
REM     pause
REM     exit /b %SCRIPT_ERRORLEVEL%
REM )

echo History update script finished successfully.

REM Uncomment the next line to keep the window open after execution to see output/errors.
REM pause 