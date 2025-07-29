@echo off
setlocal enabledelayedexpansion

REM Configuration
set CONDA_ENV=code2llm
set SCRIPT_NAME=llm_context_builder.py
set SERVER_PORT=8080

echo ===============================================
echo   DEMARRAGE SERVEUR WEB - Code-to-LLM
echo ===============================================

REM Etape 1: Verification du repertoire et des fichiers requis
echo [1/6] Verification du repertoire et des fichiers...
if not exist "%SCRIPT_NAME%" (
    echo ERREUR: Fichier %SCRIPT_NAME% non trouve
    echo Assurez-vous d'etre dans le bon repertoire
    pause
    exit /b 1
)

if not exist "requirements.txt" (
    echo ERREUR: Fichier requirements.txt non trouve
    pause
    exit /b 1
)

if not exist "config.ini" (
    echo AVERTISSEMENT: Fichier config.ini non trouve
    echo Copiez config.ini.template vers config.ini et configurez-le si necessaire
)

echo Fichiers requis OK

REM Etape 2: Recherche de conda
echo [2/6] Recherche de conda...

REM D'abord verifier si conda est dans le PATH
where conda >nul 2>&1
if %errorlevel% equ 0 (
    echo Conda trouve dans PATH
    set "CONDA_PATH=conda"
    goto found_conda
)

REM Recherche dans les emplacements courants
set CONDA_PATH=
for %%p in (
    "%USERPROFILE%\anaconda3"
    "%USERPROFILE%\miniconda3"
    "C:\ProgramData\Anaconda3"
    "C:\ProgramData\Miniconda3"
    "C:\Anaconda3"
    "C:\Miniconda3"
    "C:\APPLIS\miniconda3"
    "C:\UTILS\miniconda3"
    "D:\UTILS\miniconda3"
) do (
    if exist "%%~p\Scripts\conda.exe" (
        set CONDA_PATH=%%~p
        goto found_conda
    )
)

echo ERREUR: Conda non trouve
echo Chemins verifies:
echo   - Variable PATH
echo   - %USERPROFILE%\anaconda3
echo   - %USERPROFILE%\miniconda3  
echo   - C:\ProgramData\Anaconda3
echo   - C:\ProgramData\Miniconda3
echo   - C:\Anaconda3
echo   - C:\Miniconda3
echo   - C:\APPLIS\miniconda3
echo   - C:\UTILS\miniconda3
echo   - D:\UTILS\miniconda3
echo.
echo Veuillez installer Conda ou Miniconda depuis:
echo https://docs.conda.io/en/latest/miniconda.html
pause
exit /b 1

:found_conda
if "!CONDA_PATH!"=="conda" (
    echo Conda trouve: PATH
) else (
    echo Conda trouve: !CONDA_PATH!
)

REM Etape 3: Activation de conda base
echo [3/6] Activation de conda...
if "!CONDA_PATH!"=="conda" (
    call conda activate base
) else (
    call "!CONDA_PATH!\Scripts\activate.bat" "!CONDA_PATH!"
)

if %errorlevel% neq 0 (
    echo ERREUR: Echec de l'activation de conda base
    echo Tentative d'approche alternative...
    
    REM Approche alternative pour l'initialisation
    if "!CONDA_PATH!" neq "conda" (
        call "!CONDA_PATH!\Scripts\activate.bat"
    )
    
    if %errorlevel% neq 0 (
        echo ERREUR: Impossible d'initialiser conda
        pause
        exit /b 1
    )
)

REM Etape 4: Verification et activation de l'environnement
echo [4/6] Verification de l'environnement '%CONDA_ENV%'...

REM Verifier si l'environnement existe
conda env list | findstr /C:"%CONDA_ENV%" >nul 2>&1
if %errorlevel% neq 0 (
    echo ERREUR: Environnement '%CONDA_ENV%' non trouve
    echo.
    echo Pour creer l'environnement, executez:
    echo   conda create -n %CONDA_ENV% python=3.9
    echo   conda activate %CONDA_ENV%
    echo   pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

REM Verifier si l'environnement est deja actif
if "%CONDA_DEFAULT_ENV%"=="%CONDA_ENV%" (
    echo Environnement '%CONDA_ENV%' deja actif
) else (
    echo Activation de l'environnement '%CONDA_ENV%'...
    call conda activate %CONDA_ENV%
    if %errorlevel% neq 0 (
        echo ERREUR: Echec de l'activation de l'environnement '%CONDA_ENV%'
        pause
        exit /b 1
    )
)

REM Etape 5: Verification de Python et des dependances
echo [5/6] Verification de Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERREUR: Python non trouve dans l'environnement
    pause
    exit /b 1
)

echo Version Python:
python --version

REM Etape 6: Lancement du serveur web
echo [6/6] Lancement du serveur web...
echo Demarrage de %SCRIPT_NAME% sur le port %SERVER_PORT%...
echo.
echo Le serveur sera accessible a l'adresse: http://localhost:%SERVER_PORT%
echo Pour arreter le serveur, appuyez sur Ctrl+C
echo.

python %SCRIPT_NAME% serve --port %SERVER_PORT%

if %errorlevel% neq 0 (
    echo.
    echo ERREUR: Echec du lancement du serveur
    echo Code d'erreur: %errorlevel%
    pause
    exit /b 1
)
