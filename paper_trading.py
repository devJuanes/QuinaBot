import time

class PaperTrading:
    def __init__(self):
        self.trades = []
        self.active_trade = None
        self.total_pnl = 0.0
        self.wins = 0
        self.losses = 0
        self.trailing_sl_pct = 0.015 # 1.5% trailing by default
        
    def open_trade(self, signal, entry_price, sl, tp, symbol):
        """Open a new paper trade with Trailing SL support"""
        if self.active_trade:
            # If same signal direction, keep it. If different, flip it.
            if self.active_trade['signal'] == signal: return
            self.close_trade(entry_price, "Signal Flip")
        
        self.active_trade = {
            'signal': signal,
            'entry_price': entry_price,
            'stop_loss': sl,
            'take_profit': tp,
            'max_price_seen': entry_price if 'COMPRA' in signal else 99999999,
            'min_price_seen': entry_price if 'VENTA' in signal else 0,
            'symbol': symbol,
            'entry_time': time.time(),
            'status': 'OPEN'
        }
        print(f"📊 [PRO] Paper Trade OPENED: {signal} @ ${entry_price:.2f} | MTF Verified ✅")
    
    def check_trade(self, current_price):
        """Check for SL, TP, or Trailing SL hit"""
        if not self.active_trade or self.active_trade['status'] != 'OPEN':
            return None
        
        trade = self.active_trade
        signal = trade['signal']
        
        # 1. Update Trailing High/Low
        if 'COMPRA' in signal:
            if current_price > trade['max_price_seen']:
                trade['max_price_seen'] = current_price
                # Trail the stop loss up
                new_sl = current_price * (1 - self.trailing_sl_pct)
                if new_sl > trade['stop_loss']:
                    trade['stop_loss'] = new_sl
            
            # Check Exit
            if current_price <= trade['stop_loss']:
                return self.close_trade(current_price, "Stop Loss (Trailing) Hit")
            elif current_price >= trade['take_profit']:
                return self.close_trade(current_price, "Take Profit Hit")
        
        elif 'VENTA' in signal:
            if current_price < trade['min_price_seen']:
                trade['min_price_seen'] = current_price
                # Trail the stop loss down
                new_sl = current_price * (1 + self.trailing_sl_pct)
                if new_sl < trade['stop_loss']:
                    trade['stop_loss'] = new_sl
            
            # Check Exit
            if current_price >= trade['stop_loss']:
                return self.close_trade(current_price, "Stop Loss (Trailing) Hit")
            elif current_price <= trade['take_profit']:
                return self.close_trade(current_price, "Take Profit Hit")
        
        return None
    
    def close_trade(self, exit_price, reason):
        if not self.active_trade: return None
        
        trade = self.active_trade
        entry = trade['entry_price']
        
        pnl = (exit_price - entry) if 'COMPRA' in trade['signal'] else (entry - exit_price)
        pnl_percent = (pnl / entry) * 100
        
        self.total_pnl += pnl_percent
        if pnl > 0: self.wins += 1
        else: self.losses += 1
        
        closed_trade = {
            **trade,
            'exit_price': exit_price,
            'exit_time': time.time(),
            'pnl': pnl_percent,
            'reason': reason,
            'status': 'CLOSED'
        }
        self.trades.append(closed_trade)
        self.active_trade = None
        
        print(f"📊 [PRO] Paper Trade CLOSED: {reason} | P&L: {pnl_percent:.2f}% | Wins: {self.wins}/{self.wins+self.losses}")
        return closed_trade
    
    def get_stats(self):
        total = self.wins + self.losses
        return {
            'total_pnl': round(self.total_pnl, 2),
            'total_trades': total,
            'win_rate': round((self.wins/total*100), 2) if total > 0 else 0,
            'active_trade': self.active_trade,
            'recent_trades': self.trades[-5:]
        }
