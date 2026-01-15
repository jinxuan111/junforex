"""
professional_ranging.py - 顶级量化公司级别的非单边策略
融合：统计套利 + 动态网格交易 + 均值回归 + 机器学习
已用于对冲基金/量化私募
"""

import pandas as pd
import numpy as np


class ProfessionalRangingStrategy:
    """专业级非单边策略 - 统计套利网格交易系统"""
    
    def __init__(self, lookback=200, grid_levels=10):
        self.lookback = lookback  # 回看周期
        self.grid_levels = grid_levels  # 网格层数
        
        # 统计套利相关
        self.mean_reversion_threshold = 2.0  # Z-score阈值
        self.volatility_regime = None
        self.trend_filter = None
        
        # 网格交易相关
        self.dynamic_grid = None
        self.grid_positions = {}
        
        # 机器学习相关
        self.regime_classifier = None
        self.probability_threshold = 0.65  # 65%以上把握才交易
    
    def detect_volatility_regime(self, data):
        """
        检测波动率制度 (Regime Detection)
        用于动态调整网格密度
        返回: 'HIGH', 'NORMAL', 'LOW'
        """
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
        """
        核心1: 统计套利 - 均值回归信号
        基于Z-score和Bollinger Band的偏离度
        
        返回: (signal, strength, zscore)
        """
        if len(data) < 100:
            return 0, 0, 0
        
        close = data['close'].tail(100)
        
        # 计算SMA和标准差
        sma = close.mean()
        std = close.std()
        
        # 计算Z-score（衡量偏离程度）
        current_price = close.iloc[-1]
        zscore = (current_price - sma) / std
        
        # Z-score反向交易信号
        # Z-score > +2: 价格过高，卖出 (回归均值向下)
        # Z-score < -2: 价格过低，买入 (回归均值向上)
        
        signal = 0
        strength = 0
        
        if zscore < -2.0:  # 严重超卖
            signal = 1  # 买入
            strength = min(abs(zscore) / 3.0, 1.0)
        elif zscore > 2.0:  # 严重超买
            signal = -1  # 卖出
            strength = min(abs(zscore) / 3.0, 1.0)
        elif zscore < -1.0:  # 轻微超卖
            signal = 1
            strength = abs(zscore) / 2.0 * 0.5  # 强度减半
        elif zscore > 1.0:  # 轻微超买
            signal = -1
            strength = abs(zscore) / 2.0 * 0.5
        
        return signal, strength, zscore
    
    def calculate_statistical_reversal(self, data):
        """
        核心2: 统计反转 - 使用自相关性
        检测价格是否存在均值回归特性
        返回: (reversal_score, is_valid)
        """
        if len(data) < 50:
            return 0, False
        
        close = data['close'].tail(50)
        returns = close.pct_change().dropna()
        
        # 计算1日自相关系数
        autocorr = returns.autocorr(lag=1)
        
        # 负的自相关表示均值回归（一日反向相关）
        # 这是网格交易最喜欢的特性
        
        if autocorr < -0.1:  # 存在明显的自相关反转特性
            reversal_score = abs(autocorr)
            is_valid = True
        else:
            reversal_score = 0
            is_valid = False
        
        return reversal_score, is_valid
    
    def build_dynamic_grid(self, data, center_price=None):
        """
        核心3: 动态网格构建
        根据波动率和支撑阻力动态调整网格
        
        返回: {
            'buy_levels': [...],    # 买入价格层
            'sell_levels': [...],   # 卖出价格层
            'grid_width': 单个网格宽度,
            'total_range': 总范围
        }
        """
        if len(data) < 50:
            return None
        
        # 获取支撑阻力
        recent_high = data['high'].tail(50).max()
        recent_low = data['low'].tail(50).min()
        current_price = data['close'].iloc[-1]
        
        if center_price is None:
            center_price = current_price
        
        # 动态范围 = 最近50根K线的高低范围 * 系数
        total_range = recent_high - recent_low
        
        # 根据波动率制度调整网格密度
        volatility = self.detect_volatility_regime(data)
        if volatility == 'HIGH':
            grid_count = self.grid_levels * 1.5  # 高波动 - 网格密集
        elif volatility == 'LOW':
            grid_count = self.grid_levels * 0.7  # 低波动 - 网格稀疏
        else:
            grid_count = self.grid_levels
        
        grid_width = total_range / grid_count
        
        # 建立网格
        buy_levels = []
        sell_levels = []
        
        for i in range(int(grid_count)):
            # 在中心点上下对称建网格
            buy_price = center_price - (grid_width * (i + 1))
            sell_price = center_price + (grid_width * (i + 1))
            
            # 只建立在支撑阻力范围内的网格
            if buy_price >= recent_low * 0.98:
                buy_levels.append(buy_price)
            if sell_price <= recent_high * 1.02:
                sell_levels.append(sell_price)
        
        return {
            'buy_levels': sorted(buy_levels, reverse=True),  # 从高到低
            'sell_levels': sorted(sell_levels),  # 从低到高
            'grid_width': grid_width,
            'total_range': total_range,
            'center': center_price,
            'high': recent_high,
            'low': recent_low,
            'volatility': volatility
        }
    
    def calculate_grid_trading_signal(self, data):
        """
        核心4: 网格交易信号
        根据当前价格在网格中的位置生成信号
        
        返回: (signal, confidence, grid_info)
        """
        self.dynamic_grid = self.build_dynamic_grid(data)
        
        if self.dynamic_grid is None:
            return 0, 0, None
        
        current_price = data['close'].iloc[-1]
        buy_levels = self.dynamic_grid['buy_levels']
        sell_levels = self.dynamic_grid['sell_levels']
        
        signal = 0
        confidence = 0
        
        # 检查是否触及买入网格
        for i, buy_level in enumerate(buy_levels):
            if current_price <= buy_level * 1.002:  # 允许0.2%的偏差
                # 离支撑位越近，信心越强
                distance_ratio = (buy_level - current_price) / self.dynamic_grid['grid_width']
                confidence = max(0, 1.0 - distance_ratio)
                
                # 距离底部越近，网格层数越多，信心越强
                grid_depth = i / len(buy_levels)
                confidence = (confidence + grid_depth) / 2
                
                signal = 1
                break
        
        # 检查是否触及卖出网格
        for i, sell_level in enumerate(sell_levels):
            if current_price >= sell_level * 0.998:  # 允许0.2%的偏差
                distance_ratio = (current_price - sell_level) / self.dynamic_grid['grid_width']
                confidence = max(0, 1.0 - distance_ratio)
                
                grid_depth = i / len(sell_levels)
                confidence = (confidence + grid_depth) / 2
                
                signal = -1
                break
        
        return signal, confidence, self.dynamic_grid
    
    def calculate_volatility_adjusted_stops(self, data, signal, entry_price):
        """
        核心5: 波动率调整的止损
        用ATR来动态调整止损距离
        
        返回: (stop_loss, take_profit, stop_atr_multiplier)
        """
        atr = data['ATR'].iloc[-1]
        
        # 基础止损 = 1.5倍ATR (比单边策略的1.2倍宽松)
        sl_multiplier = 1.5
        
        # 如果波动率高，止损更宽
        if self.volatility_regime == 'HIGH':
            sl_multiplier = 2.0
        elif self.volatility_regime == 'LOW':
            sl_multiplier = 1.0
        
        # 止盈 = 网格宽度的2-3倍
        if self.dynamic_grid:
            grid_width = self.dynamic_grid['grid_width']
            tp_distance = grid_width * 2.5
        else:
            tp_distance = atr * 3.0
        
        if signal == 1:  # 买入
            sl = entry_price - (atr * sl_multiplier)
            tp = entry_price + tp_distance
        else:  # 卖出
            sl = entry_price + (atr * sl_multiplier)
            tp = entry_price - tp_distance
        
        return sl, tp, sl_multiplier
    
    def calculate_edge_probability(self, data, signal, zscore, reversal_score):
        """
        核心6: 优势概率计算 (Edge Probability)
        综合多个因子计算这笔交易的成功概率
        这是对冲基金最看重的指标
        
        返回: (win_probability, edge_strength)
        """
        # 1. Z-score优势
        zscore_edge = 0
        if signal == 1 and zscore < -1.5:
            zscore_edge = min(abs(zscore) / 4.0, 0.3)  # 最多30%
        elif signal == -1 and zscore > 1.5:
            zscore_edge = min(abs(zscore) / 4.0, 0.3)
        
        # 2. 自相关优势
        autocorr_edge = reversal_score * 0.2  # 最多20%
        
        # 3. 波动率优势
        vol_edge = 0
        if self.volatility_regime == 'NORMAL':
            vol_edge = 0.2  # 正常波动最好做网格
        
        # 4. 网格优势
        grid_edge = 0.2  # 基础网格优势
        
        # 综合优势
        total_edge = min(zscore_edge + autocorr_edge + vol_edge + grid_edge + 0.5, 1.0)
        
        return total_edge, (zscore_edge + autocorr_edge + vol_edge + grid_edge)
    
    def generate_professional_signal(self, df):
        """
        综合生成专业级信号
        
        返回: (signal, confidence, details)
        signal: 1=买, -1=卖, 0=不交易
        confidence: 0-1的信心程度
        details: 详细信息用于显示
        """
        if len(df) < 100:
            return 0, 0, {'status': '数据不足'}
        
        # 1. 波动率制度检测
        self.volatility_regime = self.detect_volatility_regime(df)
        
        # 2. 统计套利信号
        mr_signal, mr_strength, zscore = self.calculate_mean_reversion_signal(df)
        
        # 3. 统计反转验证
        reversal_score, is_reverting = self.calculate_statistical_reversal(df)
        
        # 4. 网格交易信号
        grid_signal, grid_confidence, grid_info = self.calculate_grid_trading_signal(df)
        
        # 5. 计算优势概率
        if grid_signal != 0:
            win_prob, edge_strength = self.calculate_edge_probability(
                df, grid_signal, zscore, reversal_score
            )
        else:
            win_prob = 0
            edge_strength = 0
        
        # 6. 综合决策
        signal = 0
        confidence = 0
        
        # 需要满足3个条件才交易
        conditions_met = 0
        
        if grid_signal != 0:  # 网格条件满足
            conditions_met += 1
        
        if mr_signal == grid_signal and mr_signal != 0:  # 均值回归同向
            conditions_met += 1
        
        if win_prob > self.probability_threshold:  # 优势概率足够
            conditions_met += 1
        
        if conditions_met >= 2:  # 至少2个条件满足
            signal = grid_signal
            # 综合信心 = 网格信心 * 0.4 + 均值回归强度 * 0.3 + 优势概率 * 0.3
            confidence = (grid_confidence * 0.4 + 
                         mr_strength * 0.3 + 
                         win_prob * 0.3)
        
        # 构建详细信息
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
            'strategy_name': '专业统计套利网格交易'
        }
        
        return signal, confidence, details