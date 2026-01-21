"""
MT5连接和交易执行模块
处理所有与MT5的交互
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

class MT5Connector:
    """MT5连接器"""
    
    def __init__(self, config):
        self.config = config
        self.symbol = config['symbol']
        self.timeframe = self._get_timeframe(config['timeframe'])
        self.magic_number = config['magic_number']
        self.connected = False
    
    def _get_timeframe(self, minutes):
        """将分钟数转换为MT5时间周期"""
        timeframe_map = {
            1: mt5.TIMEFRAME_M1,
            5: mt5.TIMEFRAME_M5,
            15: mt5.TIMEFRAME_M15,
            30: mt5.TIMEFRAME_M30,
            60: mt5.TIMEFRAME_H1,
            240: mt5.TIMEFRAME_H4,
            1440: mt5.TIMEFRAME_D1,
        }
        return timeframe_map.get(minutes, mt5.TIMEFRAME_M15)
    
    def connect(self, mt5_config):
        """
        连接到MT5
        
        参数:
        - mt5_config: 包含login, password, server, path的字典
        
        返回: True/False
        """
        # 尝试多个路径
        paths = [
            mt5_config.get('path'),
            r"C:\Program Files\MetaTrader 5\terminal64.exe",
            r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
        ]
        
        for path in paths:
            if path and self._try_initialize(path):
                break
        else:
            if not mt5.initialize():
                print(f"❌ MT5初始化失败: {mt5.last_error()}")
                return False
        
        # 登录账户
        authorized = mt5.login(
            login=mt5_config['login'],
            password=mt5_config['password'],
            server=mt5_config['server']
        )
        
        if authorized:
            account_info = mt5.account_info()
            print(f"\n✅ 成功连接到MT5")
            print(f"   账户: {account_info.login}")
            print(f"   服务器: {account_info.server}")
            print(f"   余额: ${account_info.balance:.2f}")
            print(f"   净值: ${account_info.equity:.2f}\n")
            self.connected = True
            return True
        else:
            print(f"❌ 登录失败: {mt5.last_error()}")
            return False
    
    def _try_initialize(self, path):
        """尝试用指定路径初始化MT5"""
        try:
            if mt5.initialize(path=path):
                print(f"✓ 使用路径: {path}")
                return True
        except:
            pass
        return False
    
    def get_historical_data(self, bars=500):
        """
        获取历史K线数据
        
        参数:
        - bars: 获取多少根K线
        
        返回: DataFrame
        """
        rates = mt5.copy_rates_from_pos(self.symbol, self.timeframe, 0, bars)
        
        if rates is None:
            print(f"❌ 获取数据失败: {mt5.last_error()}")
            return None
        
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        
        return df
    
    def get_account_info(self):
        """获取账户信息"""
        if not self.connected:
            return None
        
        account = mt5.account_info()
        if account is None:
            return None
        
        return {
            'balance': account.balance,
            'equity': account.equity,
            'margin': account.margin,
            'free_margin': account.margin_free,
            'profit': account.profit
        }
    
    def get_current_price(self):
        """获取当前价格"""
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            return None
        
        return {
            'bid': tick.bid,
            'ask': tick.ask,
            'time': datetime.fromtimestamp(tick.time)
        }
    
    def get_positions(self):
        """获取当前持仓"""
        positions = mt5.positions_get(symbol=self.symbol)
        if positions is None:
            return []
        
        # 只返回机器人的持仓
        bot_positions = [p for p in positions if p.magic == self.magic_number]
        return bot_positions
    
    def open_position(self, signal, price, lot_size, sl, tp):
        """
        开仓
        
        参数:
        - signal: 1=买入, -1=卖出
        - price: 开仓价格
        - lot_size: 手数
        - sl: 止损价格
        - tp: 止盈价格
        
        返回: True/False
        """

        
        # 确定订单类型
        if signal == 1:
            order_type = mt5.ORDER_TYPE_BUY
            action_str = "买入"
        else:
            order_type = mt5.ORDER_TYPE_SELL
            action_str = "卖出"
        
        # 构建订单请求
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": lot_size,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": self.magic_number,
            "comment": "Python Bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        # 发送订单
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"❌ 开仓失败: {result.comment}")
            return False
        
        print(f"\n{'📈' if signal == 1 else '📉'} {action_str}成功!")
        print(f"   价格: {price:.2f}")
        print(f"   手数: {lot_size}")
        print(f"   止损: {sl:.2f}")
        print(f"   止盈: {tp:.2f}")
        print(f"   订单号: {result.order}\n")
        
        return True
    
    def modify_position(self, position, new_sl, new_tp):
        """
        修改持仓的止损止盈
        
        参数:
        - position: 持仓对象
        - new_sl: 新止损价格
        - new_tp: 新止盈价格
        
        返回: True/False
        """
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": self.symbol,
            "position": position.ticket,
            "sl": new_sl,
            "tp": new_tp,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ 修改止损成功: {new_sl:.2f}")
            return True
        else:
            print(f"❌ 修改止损失败: {result.comment}")
            return False
    
    def close_position(self, position):
        """
        平仓
        
        参数:
        - position: 持仓对象
        
        返回: True/False
        """
        tick = mt5.symbol_info_tick(self.symbol)
        
        if position.type == mt5.ORDER_TYPE_BUY:
            price = tick.bid
            order_type = mt5.ORDER_TYPE_SELL
        else:
            price = tick.ask
            order_type = mt5.ORDER_TYPE_BUY
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": position.volume,
            "type": order_type,
            "position": position.ticket,
            "price": price,
            "deviation": 20,
            "magic": self.magic_number,
            "comment": "Close by bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            pnl = position.profit
            print(f"{'✅' if pnl > 0 else '❌'} 平仓成功 | 盈亏: ${pnl:.2f}")
            return True
        else:
            print(f"❌ 平仓失败: {result.comment}")
            return False
    
    def close_all_positions(self):
        """关闭所有持仓"""
        positions = self.get_positions()
        for position in positions:
            self.close_position(position)
    
    def disconnect(self):
        """断开MT5连接"""
        mt5.shutdown()
        self.connected = False
        print("✅ 已断开MT5连接")