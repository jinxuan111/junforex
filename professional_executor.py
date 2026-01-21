"""
professional_executor.py - 专业级策略执行模块
包含：网格头寸管理、动态调整、风险控制
黄金平衡版本 - 修改版：支持真正多层网格加仓（开多单）
"""

import pandas as pd
import numpy as np

class ProfessionalExecutor:
    """专业策略执行器 - 黄金平衡版"""
    
    def __init__(self, initial_capital=100):
        self.initial_capital = initial_capital
        self.balance = initial_capital
        self.grid_positions = {}
        self.trade_history = []
        self.grid_trade_count = 0
        self.consecutive_losses = 0
        self.max_consecutive_losses = 4
        self.consecutive_wins = 0
        self.max_consecutive_wins = 3
        
        # 新增：集成网格追踪器，防止重复开同一层 + 严格限单边层数
        self.grid_tracker = GridPositionTracker()

    def manage_grid_positions(self, current_price, grid_info, signal, confidence):
        """
        管理网格头寸 - 修改版：放宽触发到±1.0%，避免重复开同一层，支持多单
        """
        if grid_info is None:
            return 'HOLD', 0, None
        
        buy_levels = grid_info['buy_levels']
        sell_levels = grid_info['sell_levels']
        
        print(f"🔍 网格检查: 当前价格 {current_price:.2f} | 买层 {buy_levels} | 卖层 {sell_levels}")

        action = None
        current_level = None
        lot_multiplier = 1.0
        direction = None
        grid_id = None

        if signal == 1:  # 买入信号
            for i, buy_level in enumerate(buy_levels):
                # 修改：放宽触发到 +1.0%（更容易触发多层）
                if current_price <= buy_level * 1.010:
                    current_level = i
                    action = 'BUY_GRID'
                    direction = 'LONG'
                    lot_multiplier = 0.9 + (i * 0.35)
                    grid_id = f"LONG_{i}"
                    break
        
        elif signal == -1:  # 卖出信号
            for i, sell_level in enumerate(sell_levels):
                # 修改：放宽触发到 -1.0%
                if current_price >= sell_level * 0.990:
                    current_level = i
                    action = 'SELL_GRID'
                    direction = 'SHORT'
                    lot_multiplier = 0.9 + (i * 0.35)
                    grid_id = f"SHORT_{i}"
                    break
        
        if action is None or grid_id is None:
            print("ℹ️  未触发任何新网格层 → HOLD")
            return 'HOLD', 0, None

        # 检查是否已开该层（避免重复）
        if grid_id in self.grid_tracker.active_grids:
            print(f"ℹ️  网格 {grid_id} (层 {current_level}) 已存在 → 不重复开仓")
            return 'HOLD', 0, None
        
        # 检查单方向层数限制
        if self.grid_tracker.get_direction_count(direction) >= self.grid_tracker.max_grids_per_side:
            print(f"⚠️  {direction}方向已达最大层数 {self.grid_tracker.max_grids_per_side} → 停止加仓")
            return 'HOLD', 0, None

        print(f"✅ 触发新网格层: {action} 第 {current_level} 层 (价格 {current_price:.2f}, grid_id={grid_id})")

        # 计算手数（保持原逻辑）
        base_lot = 0.01
        loss_reduction = 1.0
        if self.consecutive_losses == 1:
            loss_reduction = 0.85
        elif self.consecutive_losses == 2:
            loss_reduction = 0.70
        elif self.consecutive_losses >= 3:
            loss_reduction = 0.55
        
        win_bonus = 1.0
        if self.consecutive_wins == 1:
            win_bonus = 1.05
        elif self.consecutive_wins == 2:
            win_bonus = 1.10
        elif self.consecutive_wins >= 3:
            win_bonus = 1.15
        
        lot_size = base_lot * lot_multiplier * confidence * loss_reduction * win_bonus
        lot_size = round(lot_size, 3)
        
        min_lot = 0.005
        max_lot = self.balance / 4000
        
        lot_size = max(min_lot, min(lot_size, max_lot))
        
        if loss_reduction < 1.0:
            print(f"⚠️  连续亏损{self.consecutive_losses}次，仓位减至{loss_reduction*100:.0f}%")
        if win_bonus > 1.0:
            print(f"✅  连续盈利{self.consecutive_wins}次，仓位增至{win_bonus*100:.0f}%")
        
        details = {
            'current_level': current_level,
            'lot_multiplier': lot_multiplier,
            'base_lot': base_lot,
            'loss_reduction': loss_reduction,
            'win_bonus': win_bonus,
            'consecutive_losses': self.consecutive_losses,
            'consecutive_wins': self.consecutive_wins,
            'grid_id': grid_id,  # 返回grid_id，供主程序记录开仓
            'direction': direction
        }
        
        return action, lot_size, details

    # 以下方法保持不变（你提供的完整版）
    def should_take_profit_early(self, position, current_price, profit_pct):
        target_profit = position['target_profit']
        current_profit = profit_pct
        
        if current_profit >= target_profit * 0.75:
            return 0.3, f"部分止盈: {profit_pct:.2f}% vs 目标 {target_profit:.2f}%"
        
        if current_profit >= target_profit * 0.9:
            return 0.4, f"再次部分止盈: {profit_pct:.2f}% vs 目标 {target_profit:.2f}%"
        
        if current_profit >= target_profit:
            return 0.3, f"完全止盈: 达到目标 {target_profit:.2f}%"
        
        if current_profit > 0 and profit_pct < current_profit * 0.8:
            return 0.5, f"保护利润: 回撤{((current_profit-profit_pct)/current_profit*100):.1f}%"
        
        return 0, None
    
    def calculate_optimal_position_size(self, balance, risk_per_trade=0.01):
        base_lot = (balance / 100) * 0.01
        estimated_win_rate = 0.58
        kelly_fraction = estimated_win_rate - (1 - estimated_win_rate)
        optimal_lot = base_lot * kelly_fraction * 0.7
        optimal_lot = max(0.006, min(optimal_lot, base_lot * 1.8))
        return round(optimal_lot, 3)
    
    def update_consecutive_counts(self, pnl):
        if pnl > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
            print(f"✅ 盈利，连胜次数: {self.consecutive_wins}")
        elif pnl < 0:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
            print(f"❌ 亏损，连亏次数: {self.consecutive_losses}")
        else:
            self.consecutive_wins = 0
            self.consecutive_losses = 0
    
    def log_trade(self, trade_info):
        if 'pnl' in trade_info:
            self.update_consecutive_counts(trade_info['pnl'])
            self.balance += trade_info['pnl']
        
        self.trade_history.append({
            'timestamp': pd.Timestamp.now(),
            'type': trade_info.get('type'),
            'signal': trade_info.get('signal'),
            'price': trade_info.get('price'),
            'lot_size': trade_info.get('lot_size'),
            'confidence': trade_info.get('confidence'),
            'zscore': trade_info.get('zscore'),
            'edge_prob': trade_info.get('edge_probability'),
            'grid_level': trade_info.get('grid_level'),
            'pnl': trade_info.get('pnl', 0),
            'balance': self.balance,
            'consecutive_wins': self.consecutive_wins,
            'consecutive_losses': self.consecutive_losses
        })
    
    def get_trade_statistics(self):
        if not self.trade_history:
            return None
        
        df = pd.DataFrame(self.trade_history)
        
        stats = {
            'total_trades': len(df),
            'balance': self.balance,
            'total_return': ((self.balance - self.initial_capital) / self.initial_capital) * 100,
            'consecutive_wins': self.consecutive_wins,
            'consecutive_losses': self.consecutive_losses
        }
        
        if 'pnl' in df.columns:
            winning_trades = df[df['pnl'] > 0]
            losing_trades = df[df['pnl'] < 0]
            
            stats.update({
                'winning_trades': len(winning_trades),
                'losing_trades': len(losing_trades),
                'win_rate': len(winning_trades) / len(df) * 100 if len(df) > 0 else 0,
                'avg_win': winning_trades['pnl'].mean() if len(winning_trades) > 0 else 0,
                'avg_loss': losing_trades['pnl'].mean() if len(losing_trades) > 0 else 0,
                'total_pnl': df['pnl'].sum(),
                'profit_factor': abs(winning_trades['pnl'].sum() / losing_trades['pnl'].sum()) if len(losing_trades) > 0 and losing_trades['pnl'].sum() != 0 else 0,
                'largest_win': df['pnl'].max() if len(df) > 0 else 0,
                'largest_loss': df['pnl'].min() if len(df) > 0 else 0,
            })
        
        return stats

# GridPositionTracker 保持不变（已很好）
class GridPositionTracker:
    def __init__(self):
        self.active_grids = {}
        self.closed_grids = []
        self.max_grids_per_side = 4
    
    def open_grid_position(self, grid_id, level, price, lot_size, direction):
        if grid_id in self.active_grids:
            return False
        
        current_count = self.get_direction_count(direction)
        if current_count >= self.max_grids_per_side:
            print(f"⚠️  {direction}方向已达到最大网格数{self.max_grids_per_side}")
            return False
        
        self.active_grids[grid_id] = {
            'level': level,
            'entry_price': price,
            'lot_size': lot_size,
            'direction': direction,
            'open_time': pd.Timestamp.now(),
            'status': 'OPEN'
        }
        print(f"📌 已记录开仓: {grid_id} (层{level}, 手数{lot_size:.3f})")
        return True
    
    def get_direction_count(self, direction):
        count = 0
        for pos in self.active_grids.values():
            if pos['direction'] == direction:
                count += 1
        return count
    
    def close_grid_position(self, grid_id, close_price):
        if grid_id in self.active_grids:
            pos = self.active_grids[grid_id]
            if pos['direction'] == 'LONG':
                pnl = (close_price - pos['entry_price']) * pos['lot_size'] * 100
            else:
                pnl = (pos['entry_price'] - close_price) * pos['lot_size'] * 100
            
            pos['close_price'] = close_price
            pos['close_time'] = pd.Timestamp.now()
            pos['pnl'] = pnl
            pos['status'] = 'CLOSED'
            
            self.closed_grids.append(self.active_grids.pop(grid_id))
            return pnl
        return 0
    
    def get_statistics(self):
        stats = {
            'active_positions': len(self.active_grids),
            'closed_positions': len(self.closed_grids)
        }
        
        if self.closed_grids:
            pnls = [g['pnl'] for g in self.closed_grids if 'pnl' in g]
            stats.update({
                'total_pnl': sum(pnls),
                'avg_pnl': np.mean(pnls) if pnls else 0,
                'win_rate': len([p for p in pnls if p > 0]) / len(pnls) * 100 if pnls else 0,
            })
        return stats