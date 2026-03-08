import ccxt
import pandas as pd
import pandas_ta as ta
import asyncio
import time
import math
import os
from paper_trading import PaperTrading
from datetime import datetime
import json


def _get_proxy_config():
    """Lee proxy desde HTTP_PROXY o HTTPS_PROXY. Necesario si Binance bloquea tu región (451)."""
    proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    if proxy:
        return {'http': proxy, 'https': proxy}
    return None


def _use_bybit():
    """Bybit tiene menos restricciones geográficas que Binance. Usar si Binance da 451."""
    return os.environ.get('USE_BYBIT', '').lower() in ('1', 'true', 'yes')


class QuinaBot:
    def __init__(self, symbol='BTC/USDT', timeframe='1m'):
        self.symbol = symbol
        self.timeframe = timeframe
        self.trend_timeframe = '15m'  # MTF Trend Confirmation

        # Professional Configuration (Optimized for precision & real-money)
        self.config = {
            'rsi_buy_threshold': 32,
            'rsi_sell_threshold': 68,
            'ema_fast': 20,
            'ema_slow': 50,
            'ema_trend': 200,
            'sl_multiplier': 1.6,
            'tp_multiplier': 2.8,
            'min_signal_strength': 65,   # Solo operar si score >= 65
            'signal_persistence': 2,     # Misma señal N velas seguidas
            'cooldown_seconds': 45,       # No reabrir misma dirección tras cerrar
        }

        # Exchanges: Bybit (menos restricciones) o Binance (proxy si 451)
        proxy = _get_proxy_config()
        common = {'enableRateLimit': True, 'trust_env': True}
        if proxy:
            common['proxies'] = proxy
            print(f"🌐 Usando proxy: {str(proxy.get('https', proxy.get('http', '')))[:60]}...")

        if _use_bybit():
            print("📊 Usando Bybit (menos restricciones geográficas)")
            self.exchange = ccxt.bybit({
                **common,
                'options': {'defaultType': 'linear'}
            })
            self.exchange_spot = ccxt.bybit(common)
        else:
            self.exchange = ccxt.binance({
                **common,
                'options': {'defaultType': 'future'}
            })
            self.exchange_spot = ccxt.binance(common)

        self.data = pd.DataFrame()
        self.trend_data = pd.DataFrame()
        self.latest_signal = "ESPERANDO"
        self.signal_reason = "Sincronizando flujo de datos..."
        self.signal_strength = 0
        self.is_running = False
        self.use_spot = False

        # Precision: persistencia de señal y cooldown
        self._signal_history = []           # Últimas señales (para persistencia)
        self._cooldown_until = 0.0
        self._cooldown_direction = ""

        # Modules
        self.paper_trading = PaperTrading()
        self.subscribers = set() 

    def update_config(self, new_config):
        """Update strategy configuration dynamically"""
        mapping = {
            'rsiBuyThreshold': 'rsi_buy_threshold',
            'rsiSellThreshold': 'rsi_sell_threshold',
            'slMultiplier': 'sl_multiplier',
            'tpMultiplier': 'tp_multiplier',
            'minSignalStrength': 'min_signal_strength',
            'cooldownSeconds': 'cooldown_seconds',
        }
        for ui_key, bot_key in mapping.items():
            if ui_key in new_config:
                self.config[bot_key] = new_config[ui_key]
        print(f"✅ Strategy Updated: {self.config}")

    def _get_atr(self, row):
        """ATR: pandas_ta usa ATRr_14 por defecto (RMA); fallback a ATR_14."""
        return row.get('ATRr_14', row.get('ATR_14', 0)) or 0

    def _in_cooldown(self, signal):
        """True si no debemos abrir esta dirección por cooldown post-cierre."""
        if time.time() < self._cooldown_until and self._cooldown_direction:
            if ('COMPRA' in signal and 'COMPRA' in self._cooldown_direction) or \
               ('VENTA' in signal and 'VENTA' in self._cooldown_direction):
                return True
        return False

    async def set_symbol(self, new_symbol):
        print(f"Professional Market Switch: {new_symbol}")
        self.symbol = new_symbol
        self.data = pd.DataFrame()
        self.trend_data = pd.DataFrame()
        self.latest_signal = "ESPERANDO"
        self.signal_reason = f"Sincronizando {new_symbol} (MTF Mode)..."
        
        try:
            if not self.exchange.markets:
                await asyncio.to_thread(self.exchange.load_markets)
            
            is_future = new_symbol in self.exchange.markets and self.exchange.markets[new_symbol].get('type') in ['swap', 'future', 'linear']
            
            if is_future:
                self.use_spot = False
                self.signal_reason = "Market: FUTURES (MTF Optimized) 🚀"
            else:
                self.use_spot = True
                self.signal_reason = "Market: SPOT (MTF Optimized) 🌍"
        except Exception as e:
            print(f"Market Sync Error: {e}")

    async def get_available_markets(self):
        """Lista de mercados disponibles (Futures y Spot USDT) para selector en API/Flutter."""
        try:
            await asyncio.to_thread(self.exchange.load_markets)
            await asyncio.to_thread(self.exchange_spot.load_markets)
            futures = []
            spot = []
            for sid, m in self.exchange.markets.items():
                if m.get('quote') == 'USDT' and m.get('type') in ('future', 'swap', 'linear') and m.get('active', True):
                    futures.append({"symbol": sid, "type": "future", "base": m.get('base'), "quote": "USDT"})
            for sid, m in self.exchange_spot.markets.items():
                if m.get('quote') == 'USDT' and m.get('type') == 'spot' and m.get('active', True):
                    spot.append({"symbol": sid, "type": "spot", "base": m.get('base'), "quote": "USDT"})
            # Eliminar duplicados por symbol (futures suelen ser los que usamos)
            seen = set()
            combined = []
            for x in futures[:50]:
                if x["symbol"] not in seen:
                    seen.add(x["symbol"])
                    combined.append({**x, "label": f"{x['symbol']} (F)"})
            for x in spot[:30]:
                if x["symbol"] not in seen:
                    seen.add(x["symbol"])
                    combined.append({**x, "label": f"{x['symbol']} (S)"})
            return {"markets": combined, "futures": futures[:30], "spot": spot[:20]}
        except Exception as e:
            print(f"get_available_markets error: {e}")
            return {"markets": [], "futures": [], "spot": []}

    async def get_recommended_market(self):
        """Mercado recomendado para operar: mayor volumen 24h y liquidez (el favorito del sistema)."""
        try:
            await asyncio.to_thread(self.exchange.load_markets)
            tickers = await asyncio.to_thread(self.exchange.fetch_tickers)
            usdt_pairs = [
                (sid, t) for sid, t in tickers.items()
                if sid.endswith("/USDT") and sid in self.exchange.markets
                and self.exchange.markets[sid].get("type") in ("future", "swap", "linear")
            ]
            # Ordenar por volumen quote (USDT) descendente
            with_vol = []
            for sid, t in usdt_pairs:
                quote_vol = float(t.get("quoteVolume") or 0)
                if quote_vol <= 0:
                    continue
                with_vol.append({
                    "symbol": sid,
                    "volume_24h": quote_vol,
                    "change_24h": float(t.get("percentage", 0) or 0),
                })
            with_vol.sort(key=lambda x: x["volume_24h"], reverse=True)
            # Los más líquidos y estables: top 5 por volumen, preferir no extremadamente volátiles
            top = with_vol[:10]
            recommended = top[0] if top else {"symbol": "BTC/USDT", "volume_24h": 0, "change_24h": 0}
            return {
                "recommended": recommended["symbol"],
                "reason": "Mayor liquidez 24h (óptimo para operar)",
                "alternatives": [x["symbol"] for x in top[1:6]],
            }
        except Exception as e:
            print(f"get_recommended_market error: {e}")
            return {"recommended": "BTC/USDT", "reason": "Default (BTC más líquido)", "alternatives": ["ETH/USDT", "SOL/USDT"]}

    async def fetch_candles(self, timeframe, limit=300):
        try:
            active_exchange = self.exchange_spot if self.use_spot else self.exchange
            ohlcv = await asyncio.to_thread(
                active_exchange.fetch_ohlcv, 
                self.symbol, 
                timeframe, 
                limit=limit
            )
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f"Fetch Error ({timeframe}): {e}")
            return pd.DataFrame()

    def analyze_data(self, df):
        min_bars = max(210, self.config['ema_trend'] + 20)
        if df.empty or len(df) < min_bars:
            return df
        df = df.copy()
        df.ta.ema(length=self.config['ema_fast'], append=True)
        df.ta.ema(length=self.config['ema_slow'], append=True)
        df.ta.ema(length=self.config['ema_trend'], append=True)
        df.ta.rsi(length=14, append=True)
        df.ta.macd(append=True)
        df.ta.bbands(length=20, std=2, append=True)
        df.ta.atr(length=14, append=True)
        # Volumen: media móvil 20 para confirmación
        if 'volume' in df.columns and df['volume'].dtype in (float, 'int64', 'int32'):
            df['volume_sma20'] = df['volume'].rolling(20).mean()
        return df

    def _compute_signal_strength(self, current, prev, trend_last, price, atr, major_trend_up, direction):
        """Calcula score 0-100 de confluencia para COMPRA (direction=1) o VENTA (direction=-1)."""
        score = 0.0
        rsi = current.get('RSI_14')
        if rsi is None or (isinstance(rsi, float) and math.isnan(rsi)):
            return 0

        macd = current.get('MACD_12_26_9')
        macd_s = current.get('MACDs_12_26_9')
        bbl = current.get('BBL_20_2.0_2.0')
        bbu = current.get('BBU_20_2.0_2.0')
        ema_fast = current.get(f"EMA_{self.config['ema_fast']}")
        ema_slow = current.get(f"EMA_{self.config['ema_slow']}")

        # MTF alineado (hasta 25 pts)
        if (direction == 1 and major_trend_up) or (direction == -1 and not major_trend_up):
            score += 25

        # RSI en zona favorable (hasta 20 pts)
        if direction == 1 and rsi < self.config['rsi_buy_threshold']:
            score += 20
        elif direction == 1 and rsi < 40:
            score += 10
        if direction == -1 and rsi > self.config['rsi_sell_threshold']:
            score += 20
        elif direction == -1 and rsi > 60:
            score += 10

        # MACD a favor (hasta 20 pts)
        if macd is not None and macd_s is not None and not (math.isnan(macd) or math.isnan(macd_s)):
            if (direction == 1 and macd > macd_s) or (direction == -1 and macd < macd_s):
                score += 20

        # Bandas: precio en banda baja (compra) o alta (venta) (hasta 15 pts)
        if bbl is not None and bbu is not None:
            if direction == 1 and price <= bbl * 1.002:
                score += 15
            elif direction == -1 and price >= bbu * 0.998:
                score += 15

        # EMAs 1m alineadas (hasta 10 pts)
        if ema_fast is not None and ema_slow is not None:
            if direction == 1 and price > ema_fast and ema_fast > ema_slow:
                score += 10
            elif direction == -1 and price < ema_fast and ema_fast < ema_slow:
                score += 10

        # Volumen por encima de la media (hasta 10 pts)
        vol = current.get('volume')
        vol_sma = current.get('volume_sma20')
        if vol is not None and vol_sma is not None and vol_sma and vol_sma > 0 and vol >= vol_sma * 0.9:
            score += 10

        return min(100, score)

    def check_signals(self, df, trend_df):
        try:
            if df.empty or trend_df.empty:
                return
            if len(df) < 3:
                return

            current = df.iloc[-1]
            prev = df.iloc[-2]
            trend_last = trend_df.iloc[-1]

            price = float(current['close'])
            rsi = current.get('RSI_14')
            atr = self._get_atr(current)
            if atr is None or (isinstance(atr, float) and math.isnan(atr)):
                atr = price * 0.005

            # MTF: tendencia 15m
            major_ema200 = trend_last.get(f"EMA_{self.config['ema_trend']}", trend_last['close'])
            if major_ema200 is None or (isinstance(major_ema200, float) and math.isnan(major_ema200)):
                major_ema200 = trend_last['close']
            major_trend_up = trend_last['close'] > major_ema200

            macd = current.get('MACD_12_26_9')
            macd_s = current.get('MACDs_12_26_9')
            bbl = current.get('BBL_20_2.0_2.0')
            bbu = current.get('BBU_20_2.0_2.0')

            signal = "ESPERAR"
            reason = "Esperando confluencia suficiente..."
            sl = 0.0
            tp = 0.0
            strength = 0

            # Volatilidad mínima
            if atr < (price * 0.0005):
                self.latest_signal = "ESPERAR"
                self.signal_reason = "Volatilidad insuficiente"
                self.signal_strength = 0
                return

            # Scores para COMPRA y VENTA
            buy_score = self._compute_signal_strength(current, prev, trend_last, price, atr, major_trend_up, 1)
            sell_score = self._compute_signal_strength(current, prev, trend_last, price, atr, major_trend_up, -1)

            min_strength = self.config.get('min_signal_strength', 65)
            persistence = self.config.get('signal_persistence', 2)

            # Decidir señal por mayor score y umbral
            if buy_score >= min_strength and buy_score > sell_score:
                # Confirmaciones extra para COMPRA
                if major_trend_up and (rsi is None or rsi < self.config['rsi_buy_threshold'] + 8):
                    if macd is not None and macd_s is not None and macd > macd_s:
                        signal = "COMPRA PRO"
                        reason = f"Confluencia COMPRA (score {int(buy_score)}) | MTF + RSI + MACD"
                        sl = price - (atr * self.config['sl_multiplier'])
                        tp = price + (atr * self.config['tp_multiplier'])
                        strength = buy_score
                    elif price <= (bbl * 1.002 if bbl is not None else price):
                        signal = "COMPRA ALPHA"
                        reason = f"Rebote BB + RSI + MTF (score {int(buy_score)})"
                        sl = price - (atr * self.config['sl_multiplier'])
                        tp = price + (atr * self.config['tp_multiplier'])
                        strength = buy_score

            elif sell_score >= min_strength and sell_score > buy_score:
                if not major_trend_up and (rsi is None or rsi > self.config['rsi_sell_threshold'] - 8):
                    if macd is not None and macd_s is not None and macd < macd_s:
                        signal = "VENTA PRO"
                        reason = f"Confluencia VENTA (score {int(sell_score)}) | MTF + RSI + MACD"
                        sl = price + (atr * self.config['sl_multiplier'])
                        tp = price - (atr * self.config['tp_multiplier'])
                        strength = sell_score
                    elif price >= (bbu * 0.998 if bbu is not None else price):
                        signal = "VENTA ALPHA"
                        reason = f"Resistencia BB + RSI + MTF (score {int(sell_score)})"
                        sl = price + (atr * self.config['sl_multiplier'])
                        tp = price - (atr * self.config['tp_multiplier'])
                        strength = sell_score

            # Persistencia: exigir misma señal N veces seguidas (evitar falsos cruces)
            self._signal_history.append(signal)
            if len(self._signal_history) > persistence * 2:
                self._signal_history = self._signal_history[-(persistence * 2):]
            same_count = 0
            for s in reversed(self._signal_history):
                if s == signal:
                    same_count += 1
                else:
                    break
            if signal not in ("ESPERAR", "ESPERANDO") and same_count < persistence:
                signal = "ESPERAR"
                reason = f"Señal en espera (persistencia {same_count}/{persistence})"

            self.latest_signal = signal
            self.signal_reason = reason
            self.signal_strength = strength
            self.stop_loss = sl
            self.take_profit = tp
            self.volatility = "ALTA" if atr > (price * 0.008) else "NORMAL"

        except Exception as e:
            print(f"Signal Processing Error: {e}")
            import traceback
            traceback.print_exc()

    async def start_loop(self):
        self.is_running = True
        print(f"🔥 QuinaBot ALPHA v3.0 (Real-Money Ready) | {self.symbol}")
        while self.is_running:
            # Parallel Fetch (1m and 15m)
            raw_1m, raw_15m = await asyncio.gather(
                self.fetch_candles('1m', 300),
                self.fetch_candles('15m', 200)
            )
            
            if not raw_1m.empty and not raw_15m.empty:
                self.data = self.analyze_data(raw_1m)
                self.trend_data = self.analyze_data(raw_15m)
                
                self.check_signals(self.data, self.trend_data)
                
                if not self.data.empty:
                    latest = self.data.iloc[-1]
                    price = latest['close']
                    closed = self.paper_trading.check_trade(price)
                    if closed:
                        self._cooldown_until = time.time() + self.config.get('cooldown_seconds', 45)
                        self._cooldown_direction = closed.get('signal', '')

                    if self.latest_signal not in ["ESPERAR", "ESPERANDO"]:
                        if not self._in_cooldown(self.latest_signal) and self.signal_strength >= self.config.get('min_signal_strength', 65):
                            self.paper_trading.open_trade(
                                self.latest_signal, price, self.stop_loss, self.take_profit, self.symbol
                            )

                    ts = datetime.now().strftime('%H:%M:%S')
                    trend_ema = self.trend_data.iloc[-1].get('EMA_200', 0) if not self.trend_data.empty else 0
                    print(f"[{ts}] {self.symbol} | Price: {price:.2f} | MTF: {'UP' if price > trend_ema else 'DOWN'} | Signal: {self.latest_signal} | Strength: {self.signal_strength}")
            
            await asyncio.sleep(2)

    def get_latest_data(self):
        if self.data.empty: return {"status": "waiting", "reason": self.signal_reason}
        last = self.data.iloc[-1]
        candles = []
        for _, row in self.data.tail(100).iterrows():
            candles.append({
                'time': int(row['timestamp'].timestamp()),
                'open': row['open'], 'high': row['high'], 'low': row['low'], 'close': row['close']
            })
        
        atr_val = self._get_atr(last)
        return {
            "symbol": self.symbol,
            "signal": self.latest_signal,
            "reason": self.signal_reason,
            "signal_strength": getattr(self, 'signal_strength', 0),
            "price": last['close'],
            "metrics": {
                "rsi": last.get('RSI_14', 0),
                "ema200": last.get(f"EMA_{self.config['ema_trend']}", 0),
                "vol": atr_val,
            },
            "risk": {"sl": getattr(self, 'stop_loss', 0), "tp": getattr(self, 'take_profit', 0), "vol": getattr(self, 'volatility', 'NORMAL')},
            "cooldown_until": max(0, self._cooldown_until - time.time()) if getattr(self, '_cooldown_until', 0) else 0,
            "candles": candles,
            "performance": self.paper_trading.get_stats(),
        }