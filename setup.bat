@echo off
echo Instalando dependencias...
pip install -r requirements.txt
echo.
echo Instalando Chromium para Playwright...
python -m playwright install chromium
echo.
echo Listo. Ejecuta: python main.py
