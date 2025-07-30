@echo off

REM Test des emplacements un par un
if exist "C:\UTILS\miniconda3\Scripts\conda.exe" (
    call "C:\UTILS\miniconda3\Scripts\activate.bat" "C:\UTILS\miniconda3" && conda activate code2llm
    goto :eof
)

if exist "C:\APPLIS\miniconda3\Scripts\conda.exe" (
    call "C:\APPLIS\miniconda3\Scripts\activate.bat" "C:\APPLIS\miniconda3" && conda activate code2llm
    goto :eof
)

if exist "%USERPROFILE%\anaconda3\Scripts\conda.exe" (
    call "%USERPROFILE%\anaconda3\Scripts\activate.bat" "%USERPROFILE%\anaconda3" && conda activate code2llm
    goto :eof
)

if exist "%USERPROFILE%\miniconda3\Scripts\conda.exe" (
    call "%USERPROFILE%\miniconda3\Scripts\activate.bat" "%USERPROFILE%\miniconda3" && conda activate code2llm
    goto :eof
)

if exist "C:\ProgramData\Anaconda3\Scripts\conda.exe" (
    call "C:\ProgramData\Anaconda3\Scripts\activate.bat" "C:\ProgramData\Anaconda3" && conda activate code2llm
    goto :eof
)

echo Conda non trouve - environnement par defaut
