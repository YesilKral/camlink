@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 camlink_pc.py
) else (
    python camlink_pc.py
)
pause
