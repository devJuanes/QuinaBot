import time

class PaperTrading:
    def __init__(self):
        self.trades = []
        self.active_trade = None
        self.total_pnl = 0.0
        self.wins = 0
        self.losses = 0
        
    def open_trade(self, signal, entry_price, sl, tp, symbol):
        """Open a new paper trade"""
        if self.active_trade:
            # Close previous trade if still open
            self.close_trade(entry_price, "New Signal")
        
        self.active_trade = {
            'signal': signal,
            'entry_price': entry_price,
            'stop_loss': sl,
            'take_profit': tp,
            'symbol': symbol,
            'entry_time': time.time(),
            'status': 'OPEN'
        }
        print(f"📊 Paper Trade OPENED: {signal} @ ${entry_price:.2f}")
    
    def check_trade(self, current_price):
        """Check if SL or TP was hit"""
        if not self.active_trade or self.active_trade['status'] != 'OPEN':
            return None
        
        trade = self.active_trade
        signal = trade['signal']
        
        # Check for BUY trades
        if 'COMPRA' in signal:
            if current_price <= trade['stop_loss']:
                return self.close_trade(current_price, "Stop Loss Hit")
            elif current_price >= trade['take_profit']:
                return self.close_trade(current_price, "Take Profit Hit")
        
        # Check for SELL trades
        elif 'VENTA' in signal:
            if current_price >= trade['stop_loss']:
                return self.close_trade(current_price, "Stop Loss Hit")
            elif current_price <= trade['take_profit']:
                return self.close_trade(current_price, "Take Profit Hit")
        
        return None
    
    def close_trade(self, exit_price, reason):
        """Close active trade and calculate P&L"""
        if not self.active_trade:
            return None
        
        trade = self.active_trade
        signal = trade['signal']
        entry = trade['entry_price']
        
        # Calculate P&L
        if 'COMPRA' in signal:
            pnl = exit_price - entry
        else:  # VENTA
            pnl = entry - exit_price
        
        pnl_percent = (pnl / entry) * 100
        
        # Update stats
        self.total_pnl += pnl_percent
        if pnl > 0:
            self.wins += 1
        else:
            self.losses += 1
        
        # Save closed trade
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
        
        print(f"📊 Paper Trade CLOSED: {reason} | P&L: {pnl_percent:.2f}%")
        return closed_trade
    
    def get_stats(self):
        """Get trading statistics"""
        total_trades = self.wins + self.losses
        win_rate = (self.wins / total_trades * 100) if total_trades > 0 else 0
        
        return {
            'total_pnl': round(self.total_pnl, 2),
            'total_trades': total_trades,
            'wins': self.wins,
            'losses': self.losses,
            'win_rate': round(win_rate, 2),
            'active_trade': self.active_trade,
            'recent_trades': self.trades[-5:]  # Last 5 trades
        }
