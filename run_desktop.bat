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

REM Check if the conda environment is activated
IF NOT DEFINED CONDA_DEFAULT_ENV (
    echo Conda is not initialized. Please initialize conda before running this script.
    exit /b 1
)

echo Current Conda environment: %CONDA_DEFAULT_ENV%

IF "%CONDA_DEFAULT_ENV%"=="code2llm" (
    echo Already in the 'code2llm' environment.
) ELSE (
    echo Activating 'code2llm' environment...
    call conda activate code2llm
    IF %ERRORLEVEL% NEQ 0 (
        echo Failed to activate 'code2llm' environment. Make sure conda is installed and the environment exists.
        exit /b 1
    )
)

REM Change to the directory of the batch script
cd /d "%~dp0"

REM Run the python script
echo Running main_desktop.py...
python main_desktop.py

echo Script finished.
pause