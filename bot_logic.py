import ccxt
import pandas as pd
import pandas_ta as ta
import asyncio
from paper_trading import PaperTrading
from datetime import datetime

class QuinaBot:
    def __init__(self, symbol='BTC/USDT', timeframe='1m'):
        self.symbol = symbol
        self.timeframe = timeframe
        
        # Configuration (can be updated dynamically)
        self.config = {
            'rsi_buy_threshold': 35,
            'rsi_sell_threshold': 65,
            'sl_multiplier': 1.0,
            'tp_multiplier': 1.5
        }
        
        # 1. Futures Exchange (Default)
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        
        # 2. Spot Exchange (Fallback for Forex/Spot pairs)
        self.exchange_spot = ccxt.binance({
            'enableRateLimit': True,
            # No options means default spot
        })
        
        self.data = pd.DataFrame()
        self.latest_signal = "ESPERANDO"
        self.signal_reason = "Iniciando conexión..."
        self.is_running = False
        self.use_spot = False # Flag to switch exchange
        
        # Paper Trading
        self.paper_trading = PaperTrading()
    
    def update_config(self, new_config):
        """Update strategy configuration dynamically"""
        self.config['rsi_buy_threshold'] = new_config.get('rsiBuyThreshold', 35)
        self.config['rsi_sell_threshold'] = new_config.get('rsiSellThreshold', 65)
        self.config['sl_multiplier'] = new_config.get('slMultiplier', 1.0)
        self.config['tp_multiplier'] = new_config.get('tpMultiplier', 1.5)
        print(f"✅ Config updated: {self.config}")

    async def set_symbol(self, new_symbol):
        print(f"Switching market to: {new_symbol}")
        self.symbol = new_symbol
        self.data = pd.DataFrame()
        self.latest_signal = "ESPERANDO"
        self.signal_reason = f"Validando {new_symbol}..."
        
        # Smart Detection: Check Futures first, then Spot
        try:
            # We must load markets to check existence
            if not self.exchange.markets:
                await asyncio.to_thread(self.exchange.load_markets)
            
            if new_symbol in self.exchange.markets:
                print(f"✅ {new_symbol} found in Futures.")
                self.use_spot = False
                self.signal_reason = "Modo: Futuros 🚀"
            else:
                print(f"⚠️ {new_symbol} not in Futures. Checking Spot...")
                if not self.exchange_spot.markets:
                    await asyncio.to_thread(self.exchange_spot.load_markets)
                
                if new_symbol in self.exchange_spot.markets:
                    print(f"✅ {new_symbol} found in Spot.")
                    self.use_spot = True
                    self.signal_reason = "Modo: Spot (Forex/Crypto) 🌍"
                else:
                    print(f"❌ {new_symbol} not found anywhere.")
                    self.signal_reason = "Error: Par no encontrado"
        except Exception as e:
            print(f"Error validating symbol: {e}")
            self.signal_reason = "Error de validación"

    async def fetch_candles(self):
        try:
            # Select active exchange
            active_exchange = self.exchange_spot if self.use_spot else self.exchange
            
            if active_exchange.has['fetchOHLCV']:
                ohlcv = await asyncio.to_thread(
                    active_exchange.fetch_ohlcv, 
                    self.symbol, 
                    self.timeframe, 
                    limit=250
                )
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                return df
        except Exception as e:
            print(f"CRITICAL ERROR fetching real data: {e}")
            self.signal_reason = f"Error Conexión: {str(e)[:20]}..."
            return pd.DataFrame()
        return pd.DataFrame()

    def analyze_data(self, df):
        if df.empty or len(df) < 50:
            return df
        
        # Trend: EMA 200
        df.ta.ema(length=200, append=True)
        # Momentum: RSI 14
        df.ta.rsi(length=14, append=True)
        # Momentum/Trend: MACD
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        # Volatility: Bollinger Bands
        df.ta.bbands(length=20, std=2, append=True)
        # Volatility: ATR 14 (For Stop Loss)
        df.ta.atr(length=14, append=True)
        
        self.check_signals(df)
            
        return df

    def check_signals(self, df):
        try:
            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            # Extract indicators
            close = last['close']
            rsi = last['RSI_14']
            ema200 = last.get('EMA_200', 0) 
            atr = last.get('ATRr_14', 0) 
            
            macd_line = last['MACD_12_26_9']
            macd_signal = last['MACDs_12_26_9']
            prev_macd_line = prev['MACD_12_26_9']
            prev_macd_signal = prev['MACDs_12_26_9']
            
            bb_lower = last['BBL_20_2.0_2.0']
            bb_upper = last['BBU_20_2.0_2.0']
            
            signal = "ESPERAR"
            reason = "Sin condiciones óptimas."
            stop_loss = 0.0
            take_profit = 0.0

            # --- STRATEGY LOGIC (SCALPING / MORE AGGRESSIVE) ---
            
            is_uptrend = close > ema200 if not pd.isna(ema200) else True
            trend_str = "Alcista" if is_uptrend else "Bajista"
            
            # Default "Waiting" message with live stats
            reason = f"{trend_str} | RSI: {int(rsi)} | Esperando setup..."
            
            # Get config values
            rsi_buy = self.config['rsi_buy_threshold']
            rsi_sell = self.config['rsi_sell_threshold']
            sl_mult = self.config['sl_multiplier']
            tp_mult = self.config['tp_multiplier']
            
            # PRIORITY 1: RSI EXTREMES (Check FIRST - Simple, RSI-only signals)
            if rsi < rsi_buy:
                signal = "COMPRA"
                reason = f"RSI Muy Bajo ({int(rsi)}) - Sobreventa"
                stop_loss = close - (atr * sl_mult)
                take_profit = close + (atr * tp_mult)
            
            elif rsi > rsi_sell:
                signal = "VENTA"
                reason = f"RSI Muy Alto ({int(rsi)}) - Sobrecompra"
                stop_loss = close + (atr * sl_mult)
                take_profit = close - (atr * tp_mult)
            
            # PRIORITY 2: STRONG REVERSAL (Bollinger Bounce + RSI)
            elif is_uptrend and rsi < 40 and close <= bb_lower * 1.015:
                signal = "COMPRA FUERTE"
                reason = "Rebote en Soporte + RSI Bajo"
                stop_loss = close - (atr * 1.2)
                take_profit = close + (atr * 2.0)
                
            elif not is_uptrend and rsi > 60 and close >= bb_upper * 0.985:
                signal = "VENTA FUERTE"
                reason = "Rebote en Resistencia + RSI Alto"
                stop_loss = close + (atr * 1.2)
                take_profit = close - (atr * 2.0)

            # PRIORITY 3: TREND MOMENTUM (MACD Cross)
            elif is_uptrend and macd_line > macd_signal and prev_macd_line <= prev_macd_signal:
                signal = "COMPRA"
                reason = "Cruce MACD a favor de tendencia"
                stop_loss = close - (atr * 1.0)
                take_profit = close + (atr * 1.5)

            elif not is_uptrend and macd_line < macd_signal and prev_macd_line >= prev_macd_signal:
                signal = "VENTA"
                reason = "Cruce MACD a favor de tendencia"
                stop_loss = close + (atr * 1.0)
                take_profit = close - (atr * 1.5)
                
            # PRIORITY 4: PULLBACK (Scalp entries)
            elif is_uptrend and 40 < rsi < 50 and macd_line > macd_signal:
                signal = "COMPRA (SCALP)"
                reason = "Pequeño retroceso en subida"
                stop_loss = close - (atr * 0.8)
                take_profit = close + (atr * 1.2)
            
            elif not is_uptrend and 50 < rsi < 60 and macd_line < macd_signal:
                signal = "VENTA (SCALP)"
                reason = "Pequeño rebote en bajada"
                stop_loss = close + (atr * 0.8)
                take_profit = close - (atr * 1.2)
                
            self.latest_signal = signal
            self.signal_reason = reason
            self.stop_loss = stop_loss
            self.take_profit = take_profit
            self.volatility = "ALTA" if atr > (close * 0.01) else "BAJA" # Simple volatility check
            
        except KeyError as e:
            print(f"⚠️ KeyError in check_signals: {e}")
            print(f"Available columns: {df.columns.tolist()}")
            self.latest_signal = "ESPERANDO"
            self.signal_reason = "Calculando indicadores..."
            self.stop_loss = 0.0
            self.take_profit = 0.0
            self.volatility = "---"
        except Exception as e:
            print(f"❌ Unexpected error in check_signals: {e}")
            self.latest_signal = "ESPERANDO"
            self.signal_reason = f"Error: {str(e)[:30]}"

    async def start_loop(self):
        self.is_running = True
        print("QuinaBot REAL DATA Mode started...")
        while self.is_running:
            raw_df = await self.fetch_candles()
            if not raw_df.empty:
                self.data = self.analyze_data(raw_df)
                if not self.data.empty:
                     latest = self.data.iloc[-1]
                     current_price = latest['close']
                     
                     # Paper Trading: Check if SL/TP hit
                     self.paper_trading.check_trade(current_price)
                     
                     # Paper Trading: Open new trade on signal change
                     if self.latest_signal not in ["ESPERANDO", "ESPERAR", "NEUTRAL"]:
                         self.paper_trading.open_trade(
                             self.latest_signal,
                             current_price,
                             getattr(self, 'stop_loss', 0),
                             getattr(self, 'take_profit', 0),
                             self.symbol
                         )
                     
                     print(f"[{datetime.now().strftime('%H:%M:%S')}] {self.symbol} | Price: {latest['close']:.2f} | RSI: {latest.get('RSI_14', 0):.2f} | Signal: {self.latest_signal}")
            
            # Respect rate limits for real API
            await asyncio.sleep(2) 

    def get_latest_data(self):
        if self.data.empty:
            return {"error": "Esperando datos reales...", "reason": self.signal_reason}
        
        last = self.data.iloc[-1]
        
        records = self.data[['timestamp', 'open', 'high', 'low', 'close']].tail(100).to_dict('records')
        formatted_candles = []
        for r in records:
            formatted_candles.append({
                'time': int(r['timestamp'].timestamp()),
                'open': r['open'], 'high': r['high'], 'low': r['low'], 'close': r['close']
            })

        return {
            "symbol": self.symbol,
            "signal": self.latest_signal,
            "reason": self.signal_reason,
            "stop_loss": getattr(self, 'stop_loss', 0.0),
            "take_profit": getattr(self, 'take_profit', 0.0),
            "volatility": getattr(self, 'volatility', '---'),
            "current_price": last['close'],
            "rsi": last.get('RSI_14', 0),
            "ema200": last.get('EMA_200', 0) if not pd.isna(last.get('EMA_200')) else None,
            "candles": formatted_candles,
            "paper_trading": self.paper_trading.get_stats()
        }