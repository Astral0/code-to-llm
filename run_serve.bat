@echo off
REM Ce script active un environnement Conda (s'il n'est pas deja actif) et lance un script Python.

echo --- Verification de l'environnement Conda ---

REM Verifie si l'environnement 'code2llm' est deja actif.
if "%CONDA_DEFAULT_ENV%"=="code2llm" (
    echo L'environnement Conda 'code2llm' est deja actif.
) else (
    echo Activation de l'environnement Conda 'code2llm'...
    call conda activate code2llm

    REM Verifie si l'activation a reussi
    if %errorlevel% neq 0 (
        echo.
        echo ERREUR: Impossible d'activer l'environnement Conda 'code2llm'.
        echo Verifiez que l'environnement existe et que Conda est dans votre PATH.
        pause
        exit /b %errorlevel%
    )
    echo Environnement active.
)

echo.
echo --- Changement de repertoire vers D:\DONNEES\DEV\gpt\code-to-llm ---
cd /D D:\DONNEES\DEV\gpt\code-to-llm

echo --- Lancement du serveur Python ---
python llm_context_builder.py serve --port 8080

echo.
echo --- Le script serveur est termine. Appuyez sur une touche pour fermer cette fenetre. ---
pause
