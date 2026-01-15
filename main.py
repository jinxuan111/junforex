"""
高级量化交易机器人 - 主程序（终极版）
支持：实盘交易 + 按月份/年份历史回测模式
已修复持仓获取 + modify_position 参数错误
已添加Spread（点差）支持
"""

import time
from datetime import datetime, timedelta
import pandas as pd
import MetaTrader5 as mt5

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
        print("🤖 高级量化交易机器人 v3.0 - 支持年度回测")
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
        print("   2. 单月历史回测")
        print("   3. 全年历史回测")
        mode = input("\n请输入 1、2 或 3（默认1）: ").strip()
        
        if mode == "2":
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
            self.backtest_single_month(year, month)
        elif mode == "3":
            default_year = datetime.now().year - 1
            year_str = input(f"回测哪一年？（格式 YYYY，默认去年 {default_year}）: ").strip()
            if not year_str:
                year = default_year
            else:
                year = int(year_str)
            self.backtest_full_year(year)
        else:
            print("\n🔌 正在连接MT5实盘...")
            if not self.mt5.connect(MT5_CONFIG):
                print("❌ 无法连接MT5,程序退出")
                return
            
            self.show_config()
            self.is_running = True
            self.main_loop()
    
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
        if RISK_CONFIG['trailing_stop']:
            print(f"移动止损触发: {RISK_CONFIG['min_profit_move_sl']}×ATR")
        print(f"保本逻辑: 启用 (触发: {RISK_CONFIG['break_even_trigger']}×ATR)")
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
                
                if signal != 0 and len(mt5.positions_get(symbol=TRADING_CONFIG['symbol']) or []) < TRADING_CONFIG['max_positions']:
                    self.execute_trade(signal, df, account['balance'])
                
                print(f"\n⏳ 等待60秒下一根K线...")
                print("-"*70)
                time.sleep(60)
                
        except KeyboardInterrupt:
            self.stop()
    
    def backtest_single_month(self, year, month):
        """单月历史回测（本金100U）- 完整支持移动止损和保本"""
        print(f"\n🚀 开始单月回测 - {year}年{month}月 {TRADING_CONFIG['symbol']} 15分钟数据（本金 $100）")
        return self._backtest_logic(year, month, year, month, "单月")
    
    def backtest_full_year(self, year):
        """全年历史回测（本金100U）"""
        print(f"\n🚀 开始全年回测 - {year}年 {TRADING_CONFIG['symbol']} 15分钟数据（本金 $100）")
        return self._backtest_logic(year, 1, year, 12, "全年")
    
    def _backtest_logic(self, start_year, start_month, end_year, end_month, test_type):
        """通用的回测逻辑（已添加Spread支持）"""
        print(f"📈 移动止损: {'启用' if RISK_CONFIG['trailing_stop'] else '禁用'}")
        print(f"📈 保本逻辑: 启用 (触发: {RISK_CONFIG['break_even_trigger']}×ATR)")
        
        # 只在移动止损启用时才显示相关参数
        if RISK_CONFIG['trailing_stop']:
            print(f"📈 移动止损触发: {RISK_CONFIG['min_profit_move_sl']}×ATR")
            trailing_distance = RISK_CONFIG.get('trailing_distance', 1.2)
            print(f"📈 移动止损距离: {trailing_distance}×ATR")
        
        print(f"💰 手数计算: 每100U开0.01手")
        
        # ================ 新增：Spread配置 ================
        SPREAD = 0.3  # 黄金典型点差，单位：美元（0.3表示0.3美元）
        print(f"💸 交易成本: 点差 ${SPREAD:.2f}（买入价=收盘价+${SPREAD/2:.2f}，卖出价=收盘价-${SPREAD/2:.2f}）")
        # =================================================
        
        if not self.mt5.connect(MT5_CONFIG):
            print("❌ 连接失败！")
            return
        
        from_date = datetime(start_year, start_month, 1)
        if end_month == 12:
            to_date = datetime(end_year + 1, 1, 1)
        else:
            to_date = datetime(end_year, end_month + 1, 1)
        
        rates = mt5.copy_rates_range(TRADING_CONFIG['symbol'], self.mt5.timeframe, from_date, to_date)
        self.mt5.disconnect()
        
        if rates is None or len(rates) == 0:
            print("❌ 获取数据失败！请在MT5打开XAUUSD M15图表，下载相应时间段数据")
            return
        
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        print(f"✅ 加载 {len(df)} 根K线 ({from_date.strftime('%Y-%m')} 到 {to_date.strftime('%Y-%m')})")
        
        df = TechnicalIndicators.calculate_all_indicators(df, STRATEGY_PARAMS)
        
        initial_balance = 100.0
        balance = initial_balance
        positions = []
        trade_count = 0
        wins = 0
        
        # ================ 新：手数计算函数 ================
        def calculate_position_size(balance):
            """计算交易手数（根据余额每100U开0.01手）"""
            # 每100U开0.01手
            lot_size = (balance / 100) * 0.01
            
            # 限制手数范围
            min_lot = 0.01
            max_lot = 1.0
            lot_size = max(min_lot, min(lot_size, max_lot))
            
            # 保留2位小数
            lot_size = round(lot_size, 2)
            
            return lot_size
        
        # ================ 新增：Spread相关函数 ================
        def calculate_trade_profit(direction, entry_price, exit_price, lot_size):
            """
            计算考虑点差的交易盈亏
            direction: 1=多单，-1=空单
            """
            # 黄金1手=100盎司，盈亏 = (价格差) × 手数 × 100
            if direction == 1:  # 多单：买入用Ask，卖出用Bid
                actual_entry = entry_price + (SPREAD / 2)  # 开仓：Ask价
                actual_exit = exit_price - (SPREAD / 2)    # 平仓：Bid价
                profit = (actual_exit - actual_entry) * lot_size * 100
            else:  # 空单：卖出用Bid，平仓用Ask
                actual_entry = entry_price - (SPREAD / 2)  # 开仓：Bid价
                actual_exit = exit_price + (SPREAD / 2)    # 平仓：Ask价
                profit = (actual_entry - actual_exit) * lot_size * 100
            
            return profit, actual_entry, actual_exit
        # ===================================================
        
        # ================ 详细交易记录 ================
        trade_records = []
        equity_curve = []
        peak_equity = initial_balance
        max_drawdown = 0
        max_drawdown_details = {}
        monthly_performance = []
        current_month = None
        month_start_balance = initial_balance
        
        print(f"\n开始模拟交易... ({test_type}模式)")
        
        for i in range(300, len(df)):
            current_df = df.iloc[:i+1].copy()
            latest = current_df.iloc[-1]
            current_time = latest['time']
            current_atr = latest['ATR']
            
            # 月度统计
            current_month_key = current_time.strftime('%Y-%m')
            if current_month != current_month_key:
                if current_month is not None:
                    # 记录上月表现
                    monthly_performance.append({
                        'month': current_month,
                        'start_balance': month_start_balance,
                        'end_balance': balance,
                        'return': ((balance - month_start_balance) / month_start_balance) * 100
                    })
                current_month = current_month_key
                month_start_balance = balance
            
            signal, _ = TradingStrategies.generate_combined_signal(current_df, STRATEGY_PARAMS)
            
            # ================ 持仓管理 - 与实盘完全一致的逻辑 ================
            for pos in positions[:]:
                close_reason = None
                profit = 0
                current_price = latest['close']
                
                # 1. BE保本逻辑 - 与实盘一致
                should_move_to_be = False
                if pos['direction'] == 1:  # 多单
                    profit_distance = current_price - pos['entry']
                    if profit_distance >= RISK_CONFIG['break_even_trigger'] * current_atr:
                        should_move_to_be = True
                else:  # 空单
                    profit_distance = pos['entry'] - current_price
                    if profit_distance >= RISK_CONFIG['break_even_trigger'] * current_atr:
                        should_move_to_be = True
                
                if should_move_to_be and not pos['be_triggered']:
                    # 移动到盈亏平衡
                    new_sl = pos['entry']
                    pos['sl'] = new_sl
                    pos['be_triggered'] = True
                    pos['adjustments'].append({
                        'time': current_time,
                        'type': '保本',
                        'new_sl': new_sl,
                        'reason': f"盈利达到{RISK_CONFIG['break_even_trigger']}×ATR"
                    })
                
                # 2. 移动止损逻辑 - 只在启用时执行
                if RISK_CONFIG['trailing_stop']:
                    min_profit = RISK_CONFIG['min_profit_move_sl'] * current_atr
                    trailing_distance = RISK_CONFIG.get('trailing_distance', 1.2) * current_atr
                    
                    if pos['direction'] == 1:  # 多单
                        current_profit = current_price - pos['entry']
                        if current_profit > min_profit:
                            # 记录最高价用于移动止损
                            if 'highest_price' not in pos:
                                pos['highest_price'] = current_price
                            else:
                                pos['highest_price'] = max(pos['highest_price'], current_price)
                            
                            # 基于最高价的移动止损
                            highest_profit = pos['highest_price'] - pos['entry']
                            if highest_profit > min_profit:
                                new_sl = pos['highest_price'] - trailing_distance
                                
                                # 只向上移动止损
                                if new_sl > pos['sl']:
                                    pos['sl'] = new_sl
                                    pos['adjustments'].append({
                                        'time': current_time,
                                        'type': '移动止损',
                                        'new_sl': new_sl,
                                        'reason': f"盈利超过{min_profit:.2f}"
                                    })
                    else:  # 空单
                        current_profit = pos['entry'] - current_price
                        if current_profit > min_profit:
                            # 记录最低价用于移动止损
                            if 'lowest_price' not in pos:
                                pos['lowest_price'] = current_price
                            else:
                                pos['lowest_price'] = min(pos['lowest_price'], current_price)
                            
                            # 基于最低价的移动止损
                            highest_profit = pos['entry'] - pos['lowest_price']
                            if highest_profit > min_profit:
                                new_sl = pos['lowest_price'] + trailing_distance
                                
                                # 只向下移动止损
                                if new_sl < pos['sl']:
                                    pos['sl'] = new_sl
                                    pos['adjustments'].append({
                                        'time': current_time,
                                        'type': '移动止损',
                                        'new_sl': new_sl,
                                        'reason': f"盈利超过{min_profit:.2f}"
                                    })
                
                # 3. 检查是否触发平仓 - 使用考虑点差的盈亏计算
                if pos['direction'] == 1:  # 多单
                    if current_price >= pos['tp']:
                        profit, actual_entry, actual_exit = calculate_trade_profit(
                            pos['direction'], pos['entry'], pos['tp'], pos['lot']
                        )
                        close_reason = "止盈"
                    elif current_price <= pos['sl']:
                        profit, actual_entry, actual_exit = calculate_trade_profit(
                            pos['direction'], pos['entry'], pos['sl'], pos['lot']
                        )
                        close_reason = "止损"
                        
                        # 标记止损类型
                        if pos['be_triggered'] and pos['sl'] == pos['entry']:
                            close_reason = f"保本止损"
                        elif len(pos['adjustments']) > 0:
                            last_adjustment = pos['adjustments'][-1]
                            if last_adjustment['type'] == '移动止损':
                                close_reason = f"移动止损"
                else:  # 空单
                    if current_price <= pos['tp']:
                        profit, actual_entry, actual_exit = calculate_trade_profit(
                            pos['direction'], pos['entry'], pos['tp'], pos['lot']
                        )
                        close_reason = "止盈"
                    elif current_price >= pos['sl']:
                        profit, actual_entry, actual_exit = calculate_trade_profit(
                            pos['direction'], pos['entry'], pos['sl'], pos['lot']
                        )
                        close_reason = "止损"
                        
                        # 标记止损类型
                        if pos['be_triggered'] and pos['sl'] == pos['entry']:
                            close_reason = f"保本止损"
                        elif len(pos['adjustments']) > 0:
                            last_adjustment = pos['adjustments'][-1]
                            if last_adjustment['type'] == '移动止损':
                                close_reason = f"移动止损"
                
                if close_reason:
                    # 平仓处理
                    balance += profit
                    
                    # 记录交易详情（添加实际成交价）
                    trade_record = {
                        '序号': trade_count + 1,
                        '时间': pos['entry_time'].strftime('%Y-%m-%d %H:%M'),
                        '方向': '多' if pos['direction'] == 1 else '空',
                        '开仓价': pos['entry'],
                        '实际开仓价': actual_entry,
                        '平仓价': current_price,
                        '实际平仓价': actual_exit,
                        '平仓时间': current_time.strftime('%Y-%m-%d %H:%M'),
                        '手数': pos['lot'],
                        '初始止损': pos['initial_sl'],
                        '最终止损': pos['sl'],
                        '止盈价': pos['tp'],
                        '盈亏金额': profit,
                        '盈亏百分比': (profit / initial_balance) * 100,
                        '平仓原因': close_reason,
                        '持仓时间': f"{(current_time - pos['entry_time']).total_seconds() / 3600:.1f}小时",
                        'ATR开仓时': pos['entry_atr'],
                        'ATR平仓时': current_atr,
                        '保本触发': '是' if pos['be_triggered'] else '否',
                        '止损调整次数': len(pos['adjustments']),
                        '调整详情': "; ".join([f"{adj['type']}→{adj['new_sl']:.2f}" for adj in pos['adjustments']]) if pos['adjustments'] else "无",
                        '当时余额': balance - profit,  # 记录开仓时的余额
                        '点差成本': SPREAD  # 新增：记录点差
                    }
                    trade_records.append(trade_record)
                    
                    # 输出每笔交易详情（全年回测时减少输出频率）
                    if test_type == "单月" or (test_type == "全年" and trade_count % 10 == 0):
                        color = "🟢" if profit > 0 else "🔴"
                        sl_info = f"止:{pos['initial_sl']:.2f}→{pos['sl']:.2f}" if pos['sl'] != pos['initial_sl'] else f"止:{pos['sl']:.2f}"
                        
                        print(f"{color} #{trade_record['序号']} | {trade_record['方向']} | "
                              f"开:{trade_record['开仓价']:.2f}(实:{actual_entry:.2f})→平:{trade_record['平仓价']:.2f}(实:{actual_exit:.2f}) | "
                              f"{sl_info} | 盈:{trade_record['止盈价']:.2f} | "
                              f"手数:{trade_record['手数']:.2f} | "
                              f"盈亏:${profit:+.2f} | 原因:{trade_record['平仓原因']} | "
                              f"调整:{trade_record['止损调整次数']}次")
                    
                    trade_count += 1
                    if profit > 0:
                        wins += 1
                    
                    positions.remove(pos)
            
            # 记录权益曲线（全年回测时抽样记录）
            if test_type == "单月" or i % 100 == 0:
                equity_curve.append({
                    'time': current_time,
                    'equity': balance,
                    'positions': len(positions)
                })
            
            # 计算最大回撤
            if balance > peak_equity:
                peak_equity = balance
            
            current_drawdown = (peak_equity - balance) / peak_equity * 100 if peak_equity > 0 else 0
            if current_drawdown > max_drawdown:
                max_drawdown = current_drawdown
                max_drawdown_details = {
                    'peak_equity': peak_equity,
                    'trough_equity': balance,
                    'drawdown_percent': max_drawdown,
                    'time': current_time
                }
            
            # 开仓逻辑 - 与实盘一致
            if signal != 0 and len(positions) < TRADING_CONFIG['max_positions']:
                # 使用新的手数计算
                lot = calculate_position_size(balance)
                
                # 计算止损止盈 - 与实盘execute_trade方法一致
                price = latest['close']
                sl_multiplier = STRATEGY_PARAMS['atr_multiplier_sl']
                tp_multiplier = STRATEGY_PARAMS['atr_multiplier_tp']
                
                if signal == 1:  # 买入
                    sl = price - (current_atr * sl_multiplier)
                    tp = price + (current_atr * tp_multiplier)
                else:  # 卖出
                    sl = price + (current_atr * sl_multiplier)
                    tp = price - (current_atr * tp_multiplier)
                
                positions.append({
                    'direction': signal,
                    'entry': price,
                    'entry_time': current_time,
                    'entry_atr': current_atr,
                    'lot': lot,
                    'sl': sl,               # 当前止损（会变动）
                    'initial_sl': sl,       # 初始止损（固定）
                    'tp': tp,
                    'be_triggered': False,  # 保本是否触发
                    'adjustments': [],      # 记录止损调整历史
                    # 新增：用于移动止损的价格极值记录
                    'highest_price': price if signal == 1 else None,
                    'lowest_price': price if signal == -1 else None
                })
        
        # 记录最后一个月表现
        if current_month is not None:
            monthly_performance.append({
                'month': current_month,
                'start_balance': month_start_balance,
                'end_balance': balance,
                'return': ((balance - month_start_balance) / month_start_balance) * 100
            })
        
        # 平掉所有剩余持仓（使用考虑点差的盈亏计算）
        if positions:
            print(f"\n📝 回测结束，平掉剩余持仓...")
            for pos in positions:
                profit, actual_entry, actual_exit = calculate_trade_profit(
                    pos['direction'], pos['entry'], df.iloc[-1]['close'], pos['lot']
                )
                
                balance += profit
                trade_count += 1
                if profit > 0:
                    wins += 1
        
        # ================ 新增：点差影响分析 ================
        print("\n" + "="*80)
        print("💸 点差影响分析")
        print("="*80)
        
        if trade_records:
            # 计算总点差成本
            total_spread_cost = 0
            for trade in trade_records:
                # 每笔交易的点差成本 = 点差 × 手数 × 100
                spread_cost = SPREAD * trade['手数'] * 100
                total_spread_cost += spread_cost
            
            print(f"总点差成本: ${total_spread_cost:.2f}")
            if len(trade_records) > 0:
                print(f"平均每笔点差成本: ${total_spread_cost/len(trade_records):.2f}")
            
            # 如果不考虑点差的收益（理论收益）
            theoretical_balance = initial_balance
            for trade in trade_records:
                # 重新计算无点差盈亏
                if trade['方向'] == '多':
                    profit_no_spread = (trade['平仓价'] - trade['开仓价']) * trade['手数'] * 100
                else:
                    profit_no_spread = (trade['开仓价'] - trade['平仓价']) * trade['手数'] * 100
                theoretical_balance += profit_no_spread
            
            theoretical_return = ((theoretical_balance / initial_balance) - 1) * 100
            actual_return = ((balance / initial_balance) - 1) * 100
            spread_impact = theoretical_return - actual_return
            
            print(f"\n📊 点差对收益率的影响:")
            print(f"   理论收益率（无点差）: {theoretical_return:+.2f}%")
            print(f"   实际收益率（有点差）: {actual_return:+.2f}%")
            print(f"   点差造成的影响: {spread_impact:+.2f}%")
            
            if actual_return > 0:
                # 计算能承受的最大点差（简易版）
                for test_spread in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
                    test_balance = initial_balance
                    for trade in trade_records:
                        if trade['方向'] == '多':
                            profit_with_spread = ((trade['平仓价'] - test_spread/2) - (trade['开仓价'] + test_spread/2)) * trade['手数'] * 100
                        else:
                            profit_with_spread = ((trade['开仓价'] - test_spread/2) - (trade['平仓价'] + test_spread/2)) * trade['手数'] * 100
                        test_balance += profit_with_spread
                    
                    if test_balance <= initial_balance:
                        print(f"   盈亏平衡点差: ${test_spread:.2f}")
                        safety_margin = ((test_spread - SPREAD) / SPREAD * 100)
                        print(f"   当前点差安全边际: {safety_margin:+.1f}%")
                        break
        # =================================================
        
        # ================ 生成详细报告 ================
        print("\n" + "="*80)
        print(f"📊 {test_type}回测详细报告 ({from_date.strftime('%Y-%m')} 到 {to_date.strftime('%Y-%m')})")
        print("="*80)
        
        # 1. 基本统计
        print(f"\n📈 基本统计:")
        print(f"   交易笔数: {trade_count} 笔")
        if trade_count > 0:
            print(f"   盈利笔数: {wins} 笔")
            print(f"   亏损笔数: {trade_count - wins} 笔")
            print(f"   胜率: {wins/trade_count*100:.1f}%")
            if trade_records:
                avg_profit = sum(t['盈亏金额'] for t in trade_records) / len(trade_records)
                print(f"   平均每笔盈亏: ${avg_profit:+.2f}")
        
        # 2. 资金表现
        print(f"\n💰 资金表现:")
        print(f"   初始本金: ${initial_balance:,.2f}")
        print(f"   最终本金: ${balance:,.2f}")
        total_return = ((balance / initial_balance) - 1) * 100
        print(f"   总收益率: {total_return:+.2f}%")
        
        # 3. 回撤分析
        print(f"\n📉 回撤分析:")
        print(f"   最大回撤: {max_drawdown:.2f}%")
        if max_drawdown_details:
            print(f"   回撤高点: ${max_drawdown_details['peak_equity']:.2f}")
            print(f"   回撤低点: ${max_drawdown_details['trough_equity']:.2f}")
            print(f"   回撤发生时间: {max_drawdown_details['time'].strftime('%Y-%m-%d %H:%M')}")
        
        # 4. 手数分析
        if trade_records:
            lots_used = [t['手数'] for t in trade_records]
            avg_lot = sum(lots_used) / len(lots_used)
            min_lot_used = min(lots_used)
            max_lot_used = max(lots_used)
            
            print(f"\n📊 手数分析:")
            print(f"   平均手数: {avg_lot:.3f}")
            print(f"   最小手数: {min_lot_used:.3f}")
            print(f"   最大手数: {max_lot_used:.3f}")
        
        # 5. 点差分析（新增）
        if trade_records:
            print(f"\n💸 点差分析:")
            print(f"   使用点差: ${SPREAD:.2f}")
            print(f"   总点差成本: ${total_spread_cost:.2f}" if 'total_spread_cost' in locals() else "   总点差成本: 无交易")
            print(f"   点差影响收益率: {spread_impact:+.2f}%" if 'spread_impact' in locals() else "   点差影响收益率: 无交易")
        
        # 6. 月度表现（仅全年回测显示）
        if test_type == "全年" and monthly_performance:
            print(f"\n📅 月度表现:")
            print("-"*60)
            print(f"{'月份':<8} {'开始余额':<12} {'结束余额':<12} {'收益率':<10}")
            print("-"*60)
            
            positive_months = 0
            total_monthly_return = 0
            
            for perf in monthly_performance:
                color = "🟢" if perf['return'] > 0 else "🔴"
                print(f"{perf['month']:<8} ${perf['start_balance']:<11.2f} ${perf['end_balance']:<11.2f} {perf['return']:>+8.2f}% {color}")
                
                if perf['return'] > 0:
                    positive_months += 1
                total_monthly_return += perf['return']
            
            print("-"*60)
            monthly_win_rate = positive_months / len(monthly_performance) * 100
            avg_monthly_return = total_monthly_return / len(monthly_performance)
            print(f"   盈利月份: {positive_months}/{len(monthly_performance)} ({monthly_win_rate:.1f}%)")
            print(f"   平均月收益: {avg_monthly_return:.2f}%")
        
        # 7. 止损分析
        if trade_records:
            be_stops = [t for t in trade_records if t['保本触发'] == '是']
            be_stop_wins = [t for t in be_stops if t['盈亏金额'] > 0]
            
            print(f"\n🛡️  止损分析:")
            print(f"   移动止损启用: {'是' if RISK_CONFIG['trailing_stop'] else '否'}")
            print(f"   保本触发: {len(be_stops)} 笔 ({len(be_stops)/len(trade_records)*100:.1f}%)")
            
            if RISK_CONFIG['trailing_stop']:
                moved_stops = [t for t in trade_records if t['止损调整次数'] > 0]
                moved_stop_wins = [t for t in moved_stops if t['盈亏金额'] > 0]
                print(f"   止损调整: {len(moved_stops)} 笔 ({len(moved_stops)/len(trade_records)*100:.1f}%)")
                
                if moved_stops:
                    moved_stop_win_rate = len(moved_stop_wins)/len(moved_stops)*100 if moved_stops else 0
                    print(f"   移动止损交易胜率: {moved_stop_win_rate:.1f}%")
            
            if be_stops:
                be_stop_win_rate = len(be_stop_wins)/len(be_stops)*100 if be_stops else 0
                print(f"   保本触发交易胜率: {be_stop_win_rate:.1f}%")
        
        # 8. 按平仓原因分类统计
        if trade_records:
            print(f"\n📊 按平仓原因统计:")
            reasons = {}
            for trade in trade_records:
                reason = trade['平仓原因']
                reasons[reason] = reasons.get(reason, 0) + 1
            
            for reason, count in reasons.items():
                percentage = count / len(trade_records) * 100
                # 按原因分类的盈亏统计
                reason_trades = [t for t in trade_records if t['平仓原因'] == reason]
                reason_profit = sum(t['盈亏金额'] for t in reason_trades)
                avg_reason_profit = reason_profit / count if count > 0 else 0
                
                print(f"   {reason}: {count}笔 ({percentage:.1f}%) | "
                      f"总盈亏:${reason_profit:+.2f} | 平均:${avg_reason_profit:+.2f}")
        
        # 9. 交易明细表格（只显示前10笔，新增实际成交价）
        if trade_records:
            print(f"\n📋 交易明细 (显示前10笔，含实际成交价):")
            print("-"*140)
            header = f"{'序号':<4} {'时间':<16} {'方向':<4} {'开仓':<7} {'实际开':<7} {'平仓':<7} {'实际平':<7} {'手数':<6} {'盈亏($)':<9} {'原因':<10}"
            print(header)
            print("-"*140)
            
            for i, trade in enumerate(trade_records[:10]):
                if trade['盈亏金额'] > 0:
                    print(f"{trade['序号']:<4} {trade['时间']:<16} {trade['方向']:<4} "
                          f"{trade['开仓价']:<7.1f} {trade['实际开仓价']:<7.1f} {trade['平仓价']:<7.1f} {trade['实际平仓价']:<7.1f} "
                          f"{trade['手数']:<6.2f} {trade['盈亏金额']:<+9.2f} {trade['平仓原因']:<10}")
                else:
                    print(f"{trade['序号']:<4} {trade['时间']:<16} {trade['方向']:<4} "
                          f"{trade['开仓价']:<7.1f} {trade['实际开仓价']:<7.1f} {trade['平仓价']:<7.1f} {trade['实际平仓价']:<7.1f} "
                          f"{trade['手数']:<6.2f} {trade['盈亏金额']:<+9.2f} {trade['平仓原因']:<10}")
            
            if len(trade_records) > 10:
                print(f"... 还有 {len(trade_records) - 10} 笔交易未显示")
            
            print("-"*80)
            
            # 10. 保存详细报告到CSV
            try:
                import csv
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"backtest_report_{test_type}_{start_year}_{start_month}_to_{end_year}_{end_month}_{timestamp}.csv"
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=trade_records[0].keys())
                    writer.writeheader()
                    writer.writerows(trade_records)
                print(f"\n💾 详细交易记录已保存到: {filename}")
                
                # 保存权益曲线
                equity_filename = f"equity_curve_{test_type}_{start_year}_{start_month}_to_{end_year}_{end_month}_{timestamp}.csv"
                with open(equity_filename, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['时间', '权益', '持仓数'])
                    for point in equity_curve:
                        writer.writerow([point['time'], point['equity'], point['positions']])
                print(f"💾 权益曲线已保存到: {equity_filename}")
                
                # 保存月度表现
                if test_type == "全年" and monthly_performance:
                    monthly_filename = f"monthly_performance_{start_year}_{timestamp}.csv"
                    with open(monthly_filename, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.DictWriter(f, fieldnames=monthly_performance[0].keys())
                        writer.writeheader()
                        writer.writerows(monthly_performance)
                    print(f"💾 月度表现已保存到: {monthly_filename}")
                
            except Exception as e:
                print(f"\n⚠️  保存文件失败: {e}")
        
        return {
            'trade_records': trade_records,
            'equity_curve': equity_curve,
            'monthly_performance': monthly_performance,
            'summary': {
                'initial_balance': initial_balance,
                'final_balance': balance,
                'total_return': total_return,
                'trade_count': trade_count,
                'win_rate': wins/trade_count*100 if trade_count > 0 else 0,
                'max_drawdown': max_drawdown,
                'max_drawdown_details': max_drawdown_details,
                'spread_used': SPREAD,
                'spread_impact': spread_impact if 'spread_impact' in locals() else 0
            }
        }
    
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
        positions = mt5.positions_get(symbol=TRADING_CONFIG['symbol'])
        positions_count = len(positions) if positions else 0
        print(f"📌 持仓: {positions_count} 张" if positions_count > 0 else "📌 当前无持仓")
    
    def execute_trade(self, signal, df, balance):
        latest = df.iloc[-1]
        price_info = self.mt5.get_current_price()
        if not price_info: return
        
        price = price_info['ask'] if signal == 1 else price_info['bid']
        
        # 固定倍数（去除动态）
        sl_multiplier = STRATEGY_PARAMS['atr_multiplier_sl']  # 固定1.2
        tp_multiplier = STRATEGY_PARAMS['atr_multiplier_tp']  # 固定5.5
        
        # 新：使用新的手数计算
        def calculate_position_size(balance):
            """计算交易手数（根据余额每100U开0.01手）"""
            lot_size = (balance / 100) * 0.01
            min_lot = 0.01
            max_lot = 1.0
            lot_size = max(min_lot, min(lot_size, max_lot))
            return round(lot_size, 2)
        
        lot_size = calculate_position_size(balance)
        
        sl = price - (latest['ATR'] * sl_multiplier) * signal
        tp = price + (latest['ATR'] * tp_multiplier) * signal
        
        if self.mt5.open_position(signal, price, lot_size, sl, tp):
            self.trade_count += 1
            self.risk_manager.daily_trades += 1
    
    def manage_positions(self, df):
        """持仓管理（BE + 移动止损）"""
        # 使用MT5官方函数获取当前品种持仓对象
        positions = mt5.positions_get(symbol=TRADING_CONFIG['symbol'])
        if positions is None or len(positions) == 0:
            return
        
        latest = df.iloc[-1]
        price_info = self.mt5.get_current_price()
        if not price_info:
            return
        
        for position in positions:
            pos_type = 'LONG' if position.type == 0 else 'SHORT'
            current_price = price_info['bid'] if pos_type == 'LONG' else price_info['ask']
            
            # BE保本
            if self.risk_manager.should_move_to_breakeven(pos_type, position.price_open, current_price, latest['ATR']):
                new_sl = position.price_open
                # 修复：传入完整的position对象，而不是position.ticket
                self.mt5.modify_position(position, new_sl, position.tp)
                print(f"✅ [{position.ticket}] 移至盈亏平衡: {new_sl:.2f}")
            
            # 移动止损 - 只在启用时执行
            if RISK_CONFIG['trailing_stop']:
                new_sl = self.risk_manager.calculate_trailing_stop(
                    pos_type, position.price_open, current_price, position.sl, latest['ATR']
                )
                if new_sl:
                    if (pos_type == 'LONG' and new_sl > position.sl) or (pos_type == 'SHORT' and new_sl < position.sl):
                        # 修复：传入完整的position对象，而不是position.ticket
                        self.mt5.modify_position(position, new_sl, position.tp)
                        print(f"✅ [{position.ticket}] 移动止损更新: {new_sl:.2f}")
    
    def stop(self):
        """停止机器人"""
        print("\n\n⚠️  收到停止信号...")
        self.is_running = False
        print(f"\n📊 今日交易统计: {self.trade_count} 笔")
        positions = mt5.positions_get(symbol=TRADING_CONFIG['symbol'])
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
║            💎 高级量化交易机器人 v3.0 - 终极版                    ║
║      支持实盘交易 + 单月回测 + 全年回测 + 年度回撤分析            ║
╚════════════════════════════════════════════════════════════════════╝

📦 模块加载完成

🚀 正在启动...
""")
    
    bot = TradingBot()
    bot.start()