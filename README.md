# QuinaBot Pro

Terminal de trading con señales en tiempo real y automatización de broker (IQ Option).

## Instalación

```powershell
# 1. Dependencias
pip install -r requirements.txt

# 2. Chromium (Playwright) - usa python -m, no "playwright" directo
python -m playwright install chromium

# 3. Configura .env (copia .env.example)
copy .env.example .env
# Edita .env con IQ_OPTION_EMAIL e IQ_OPTION_PASSWORD
```

O ejecuta el script de setup:

```powershell
.\setup.bat
```

## Uso

```powershell
# Iniciar API y bot
python main.py

# Login IQ Option (navegador se cierra al terminar)
python automation.py

# Login IQ Option (navegador abierto para operar)
python automation.py --keep-open
```

La UI web (QuinaUI) tiene un botón **"Abrir IQ Option"** que hace el login y deja el navegador abierto.
