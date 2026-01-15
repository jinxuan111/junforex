"""
stops_implementation.py - 专业级止盈止损机制完整实现
包含：波动率调整、分批止盈、动态止损、网格协调
"""

import pandas as pd
import numpy as np

class ProfessionalStopsManager:
    """专业止盈止损管理器"""
    
    def __init__(self):
        self.positions = {}  # 追踪所有头寸
        self.closed_trades = []  # 已平仓交易记录
    
    # ========== 1. 基础止损计算 ==========
    
    def calculate_stop_loss_basic(self, entry_price, atr, signal, volatility_regime='NORMAL'):
        """
        计算基础止损价格（根据波动率制度调整）
        
        参数：
        - entry_price: 入场价格
        - atr: ATR值（波幅指标）
        - signal: 1=买入, -1=卖出
        - volatility_regime: 波动率制度 ('HIGH', 'NORMAL', 'LOW')
        
        返回：stop_loss_price
        """
        
        # 根据波动率选择止损倍数
        if volatility_regime == 'HIGH':
            sl_multiplier = 2.0   # 高波动：止损更宽，不容易被假突破骗
        elif volatility_regime == 'LOW':
            sl_multiplier = 1.0   # 低波动：止损可以紧一些，网格范围本来就小
        else:  # NORMAL
            sl_multiplier = 1.5   # 正常波动：标准配置，最赚钱的环境
        
        # 计算止损距离
        sl_distance = atr * sl_multiplier
        
        # 根据方向计算止损价格
        if signal == 1:  # 买入
            stop_loss = entry_price - sl_distance
        else:  # 卖出（做空）
            stop_loss = entry_price + sl_distance
        
        return stop_loss, sl_multiplier
    
    # ========== 2. 止盈计算 ==========
    
    def calculate_take_profit(self, entry_price, grid_width=None, atr=None, signal=1):
        """
        计算止盈价格
        
        优先使用网格宽度（如果有），否则用ATR
        网格交易的止盈 = 网格宽度 × 2.5
        
        参数：
        - entry_price: 入场价格
        - grid_width: 网格宽度（优先）
        - atr: ATR值（备用）
        - signal: 1=买入, -1=卖出
        
        返回：(take_profit_price, tp_distance)
        """
        
        if grid_width is not None and grid_width > 0:
            # 使用网格宽度计算止盈
            tp_distance = grid_width * 2.5
            tp_reason = f"网格宽度{grid_width:.2f}点 × 2.5"
        else:
            # 使用ATR作为备用
            tp_distance = atr * 3.0 if atr else 50
            tp_reason = f"ATR{atr:.2f}点 × 3.0"
        
        # 计算止盈价格
        if signal == 1:  # 买入
            take_profit = entry_price + tp_distance
        else:  # 卖出
            take_profit = entry_price - tp_distance
        
        return take_profit, tp_distance, tp_reason
    
    # ========== 3. 分批止盈逻辑 ==========
    
    def check_partial_take_profit(self, position, current_price):
        """
        检查是否应该分批止盈
        逻辑：到达目标的80%时平仓50%，到达100%时全部平仓
        
        参数：
        - position: 头寸对象
        - current_price: 当前价格
        
        返回：(should_close_ratio, close_reason)
        should_close_ratio: 0(不平), 0.5(平50%), 1.0(全部平)
        """
        
        entry = position['entry_price']
        tp = position['take_profit']
        signal = position['direction']
        
        # 计算当前利润%
        if signal == 1:  # 买入头寸
            current_profit = current_price - entry
            target_profit = tp - entry
        else:  # 卖出头寸
            current_profit = entry - current_price
            target_profit = entry - tp
        
        if target_profit == 0:
            return 0, None
        
        profit_ratio = current_profit / target_profit  # 达到目标的百分比
        
        # 分批平仓逻辑
        if profit_ratio >= 1.0:  # 达到100%目标
            close_ratio = 1.0
            reason = f"完全止盈：达到目标利润 (当前{profit_ratio*100:.1f}%)"
        
        elif profit_ratio >= 0.8:  # 达到80%目标
            # 第一次到80%时平50%，记录状态避免重复平仓
            if not position.get('partial_tp_triggered', False):
                close_ratio = 0.5
                position['partial_tp_triggered'] = True
                reason = f"部分止盈：达到目标的80% ({profit_ratio*100:.1f}%，平仓50%)"
            else:
                close_ratio = 0
                reason = None
        
        else:
            close_ratio = 0
            reason = None
        
        return close_ratio, reason
    
    # ========== 4. 动态止损（移动止损） ==========
    
    def update_trailing_stop(self, position, current_price, atr, signal, 
                           min_profit_to_trigger=1.5):
        """
        更新动态止损（追踪止损）
        
        核心逻辑：
        - 当利润达到min_profit_to_trigger倍ATR时，移至盈亏平衡点
        - 之后继续跟踪价格上升
        - 但止损只能往有利方向移动，不能往回移
        
        参数：
        - position: 头寸对象
        - current_price: 当前价格
        - atr: ATR值
        - signal: 方向
        - min_profit_to_trigger: 触发移动止损的利润倍数
        
        返回：(new_stop_loss, was_updated, reason)
        """
        
        entry = position['entry_price']
        current_sl = position['stop_loss']
        
        if signal == 1:  # 买入头寸
            current_profit = current_price - entry
            trigger_distance = atr * min_profit_to_trigger
            
            # 利润足够时，尝试移至保本
            if current_profit >= trigger_distance:
                # 新止损 = 入场价（保本）
                new_sl = entry
                
                # 只有当新止损更优时才更新（比当前止损更高）
                if new_sl > current_sl:
                    position['stop_loss'] = new_sl
                    was_updated = True
                    reason = f"移动至保本: {new_sl:.2f}"
                else:
                    was_updated = False
                    reason = None
            else:
                was_updated = False
                reason = None
        
        else:  # 卖出头寸
            current_profit = entry - current_price
            trigger_distance = atr * min_profit_to_trigger
            
            if current_profit >= trigger_distance:
                new_sl = entry  # 保本价格
                
                # 只有当新止损更优时才更新（比当前止损更低）
                if new_sl < current_sl:
                    position['stop_loss'] = new_sl
                    was_updated = True
                    reason = f"移动至保本: {new_sl:.2f}"
                else:
                    was_updated = False
                    reason = None
            else:
                was_updated = False
                reason = None
        
        return position['stop_loss'], was_updated, reason
    
    # ========== 5. 网格层级止损协调 ==========
    
    def calculate_grid_level_stops(self, entry_price, grid_info, grid_level, signal, atr):
        """
        计算网格特定层级的止损止盈
        
        原理：网格层级越深（离底部越近），止损越宽，止盈越远
        这样形成金字塔加仓的最优风险管理
        
        参数：
        - entry_price: 入场价格
        - grid_info: 网格信息
        - grid_level: 当前网格层级 (0=最底层, 最深)
        - signal: 方向
        - atr: ATR值
        
        返回：{
            'stop_loss': 止损价格,
            'take_profit': 止盈价格,
            'risk_reward_ratio': 风险收益比,
            'expected_return': 期望收益,
            'lot_multiplier': 手数倍数
        }
        """
        
        grid_width = grid_info['grid_width']
        total_range = grid_info['total_range']
        
        # 根据网格深度调整止损和止盈
        # 网格层级越深，止损越宽
        depth_ratio = grid_level / max(len(grid_info['buy_levels']), 1)
        
        # 止损倍数随深度增加
        sl_multiplier = 1.5 + (depth_ratio * 0.5)  # 从1.5到2.0
        sl_distance = atr * sl_multiplier
        
        # 止盈距离 = 网格宽度 × (2.5 - 深度比)
        # 越深的网格越容易止盈，越浅的网格止盈越远
        tp_distance = grid_width * (2.5 - depth_ratio * 0.5)
        
        # 计算价格
        if signal == 1:  # 买入
            stop_loss = entry_price - sl_distance
            take_profit = entry_price + tp_distance
        else:  # 卖出
            stop_loss = entry_price + sl_distance
            take_profit = entry_price - tp_distance
        
        # 风险收益比
        risk = abs(stop_loss - entry_price)
        reward = abs(take_profit - entry_price)
        risk_reward_ratio = reward / risk if risk > 0 else 0
        
        # 期望收益（假设胜率62%）
        win_rate = 0.62
        expected_return = (win_rate * reward) - ((1 - win_rate) * risk)
        
        # 手数倍数（金字塔加仓）
        lot_multiplier = 1.0 + (depth_ratio * 1.0)  # 从1.0到2.0
        
        return {
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'risk_reward_ratio': risk_reward_ratio,
            'expected_return': expected_return,
            'lot_multiplier': lot_multiplier,
            'sl_distance': sl_distance,
            'tp_distance': tp_distance,
            'depth_ratio': depth_ratio
        }
    
    # ========== 6. 检查止损触发 ==========
    
    def check_stop_triggered(self, position, current_price):
        """
        检查是否触发止损或止盈
        
        返回：('SL', pnl) | ('TP', pnl) | (None, 0)
        """
        
        entry = position['entry_price']
        sl = position['stop_loss']
        tp = position['take_profit']
        signal = position['direction']
        lot_size = position['lot_size']
        
        # 检查止损
        if signal == 1:  # 买入
            if current_price <= sl:
                pnl = (sl - entry) * lot_size * 100
                return 'SL', pnl
            elif current_price >= tp:
                pnl = (tp - entry) * lot_size * 100
                return 'TP', pnl
        
        else:  # 卖出
            if current_price >= sl:
                pnl = (entry - sl) * lot_size * 100
                return 'SL', pnl
            elif current_price <= tp:
                pnl = (entry - tp) * lot_size * 100
                return 'TP', pnl
        
        return None, 0
    
    # ========== 7. 生成交易报告 ==========
    
    def generate_stop_report(self, position):
        """
        生成止损止盈详细报告
        """
        entry = position['entry_price']
        sl = position['stop_loss']
        tp = position['take_profit']
        signal = position['direction']
        
        if signal == 1:  # 买入
            risk = entry - sl
            reward = tp - entry
        else:  # 卖出
            risk = sl - entry
            reward = entry - tp
        
        report = {
            '入场价': entry,
            '止损价': sl,
            '止盈价': tp,
            '风险点数': risk,
            '收益点数': reward,
            '风险收益比': reward / risk if risk > 0 else 0,
            '期望收益': (0.62 * reward - 0.38 * risk),  # 假设胜率62%
            '头寸方向': '多头' if signal == 1 else '空头'
        }
        
        return report


# ========== 使用示例 ==========

if __name__ == "__main__":
    
    manager = ProfessionalStopsManager()
    
    # 示例1：基础止损计算
    print("="*60)
    print("示例1：波动率调整的止损")
    print("="*60)
    
    entry_price = 2025
    atr = 12
    
    for volatility in ['HIGH', 'NORMAL', 'LOW']:
        sl, multiplier = manager.calculate_stop_loss_basic(
            entry_price, atr, signal=1, volatility_regime=volatility
        )
        print(f"{volatility:8} 波动: 止损 = {entry_price} - {atr}×{multiplier} = {sl:.2f}")
    
    # 示例2：止盈计算
    print("\n" + "="*60)
    print("示例2：止盈计算")
    print("="*60)
    
    grid_width = 5  # 网格宽度5点
    tp, tp_dist, reason = manager.calculate_take_profit(
        entry_price=2010, 
        grid_width=grid_width,
        signal=1
    )
    print(f"入场: 2010")
    print(f"止盈: 2010 + {tp_dist:.2f} = {tp:.2f}")
    print(f"原因: {reason}")
    
    # 示例3：网格层级止损
    print("\n" + "="*60)
    print("示例3：网格层级止损协调")
    print("="*60)
    
    grid_info = {
        'grid_width': 5,
        'total_range': 50,
        'buy_levels': [2010, 2015, 2020, 2025]
    }
    
    for level in range(4):
        stops = manager.calculate_grid_level_stops(
            entry_price=2025 - (level * 5),
            grid_info=grid_info,
            grid_level=level,
            signal=1,
            atr=12
        )
        print(f"\n网格{level}: 入场{2025 - (level * 5):.0f}")
        print(f"  止损: {stops['stop_loss']:.2f} | 止盈: {stops['take_profit']:.2f}")
        print(f"  风险收益比: {stops['risk_reward_ratio']:.2f}:1")
        print(f"  期望收益: {stops['expected_return']:.2f}点")
        print(f"  手数倍数: {stops['lot_multiplier']:.2f}x")