import ccxt
import time

def debug_markets():
    try:
        # Configuration EXACTLY like bot_logic.py
        exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'
            }
        })
        print("Loading Futures markets...")
        exchange.load_markets()
        
        target = "EUR/USDT"
        
        if target in exchange.markets:
            print(f"✅ {target} is present in exchange.markets keys.")
            print(f"Details: {exchange.markets[target]['id']} / {exchange.markets[target]['type']}")
            
            # Try fetching
            print(f"Attempting fetch_ohlcv for {target}...")
            try:
                candles = exchange.fetch_ohlcv(target, '1m', limit=5)
                print(f"✅ SUCCESS! Fetched {len(candles)} candles.")
            except Exception as inner_e:
                print(f"❌ FETCH FAILED: {inner_e}")
        else:
            print(f"❌ {target} is NOT in exchange.markets.")
            # Search for alternatives
            print("Searching for 'EUR' alternatives...")
            for s in exchange.markets:
                if 'EUR' in s:
                    print(f"Found: {s} (ID: {exchange.markets[s]['id']})")
                    
    except Exception as e:
        print(f"Create Exchange Error: {e}")

debug_markets()
