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

**El bot ahora es resiliente por defecto** (sin configurar nada):

1. **Fallback de endpoints**: Prueba api.binance.com → api1 → api2 → api3
2. **Retry con backoff**: 5s, 10s, 30s entre reintentos
3. **CoinGecko fallback**: Si Binance falla, usa CoinGecko para precio (modo degradado)

Verás `[WARN] Binance unavailable. Using CoinGecko fallback.` si activa el fallback.

**Alternativas**:

- **USE_BYBIT=1** en .env → Usa Bybit (menos restricciones)
- **HTTPS_PROXY** en .env → Proxy para Binance
