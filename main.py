from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio
from bot_logic import QuinaBot

app = FastAPI(title="QuinaBot API")

# Enable CORS for local UI development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for local dev convenience
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bot = QuinaBot()

@app.get("/")
def read_root():
    return {"status": "running", "bot_name": "QuinaBot"}

@app.get("/market-data")
async def get_market_data():
    """Returns the latest candles and indicators"""
    return bot.get_latest_data()

@app.post("/set-symbol")
async def set_symbol(symbol: str):
    """Updates the trading pair"""
    await bot.set_symbol(symbol)
    return {"status": "ok", "symbol": symbol}

@app.on_event("startup")
async def startup_event():
    # Start the bot loop in background
    asyncio.create_task(bot.start_loop())

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
