"""
高级量化交易机器人 - 主程序
整合所有模块,协调运行
"""

import time
from datetime import datetime
import sys

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
        print("🤖 高级量化交易机器人 v2.0")
        print("="*70)
        
        # 初始化各个模块
        self.mt5 = MT5Connector(TRADING_CONFIG)
        self.risk_manager = RiskManager(RISK_CONFIG)
        self.is_running = False
        self.trade_count = 0
        
    def start(self):
        """启动机器人"""
        # 连接MT5
        print("\n🔌 正在连接MT5...")
        if not self.mt5.connect(MT5_CONFIG):
            print("❌ 无法连接MT5,程序退出")
            return False
        
        # 显示配置信息
        self.show_config()
        
        # 开始主循环
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
        print(f"盈亏比: 1:{RISK_CONFIG['take_profit_ratio']}")
        print(f"移动止损: {'启用' if RISK_CONFIG['trailing_stop'] else '禁用'}")
        print("\n💡 策略:")
        print("  1. 趋势跟踪 (EMA排列)")
        print("  2. 均值回归 (RSI超买超卖)")
        print("  3. 突破策略 (布林带突破)")
        print("  4. 动量策略 (价格动量)")
        print(f"\n✅ 信号阈值: 至少{STRATEGY_PARAMS['signal_threshold_buy']}个策略同意")
        print("\n⚠️  按 Ctrl+C 停止机器人")
        print("="*70 + "\n")
    
    def main_loop(self):
        """主运行循环"""
        try:
            while self.is_running:
                # 1. 获取账户信息
                account = self.mt5.get_account_info()
                if not account:
                    print("❌ 获取账户信息失败")
                    time.sleep(60)
                    continue
                
                # 2. 检查风险限制
                if self.check_risk_limits(account['balance']):
                    print("⚠️  达到风险限制,停止交易")
                    break
                
                # 3. 获取历史数据
                df = self.mt5.get_historical_data(bars=500)
                if df is None:
                    time.sleep(60)
                    continue
                
                # 4. 计算技术指标
                df = TechnicalIndicators.calculate_all_indicators(df, STRATEGY_PARAMS)
                
                # 5. 生成交易信号
                signal, strategy_votes = TradingStrategies.generate_combined_signal(df, STRATEGY_PARAMS)
                
                # 6. 显示当前状态
                self.display_status(df, signal, strategy_votes, account)
                
                # 7. 管理现有持仓
                self.manage_positions(df)
                
                # 8. 执行新交易
                if signal != 0:
                    self.execute_trade(signal, df, account['balance'])
                
                # 9. 等待下一个周期
                print(f"\n⏳ 等待60秒...")
                print("-"*70)
                time.sleep(60)
                
        except KeyboardInterrupt:
            self.stop()
    
    def check_risk_limits(self, balance):
        """检查风险限制"""
        # 检查日亏损
        if self.risk_manager.check_daily_loss_limit(balance):
            return True
        
        # 检查最大回撤
        if self.risk_manager.check_max_drawdown(balance):
            return True
        
        return False
    
    def display_status(self, df, signal, strategy_votes, account):
        """显示当前状态"""
        latest = df.iloc[-1]
        
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
        print(f"{'='*70}")
        
        # 账户信息
        print(f"💰 账户状态:")
        print(f"   余额: ${account['balance']:.2f} | 净值: ${account['equity']:.2f} | 浮盈: ${account['profit']:.2f}")
        
        # 价格和指标
        print(f"\n📊 市场数据:")
        print(f"   价格: {latest['close']:.2f}")
        print(f"   RSI: {latest['RSI']:.1f}")
        print(f"   MACD: {latest['MACD_hist']:.4f}")
        print(f"   ATR: {latest['ATR']:.2f}")
        
        # 策略投票
        print(f"\n🗳️  策略投票:")
        for strategy, vote in strategy_votes.items():
            emoji = "📈" if vote == "买入" else "📉" if vote == "卖出" else "➖"
            print(f"   {emoji} {strategy}: {vote}")
        
        # 最终信号
        signal_str = "🟢 买入信号" if signal == 1 else "🔴 卖出信号" if signal == -1 else "⚪ 无信号"
        print(f"\n{signal_str}")
        
        # 风险摘要
        risk_summary = self.risk_manager.get_risk_summary(account['balance'])
        print(f"\n📉 风险状态:")
        print(f"   当日盈亏: ${risk_summary['daily_pnl']:.2f} ({risk_summary['daily_pnl_pct']:.2f}%)")
        print(f"   当前回撤: ${risk_summary['drawdown']:.2f} ({risk_summary['drawdown_pct']:.2f}%)")
        
        # 持仓信息
        positions = self.mt5.get_positions()
        if positions:
            print(f"\n📌 当前持仓:")
            for pos in positions:
                pos_type = "买入" if pos.type == 0 else "卖出"
                print(f"   {pos_type} | 手数: {pos.volume} | 盈亏: ${pos.profit:.2f}")
        else:
            print(f"\n📌 当前无持仓")
    
    def execute_trade(self, signal, df, balance):
        """执行交易"""
        latest = df.iloc[-1]
        price_info = self.mt5.get_current_price()
        
        if not price_info:
            return
        
        # 确定价格
        if signal == 1:
            price = price_info['ask']
        else:
            price = price_info['bid']
        
        # 计算手数
        lot_size = self.risk_manager.calculate_position_size(
            balance=balance,
            atr=latest['ATR'],
            price=price,
            risk_per_trade=TRADING_CONFIG['risk_per_trade'],
            atr_multiplier=STRATEGY_PARAMS['atr_multiplier_sl']
        )
        
        # 计算止损止盈
        sl, tp = self.risk_manager.calculate_stop_loss_take_profit(
            signal=signal,
            price=price,
            atr=latest['ATR'],
            config=STRATEGY_PARAMS
        )
        
        # 开仓
        if self.mt5.open_position(signal, price, lot_size, sl, tp):
            self.trade_count += 1
            self.risk_manager.daily_trades += 1
    
    def manage_positions(self, df):
        """管理持仓"""
        positions = self.mt5.get_positions()
        if not positions:
            return
        
        latest = df.iloc[-1]
        price_info = self.mt5.get_current_price()
        
        if not price_info:
            return
        
        for position in positions:
            pos_type = 'LONG' if position.type == 0 else 'SHORT'
            current_price = price_info['bid'] if pos_type == 'LONG' else price_info['ask']
            
            # 检查是否应该移至盈亏平衡
            if self.risk_manager.should_move_to_breakeven(
                pos_type, position.price_open, current_price, latest['ATR']
            ):
                self.mt5.modify_position(position, position.price_open, position.tp)
                print(f"✅ 移至盈亏平衡: {position.price_open:.2f}")
            
            # 检查移动止损
            elif RISK_CONFIG['trailing_stop']:
                new_sl = self.risk_manager.calculate_trailing_stop(
                    pos_type, position.price_open, current_price, position.sl, latest['ATR']
                )
                if new_sl:
                    self.mt5.modify_position(position, new_sl, position.tp)
    
    def stop(self):
        """停止机器人"""
        print("\n\n⚠️  收到停止信号...")
        self.is_running = False
        
        # 显示统计
        print(f"\n📊 交易统计:")
        print(f"   总交易次数: {self.trade_count}")
        
        # 询问是否关闭持仓
        positions = self.mt5.get_positions()
        if positions:
            response = input(f"\n当前有 {len(positions)} 个持仓,是否关闭? (y/n): ")
            if response.lower() == 'y':
                self.mt5.close_all_positions()
        
        # 断开连接
        self.mt5.disconnect()
        print("\n✅ 机器人已停止")


# ==================== 主程序入口 ====================
if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════════════╗
║                                                                    ║
║            💎 高级量化交易机器人 v2.0                              ║
║            Professional Quantitative Trading System                ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝

📦 模块加载:
   ✓ config.py         - 配置管理
   ✓ indicators.py     - 技术指标
   ✓ strategies.py     - 交易策略
   ✓ risk_manager.py   - 风险管理
   ✓ mt5_connector.py  - MT5连接

🚀 正在启动...
""")
    
    # 创建并启动机器人
    bot = TradingBot()
    bot.start()
