"""
adx_analyzer.py - ADX计算和市场类型判断（修复优化版）
修复内容：
1. 切换到标准Wilder's平滑方法（ewm alpha=1/period），取代rolling.mean()，避免大量NaN
2. 正确处理DX分母为0的情况（避免NaN/inf）
3. 所有指标列添加后自动fillna(0)，确保最新值永远有数值（不会因为数据不足显示NaN）
4. 加强数据不足判断（至少需要30根K线才有可靠ADX）
5. 优化identify_market_type的方向判断（容差3点，避免弱方向误判）
6. 打印报告更醒目，第一行直接显示当前推荐策略（网格还是趋势）
7. 小幅优化性能和数值稳定性
专为XAUUSD黄金交易优化，整合到自适应策略系统中
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class ADXAnalyzer:
    """ADX计算和行情类型判断（标准Wilder平滑版）"""
    
    def __init__(self, period=14, adx_threshold=20):
        self.period = period
        self.adx_threshold = adx_threshold
        self.alpha = 1.0 / period  # Wilder平滑系数
        
    def calculate_adx(self, high, low, close):
        """
        计算ADX指标（标准Wilder平滑实现）
        返回: (adx, +DI, -DI) 均为Series，已fillna(0)
        """
        # 确保是Series
        high = pd.Series(high) if not isinstance(high, pd.Series) else high
        low = pd.Series(low) if not isinstance(low, pd.Series) else low
        close = pd.Series(close) if not isinstance(close, pd.Series) else close
        
        # 1. 真实波幅 TR
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # 2. +DM 和 -DM
        up_move = high.diff()
        down_move = -low.diff()
        
        pos_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        neg_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        pos_dm = pd.Series(pos_dm, index=high.index)
        neg_dm = pd.Series(neg_dm, index=high.index)
        
        # 3. Wilder平滑（等价于EMA adjust=False）
        atr = tr.ewm(alpha=self.alpha, adjust=False).mean()
        pos_dm_smooth = pos_dm.ewm(alpha=self.alpha, adjust=False).mean()
        neg_dm_smooth = neg_dm.ewm(alpha=self.alpha, adjust=False).mean()
        
        # 4. +DI 和 -DI
        pos_di = 100 * pos_dm_smooth / atr
        neg_di = 100 * neg_dm_smooth / atr
        
        # 5. DX（处理分母为0）
        di_sum = pos_di + neg_di
        dx = np.where(di_sum == 0, 0, 100 * abs(pos_di - neg_di) / di_sum)
        dx = pd.Series(dx, index=high.index)
        
        # 6. ADX（DX的Wilder平滑）
        adx = dx.ewm(alpha=self.alpha, adjust=False).mean()
        
        # 填充初始NaN为0（确保最新值永远可用）
        adx = adx.fillna(0)
        pos_di = pos_di.fillna(0)
        neg_di = neg_di.fillna(0)
        
        return adx, pos_di, neg_di
    
    def identify_market_type(self, adx_value, pos_di, neg_di):
        """判断市场类型和方向（优化容差）"""
        adx_value = float(adx_value)
        pos_di = float(pos_di)
        neg_di = float(neg_di)
        di_diff = pos_di - neg_di
        
        # 市场类型
        if adx_value < self.adx_threshold:
            market_type = 'RANGING'
            market_desc = '盘整/双边市'
            strength = '弱'
        else:
            market_type = 'TRENDING'
            if adx_value >= 40:
                market_desc = '强单边市'
                strength = '强'
            else:
                market_desc = '趋势开始'
                strength = '中'
        
        # 方向判断（容差3点，避免小幅震荡误判中性）
        if di_diff > 3:
            direction = '看涨'
            direction_code = 'BULLISH'
        elif di_diff < -3:
            direction = '看跌'
            direction_code = 'BEARISH'
        else:
            direction = '中性'
            direction_code = 'NEUTRAL'
        
        return market_type, market_desc, strength, direction, direction_code, di_diff
    
    def get_trading_suggestion(self, adx_value, market_desc, direction):
        """交易建议"""
        if '盘整' in market_desc or '双边' in market_desc:
            return "市场盘整，建议使用双边网格策略（震荡市）"
        elif '趋势开始' in market_desc:
            return f"趋势初现，{direction}方向可轻仓尝试，严格止损"
        elif '强单边' in market_desc:
            return f"强{direction}趋势，建议跟随趋势并使用移动止损保护利润"
        else:
            return "市场状态不明，建议观望"

class MarketAnalysis:
    """市场分析主类（优化版）"""
    
    def __init__(self, df, adx_threshold=20):
        self.df = df.copy() if df is not None else None
        self.analyzer = ADXAnalyzer(period=14, adx_threshold=adx_threshold)
        self.adx_threshold = adx_threshold
    
    def analyze(self):
        """执行分析并添加指标"""
        if self.df is None or len(self.df) < 30:  # 至少30根才可靠
            print(f"⚠️  数据不足（当前{len(self.df) if self.df is not None else 0}根K线），ADX暂不可用，将默认使用RANGING模式")
            if self.df is not None:
                self.df['ADX'] = 0.0
                self.df['+DI'] = 0.0
                self.df['-DI'] = 0.0
            return self.df
        
        adx, pos_di, neg_di = self.analyzer.calculate_adx(
            self.df['high'], self.df['low'], self.df['close']
        )
        
        self.df['ADX'] = adx
        self.df['+DI'] = pos_di
        self.df['-DI'] = neg_di
        
        return self.df
    
    def get_current_market_info(self):
        """获取当前市场信息（安全取值）"""
        if self.df is None or len(self.df) == 0 or 'ADX' not in self.df.columns:
            return {
                'adx': 0.0,
                '+DI': 0.0,
                '-DI': 0.0,
                'di_diff': 0.0,
                'market_type': 'RANGING',
                'market_desc': '数据不足，默认盘整',
                'strength': '弱',
                'direction': '中性',
                'direction_signal': 0,
                'is_ranging': True,
                'is_trending': False,
                'price': 0.0,
                'suggestion': '数据不足，默认使用双边网格策略'
            }
        
        latest = self.df.iloc[-1]
        
        adx_val = float(latest.get('ADX', 0.0))
        pos_di = float(latest.get('+DI', 0.0))
        neg_di = float(latest.get('-DI', 0.0))
        
        market_type, market_desc, strength, direction, direction_code, di_diff = self.analyzer.identify_market_type(
            adx_val, pos_di, neg_di
        )
        
        direction_signal = 1 if direction_code == 'BULLISH' else -1 if direction_code == 'BEARISH' else 0
        
        return {
            'adx': adx_val,
            '+DI': pos_di,
            '-DI': neg_di,
            'di_diff': di_diff,
            'market_type': market_type,
            'market_desc': market_desc,
            'strength': strength,
            'direction': direction,
            'direction_signal': direction_signal,
            'is_ranging': market_type == 'RANGING',
            'is_trending': market_type == 'TRENDING',
            'price': float(latest['close']) if 'close' in latest else 0.0,
            'suggestion': self.analyzer.get_trading_suggestion(adx_val, market_desc, direction)
        }
    
    def print_market_report(self):
        """打印醒目市场报告（第一行直接显示当前策略）"""
        info = self.get_current_market_info()
        
        print("\n" + "="*70)
        print("🤖 ADX自适应策略 - 当前市场状态")
        print("="*70)
        
        # 第一行最醒目：当前策略
        if info['is_ranging']:
            print("🔄 当前推荐策略 → 双边网格策略（震荡市）")
        else:
            print("📈📉 当前推荐策略 → 单边趋势策略（趋势市）")
        
        print(f"💰 当前价格: ${info['price']:.2f}")
        print(f"📊 ADX 值: {info['adx']:.2f}  （阈值 {self.adx_threshold}）")
        print(f"📈 +DI: {info['+DI']:.2f}   📉 -DI: {info['-DI']:.2f}   🔄 DI差: {info['di_diff']:+.2f}")
        print(f"🏷️  市场状态: {info['market_desc']}（强度：{info['strength']}）")
        print(f"🧭  方向: {info['direction']}")
        print(f"💡  交易建议: {info['suggestion']}")
        print("="*70 + "\n")
        
        return info

# ==================== 使用示例（保留原测试代码，便于本地验证） ====================

def generate_sample_data(periods=100):
    """生成示例数据"""
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', periods=periods, freq='H')
    
    # 模拟XAUUSD数据
    close_prices = 2000 + np.cumsum(np.random.randn(periods) * 2)
    high_prices = close_prices + abs(np.random.randn(periods) * 1)
    low_prices = close_prices - abs(np.random.randn(periods) * 1)
    
    df = pd.DataFrame({
        'time': dates,
        'high': high_prices,
        'low': low_prices,
        'close': close_prices
    }).set_index('time')
    
    return df

if __name__ == "__main__":
    print("🧪 ADX分析器测试...")
    
    # 生成示例数据
    df = generate_sample_data(periods=200)
    
    # 测试市场分析器
    market_analysis = MarketAnalysis(df, adx_threshold=20)
    df_result = market_analysis.analyze()
    market_analysis.print_market_report()
    
    # 显示最后10条K线数据
    print("\n最近10条K线数据 (包含ADX):")
    display_cols = ['high', 'low', 'close', 'ADX', '+DI', '-DI']
    print(df_result[display_cols].tail(10).to_string())
    
    print("\n✅ ADX分析器测试完成!")