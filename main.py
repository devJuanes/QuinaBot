"""
QuinaBot Pro API — REST API escalable para trading.
Lista para consumo por Web (QuinaUI) y aplicación móvil Flutter.
Versión: 3.0 | Base: /api/v1
"""
from dotenv import load_dotenv
load_dotenv()  # Carga .env antes de crear el bot (proxy, etc.)

import sys
import asyncio
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
import uvicorn
import json
import os
import time
from contextlib import asynccontextmanager

from bot_logic import QuinaBot

# --- App & Bot ---
bot = QuinaBot()
API_VERSION = "3.0.0"
BASE_PATH = "/api/v1"


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass


manager = ConnectionManager()


# --- Request/Response schemas (para Flutter y documentación) ---
class MarketSelectBody(BaseModel):
    symbol: str = Field(..., description="Par de trading, ej: BTC/USDT")


class ConfigUpdateBody(BaseModel):
    rsiBuyThreshold: Optional[int] = Field(None, ge=1, le=50)
    rsiSellThreshold: Optional[int] = Field(None, ge=50, le=99)
    slMultiplier: Optional[float] = Field(None, ge=0.5, le=5.0)
    tpMultiplier: Optional[float] = Field(None, ge=1.0, le=10.0)
    minSignalStrength: Optional[int] = Field(None, ge=50, le=95)
    cooldownSeconds: Optional[int] = Field(None, ge=0, le=300)


# --- Respuestas estándar ---
def ok(data=None, message: str = "OK"):
    return {"success": True, "message": message, "data": data}


def fail(message: str, code: str = "ERROR"):
    return {"success": False, "error": message, "code": code}


# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    bot_task = asyncio.create_task(bot.start_loop())

    async def broadcast_loop():
        while bot.is_running:
            try:
                data = bot.get_latest_data()
                await manager.broadcast(json.dumps(data))
            except Exception:
                pass
            await asyncio.sleep(1)

    broadcast_task = asyncio.create_task(broadcast_loop())
    yield
    bot.is_running = False
    for t in (bot_task, broadcast_task):
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="QuinaBot Pro API",
    description="API REST para señales de trading, mercados y configuración. Compatible con Web y Flutter.",
    version=API_VERSION,
    lifespan=lifespan,
    docs_url=f"{BASE_PATH}/docs",
    redoc_url=f"{BASE_PATH}/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Raíz y salud (para móvil y load balancers) ---
@app.get("/")
def root():
    return ok({
        "service": "QuinaBot Pro API",
        "version": API_VERSION,
        "docs": BASE_PATH + "/docs",
        "api_base": BASE_PATH,
    })


@app.get("/health")
@app.get(f"{BASE_PATH}/health")
def health():
    """Health check: ideal para Flutter y monitoreo."""
    return JSONResponse(status_code=200, content=ok({
        "status": "healthy",
        "timestamp": time.time(),
        "bot_running": bot.is_running,
    }))


# ========== API v1 ==========

@app.get(f"{BASE_PATH}/")
def api_info():
    return ok({
        "version": API_VERSION,
        "endpoints": {
            "health": f"{BASE_PATH}/health",
            "market_current": f"{BASE_PATH}/market/current",
            "markets": f"{BASE_PATH}/markets",
            "markets_recommended": f"{BASE_PATH}/markets/recommended",
            "market_select": f"{BASE_PATH}/market/select (POST)",
            "config": f"{BASE_PATH}/config (GET/POST)",
            "history": f"{BASE_PATH}/history",
            "news": f"{BASE_PATH}/news",
        },
        "websocket": "/ws",
    })


@app.get(f"{BASE_PATH}/market/current")
def market_current():
    """Datos actuales del mercado: precio, señal, métricas, velas, rendimiento."""
    data = bot.get_latest_data()
    return ok(data)


@app.get(f"{BASE_PATH}/markets")
async def markets():
    """Lista de mercados disponibles (futuros y spot USDT). Para selector en UI/Flutter."""
    try:
        result = await bot.get_available_markets()
        return ok(result)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get(f"{BASE_PATH}/markets/recommended")
async def markets_recommended():
    """Mercado recomendado para operar: mayor liquidez y estabilidad (favorito del sistema)."""
    try:
        result = await bot.get_recommended_market()
        return ok(result)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post(f"{BASE_PATH}/market/select")
async def market_select(body: MarketSelectBody):
    """Cambiar el par de trading activo."""
    try:
        await bot.set_symbol(body.symbol.strip())
        return ok({"symbol": bot.symbol}, "Mercado actualizado")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get(f"{BASE_PATH}/config")
def config_get():
    """Obtener configuración actual del algoritmo."""
    return ok(bot.config)


@app.post(f"{BASE_PATH}/config")
async def config_update(body: ConfigUpdateBody):
    """Actualizar parámetros del algoritmo (RSI, SL/TP, etc.)."""
    payload = body.model_dump(exclude_none=True)
    if not payload:
        return JSONResponse(status_code=400, content=fail("Ningún campo para actualizar"))
    bot.update_config(payload)
    return ok(bot.config, "Configuración aplicada")


@app.get(f"{BASE_PATH}/history")
def history():
    """Historial de operaciones (paper trading) y estadísticas."""
    stats = bot.paper_trading.get_stats()
    return ok({
        "performance": {
            "total_pnl": stats["total_pnl"],
            "total_trades": stats["total_trades"],
            "win_rate": stats["win_rate"],
        },
        "active_trade": stats["active_trade"],
        "recent_trades": stats["recent_trades"],
    })


@app.get(f"{BASE_PATH}/news")
def news():
    """Feed de noticias/sentimiento (datos reales cuando exista integración)."""
    items = [
        {"title": "Mercado en tiempo real", "sentiment": "neutral", "source": "QuinaBot Engine"},
        {"title": "Volatilidad monitorizada por ATR", "sentiment": "info", "source": "ATR Monitor"},
    ]
    return ok(items)


# --- Broker (IQ Option) ---
BROKER_STATUS_FILE = os.path.join(os.path.dirname(__file__), "broker_status.json")
BROKER_DATA_FILE = os.path.join(os.path.dirname(__file__), "broker_data.json")


def _read_broker_data():
    """Lee broker_data.json o broker_status.json."""
    for path in (BROKER_DATA_FILE, BROKER_STATUS_FILE):
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
    return {"status": "idle", "error": None, "logged_in": False}


def _write_broker_cmd(cmd: dict):
    """Escribe comando para el broker service."""
    try:
        with open(os.path.join(os.path.dirname(__file__), "broker_cmd.json"), "w", encoding="utf-8") as f:
            json.dump(cmd, f)
    except Exception:
        pass


def _run_broker_subprocess():
    """Ejecuta el broker en proceso separado (login + servicio con saldo/cuenta)."""
    import subprocess
    script = os.path.join(os.path.dirname(__file__), "broker_service.py")
    subprocess.Popen(
        [sys.executable, script],
        cwd=os.path.dirname(__file__),
        env={**os.environ},
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )
    try:
        with open(BROKER_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump({"status": "pending", "error": None, "logged_in": False}, f)
    except Exception:
        pass


@app.post(f"{BASE_PATH}/broker/login")
async def broker_login():
    """Conecta a IQ Option. El boton muestra verde=ok, rojo=error."""
    _run_broker_subprocess()
    return ok({"status": "pending", "message": "Conectando..."})


@app.get(f"{BASE_PATH}/broker/status")
def broker_status():
    """Estado: status, balance, account_type, market, logged_in, error."""
    return ok(_read_broker_data())


@app.post(f"{BASE_PATH}/broker/switch-account")
async def broker_switch_account(to_demo: bool = None):
    """Cambia entre cuenta Demo y Real. to_demo=true va a demo, false a real."""
    _write_broker_cmd({"command": "switch_account", "to_demo": to_demo})
    return ok({"message": "Comando enviado"})


class SelectMarketBody(BaseModel):
    market: str = Field(..., description="Mercado a seleccionar, ej. BTC/USD OTC")


@app.post(f"{BASE_PATH}/broker/select-market")
async def broker_select_market(body: SelectMarketBody):
    """Selecciona el mercado en IQ Option (ej. BTC/USD OTC)."""
    _write_broker_cmd({"command": "select_market", "market": body.market})
    return ok({"message": "Comando enviado"})


# --- WebSocket (stream en tiempo real) ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# --- Compatibilidad con rutas antiguas (respuesta sin wrapper) ---
@app.get("/market-data")
def market_data_legacy():
    return bot.get_latest_data()


@app.post("/set-symbol")
async def set_symbol_legacy(symbol: str):
    await bot.set_symbol(symbol)
    return {"status": "ok", "symbol": bot.symbol}


@app.post("/update-config")
async def update_config_legacy(request: Request):
    config = await request.json()
    bot.update_config(config)
    return {"status": "ok", "config": bot.config}


# --- Run ---
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
