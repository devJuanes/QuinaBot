import ccxt

def debug_separate():
    try:
        # PURE SPOT INSTANCE
        print("Initializing separate SPOT instance...")
        exchange_spot = ccxt.binance()
        exchange_spot.load_markets()
        
        target = "EUR/USDT"
        
        if target in exchange_spot.markets:
            print(f"✅ {target} FOUND in Spot Markets!")
            candles = exchange_spot.fetch_ohlcv(target, '1m', limit=5)
            print(f"✅ SUCCESS! Fetched {len(candles)} candles from Spot.")
        else:
            print(f"❌ {target} NOT found in Spot markets.")

    except Exception as e:
        print(f"Error: {e}")

debug_separate()
