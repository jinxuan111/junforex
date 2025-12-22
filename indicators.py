"""
技术指标计算模块 - 顶级量化升级版
支持更快EMA + 所有策略所需指标
"""

import pandas as pd
import numpy as np

class TechnicalIndicators:
    """技术指标计算类"""
    
    @staticmethod
    def calculate_ema(data, period):
        """计算指数移动平均线"""
        return data.ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def calculate_sma(data, period):
        """计算简单移动平均线"""
        return data.rolling(window=period).mean()
    
    @staticmethod
    def calculate_rsi(data, period=14):
        """计算RSI"""
        delta = data.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    @staticmethod
    def calculate_macd(data, fast=12, slow=26, signal=9):
        """计算MACD"""
        exp1 = data.ewm(span=fast, adjust=False).mean()
        exp2 = data.ewm(span=slow, adjust=False).mean()
        macd = exp1 - exp2
        macd_signal = macd.ewm(span=signal, adjust=False).mean()
        macd_hist = macd - macd_signal
        return macd, macd_signal, macd_hist
    
    @staticmethod
    def calculate_bollinger_bands(data, period=20, std=2):
        """计算布林带"""
        middle = data.rolling(window=period).mean()
        std_dev = data.rolling(window=period).std()
        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)
        return upper, middle, lower
    
    @staticmethod
    def calculate_atr(high, low, close, period=14):
        """计算ATR"""
        tr = np.maximum(
            high - low,
            np.maximum(
                abs(high - close.shift()),
                abs(low - close.shift())
            )
        )
        atr = tr.rolling(window=period).mean()
        return atr
    
    @staticmethod
    def calculate_momentum(data, period=10):
        """计算价格动量"""
        return data.diff(period)
    
    @staticmethod
    def calculate_stochastic(high, low, close, k_period=14, d_period=3):
        """计算随机指标(KD)"""
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()
        k = 100 * (close - lowest_low) / (highest_high - lowest_low)
        d = k.rolling(window=d_period).mean()
        return k, d
    
    @staticmethod
    def calculate_all_indicators(df, params):
        """
        一次性计算所有指标（升级版支持更快EMA）
        """
        close = df['close']
        high = df['high']
        low = df['low']
        
        # 趋势指标 - 升级为更快EM8/21/100
        df['EMA_8'] = TechnicalIndicators.calculate_ema(close, params['ema_short'])   # 8
        df['EMA_21'] = TechnicalIndicators.calculate_ema(close, params['ema_medium']) # 21
        df['EMA_100'] = TechnicalIndicators.calculate_ema(close, params['ema_long'])  # 100
        
        # RSI
        df['RSI'] = TechnicalIndicators.calculate_rsi(close, params['rsi_period'])
        
        # MACD
        df['MACD'], df['MACD_signal'], df['MACD_hist'] = TechnicalIndicators.calculate_macd(
            close, params['macd_fast'], params['macd_slow'], params['macd_signal']
        )
        
        # 布林带
        df['BB_upper'], df['BB_middle'], df['BB_lower'] = TechnicalIndicators.calculate_bollinger_bands(
            close, params['bb_period'], params['bb_std']
        )
        
        # ATR
        df['ATR'] = TechnicalIndicators.calculate_atr(high, low, close, params['atr_period'])
        
        # 动量
        df['MOM'] = TechnicalIndicators.calculate_momentum(close, 10)
        
        # 随机指标
        df['STOCH_K'], df['STOCH_D'] = TechnicalIndicators.calculate_stochastic(high, low, close)
        
        return df