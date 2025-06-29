@echo off
REM Check if conda is in the path
where conda >nul 2>&1
if %errorlevel% neq 0 (
    echo Conda not found in path. Trying Miniconda installation...
    if exist "C:\APPLIS\miniconda3\Scripts\activate.bat" (
        call C:\APPLIS\miniconda3\Scripts\activate.bat
    ) else (
        echo Miniconda installation not found. Make sure conda is installed.
        exit /b 1
    )
)

REM This script activates a Conda environment (if not already active) and runs a Python script.

echo --- Checking Conda environment ---

REM Check if the 'code2llm' environment is already active.
if "%CONDA_DEFAULT_ENV%"=="code2llm" (
    echo Conda environment 'code2llm' is already active.
) else (
    echo Activating Conda environment 'code2llm'...
    call conda activate code2llm

    REM Verify if the activation was successful
    if %errorlevel% neq 0 (
        echo.
        echo ERROR: Could not activate Conda environment 'code2llm'.
        echo Verify that the environment exists and that Conda is in your PATH.
        pause
        exit /b %errorlevel%
    )
    echo Environment activated.
)

echo.
echo --- Changing directory to D:\DONNEES\DEV\gpt\code-to-llm ---
cd /d "%~dp0"

echo --- Launching the Python server ---
python llm_context_builder.py serve --port 8080

echo.
echo --- The server script is finished. Press any key to close this window. ---
pause