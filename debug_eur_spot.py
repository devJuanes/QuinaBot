import ccxt
import time

def debug_spot_override():
    try:
        # Same Futures config
        exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'
            }
        })
        exchange.load_markets()
        
        target = "EUR/USDT"
        print(f"Attempting fetch_ohlcv for {target} with params={{'type': 'spot'}}...")
        
        try:
            # TRY OVERRIDE
            candles = exchange.fetch_ohlcv(target, '1m', limit=5, params={'type': 'spot'})
            print(f"✅ SUCCESS with override! Fetched {len(candles)} candles.")
            print(candles[0])
        except Exception as inner_e:
            print(f"❌ FETCH FAILED even with override: {inner_e}")

    except Exception as e:
        print(f"Error: {e}")

debug_spot_override()
