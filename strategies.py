"""
交易策略模块
包含4个独立策略 + 综合信号生成
"""

class TradingStrategies:
    """交易策略集合"""
    
    @staticmethod
    def trend_following_strategy(df, params):
        """
        策略1: 趋势跟踪
        
        买入条件:
        - EMA_20 > EMA_50 > EMA_200 (多头排列)
        - RSI < 70 (未超买)
        - MACD柱 > 0 (多头动量)
        
        卖出条件:
        - EMA_20 < EMA_50 < EMA_200 (空头排列)
        - RSI > 30 (未超卖)
        - MACD柱 < 0 (空头动量)
        """
        latest = df.iloc[-1]
        
        # 多头信号
        if (latest['EMA_20'] > latest['EMA_50'] > latest['EMA_200'] and
            latest['RSI'] < params['rsi_overbought'] and 
            latest['MACD_hist'] > 0):
            return 1
        
        # 空头信号
        elif (latest['EMA_20'] < latest['EMA_50'] < latest['EMA_200'] and
              latest['RSI'] > params['rsi_oversold'] and 
              latest['MACD_hist'] < 0):
            return -1
        
        return 0
    
    @staticmethod
    def mean_reversion_strategy(df, params):
        """
        策略2: 均值回归
        
        买入条件:
        - RSI < 30 (超卖)
        - 价格在布林带下轨附近 (position < 0.2)
        
        卖出条件:
        - RSI > 70 (超买)
        - 价格在布林带上轨附近 (position > 0.8)
        """
        latest = df.iloc[-1]
        
        # 计算布林带位置 (0-1之间)
        bb_position = (latest['close'] - latest['BB_lower']) / (latest['BB_upper'] - latest['BB_lower'])
        
        # 超卖买入
        if latest['RSI'] < params['rsi_oversold'] and bb_position < 0.2:
            return 1
        
        # 超买卖出
        elif latest['RSI'] > params['rsi_overbought'] and bb_position > 0.8:
            return -1
        
        return 0
    
    @staticmethod
    def breakout_strategy(df, params):
        """
        策略3: 突破策略
        
        买入条件:
        - 价格突破布林带上轨
        - ATR > 过去20根均值 (波动率增加)
        
        卖出条件:
        - 价格跌破布林带下轨
        - ATR > 过去20根均值 (波动率增加)
        """
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 计算ATR均值
        atr_mean = df['ATR'].iloc[-20:].mean()
        
        # 向上突破
        if (latest['close'] > latest['BB_upper'] and 
            prev['close'] <= prev['BB_upper'] and
            latest['ATR'] > atr_mean):
            return 1
        
        # 向下突破
        elif (latest['close'] < latest['BB_lower'] and 
              prev['close'] >= prev['BB_lower'] and
              latest['ATR'] > atr_mean):
            return -1
        
        return 0
    
    @staticmethod
    def momentum_strategy(df, params):
        """
        策略4: 动量策略
        
        买入条件:
        - 价格动量 > 0 (上涨)
        - STOCH_K 向上穿越 STOCH_D
        - STOCH_K < 80 (未超买)
        
        卖出条件:
        - 价格动量 < 0 (下跌)
        - STOCH_K 向下穿越 STOCH_D
        - STOCH_K > 20 (未超卖)
        """
        latest = df.iloc[-1]
        
        # 强势动量
        if (latest['MOM'] > 0 and 
            latest['STOCH_K'] > latest['STOCH_D'] and 
            latest['STOCH_K'] < 80):
            return 1
        
        # 弱势动量
        elif (latest['MOM'] < 0 and 
              latest['STOCH_K'] < latest['STOCH_D'] and 
              latest['STOCH_K'] > 20):
            return -1
        
        return 0
    
    @staticmethod
    def generate_combined_signal(df, params):
        """
        综合信号生成器
        
        投票机制:
        - 收集所有4个策略的信号
        - 买入信号: 至少2个策略投票买入
        - 卖出信号: 至少2个策略投票卖出
        - 否则: 无信号
        
        返回: (最终信号, 各策略投票详情)
        """
        signals = []
        
        # 收集所有策略信号
        signal1 = TradingStrategies.trend_following_strategy(df, params)
        signal2 = TradingStrategies.mean_reversion_strategy(df, params)
        signal3 = TradingStrategies.breakout_strategy(df, params)
        signal4 = TradingStrategies.momentum_strategy(df, params)
        
        signals = [signal1, signal2, signal3, signal4]
        
        # 投票机制
        total_signal = sum(signals)
        
        # 策略名称
        strategy_names = ['趋势跟踪', '均值回归', '突破', '动量']
        signal_details = {
            name: '买入' if sig == 1 else '卖出' if sig == -1 else '中性'
            for name, sig in zip(strategy_names, signals)
        }
        
        # 返回最终信号
        if total_signal >= params['signal_threshold_buy']:
            return 1, signal_details  # 买入
        elif total_signal <= params['signal_threshold_sell']:
            return -1, signal_details  # 卖出
        else:
            return 0, signal_details  # 无信号