"""
风险管理模块
负责仓位计算、止损止盈、风险控制
已加入动态止损止盈倍数（根据波动率自适应）
"""

class RiskManager:
    """风险管理器"""
    
    def __init__(self, risk_config):
        self.config = risk_config
        self.daily_pnl = 0
        self.start_balance = 0
        self.peak_balance = 0
        self.daily_trades = 0
    
    def calculate_position_size(self, balance, atr, price, risk_per_trade, atr_multiplier):
        """
        计算交易手数
        
        公式:
        手数 = 风险金额 / (止损距离 × 点值)
        """
        # 风险金额
        risk_amount = balance * risk_per_trade
        
        # 止损距离(点数)
        stop_distance = atr * atr_multiplier
        
        # 黄金: 1手 = 100盎司，每点价值 = 100美元
        point_value = 100
        
        # 计算手数
        lot_size = risk_amount / (stop_distance * point_value)
        
        # 限制手数范围
        min_lot = 0.01
        max_lot = 1.0
        lot_size = max(min_lot, min(lot_size, max_lot))
        
        # 保留2位小数
        lot_size = round(lot_size, 2)
        
        return lot_size
    
    def calculate_stop_loss_take_profit(self, signal, price, atr, config):
        """
        计算止损和止盈价格（兼容旧调用）
        """
        atr_sl = config['atr_multiplier_sl'] * atr
        atr_tp = config['atr_multiplier_tp'] * atr
        
        if signal == 1:  # 买入
            sl = price - atr_sl
            tp = price + atr_tp
        else:  # 卖出
            sl = price + atr_sl
            tp = price - atr_tp
        
        return sl, tp

    def get_dynamic_multipliers(self, df, params):
        """
        新增：动态计算止损止盈倍数（根据当前波动率自适应）
        """
        latest = df.iloc[-1]
        atr = latest['ATR']
        atr_mean = df['ATR'].iloc[-20:].mean()  # 过去20根平均ATR
        volatility_ratio = atr / atr_mean if atr_mean > 0 else 1.0  # 当前波动/平均波动

        # 基础倍数
        base_sl = params['atr_multiplier_sl']  # 1.2
        base_tp = params['atr_multiplier_tp']  # 5.5

        # 动态调整
        if volatility_ratio > 1.3:  # 高波动（大行情）
            sl_multiplier = base_sl * 1.5  # 止损松到1.8，扛回调
            tp_multiplier = base_tp * 1.3  # 止盈远到7.15，吃大肉
        elif volatility_ratio < 0.8:  # 低波动（假期/震荡）
            sl_multiplier = base_sl * 0.8  # 止损紧到0.96，亏少
            tp_multiplier = base_tp * 0.8  # 止盈近到4.4，快出局
        else:
            sl_multiplier = base_sl
            tp_multiplier = base_tp

        return sl_multiplier, tp_multiplier
    
    def check_daily_loss_limit(self, current_balance):
        """检查是否超过日亏损限制"""
        if self.start_balance == 0:
            self.start_balance = current_balance
            return False
        
        daily_loss = (self.start_balance - current_balance) / self.start_balance
        
        if daily_loss >= self.config['max_daily_loss']:
            print(f"⚠️  警告: 达到日亏损限制 {daily_loss*100:.2f}%")
            return True
        
        return False
    
    def check_max_drawdown(self, current_balance):
        """检查最大回撤"""
        if current_balance > self.peak_balance:
            self.peak_balance = current_balance
        
        if self.peak_balance == 0:
            return False
        
        drawdown = (self.peak_balance - current_balance) / self.peak_balance
        
        if drawdown >= self.config['max_drawdown']:
            print(f"⚠️  警告: 达到最大回撤限制 {drawdown*100:.2f}%")
            return True
        
        return False
    
    def should_move_to_breakeven(self, position_type, entry_price, current_price, atr):
        """判断是否移至盈亏平衡"""
        if position_type == 'LONG':
            profit = current_price - entry_price
            if profit >= self.config['break_even_trigger'] * atr:
                return True
        else:  # SHORT
            profit = entry_price - current_price
            if profit >= self.config['break_even_trigger'] * atr:
                return True
        
        return False
    
    def calculate_trailing_stop(self, position_type, entry_price, current_price, current_sl, atr):
        """计算移动止损"""
        min_profit = self.config['min_profit_move_sl'] * atr
        
        if position_type == 'LONG':
            profit = current_price - entry_price
            if profit > min_profit:
                new_sl = current_price - (1.5 * atr)
                if new_sl > current_sl:
                    return new_sl
        
        else:  # SHORT
            profit = entry_price - current_price
            if profit > min_profit:
                new_sl = current_price + (1.5 * atr)
                if new_sl < current_sl:
                    return new_sl
        
        return None
    
    def get_risk_summary(self, balance):
        """获取风险摘要"""
        if self.start_balance == 0:
            daily_pnl_pct = 0
        else:
            daily_pnl_pct = ((balance - self.start_balance) / self.start_balance) * 100
        
        if self.peak_balance == 0:
            drawdown_pct = 0
        else:
            drawdown_pct = ((self.peak_balance - balance) / self.peak_balance) * 100
        
        return {
            'daily_pnl': balance - self.start_balance,
            'daily_pnl_pct': daily_pnl_pct,
            'drawdown': self.peak_balance - balance,
            'drawdown_pct': drawdown_pct,
            'daily_trades': self.daily_trades
        }