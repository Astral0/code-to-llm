@echo off
setlocal enabledelayedexpansion

REM Function to find conda installation
set "CONDA_PATH="

REM Check if conda is in the path
where conda >nul 2>&1
if %errorlevel% equ 0 (
    echo Conda found in PATH.
    set "CONDA_PATH=conda"
    goto :conda_found
)

REM Try common conda installation paths
echo Conda not found in PATH. Searching for conda installation...

REM Check for Miniconda installation
if exist "C:\APPLIS\miniconda3\Scripts\conda.exe" (
    echo Found Miniconda installation at C:\APPLIS\miniconda3
    set "CONDA_PATH=C:\APPLIS\miniconda3\Scripts\conda.exe"
    goto :conda_found
)

REM Check for Anaconda installation
if exist "C:\Users\%USERNAME%\miniconda3\Scripts\conda.exe" (
    echo Found Miniconda installation in user directory
    set "CONDA_PATH=C:\Users\%USERNAME%\miniconda3\Scripts\conda.exe"
    goto :conda_found
)

if exist "C:\Users\%USERNAME%\anaconda3\Scripts\conda.exe" (
    echo Found Anaconda installation in user directory
    set "CONDA_PATH=C:\Users\%USERNAME%\anaconda3\Scripts\conda.exe"
    goto :conda_found
)

if exist "C:\ProgramData\miniconda3\Scripts\conda.exe" (
    echo Found Miniconda installation in ProgramData
    set "CONDA_PATH=C:\ProgramData\miniconda3\Scripts\conda.exe"
    goto :conda_found
)

if exist "C:\ProgramData\anaconda3\Scripts\conda.exe" (
    echo Found Anaconda installation in ProgramData
    set "CONDA_PATH=C:\ProgramData\anaconda3\Scripts\conda.exe"
    goto :conda_found
)

echo Error: Conda installation not found. Please install conda or miniconda.
echo Checked paths:
echo   - PATH environment variable
echo   - C:\APPLIS\miniconda3
echo   - C:\Users\%USERNAME%\miniconda3
echo   - C:\Users\%USERNAME%\anaconda3
echo   - C:\ProgramData\miniconda3
echo   - C:\ProgramData\anaconda3
pause
exit /b 1

:conda_found
echo Using conda from: !CONDA_PATH!

REM Change to the directory of the batch script
cd /d "%~dp0"

REM Initialize conda for batch script
call conda activate base
if %errorlevel% neq 0 (
    echo Error: Failed to initialize conda. Trying alternative approach...
    REM Try to initialize conda for cmd
    for /f "tokens=*" %%i in ('conda info --base') do set CONDA_ROOT=%%i
    call "!CONDA_ROOT!\Scripts\activate.bat"
)

REM Activate the code2llm environment
echo Activating 'code2llm' environment...
call conda activate code2llm
if %errorlevel% neq 0 (
    echo Error: Failed to activate 'code2llm' environment.
    echo Make sure the environment exists. Create it with:
    echo conda create -n code2llm python=3.9
    echo Then install the required packages from requirements.txt
    pause
    exit /b 1
)

REM Run the Python script
echo Running main_desktop.py...
python main_desktop.py

if %errorlevel% neq 0 (
    echo Error: Failed to run the Python script.
    pause
    exit /b 1
)

echo Script finished successfully.
pause