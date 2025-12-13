"""
交易策略模块 - 终极版
已加入：震荡市自动休眠 + 四大经典策略投票
"""

class TradingStrategies:
    """交易策略集合"""
    
    @staticmethod
    def trend_following_strategy(df, params):
        """策略1: 趋势跟踪"""
        latest = df.iloc[-1]
        
        if (latest['EMA_20'] > latest['EMA_50'] > latest['EMA_200'] and
            latest['RSI'] < params['rsi_overbought'] and 
            latest['MACD_hist'] > 0):
            return 1
        elif (latest['EMA_20'] < latest['EMA_50'] < latest['EMA_200'] and
              latest['RSI'] > params['rsi_oversold'] and 
              latest['MACD_hist'] < 0):
            return -1
        return 0
    
    @staticmethod
    def mean_reversion_strategy(df, params):
        """策略2: 均值回归"""
        latest = df.iloc[-1]
        bb_position = (latest['close'] - latest['BB_lower']) / (latest['BB_upper'] - latest['BB_lower'])
        
        if latest['RSI'] < params['rsi_oversold'] and bb_position < 0.2:
            return 1
        elif latest['RSI'] > params['rsi_overbought'] and bb_position > 0.8:
            return -1
        return 0
    
    @staticmethod
    def breakout_strategy(df, params):
        """策略3: 突破策略"""
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        atr_mean = df['ATR'].iloc[-20:].mean()
        
        if (latest['close'] > latest['BB_upper'] and 
            prev['close'] <= prev['BB_upper'] and
            latest['ATR'] > atr_mean):
            return 1
        elif (latest['close'] < latest['BB_lower'] and 
              prev['close'] >= prev['BB_lower'] and
              latest['ATR'] > atr_mean):
            return -1
        return 0
    
    @staticmethod
    def momentum_strategy(df, params):
        """策略4: 动量策略"""
        latest = df.iloc[-1]
        
        if (latest['MOM'] > 0 and 
            latest['STOCH_K'] > latest['STOCH_D'] and 
            latest['STOCH_K'] < 80):
            return 1
        elif (latest['MOM'] < 0 and 
              latest['STOCH_K'] < latest['STOCH_D'] and 
              latest['STOCH_K'] > 20):
            return -1
        return 0
    
    @staticmethod
    def generate_combined_signal(df, params):
        """
        终极综合信号生成器（已加入震荡市自动休眠）
        """
        latest = df.iloc[-1]

        # ==================== 震荡市自动休眠神器 ====================
        if params.get('enable_vol_filter', False):
            vol_period = params.get('vol_period', 20)
            vol_threshold = params.get('vol_threshold', 0.7)
            
            # 计算过去N根K线的ATR平均值（用前一根避免未来函数）
            atr_history = df['ATR'].rolling(window=vol_period).mean()
            atr_avg = atr_history.iloc[-2] if len(atr_history) > 1 else latest['ATR']
            
            # 当前波动太小 → 全员睡觉
            if latest['ATR'] < atr_avg * vol_threshold:
                strategy_names = ['趋势跟踪', '均值回归', '突破', '动量']
                signal_details = {name: '休眠(低波动)' for name in strategy_names}
                return 0, signal_details
        # ==========================================================

        # 四大策略正常投票
        signals = [
            TradingStrategies.trend_following_strategy(df, params),
            TradingStrategies.mean_reversion_strategy(df, params),
            TradingStrategies.breakout_strategy(df, params),
            TradingStrategies.momentum_strategy(df, params)
        ]
        
        total_signal = sum(signals)
        
        strategy_names = ['趋势跟踪', '均值回归', '突破', '动量']
        signal_details = {
            name: '买入' if sig == 1 else '卖出' if sig == -1 else '中性'
            for name, sig in zip(strategy_names, signals)
        }
        
        if total_signal >= params['signal_threshold_buy']:
            return 1, signal_details
        elif total_signal <= params['signal_threshold_sell']:
            return -1, signal_details
        else:
            return 0, signal_details