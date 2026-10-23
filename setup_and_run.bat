@echo off
REM One-click setup + run (Windows). Double-click or run from CMD inside the project folder.
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate
pip install -r requirements.txt
echo.
echo Starting CineMatch on http://127.0.0.1:5000  (demo login: demo / demo123)
python app.py
pause