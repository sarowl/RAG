@echo off
setlocal

set "VENV_DIR=%~dp0.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    if exist "%VENV_DIR%\" (
        echo Cannot use "%VENV_DIR%" as a Windows virtual environment. 1>&2
        exit /b 1
    )
    py -3.11 -c "import sys, struct; sys.exit(struct.calcsize('P') != 8)" >nul 2>&1
    if errorlevel 1 (
        python -c "import sys, struct; sys.exit(sys.version_info[:2] != (3, 11) or struct.calcsize('P') != 8)" >nul 2>&1
        if errorlevel 1 (
            echo Install Python 3.11 x64 and make py or python available on PATH. 1>&2
            exit /b 1
        )
        python -m venv "%VENV_DIR%" || exit /b 1
    ) else (
        py -3.11 -m venv "%VENV_DIR%" || exit /b 1
    )
)

"%VENV_PYTHON%" -m pip install -r "%~dp0requirements_windows.txt" || exit /b 1
"%VENV_PYTHON%" -m pip check || exit /b 1
echo Windows backend environment ready at "%VENV_DIR%".

pushd "%~dp0" || exit /b 1
echo Starting the RAG API on port 8000 and the Admin API on port 8003. Press Ctrl+C to stop.
"%VENV_PYTHON%" api.py --host 0.0.0.0 --port 8000 --admin-port 8003
set "BACKEND_EXIT=%ERRORLEVEL%"
popd
exit /b %BACKEND_EXIT%
