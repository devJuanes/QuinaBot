import ccxt
import time

def test_exchange(name, exchange_class):
    print(f"Testing {name}...")
    try:
        exchange = exchange_class()
        exchange.load_markets()
        print(f"✅ {name} Connected! Loaded {len(exchange.markets)} markets.")
        return True
    except Exception as e:
        print(f"❌ {name} Failed: {e}")
        return False

print("Checkng Internet Connection to Crypto Exchanges...")
results = {}
results['binance'] = test_exchange('Binance', ccxt.binance)
results['kraken'] = test_exchange('Kraken', ccxt.kraken)
results['coinbase'] = test_exchange('Coinbase', ccxt.coinbase)
results['kucoin'] = test_exchange('KuCoin', ccxt.kucoin)
results['bitstamp'] = test_exchange('Bitstamp', ccxt.bitstamp)

print("\nSummary:")
for name, success in results.items():
    print(f"{name}: {'Working' if success else 'Blocked/Error'}")
