"""
professional_ranging.py - 顶级量化公司级别的非单边策略
融合：统计套利 + 动态网格交易 + 均值回归 + 机器学习
黄金平衡优化版本 - 恢复保守条件：conditions_met >= 2
"""

import pandas as pd
import numpy as np

class ProfessionalRangingStrategy:
    """专业级非单边策略 - 统计套利网格交易系统（黄金平衡版）"""
    
    def __init__(self, lookback=150, grid_levels=10):
        self.lookback = lookback
        self.grid_levels = grid_levels
        self.mean_reversion_threshold = 2.2
        self.volatility_regime = None
        self.trend_filter = None
        self.dynamic_grid = None
        self.grid_positions = {}
        self.regime_classifier = None
        self.probability_threshold = 0.65  # 恢复原值65%
        self.gold_key_levels = [1900, 1950, 2000, 2050, 2100]
        self.last_trade_time = None
        self.min_trade_interval = pd.Timedelta(minutes=20)  # 恢复原冷却20分钟
        self.consecutive_skip = 0
        self.max_consecutive_skip = 5
        
    # 以下方法保持原样
    def detect_volatility_regime(self, data):
        if len(data) < 60:
            return 'NORMAL'
        recent_atr = data['ATR'].tail(20).mean()
        historical_atr = data['ATR'].tail(self.lookback).mean()
        atr_ratio = recent_atr / historical_atr
        if atr_ratio > 1.3:
            return 'HIGH'
        elif atr_ratio < 0.7:
            return 'LOW'
        else:
            return 'NORMAL'
    
    def calculate_mean_reversion_signal(self, data):
        if len(data) < 80:
            return 0, 0, 0
        close = data['close'].tail(80)
        sma = close.mean()
        std = close.std()
        current_price = close.iloc[-1]
        zscore = (current_price - sma) / std
        signal = 0
        strength = 0
        if zscore < -2.0:
            signal = 1
            strength = min(abs(zscore) / 3.5, 1.0)
        elif zscore > 2.0:
            signal = -1
            strength = min(abs(zscore) / 3.5, 1.0)
        elif zscore < -1.5:
            signal = 1
            strength = min(abs(zscore) / 3.0, 0.7) * 0.5
        elif zscore > 1.5:
            signal = -1
            strength = min(abs(zscore) / 3.0, 0.7) * 0.5
        return signal, strength, zscore
    
    def calculate_statistical_reversal(self, data):
        if len(data) < 40:
            return 0, False
        close = data['close'].tail(40)
        returns = close.pct_change().dropna()
        autocorr = returns.autocorr(lag=1)
        if autocorr < -0.12:
            reversal_score = abs(autocorr)
            is_valid = True
        else:
            reversal_score = 0
            is_valid = False
        return reversal_score, is_valid
    
    def is_near_key_level(self, price):
        for level in self.gold_key_levels:
            if abs(price - level) < 5.0:
                return True, level
        return False, None
    
    def build_dynamic_grid(self, data, center_price=None):
        if len(data) < 40:
            return None
        recent_high = data['high'].tail(40).max()
        recent_low = data['low'].tail(40).min()
        current_price = data['close'].iloc[-1]
        near_key_level, key_level = self.is_near_key_level(current_price)
        if near_key_level:
            print(f"ℹ️  价格在关键位 {key_level} 附近，调整网格布局")
        if center_price is None:
            center_price = current_price
        price_range = recent_high - recent_low
        atr = data['ATR'].iloc[-1] if 'ATR' in data else 10
        total_range = max(price_range * 0.8, atr * 6)
        min_range = atr * 4
        total_range = max(total_range, min_range)
        volatility = self.detect_volatility_regime(data)
        if volatility == 'HIGH':
            grid_count = int(self.grid_levels * 0.9)
        elif volatility == 'LOW':
            grid_count = int(self.grid_levels * 0.8)
        else:
            grid_count = self.grid_levels
        grid_count = max(6, min(grid_count, 12))
        grid_width = total_range / grid_count
        min_grid_width = atr * 0.4
        max_grid_width = atr * 1.5
        if grid_width < min_grid_width:
            grid_width = min_grid_width
            grid_count = int(total_range / grid_width)
        elif grid_width > max_grid_width:
            grid_width = max_grid_width
            grid_count = int(total_range / grid_width)
        buy_levels = []
        sell_levels = []
        for i in range(grid_count):
            buy_price = center_price - (grid_width * (i + 1))
            sell_price = center_price + (grid_width * (i + 1))
            near_buy_key, buy_key_level = self.is_near_key_level(buy_price)
            near_sell_key, sell_key_level = self.is_near_key_level(sell_price)
            if near_buy_key:
                buy_price = buy_key_level - (grid_width * 0.3)
            if near_sell_key:
                sell_price = sell_key_level + (grid_width * 0.3)
            if buy_price >= recent_low * 0.97:
                buy_levels.append(buy_price)
            if sell_price <= recent_high * 1.03:
                sell_levels.append(sell_price)
        min_layers = 4
        if len(buy_levels) < min_layers or len(sell_levels) < min_layers:
            print(f"⚠️  网格太少（买:{len(buy_levels)}层, 卖:{len(sell_levels)}层），不交易")
            return None
        return {
            'buy_levels': sorted(buy_levels, reverse=True),
            'sell_levels': sorted(sell_levels),
            'grid_width': grid_width,
            'total_range': total_range,
            'center': center_price,
            'high': recent_high,
            'low': recent_low,
            'volatility': volatility,
            'atr': atr
        }
    
    def calculate_grid_trading_signal(self, data):
        self.dynamic_grid = self.build_dynamic_grid(data)
        if self.dynamic_grid is None:
            self.consecutive_skip += 1
            return 0, 0, None
        current_price = data['close'].iloc[-1]
        buy_levels = self.dynamic_grid['buy_levels']
        sell_levels = self.dynamic_grid['sell_levels']
        signal = 0
        confidence = 0
        for i, buy_level in enumerate(buy_levels):
            if current_price <= buy_level * 1.004:
                distance_ratio = (buy_level - current_price) / self.dynamic_grid['grid_width']
                confidence = max(0, 1.0 - distance_ratio)
                grid_depth = i / len(buy_levels)
                confidence = (confidence * 0.6 + grid_depth * 0.4)
                if self.consecutive_skip >= self.max_consecutive_skip:
                    min_confidence = 0.45
                else:
                    min_confidence = 0.55
                if confidence >= min_confidence:
                    signal = 1
                    self.consecutive_skip = 0
                break
        for i, sell_level in enumerate(sell_levels):
            if current_price >= sell_level * 0.996:
                distance_ratio = (current_price - sell_level) / self.dynamic_grid['grid_width']
                confidence = max(0, 1.0 - distance_ratio)
                grid_depth = i / len(sell_levels)
                confidence = (confidence * 0.6 + grid_depth * 0.4)
                if self.consecutive_skip >= self.max_consecutive_skip:
                    min_confidence = 0.45
                else:
                    min_confidence = 0.55
                if confidence >= min_confidence:
                    signal = -1
                    self.consecutive_skip = 0
                break
        if signal == 0:
            self.consecutive_skip += 1
        return signal, confidence, self.dynamic_grid
    
    def calculate_volatility_adjusted_stops(self, data, signal, entry_price):
        atr = data['ATR'].iloc[-1]
        sl_multiplier = 1.8
        if self.volatility_regime == 'HIGH':
            sl_multiplier = 2.2
        elif self.volatility_regime == 'LOW':
            sl_multiplier = 1.5
        if self.dynamic_grid:
            grid_width = self.dynamic_grid['grid_width']
            tp_distance = grid_width * 2.8
        else:
            tp_distance = atr * 3.2
        if signal == 1:
            sl = entry_price - (atr * sl_multiplier)
            tp = entry_price + tp_distance
        else:
            sl = entry_price + (atr * sl_multiplier)
            tp = entry_price - tp_distance
        return sl, tp, sl_multiplier
    
    def calculate_edge_probability(self, data, signal, zscore, reversal_score):
        zscore_edge = 0
        if signal == 1 and zscore < -1.8:
            zscore_edge = min(abs(zscore) / 4.0, 0.35)
        elif signal == -1 and zscore > 1.8:
            zscore_edge = min(abs(zscore) / 4.0, 0.35)
        autocorr_edge = reversal_score * 0.25
        vol_edge = 0
        if self.volatility_regime == 'NORMAL':
            vol_edge = 0.25
        elif self.volatility_regime == 'LOW':
            vol_edge = 0.15
        grid_edge = 0.25
        skip_bonus = min(self.consecutive_skip * 0.05, 0.15)
        total_edge = min(zscore_edge + autocorr_edge + vol_edge + grid_edge + skip_bonus + 0.35, 1.0)
        return total_edge, (zscore_edge + autocorr_edge + vol_edge + grid_edge)
    
    def check_trade_cooldown(self):
        if self.last_trade_time is None:
            return True
        current_time = pd.Timestamp.now()
        time_diff = current_time - self.last_trade_time
        if time_diff < self.min_trade_interval:
            return False
        return True
    
    def generate_professional_signal(self, df):
        if len(df) < 80:
            return 0, 0, {'status': '数据不足'}
        if not self.check_trade_cooldown():
            return 0, 0, {'status': '冷却时间中'}
        self.volatility_regime = self.detect_volatility_regime(df)
        mr_signal, mr_strength, zscore = self.calculate_mean_reversion_signal(df)
        reversal_score, is_reverting = self.calculate_statistical_reversal(df)
        grid_signal, grid_confidence, grid_info = self.calculate_grid_trading_signal(df)
        if grid_signal != 0:
            win_prob, edge_strength = self.calculate_edge_probability(df, grid_signal, zscore, reversal_score)
        else:
            win_prob = 0
            edge_strength = 0
        
        # 计算满足的条件数（恢复原5个条件）
        conditions_met = 0
        conditions = []
        if grid_signal != 0 and grid_confidence > 0.5:
            conditions_met += 1
            conditions.append(f"网格({grid_signal},信{grid_confidence:.2f})")
        if mr_signal == grid_signal and mr_signal != 0 and mr_strength > 0.25:
            conditions_met += 1
            conditions.append(f"均值回归({mr_signal},强{mr_strength:.2f})")
        if win_prob > self.probability_threshold:
            conditions_met += 1
            conditions.append(f"胜率{win_prob:.2f}>阈值{self.probability_threshold}")
        if is_reverting and reversal_score > 0.15:
            conditions_met += 1
            conditions.append(f"反转{reversal_score:.2f}")
        current_hour = pd.Timestamp.now().hour
        if not (13 <= current_hour <= 19):  # 恢复原极端时段过滤
            conditions_met += 1
            conditions.append("非极端波动时段")
        
        signal = 0
        confidence = 0
        
        # 修改位置：恢复为 >=2
        if conditions_met >= 2:  # 已改回 >=2（更保守，不易频繁开单）
            if self.consecutive_skip >= 3 and conditions_met >= 1:
                signal = grid_signal
                confidence = max(grid_confidence, 0.5)
            elif conditions_met >= 2:
                signal = grid_signal
                confidence = (grid_confidence * 0.4 + mr_strength * 0.3 + win_prob * 0.3)
            
            if signal != 0:
                self.last_trade_time = pd.Timestamp.now()
                print(f"✅ 生成信号: {signal}, 条件满足: {conditions_met}/5")
        
        details = {
            'signal': signal,
            'confidence': confidence,
            'volatility_regime': self.volatility_regime,
            'zscore': zscore,
            'mr_signal': mr_signal,
            'mr_strength': mr_strength,
            'reversal_score': reversal_score,
            'is_reverting': is_reverting,
            'grid_signal': grid_signal,
            'grid_confidence': grid_confidence,
            'grid_info': grid_info,
            'win_probability': win_prob,
            'edge_strength': edge_strength,
            'conditions_met': conditions_met,
            'total_conditions': 5,
            'conditions': conditions,
            'consecutive_skip': self.consecutive_skip,
            'strategy_name': '黄金平衡网格交易'
        }
        
        return signal, confidence, details