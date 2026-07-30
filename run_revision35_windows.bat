@echo off
call run_windows.bat revision35.py
if errorlevel 1 python revision35.py %*
