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

## Error 451 (Binance bloqueado por región)

Si tu VPS está en una región donde Binance restringe el acceso, verás:

```
Service unavailable from a restricted location according to 'b. Eligibility'
```

**Solución: usar un proxy** en una región permitida (EU, Asia, etc.):

```bash
# Antes de ejecutar, exporta la variable (o añádela a .env y haz source)
export HTTPS_PROXY=http://tu-proxy:puerto
# Con autenticación: export HTTPS_PROXY=http://user:pass@proxy:puerto

python main.py
```

O en `.env` (si usas python-dotenv, hay que cargarlo antes del bot):

```
HTTPS_PROXY=http://proxy.ejemplo.com:3128
```

Proveedores de proxy que suelen funcionar: Bright Data, Oxylabs, SmartProxy, o un VPS barato en EU como proxy.
