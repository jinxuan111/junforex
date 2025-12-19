"""
高级量化交易机器人 - 主程序（终极版）
支持：实盘交易 + 按月份历史回测模式
"""

import time
from datetime import datetime, timedelta
import pandas as pd
import sys
import MetaTrader5 as mt5  # 必须导入，用于回测直接调用

# 导入所有模块
from config import *
from indicators import TechnicalIndicators
from strategies import TradingStrategies
from risk_manager import RiskManager
from mt5_connector import MT5Connector

class TradingBot:
    """交易机器人主类"""
    
    def __init__(self):
        print("\n" + "="*70)
        print("🤖 高级量化交易机器人 v2.0 - 终极版")
        print("="*70)
        
        # 初始化各个模块
        self.mt5 = MT5Connector(TRADING_CONFIG)
        self.risk_manager = RiskManager(RISK_CONFIG)
        self.is_running = False
        self.trade_count = 0
        
    def start(self):
        """启动机器人 - 模式选择"""
        print("\n请选择运行模式:")
        print("   1. 实盘交易模式")
        print("   2. 历史回测模式（按月份回测）")
        mode = input("\n请输入 1 或 2（默认1）: ").strip()
        
        if mode == "2":
            # 输入回测月份
            default_month = (datetime.now().replace(day=1) - timedelta(days=1)).strftime('%Y-%m')
            month_str = input(f"回测哪个月份？（格式 YYYY-MM，默认上个月 {default_month}）: ").strip()
            if not month_str:
                month_str = default_month
            try:
                year = int(month_str.split('-')[0])
                month = int(month_str.split('-')[1])
            except:
                print("格式错误，使用默认上个月")
                year, month = datetime.now().year, datetime.now().month - 1
                if month == 0:
                    month = 12
                    year -= 1
            self.backtest_month(year, month)
        else:
            # 实盘模式
            print("\n🔌 正在连接MT5实盘...")
            if not self.mt5.connect(MT5_CONFIG):
                print("❌ 无法连接MT5,程序退出")
                return False
            
            self.show_config()
            self.is_running = True
            self.main_loop()
        
        return True
    
    def show_config(self):
        """显示配置信息"""
        print("\n" + "="*70)
        print("⚙️  系统配置")
        print("="*70)
        print(f"交易品种: {TRADING_CONFIG['symbol']}")
        print(f"时间周期: {TRADING_CONFIG['timeframe']}分钟")
        print(f"每笔风险: {TRADING_CONFIG['risk_per_trade']*100}%")
        print(f"最大持仓: {TRADING_CONFIG['max_positions']}")
        print(f"止损距离: {STRATEGY_PARAMS['atr_multiplier_sl']} × ATR")
        print(f"止盈距离: {STRATEGY_PARAMS['atr_multiplier_tp']} × ATR")
        print(f"移动止损: {'启用' if RISK_CONFIG['trailing_stop'] else '禁用'}")
        print(f"信号阈值: 至少{STRATEGY_PARAMS['signal_threshold_buy']}个策略同意")
        if STRATEGY_PARAMS.get('enable_vol_filter'):
            print("震荡市休眠: 启用（低波动自动0单）")
        print("\n⚠️  按 Ctrl+C 停止机器人")
        print("="*70 + "\n")
    
    def main_loop(self):
        """实盘主运行循环"""
        try:
            while self.is_running:
                account = self.mt5.get_account_info()
                if not account:
                    print("❌ 获取账户信息失败，60秒后重试...")
                    time.sleep(60)
                    continue
                
                if self.check_risk_limits(account['balance']):
                    print("⚠️  达到风险限制，机器人自动停止")
                    break
                
                df = self.mt5.get_historical_data(bars=500)
                if df is None:
                    print("❌ 获取K线数据失败，60秒后重试...")
                    time.sleep(60)
                    continue
                
                df = TechnicalIndicators.calculate_all_indicators(df, STRATEGY_PARAMS)
                
                signal, strategy_votes = TradingStrategies.generate_combined_signal(df, STRATEGY_PARAMS)
                
                self.display_status(df, signal, strategy_votes, account)
                
                self.manage_positions(df)
                
                if signal != 0 and len(self.mt5.get_positions()) < TRADING_CONFIG['max_positions']:
                    self.execute_trade(signal, df, account['balance'])
                
                print(f"\n⏳ 等待60秒下一根K线...")
                print("-"*70)
                time.sleep(60)
                
        except KeyboardInterrupt:
            self.stop()
    
    def backtest_month(self, year, month):
        """按月份历史回测（本金1000U）"""
        print(f"\n🚀 开始历史回测 - {year}年{month}月 {TRADING_CONFIG['symbol']} 15分钟数据（本金 $1000）")
        
        # 连接MT5
        print("正在连接MT5获取历史数据...")
        if not self.mt5.connect(MT5_CONFIG):
            print("❌ 连接失败！请确认MT5已打开并登录")
            return
        
        # 时间范围：该月1日 00:00 到下月1日 00:00
        from_date = datetime(year, month, 1)
        # 下个月1日
        if month == 12:
            to_date = datetime(year + 1, 1, 1)
        else:
            to_date = datetime(year, month + 1, 1)
        
        print(f"正在下载 {year}-{month:02d} 月历史数据...")
        rates = mt5.copy_rates_range(
            TRADING_CONFIG['symbol'],
            self.mt5.timeframe,
            from_date,
            to_date
        )
        
        self.mt5.disconnect()
        
        if rates is None or len(rates) == 0:
            print("❌ 获取该月数据失败！")
            print("可能原因：该月数据未加载 → 开XAUUSD M15图表，拉到该月下载")
            return
        
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        print(f"✅ 成功加载 {len(df):,} 根K线（{year}年{month}月数据）")
        
        initial_balance = 200.0
        balance = initial_balance
        positions = []
        trade_count = 0
        wins = 0
        
        print("\n开始模拟该月交易...\n")
        
        for i in range(300, len(df)):
            current_df = df.iloc[:i+1].copy()
            current_df = TechnicalIndicators.calculate_all_indicators(current_df, STRATEGY_PARAMS)
            latest = current_df.iloc[-1]
            
            signal, _ = TradingStrategies.generate_combined_signal(current_df, STRATEGY_PARAMS)
            
            # 持仓管理和平仓
            for pos in positions[:]:
                profit_points = (latest['close'] - pos['entry']) * (1 if pos['direction'] == 1 else -1)
                profit = profit_points * pos['lot'] * 100
                
                if pos['direction'] == 1:
                    if latest['close'] >= pos['tp']:
                        balance += profit
                        wins += 1
                        positions.remove(pos)
                    elif latest['close'] <= pos['sl']:
                        loss = (pos['entry'] - pos['sl']) * pos['lot'] * 100
                        balance -= loss
                        positions.remove(pos)
                else:
                    if latest['close'] <= pos['tp']:
                        balance += profit
                        wins += 1
                        positions.remove(pos)
                    elif latest['close'] >= pos['sl']:
                        loss = (pos['sl'] - pos['entry']) * pos['lot'] * 100
                        balance -= loss
                        positions.remove(pos)
            
            # 开仓
            if signal != 0 and len(positions) < TRADING_CONFIG['max_positions']:
                lot = self.risk_manager.calculate_position_size(
                    balance, latest['ATR'], latest['close'], 
                    TRADING_CONFIG['risk_per_trade'], STRATEGY_PARAMS['atr_multiplier_sl']
                )
                sl, tp = self.risk_manager.calculate_stop_loss_take_profit(
                    signal, latest['close'], latest['ATR'], STRATEGY_PARAMS
                )
                positions.append({
                    'direction': signal,
                    'entry': latest['close'],
                    'lot': lot,
                    'sl': sl,
                    'tp': tp
                })
                trade_count += 1
        
        # 输出结果
        print("\n" + "="*70)
        print(f"📊 {year}年{month}月回测完成！")
        print("="*70)
        print(f"交易笔数: {trade_count} 笔")
        if trade_count > 0:
            print(f"胜率: {wins/trade_count*100:.1f}%")
        print(f"初始本金: ${initial_balance:,.2f}")
        print(f"最终本金: ${balance:,.2f}")
        print(f"该月收益: {((balance/initial_balance)-1)*100:.2f}%")
        print("="*70)
    
    def check_risk_limits(self, balance):
        return self.risk_manager.check_daily_loss_limit(balance) or \
               self.risk_manager.check_max_drawdown(balance)
    
    def display_status(self, df, signal, strategy_votes, account):
        latest = df.iloc[-1]
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
        print("="*70)
        print(f"💰 账户: 余额 ${account['balance']:.2f} | 净值 ${account['equity']:.2f} | 浮盈 ${account['profit']:.2f}")
        print(f"📊 价格: {latest['close']:.2f} | RSI {latest['RSI']:.1f} | ATR {latest['ATR']:.2f}")
        print(f"\n🗳️ 策略投票:")
        for name, vote in strategy_votes.items():
            emoji = "📈" if "买入" in vote else "📉" if "卖出" in vote else "🛌" if "休眠" in vote else "➖"
            print(f"   {emoji} {name}: {vote}")
        signal_text = "🟢 买入" if signal == 1 else "🔴 卖出" if signal == -1 else "⚪ 无信号"
        print(f"\n{signal_text}")
        positions = self.mt5.get_positions()
        print(f"📌 持仓: {len(positions)} 张" if positions else "📌 当前无持仓")
    
    def execute_trade(self, signal, df, balance):
        latest = df.iloc[-1]
        price_info = self.mt5.get_current_price()
        if not price_info: return
        
        price = price_info['ask'] if signal == 1 else price_info['bid']
        lot_size = self.risk_manager.calculate_position_size(balance, latest['ATR'], price,
                                                            TRADING_CONFIG['risk_per_trade'],
                                                            STRATEGY_PARAMS['atr_multiplier_sl'])
        sl, tp = self.risk_manager.calculate_stop_loss_take_profit(signal, price, latest['ATR'], STRATEGY_PARAMS)
        
        if self.mt5.open_position(signal, price, lot_size, sl, tp):
            self.trade_count += 1
            self.risk_manager.daily_trades += 1
    
    def manage_positions(self, df):
        positions = self.mt5.get_positions()
        if not positions: return
        
        latest = df.iloc[-1]
        price_info = self.mt5.get_current_price()
        if not price_info: return
        
        for position in positions:
            pos_type = 'LONG' if position.type == 0 else 'SHORT'
            current_price = price_info['bid'] if pos_type == 'LONG' else price_info['ask']
            
            if self.risk_manager.should_move_to_breakeven(pos_type, position.price_open, current_price, latest['ATR']):
                self.mt5.modify_position(position, position.price_open, position.tp)
                print(f"✅ 移至盈亏平衡: {position.price_open:.2f}")
            
            elif RISK_CONFIG['trailing_stop']:
                new_sl = self.risk_manager.calculate_trailing_stop(pos_type, position.price_open, current_price, position.sl, latest['ATR'])
                if new_sl:
                    self.mt5.modify_position(position, new_sl, position.tp)
                    print(f"✅ 移动止损更新: {new_sl:.2f}")
    
    def stop(self):
        print("\n\n⚠️  收到停止信号...")
        self.is_running = False
        print(f"\n📊 今日交易统计: {self.trade_count} 笔")
        positions = self.mt5.get_positions()
        if positions:
            response = input(f"\n当前有 {len(positions)} 张持仓，是否全部平仓？(y/n): ")
            if response.lower() == 'y':
                self.mt5.close_all_positions()
                print("✅ 所有持仓已平")
        self.mt5.disconnect()
        print("\n✅ 机器人已安全停止")

# ==================== 主程序入口 ====================
if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════════════╗
║            💎 高级量化交易机器人 v2.0 - 终极版                    ║
║            支持实盘交易 + 按月份历史回测                          ║
╚════════════════════════════════════════════════════════════════════╝

📦 模块加载完成

🚀 正在启动...
""")
    
    bot = TradingBot()
    bot.start()