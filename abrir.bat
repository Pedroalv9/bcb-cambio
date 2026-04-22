@echo off
start /B pythonw bcb_server.py
timeout /t 2 /nobreak > nul
start http://localhost:5000
