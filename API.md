# QuinaBot Pro API

API REST para el terminal de trading. Compatible con la web (QuinaUI) y con la **app Flutter** (Android/iOS).

**Base URL:** `http://tu-servidor:8000`  
**Prefijo API:** `/api/v1`  
**Documentación interactiva:** `GET /api/v1/docs`

---

## Autenticación

Por ahora la API es abierta (sin auth). En producción conviene proteger con API Key o JWT para la app móvil.

---

## Endpoints

### Salud (para móvil y monitoreo)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/health` o `/api/v1/health` | Health check. Responde 200 si el servicio está bien. |

**Respuesta:** `{ "success": true, "data": { "status": "healthy", "bot_running": true } }`

---

### Mercado actual

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/v1/market/current` | Precio, señal, métricas, velas, rendimiento del par activo. |

**Respuesta:** Objeto con `symbol`, `signal`, `reason`, `signal_strength`, `price`, `metrics`, `risk`, `candles`, `performance`, `cooldown_until`.

---

### Listado y recomendado

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/v1/markets` | Lista de mercados disponibles (futuros y spot USDT). |
| GET | `/api/v1/markets/recommended` | Mercado recomendado para operar (mayor liquidez). |

**Ejemplo recommended:** `{ "success": true, "data": { "recommended": "BTC/USDT", "reason": "Mayor liquidez 24h", "alternatives": ["ETH/USDT", ...] } }`

---

### Cambiar par

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/v1/market/select` | Cambiar el par de trading activo. |

**Body:** `{ "symbol": "BTC/USDT" }`

---

### Configuración del algoritmo

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/v1/config` | Obtener parámetros actuales (RSI, SL/TP, etc.). |
| POST | `/api/v1/config` | Actualizar parámetros. |

**Body (POST):**  
`{ "rsiBuyThreshold": 32, "rsiSellThreshold": 68, "slMultiplier": 1.6, "tpMultiplier": 2.8, "minSignalStrength": 65, "cooldownSeconds": 45 }`

---

### Historial

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/v1/history` | Rendimiento y últimas operaciones (paper trading). |

**Respuesta:** `performance` (total_pnl, total_trades, win_rate), `active_trade`, `recent_trades`.

---

### Noticias / feed

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/v1/news` | Feed de noticias/sentimiento. |

---

## WebSocket (tiempo real)

**URL:** `ws://tu-servidor:8000/ws`

El servidor envía cada segundo un JSON con el mismo formato que `GET /api/v1/market/current`. Úsalo en Flutter con `web_socket_channel` o similar para precio, señal y gráfico en vivo.

---

## Respuestas estándar

- **Éxito:** `{ "success": true, "message": "OK", "data": { ... } }`
- **Error:** `{ "success": false, "error": "mensaje", "code": "ERROR" }`  
  En errores de validación FastAPI devuelve `422` con `detail` en array.

---

## Uso desde Flutter

1. Base URL configurable (ej. `https://api.quinabot.com` o IP:8000).
2. Health: `GET /api/v1/health` al abrir la app.
3. Mercado actual: `GET /api/v1/market/current` o WebSocket `/ws`.
4. Selector de pares: `GET /api/v1/markets` y `GET /api/v1/markets/recommended`.
5. Cambiar par: `POST /api/v1/market/select` con `{"symbol": "ETH/USDT"}`.
6. Historial: `GET /api/v1/history`.
