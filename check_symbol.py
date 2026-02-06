import ccxt
import time

def check_symbol(symbol):
    try:
        # Check Futures
        print(f"Checking {symbol} on Binance Futures...")
        exchange = ccxt.binance({'options': {'defaultType': 'future'}})
        exchange.load_markets()
        if symbol in exchange.markets:
            print(f"✅ {symbol} FOUND in Futures!")
        else:
            print(f"❌ {symbol} NOT found in Futures.")
            
        # Check Spot
        print(f"Checking {symbol} on Binance Spot...")
        exchange_spot = ccxt.binance()
        exchange_spot.load_markets()
        if symbol in exchange_spot.markets:
            print(f"✅ {symbol} FOUND in Spot!")
        else:
            print(f"❌ {symbol} NOT found in Spot.")

    except Exception as e:
        print(f"Error: {e}")

check_symbol('EUR/USDT')
check_symbol('EUR/USD')
