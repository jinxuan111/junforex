"""
高级量化交易机器人 - 主程序（ADX自适应策略版）
支持：ADX智能切换单边/双边策略
整合：professional_ranging + professional_executor + stops_implementation
修复：ADX nan 处理 + 数据不足安全默认 + 完整回测逻辑
+ 新增：显示ATR和ADX
+ 修复持仓冲突：网格和趋势都允许重复开单（最多max_positions）
+ 修复show_config中max_positions未定义bug
"""

import time
from datetime import datetime, timedelta
import pandas as pd
import MetaTrader5 as mt5
import numpy as np  # 用于NaN检查

# 导入所有模块
from config import *
from indicators import TechnicalIndicators
from strategies import TradingStrategies
from risk_manager import RiskManager
from mt5_connector import MT5Connector

# 导入ADX分析器
from adx_analyzer import MarketAnalysis

# 导入专业策略模块
from professional_ranging import ProfessionalRangingStrategy
from professional_executor import ProfessionalExecutor
from stops_implementation import ProfessionalStopsManager

class AdaptiveStrategyManager:
    """自适应策略管理器"""
    
    def __init__(self, initial_capital=100):
        # 初始化所有策略
        self.ranging_strategy = ProfessionalRangingStrategy()
        self.executor = ProfessionalExecutor(initial_capital)
        self.stops_manager = ProfessionalStopsManager()
        
        # ADX阈值
        self.adx_threshold = 20
        
        # 当前状态
        self.current_market_type = None
        self.last_adx = 0
        self.adx_history = []
        
    def analyze_market(self, df):
        """分析市场状态 - 修复：安全处理数据不足和NaN"""
        if len(df) < 80:  # 数据不足时返回安全默认
            print("⚠️  K线数据不足（<80根），无法计算ADX，使用默认RANGING模式")
            return {
                'market_type': 'RANGING',
                'market_desc': '数据不足/盘整',
                'direction': '中性',
                'direction_signal': 0,
                'adx': 0.0,
                '+DI': 0.0,
                '-DI': 0.0,
                'df': df
            }
        
        # 计算ADX
        analyzer = MarketAnalysis(df)
        df_with_adx = analyzer.analyze()
        latest = df_with_adx.iloc[-1]
        
        # 安全取值：处理缺失列和NaN
        adx_value = latest['ADX'] if 'ADX' in latest and pd.notna(latest['ADX']) else 0.0
        pos_di = latest['+DI'] if '+DI' in latest and pd.notna(latest['+DI']) else 0.0
        neg_di = latest['-DI'] if '-DI' in latest and pd.notna(latest['-DI']) else 0.0
        
        if np.isnan(adx_value):
            print("⚠️  ADX计算为NaN，使用默认值0")
            adx_value = 0.0
        
        # 判断市场类型
        if adx_value < self.adx_threshold:
            market_type = 'RANGING'
            market_desc = '盘整/双边'
        else:
            market_type = 'TRENDING'
            if adx_value >= 40:
                market_desc = '强单边'
            else:
                market_desc = '趋势开始'
        
        # 判断方向（加容差避免弱方向误判）
        if pos_di > neg_di + 1:
            direction = '看涨'
            direction_signal = 1
        elif neg_di > pos_di + 1:
            direction = '看跌'
            direction_signal = -1
        else:
            direction = '中性'
            direction_signal = 0
        
        self.current_market_type = market_type
        self.last_adx = adx_value
        
        return {
            'market_type': market_type,
            'market_desc': market_desc,
            'direction': direction,
            'direction_signal': direction_signal,
            'adx': adx_value,
            '+DI': pos_di,
            '-DI': neg_di,
            'df': df_with_adx
        }
    
    def generate_signal(self, df):
        """生成交易信号"""
        market_info = self.analyze_market(df)
        market_type = market_info['market_type']
        
        if market_type == 'RANGING':
            # 双边策略：专业网格交易
            signal, confidence, details = self.ranging_strategy.generate_professional_signal(df)
            
            # 网格管理
            grid_info = details.get('grid_info', None) if details else None
            position_action, lot_size, grid_details = self.executor.manage_grid_positions(
                df['close'].iloc[-1], grid_info, signal, confidence
            )
            
            details['grid_action'] = position_action
            details['grid_lot_size'] = lot_size
            details['grid_details'] = grid_details
            
            return {
                'signal': signal,
                'confidence': confidence,
                'market_type': market_type,
                'details': details,
                'market_info': market_info
            }
            
        else:  # TRENDING
            # 单边策略：原有趋势跟随策略
            signal, strategy_votes = TradingStrategies.generate_combined_signal(df, STRATEGY_PARAMS)
            
            details = {
                'strategy_votes': strategy_votes,
                'market_desc': market_info['market_desc'],
                'direction': market_info['direction']
            }
            
            return {
                'signal': signal,
                'confidence': market_info['adx'] / 50.0,  # ADX越高信心越强
                'market_type': market_type,
                'details': details,
                'market_info': market_info
            }
    
    def calculate_stops(self, signal, entry_price, df, market_type, grid_info=None):
        """计算止损止盈"""
        atr = df['ATR'].iloc[-1] if 'ATR' in df.columns and pd.notna(df['ATR'].iloc[-1]) else 10
        
        if market_type == 'RANGING':
            if grid_info and 'grid_width' in grid_info:
                grid_width = grid_info['grid_width']
                sl_distance = atr * 1.5
                tp_distance = grid_width * 2.5
            else:
                sl_distance = atr * 1.5
                tp_distance = atr * 2.5
        else:
            sl_distance = atr * STRATEGY_PARAMS['atr_multiplier_sl']
            tp_distance = atr * STRATEGY_PARAMS['atr_multiplier_tp']
        
        if signal == 1:
            sl = entry_price - sl_distance
            tp = entry_price + tp_distance
        else:
            sl = entry_price + sl_distance
            tp = entry_price - tp_distance
        
        return {
            'stop_loss': sl,
            'take_profit': tp,
            'sl_distance': sl_distance,
            'tp_distance': tp_distance,
            'risk_reward_ratio': tp_distance / sl_distance if sl_distance > 0 else 0
        }
    
    def get_strategy_description(self, market_type):
        """获取策略描述"""
        if market_type == 'RANGING':
            return {
                'name': '统计套利网格交易',
                'description': 'ADX < 20，市场盘整，使用双边网格策略',
                'icon': '🔄'
            }
        else:
            return {
                'name': '趋势跟随策略',
                'description': 'ADX ≥ 20，市场有趋势，使用单边趋势策略',
                'icon': '📈'
            }

class TradingBot:
    """交易机器人主类"""
    
    def __init__(self):
        print("\n" + "="*70)
        print("🤖 高级量化交易机器人 v4.0 - ADX自适应策略版")
        print("="*70)
        
        # 初始化各个模块
        self.mt5 = MT5Connector(TRADING_CONFIG)
        self.risk_manager = RiskManager(RISK_CONFIG)
        self.adaptive_manager = AdaptiveStrategyManager(initial_capital=100)
        self.is_running = False
        self.trade_count = 0
        
    def start(self):
        """启动机器人 - 模式选择"""
        print("\n请选择运行模式:")
        print("   1. 实盘交易模式 (ADX自适应)")
        print("   2. 单月历史回测 (ADX自适应)")
        print("   3. 全年历史回测 (ADX自适应)")
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
        print(f"最大持仓: {TRADING_CONFIG['max_positions']} 单（网格/趋势均适用）")
        print(f"ADX阈值: {self.adaptive_manager.adx_threshold}")
        print(f"ADX<{self.adaptive_manager.adx_threshold}: 双边网格策略（允许多层加仓）")
        print(f"ADX≥{self.adaptive_manager.adx_threshold}: 单边趋势策略（允许重复开单，最多{TRADING_CONFIG['max_positions']}单）")
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
                
                df = self.mt5.get_historical_data(bars=600)  # 增加数据量，确保ADX稳定
                if df is None or len(df) < 100:
                    print(f"❌ 获取K线数据失败或不足（当前{len(df) if df is not None else 0}根），60秒后重试...")
                    time.sleep(60)
                    continue
                
                # 计算技术指标
                df = TechnicalIndicators.calculate_all_indicators(df, STRATEGY_PARAMS)
                
                # 使用自适应策略生成信号
                signal_data = self.adaptive_manager.generate_signal(df)
                signal = signal_data['signal']
                market_type = signal_data['market_type']
                details = signal_data['details']
                market_info = signal_data['market_info']
                
                self.display_status(df, signal, market_type, details, market_info, account)
                
                self.manage_positions(df)
                
                # === 统一开仓逻辑：网格和趋势都允许重复开单（最多max_positions）===
                positions = mt5.positions_get(symbol=TRADING_CONFIG['symbol'])
                current_positions_count = len(positions) if positions else 0
                
                price_info = self.mt5.get_current_price()
                if not price_info:
                    print("⚠️ 获取当前价格失败，跳过本次开仓检查")
                else:
                    price = price_info['ask'] if signal == 1 else price_info['bid']
                    
                    if current_positions_count < TRADING_CONFIG['max_positions'] and signal != 0:
                        if market_type == 'RANGING':
                            grid_action = details.get('grid_action', 'HOLD')
                            grid_lot_size = details.get('grid_lot_size', 0.01)
                            
                            if grid_action != 'HOLD':
                                # 网格使用executor计算的专业手数
                                lot_size = max(grid_lot_size, 0.01)
                                stops = self.adaptive_manager.calculate_stops(signal, price, df, market_type, details.get('grid_info'))
                                sl = stops['stop_loss']
                                tp = stops['take_profit']
                                
                                if self.mt5.open_position(signal, price, lot_size, sl, tp):
                                    self.trade_count += 1
                                    self.risk_manager.daily_trades += 1
                                    print(f"✅ 网格加仓成功! 动作: {grid_action} | 方向: {'多' if signal == 1 else '空'} | "
                                          f"手数: {lot_size:.3f} | 止损: {sl:.2f} | 止盈: {tp:.2f}")
                        
                        else:  # TRENDING
                            # 趋势模式使用标准手数计算（允许重复开单）
                            self.execute_adaptive_trade(signal, df, account['balance'], market_type, details)
                
                print(f"\n⏳ 等待60秒下一根K线...")
                print("-"*70)
                time.sleep(60)
                
        except KeyboardInterrupt:
            self.stop()
    
    def backtest_single_month(self, year, month):
        """单月历史回测（本金100U）- ADX自适应"""
        print(f"\n🚀 开始单月回测 - {year}年{month}月 {TRADING_CONFIG['symbol']} 15分钟数据（本金 $100）")
        print(f"📊 ADX自适应策略: ADX<{self.adaptive_manager.adx_threshold}=双边网格, ADX≥{self.adaptive_manager.adx_threshold}=单边趋势")
        return self._backtest_logic(year, month, year, month, "单月")
    
    def backtest_full_year(self, year):
        """全年历史回测（本金100U）- ADX自适应"""
        print(f"\n🚀 开始全年回测 - {year}年 {TRADING_CONFIG['symbol']} 15分钟数据（本金 $100）")
        print(f"📊 ADX自适应策略: ADX<{self.adaptive_manager.adx_threshold}=双边网格, ADX≥{self.adaptive_manager.adx_threshold}=单边趋势")
        return self._backtest_logic(year, 1, year, 12, "全年")
    
    def _backtest_logic(self, start_year, start_month, end_year, end_month, test_type):
        """通用的回测逻辑（ADX自适应版） - 完整未删除"""
        print(f"📈 移动止损: {'启用' if RISK_CONFIG['trailing_stop'] else '禁用'}")
        print(f"📈 保本逻辑: 启用 (触发: {RISK_CONFIG['break_even_trigger']}×ATR)")
        
        if RISK_CONFIG['trailing_stop']:
            print(f"📈 移动止损触发: {RISK_CONFIG['min_profit_move_sl']}×ATR")
        
        SPREAD = 0.3  # 黄金典型点差
        print(f"💸 交易成本: 点差 ${SPREAD:.2f}")
        print(f"💰 手数计算: 每100U开0.01手")
        
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
        
        # 计算技术指标
        df = TechnicalIndicators.calculate_all_indicators(df, STRATEGY_PARAMS)
        
        initial_balance = 100.0
        balance = initial_balance
        positions = []
        trade_count = 0
        wins = 0
        
        # 手数计算函数
        def calculate_position_size(balance, market_type):
            """计算交易手数"""
            lot_size = (balance / 100) * 0.01
            if market_type == 'RANGING':
                multiplier = 1.0
            else:
                multiplier = 1.2
            lot_size *= multiplier
            min_lot = 0.01
            max_lot = 1.0
            lot_size = max(min_lot, min(lot_size, max_lot))
            return round(lot_size, 2)
        
        # 考虑点差的盈亏计算
        def calculate_trade_profit(direction, entry_price, exit_price, lot_size):
            if direction == 1:  # 多单
                actual_entry = entry_price + (SPREAD / 2)
                actual_exit = exit_price - (SPREAD / 2)
                profit = (actual_exit - actual_entry) * lot_size * 100
            else:  # 空单
                actual_entry = entry_price - (SPREAD / 2)
                actual_exit = exit_price + (SPREAD / 2)
                profit = (actual_entry - actual_exit) * lot_size * 100
            return profit, actual_entry, actual_exit
        
        # 详细交易记录
        trade_records = []
        equity_curve = []
        peak_equity = initial_balance
        max_drawdown = 0
        max_drawdown_details = {}
        monthly_performance = []
        current_month = None
        month_start_balance = initial_balance
        
        # 市场类型统计
        market_type_stats = {
            'RANGING': {'trades': 0, 'wins': 0, 'profit': 0},
            'TRENDING': {'trades': 0, 'wins': 0, 'profit': 0}
        }
        
        print(f"\n开始模拟交易... ({test_type}模式)")
        
        for i in range(300, len(df)):
            current_df = df.iloc[:i+1].copy()
            latest = current_df.iloc[-1]
            current_time = latest['time']
            current_atr = latest['ATR'] if 'ATR' in latest else 10
            
            # 月度统计
            current_month_key = current_time.strftime('%Y-%m')
            if current_month != current_month_key:
                if current_month is not None:
                    monthly_performance.append({
                        'month': current_month,
                        'start_balance': month_start_balance,
                        'end_balance': balance,
                        'return': ((balance - month_start_balance) / month_start_balance) * 100
                    })
                current_month = current_month_key
                month_start_balance = balance
            
            # 使用自适应策略生成信号
            signal_data = self.adaptive_manager.generate_signal(current_df)
            signal = signal_data['signal']
            market_type = signal_data['market_type']
            confidence = signal_data['confidence']
            details = signal_data['details']
            
            # 持仓管理
            for pos in positions[:]:
                close_reason = None
                profit = 0
                current_price = latest['close']
                
                # BE保本逻辑
                should_move_to_be = False
                if pos['direction'] == 1:
                    profit_distance = current_price - pos['entry']
                    if profit_distance >= RISK_CONFIG['break_even_trigger'] * current_atr:
                        should_move_to_be = True
                else:
                    profit_distance = pos['entry'] - current_price
                    if profit_distance >= RISK_CONFIG['break_even_trigger'] * current_atr:
                        should_move_to_be = True
                
                if should_move_to_be and not pos['be_triggered']:
                    new_sl = pos['entry']
                    pos['sl'] = new_sl
                    pos['be_triggered'] = True
                    pos['adjustments'].append({
                        'time': current_time,
                        'type': '保本',
                        'new_sl': new_sl,
                        'reason': f"盈利达到{RISK_CONFIG['break_even_trigger']}×ATR"
                    })
                
                # 移动止损逻辑
                if RISK_CONFIG['trailing_stop']:
                    min_profit = RISK_CONFIG['min_profit_move_sl'] * current_atr
                    if pos['direction'] == 1:
                        current_profit = current_price - pos['entry']
                        if current_profit > min_profit:
                            if 'highest_price' not in pos:
                                pos['highest_price'] = current_price
                            else:
                                pos['highest_price'] = max(pos['highest_price'], current_price)
                            highest_profit = pos['highest_price'] - pos['entry']
                            if highest_profit > min_profit:
                                new_sl = pos['highest_price'] - (1.2 * current_atr)
                                if new_sl > pos['sl']:
                                    pos['sl'] = new_sl
                                    pos['adjustments'].append({
                                        'time': current_time,
                                        'type': '移动止损',
                                        'new_sl': new_sl,
                                        'reason': f"盈利超过{min_profit:.2f}"
                                    })
                    else:
                        current_profit = pos['entry'] - current_price
                        if current_profit > min_profit:
                            if 'lowest_price' not in pos:
                                pos['lowest_price'] = current_price
                            else:
                                pos['lowest_price'] = min(pos['lowest_price'], current_price)
                            highest_profit = pos['entry'] - pos['lowest_price']
                            if highest_profit > min_profit:
                                new_sl = pos['lowest_price'] + (1.2 * current_atr)
                                if new_sl < pos['sl']:
                                    pos['sl'] = new_sl
                                    pos['adjustments'].append({
                                        'time': current_time,
                                        'type': '移动止损',
                                        'new_sl': new_sl,
                                        'reason': f"盈利超过{min_profit:.2f}"
                                    })
                
                # 检查平仓
                if pos['direction'] == 1:
                    if current_price >= pos['tp']:
                        profit, actual_entry, actual_exit = calculate_trade_profit(pos['direction'], pos['entry'], pos['tp'], pos['lot'])
                        close_reason = "止盈"
                    elif current_price <= pos['sl']:
                        profit, actual_entry, actual_exit = calculate_trade_profit(pos['direction'], pos['entry'], pos['sl'], pos['lot'])
                        close_reason = "止损"
                        if pos['be_triggered'] and pos['sl'] == pos['entry']:
                            close_reason = f"保本止损"
                        elif len(pos['adjustments']) > 0 and pos['adjustments'][-1]['type'] == '移动止损':
                            close_reason = f"移动止损"
                else:
                    if current_price <= pos['tp']:
                        profit, actual_entry, actual_exit = calculate_trade_profit(pos['direction'], pos['entry'], pos['tp'], pos['lot'])
                        close_reason = "止盈"
                    elif current_price >= pos['sl']:
                        profit, actual_entry, actual_exit = calculate_trade_profit(pos['direction'], pos['entry'], pos['sl'], pos['lot'])
                        close_reason = "止损"
                        if pos['be_triggered'] and pos['sl'] == pos['entry']:
                            close_reason = f"保本止损"
                        elif len(pos['adjustments']) > 0 and pos['adjustments'][-1]['type'] == '移动止损':
                            close_reason = f"移动止损"
                
                if close_reason:
                    balance += profit
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
                        '当时余额': balance - profit,
                        '点差成本': SPREAD,
                        '市场类型': pos['market_type'],
                        '信号信心度': pos.get('confidence', 0)
                    }
                    trade_records.append(trade_record)
                    
                    market_type_stats[pos['market_type']]['trades'] += 1
                    market_type_stats[pos['market_type']]['profit'] += profit
                    if profit > 0:
                        market_type_stats[pos['market_type']]['wins'] += 1
                    
                    if test_type == "单月" or (test_type == "全年" and trade_count % 10 == 0):
                        color = "🟢" if profit > 0 else "🔴"
                        market_icon = "🔄" if pos['market_type'] == 'RANGING' else "📈"
                        print(f"{market_icon}{color} #{trade_record['序号']} | {trade_record['方向']} | "
                              f"市场:{pos['market_type']} | "
                              f"开:{trade_record['开仓价']:.2f}→平:{trade_record['平仓价']:.2f} | "
                              f"止:{pos['sl']:.2f} | 盈:{trade_record['止盈价']:.2f} | "
                              f"手数:{trade_record['手数']:.2f} | "
                              f"盈亏:${profit:+.2f} | 原因:{trade_record['平仓原因']}")
                    
                    trade_count += 1
                    if profit > 0:
                        wins += 1
                    
                    positions.remove(pos)
            
            # 记录权益曲线
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
            
            # 开仓逻辑
            if signal != 0 and len(positions) < TRADING_CONFIG['max_positions']:
                lot = calculate_position_size(balance, market_type)
                price = latest['close']
                stops = self.adaptive_manager.calculate_stops(signal, price, current_df, market_type, 
                                                            details.get('grid_info') if details else None)
                
                positions.append({
                    'direction': signal,
                    'entry': price,
                    'entry_time': current_time,
                    'entry_atr': current_atr,
                    'lot': lot,
                    'sl': stops['stop_loss'],
                    'initial_sl': stops['stop_loss'],
                    'tp': stops['take_profit'],
                    'be_triggered': False,
                    'adjustments': [],
                    'market_type': market_type,
                    'confidence': confidence,
                    'highest_price': price if signal == 1 else None,
                    'lowest_price': price if signal == -1 else None
                })
        
        # 最后一个月
        if current_month is not None:
            monthly_performance.append({
                'month': current_month,
                'start_balance': month_start_balance,
                'end_balance': balance,
                'return': ((balance - month_start_balance) / month_start_balance) * 100
            })
        
        # 平剩余持仓
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
        
        # 完整报告（你的原代码未删）
        print("\n" + "="*80)
        print(f"📊 {test_type}回测详细报告 - ADX自适应策略")
        print("="*80)
        
        print(f"\n📈 基本统计:")
        print(f"   交易笔数: {trade_count} 笔")
        if trade_count > 0:
            print(f"   盈利笔数: {wins} 笔")
            print(f"   亏损笔数: {trade_count - wins} 笔")
            print(f"   胜率: {wins/trade_count*100:.1f}%")
            if trade_records:
                avg_profit = sum(t['盈亏金额'] for t in trade_records) / len(trade_records)
                print(f"   平均每笔盈亏: ${avg_profit:+.2f}")
        
        print(f"\n🌐 市场类型表现:")
        for market_type, stats in market_type_stats.items():
            if stats['trades'] > 0:
                win_rate = stats['wins'] / stats['trades'] * 100
                avg_profit = stats['profit'] / stats['trades']
                market_name = "双边网格" if market_type == 'RANGING' else "单边趋势"
                print(f"   {market_name}: {stats['trades']}笔 | 胜率: {win_rate:.1f}% | "
                      f"总盈亏: ${stats['profit']:+.2f} | 平均: ${avg_profit:+.2f}")
        
        print(f"\n💰 资金表现:")
        print(f"   初始本金: ${initial_balance:,.2f}")
        print(f"   最终本金: ${balance:,.2f}")
        total_return = ((balance / initial_balance) - 1) * 100
        print(f"   总收益率: {total_return:+.2f}%")
        
        print(f"\n📉 回撤分析:")
        print(f"   最大回撤: {max_drawdown:.2f}%")
        if max_drawdown_details:
            print(f"   回撤高点: ${max_drawdown_details['peak_equity']:.2f}")
            print(f"   回撤低点: ${max_drawdown_details['trough_equity']:.2f}")
            print(f"   回撤发生时间: {max_drawdown_details['time'].strftime('%Y-%m-%d %H:%M')}")
        
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
        
        # 保存CSV
        if trade_records:
            try:
                import csv
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"backtest_adx_report_{test_type}_{start_year}_{start_month}_to_{end_year}_{end_month}_{timestamp}.csv"
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=trade_records[0].keys())
                    writer.writeheader()
                    writer.writerows(trade_records)
                print(f"\n💾 详细交易记录已保存到: {filename}")
            except Exception as e:
                print(f"\n⚠️  保存文件失败: {e}")
        
        return {
            'trade_records': trade_records,
            'equity_curve': equity_curve,
            'monthly_performance': monthly_performance,
            'market_type_stats': market_type_stats,
            'summary': {
                'initial_balance': initial_balance,
                'final_balance': balance,
                'total_return': total_return,
                'trade_count': trade_count,
                'win_rate': wins/trade_count*100 if trade_count > 0 else 0,
                'max_drawdown': max_drawdown,
                'max_drawdown_details': max_drawdown_details
            }
        }
    
    def check_risk_limits(self, balance):
        return self.risk_manager.check_daily_loss_limit(balance) or \
               self.risk_manager.check_max_drawdown(balance)
    
    def display_status(self, df, signal, market_type, details, market_info, account):
        """显示状态 - 显示ATR和ADX"""
        latest = df.iloc[-1]
        current_atr = latest['ATR'] if 'ATR' in latest and pd.notna(latest['ATR']) else 0.0
        
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
        print("="*70)
        print(f"💰 账户: 余额 ${account['balance']:.2f} | 净值 ${account['equity']:.2f} | 浮盈 ${account['profit']:.2f}")
        
        adx_display = f"{market_info['adx']:.1f}" if market_info['adx'] > 0 else "计算中..."
        atr_display = f"{current_atr:.2f}" if current_atr > 0 else "计算中..."
        print(f"📊 价格: {latest['close']:.2f} | ATR: {atr_display} | ADX: {adx_display} | 市场: {market_info['market_desc']} | 方向: {market_info['direction']}")
        
        strategy_desc = self.adaptive_manager.get_strategy_description(market_type)
        print(f"🤖 策略: {strategy_desc['icon']} {strategy_desc['name']}")
        
        if market_type == 'RANGING':
            if 'grid_info' in details and details['grid_info']:
                grid = details['grid_info']
                print(f"🔄 网格: {len(grid.get('buy_levels', []))}买层/{len(grid.get('sell_levels', []))}卖层 | 宽度: {grid.get('grid_width', 0):.2f}")
            grid_action = details.get('grid_action', 'HOLD')
            if grid_action != 'HOLD':
                print(f"📋 网格动作: {grid_action} | 建议手数: {details.get('grid_lot_size', 0):.3f}")
        else:
            if 'strategy_votes' in details:
                print(f"\n🗳️ 策略投票:")
                for name, vote in details['strategy_votes'].items():
                    emoji = "📈" if "买入" in vote else "📉" if "卖出" in vote else "➖"
                    print(f"   {emoji} {name}: {vote}")
        
        signal_text = "🟢 买入" if signal == 1 else "🔴 卖出" if signal == -1 else "⚪ 无信号"
        print(f"\n{signal_text}")
        positions = mt5.positions_get(symbol=TRADING_CONFIG['symbol'])
        positions_count = len(positions) if positions else 0
        print(f"📌 持仓: {positions_count} 张 (最大{TRADING_CONFIG['max_positions']}张)" if positions_count > 0 else "📌 当前无持仓")
    
    def execute_adaptive_trade(self, signal, df, balance, market_type, details):
        """执行自适应交易（趋势模式使用）"""
        latest = df.iloc[-1]
        price_info = self.mt5.get_current_price()
        if not price_info: return
        
        price = price_info['ask'] if signal == 1 else price_info['bid']
        
        def calculate_position_size(balance, market_type):
            lot_size = (balance / 100) * 0.01
            if market_type == 'RANGING':
                multiplier = 1.0
            else:
                multiplier = 1.2
            lot_size *= multiplier
            min_lot = 0.01
            max_lot = 1.0
            lot_size = max(min_lot, min(lot_size, max_lot))
            return round(lot_size, 2)
        
        lot_size = calculate_position_size(balance, market_type)
        
        grid_info = details.get('grid_info') if details else None
        stops = self.adaptive_manager.calculate_stops(signal, price, df, market_type, grid_info)
        
        sl = stops['stop_loss']
        tp = stops['take_profit']
        
        if self.mt5.open_position(signal, price, lot_size, sl, tp):
            self.trade_count += 1
            self.risk_manager.daily_trades += 1
            print(f"✅ 开仓成功! 方向: {'多' if signal == 1 else '空'} | 手数: {lot_size:.3f} | "
                  f"止损: {sl:.2f} | 止盈: {tp:.2f}")
    
    def manage_positions(self, df):
        """持仓管理（BE + 移动止损） - ATR NaN保护"""
        positions = mt5.positions_get(symbol=TRADING_CONFIG['symbol'])
        if positions is None or len(positions) == 0:
            return
        
        latest = df.iloc[-1]
        price_info = self.mt5.get_current_price()
        if not price_info:
            return
        
        atr = latest['ATR'] if 'ATR' in latest and pd.notna(latest['ATR']) else 10
        
        for position in positions:
            pos_type = 'LONG' if position.type == 0 else 'SHORT'
            current_price = price_info['bid'] if pos_type == 'LONG' else price_info['ask']
            
            if self.risk_manager.should_move_to_breakeven(pos_type, position.price_open, current_price, atr):
                new_sl = position.price_open
                self.mt5.modify_position(position, new_sl, position.tp)
                print(f"✅ [{position.ticket}] 移至盈亏平衡: {new_sl:.2f}")
            
            if RISK_CONFIG['trailing_stop']:
                new_sl = self.risk_manager.calculate_trailing_stop(
                    pos_type, position.price_open, current_price, position.sl, atr
                )
                if new_sl:
                    if (pos_type == 'LONG' and new_sl > position.sl) or (pos_type == 'SHORT' and new_sl < position.sl):
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
║            🤖 高级量化交易机器人 v4.0 - ADX自适应版              ║
║       ADX<20: 双边网格策略 | ADX≥20: 单边趋势策略                ║
╚════════════════════════════════════════════════════════════════════╝

📦 模块加载完成

🚀 正在启动...
""")
    
    bot = TradingBot()
    bot.start()