@echo off
rem Abre a Central AC Cobranca neste computador (http://127.0.0.1:8765). Feche esta janela para encerrar.
cd /d "%~dp0"
title Central AC Cobranca
".venv\Scripts\python.exe" -m central_ac
pause
