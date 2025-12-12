"""
风险管理模块
负责仓位计算、止损止盈、风险控制
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
        
        参数:
        - balance: 账户余额
        - atr: 当前ATR值
        - price: 当前价格
        - risk_per_trade: 风险比例(如0.02 = 2%)
        - atr_multiplier: ATR倍数(如2 = 2倍ATR作为止损)
        
        返回: 手数(保留2位小数)
        """
        # 风险金额
        risk_amount = balance * risk_per_trade
        
        # 止损距离(点数)
        stop_distance = atr * atr_multiplier
        
        # 黄金: 1手 = 100盎司
        # 每点价值 = 100美元
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
        计算止损和止盈价格
        
        止损 = 价格 ± (ATR × 止损倍数)
        止盈 = 价格 ± (ATR × 止盈倍数)
        
        参数:
        - signal: 1=买入, -1=卖出
        - price: 开仓价格
        - atr: ATR值
        - config: 策略参数
        
        返回: (止损价格, 止盈价格)
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
    
    def check_daily_loss_limit(self, current_balance):
        """
        检查是否超过日亏损限制
        
        如果当日亏损超过5%,返回True(停止交易)
        """
        if self.start_balance == 0:
            self.start_balance = current_balance
            return False
        
        daily_loss = (self.start_balance - current_balance) / self.start_balance
        
        if daily_loss >= self.config['max_daily_loss']:
            print(f"⚠️  警告: 达到日亏损限制 {daily_loss*100:.2f}%")
            return True
        
        return False
    
    def check_max_drawdown(self, current_balance):
        """
        检查最大回撤
        
        回撤 = (峰值 - 当前) / 峰值
        如果回撤超过15%,返回True(停止交易)
        """
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
        """
        判断是否应该移至盈亏平衡
        
        当盈利达到1倍ATR时,将止损移至开仓价(保本)
        
        参数:
        - position_type: 'LONG' 或 'SHORT'
        - entry_price: 开仓价
        - current_price: 当前价
        - atr: ATR值
        
        返回: True/False
        """
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
        """
        计算移动止损
        
        当盈利超过1.5倍ATR时,止损跟随价格移动
        新止损 = 当前价 - 1.5倍ATR
        
        参数:
        - position_type: 'LONG' 或 'SHORT'
        - entry_price: 开仓价
        - current_price: 当前价
        - current_sl: 当前止损价
        - atr: ATR值
        
        返回: 新止损价格(如果需要调整)
        """
        min_profit = self.config['min_profit_move_sl'] * atr
        
        if position_type == 'LONG':
            profit = current_price - entry_price
            if profit > min_profit:
                new_sl = current_price - (1.5 * atr)
                # 只能向上移动止损
                if new_sl > current_sl:
                    return new_sl
        
        else:  # SHORT
            profit = entry_price - current_price
            if profit > min_profit:
                new_sl = current_price + (1.5 * atr)
                # 只能向下移动止损
                if new_sl < current_sl:
                    return new_sl
        
        return None
    
    def get_risk_summary(self, balance):
        """
        获取风险摘要
        
        返回当前风险状态
        """
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