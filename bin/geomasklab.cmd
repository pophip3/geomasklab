@echo off
setlocal
cd /d "%~dp0.."
if errorlevel 1 exit /b 1
if exist ".venv\Scripts\python.exe" goto run_venv
python -c "import sys;sys.exit(sys.version_info < (3,10))" >nul 2>nul
if not errorlevel 1 goto run_python
py -3 -c "import sys;sys.exit(sys.version_info < (3,10))" >nul 2>nul
if not errorlevel 1 goto run_py
echo Python 3.10 or newer is required. See README.md for installation steps.
exit /b 1
:run_venv
".venv\Scripts\python.exe" quickstart.py %*
exit /b %errorlevel%
:run_python
python quickstart.py %*
exit /b %errorlevel%
:run_py
py -3 quickstart.py %*
exit /b %errorlevel%
