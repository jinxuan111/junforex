"""
professional_executor.py - 专业级策略执行模块
包含：网格头寸管理、动态调整、风险控制
"""

import pandas as pd
import numpy as np

class ProfessionalExecutor:
    """专业策略执行器"""
    
    def __init__(self, initial_capital=100):
        self.initial_capital = initial_capital
        self.balance = initial_capital
        self.grid_positions = {}  # 追踪网格头寸
        self.trade_history = []
        self.grid_trade_count = 0
    
    def manage_grid_positions(self, current_price, grid_info, signal, confidence):
        """
        管理网格头寸
        核心思想：
        - 在支撑位逐层买入（越低越多）
        - 在阻力位逐层卖出（越高越多）
        - 自动平衡持仓
        
        返回: (position_action, lot_size, details)
        """
        if grid_info is None:
            return 'HOLD', 0, None
        
        buy_levels = grid_info['buy_levels']
        sell_levels = grid_info['sell_levels']
        current_level = None
        
        # 确定当前在哪个网格层
        action = None
        
        if signal == 1:  # 买入信号
            for i, buy_level in enumerate(buy_levels):
                if current_price <= buy_level * 1.005:
                    current_level = i
                    action = 'BUY_GRID'
                    
                    # 网格层数越深，下注越大
                    # 最底层 (i=0) = 基础手数
                    # 倒数第二层 (i=1) = 基础手数 * 1.5
                    # 倒数第三层 (i=2) = 基础手数 * 2.0
                    lot_multiplier = 1.0 + (i * 0.5)
                    break
        
        elif signal == -1:  # 卖出信号
            for i, sell_level in enumerate(sell_levels):
                if current_price >= sell_level * 0.995:
                    current_level = i
                    action = 'SELL_GRID'
                    
                    lot_multiplier = 1.0 + (i * 0.5)
                    break
        
        if action is None:
            return 'HOLD', 0, None
        
        # 计算手数
        base_lot = 0.01  # 基础手数
        lot_size = base_lot * lot_multiplier * confidence
        lot_size = round(lot_size, 3)
        
        return action, lot_size, {
            'current_level': current_level,
            'lot_multiplier': lot_multiplier,
            'base_lot': base_lot
        }
    
    def should_take_profit_early(self, position, current_price, profit_pct):
        """
        专业的部分止盈逻辑
        当利润达到目标的一定比例时，平掉部分头寸
        
        返回: (should_close_ratio, reason)
        """
        # 目标利润 = 网格宽度 * 2.5
        target_profit = position['target_profit']
        current_profit = profit_pct
        
        # 到达目标利润的80% 时，平掉50%
        if current_profit >= target_profit * 0.8:
            return 0.5, f"部分止盈: {profit_pct:.2f}% vs 目标 {target_profit:.2f}%"
        
        # 到达目标利润的100% 时，全部平仓
        if current_profit >= target_profit:
            return 1.0, f"完全止盈: 达到目标 {target_profit:.2f}%"
        
        return 0, None
    
    def calculate_optimal_position_size(self, balance, risk_per_trade=0.01):
        """
        Kelly准则 + 网格交易优化的头寸计算
        
        返回: lot_size
        """
        # 基础：每100U开0.01手
        base_lot = (balance / 100) * 0.01
        
        # Kelly准则优化
        # kelly_fraction = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
        # 对于网格交易，假设胜率60%，赔率1:1
        estimated_win_rate = 0.60
        kelly_fraction = estimated_win_rate - (1 - estimated_win_rate)  # = 0.20
        
        # 实际头寸 = 基础头寸 * Kelly分数 * 0.8 (留20%安全边际)
        optimal_lot = base_lot * kelly_fraction * 0.8
        
        # 限制范围
        optimal_lot = max(0.01, min(optimal_lot, base_lot * 2))
        
        return round(optimal_lot, 3)
    
    def estimate_grid_performance(self, grid_info, historical_volatility):
        """
        预估网格交易在当前环境下的表现
        
        返回: (expected_return, max_drawdown, sharpe_ratio)
        """
        if grid_info is None:
            return 0, 0, 0
        
        grid_width = grid_info['grid_width']
        volatility = grid_info['volatility']
        
        # 期望收益 = 网格宽度 * 网格层数 / 总范围
        grid_count = len(grid_info['buy_levels']) + len(grid_info['sell_levels'])
        total_range = grid_info['total_range']
        
        if total_range == 0:
            expected_return = 0
        else:
            # 每次触及网格的收益
            per_grid_return = (grid_width / total_range) * 100
            # 预期在这个范围内会触及的网格数
            expected_touches = 3  # 保守估计
            expected_return = per_grid_return * expected_touches
        
        # 最大回撤 = 网格总范围
        max_drawdown = (total_range / grid_info['center']) * 100
        
        # 简化的Sharpe比
        if max_drawdown > 0:
            sharpe = expected_return / max_drawdown
        else:
            sharpe = 0
        
        return expected_return, max_drawdown, sharpe
    
    def log_trade(self, trade_info):
        """记录交易日志"""
        self.trade_history.append({
            'timestamp': pd.Timestamp.now(),
            'type': trade_info.get('type'),
            'signal': trade_info.get('signal'),
            'price': trade_info.get('price'),
            'lot_size': trade_info.get('lot_size'),
            'confidence': trade_info.get('confidence'),
            'zscore': trade_info.get('zscore'),
            'edge_prob': trade_info.get('edge_probability'),
            'grid_level': trade_info.get('grid_level')
        })
    
    def get_trade_statistics(self):
        """获取交易统计"""
        if not self.trade_history:
            return None
        
        df = pd.DataFrame(self.trade_history)
        
        return {
            'total_trades': len(df),
            'buy_trades': len(df[df['signal'] == 1]),
            'sell_trades': len(df[df['signal'] == -1]),
            'avg_confidence': df['confidence'].mean(),
            'avg_zscore': df['zscore'].mean(),
            'avg_edge_prob': df['edge_prob'].mean()
        }

class GridPositionTracker:
    """网格头寸追踪器"""
    
    def __init__(self):
        self.active_grids = {}  # 活跃的网格头寸
        self.closed_grids = []  # 已平仓的网格
    
    def open_grid_position(self, grid_id, level, price, lot_size, direction):
        """打开网格头寸"""
        self.active_grids[grid_id] = {
            'level': level,
            'entry_price': price,
            'lot_size': lot_size,
            'direction': direction,  # 'LONG' or 'SHORT'
            'open_time': pd.Timestamp.now(),
            'status': 'OPEN'
        }
    
    def close_grid_position(self, grid_id, close_price):
        """关闭网格头寸"""
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
    
    def get_net_exposure(self):
        """获取当前净敞口"""
        long_exposure = 0
        short_exposure = 0
        
        for grid_id, pos in self.active_grids.items():
            if pos['direction'] == 'LONG':
                long_exposure += pos['lot_size']
            else:
                short_exposure += pos['lot_size']
        
        return {
            'long': long_exposure,
            'short': short_exposure,
            'net': long_exposure - short_exposure
        }
    
    def get_statistics(self):
        """获取统计信息"""
        if not self.closed_grids:
            return None
        
        pnls = [g['pnl'] for g in self.closed_grids if 'pnl' in g]
        
        return {
            'closed_positions': len(self.closed_grids),
            'total_pnl': sum(pnls),
            'avg_pnl': np.mean(pnls) if pnls else 0,
            'win_rate': len([p for p in pnls if p > 0]) / len(pnls) if pnls else 0,
            'profit_factor': sum([p for p in pnls if p > 0]) / abs(sum([p for p in pnls if p < 0])) if any(p < 0 for p in pnls) else 0
        }