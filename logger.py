"""
日志记录模块
"""

import logging
import sys
from datetime import datetime
import os

class TradingLogger:
    """交易日志记录器"""
    
    def __init__(self, config):
        self.config = config
        self.logger = None
        self.log_file = None
        self.setup_logger()
        
        # 交易统计
        self.trade_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.total_profit = 0
    
    def setup_logger(self):
        """设置日志记录器"""
        # 创建logger
        self.logger = logging.getLogger('TradingBot')
        self.logger.setLevel(logging.DEBUG)
        
        # 防止重复添加handler
        if self.logger.hasHandlers():
            self.logger.handlers.clear()
        
        # 控制台输出
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        # 文件输出
        if self.config.get('save_to_file', True):
            log_file = self.config.get('log_file', 'trading_bot.log')
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            
            # 文件格式更详细
            file_formatter = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)
            
            self.log_file = log_file
        
        # 控制台格式
        console_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
    
    def log_system(self, message):
        """系统日志"""
        self.logger.info(f"🤖 {message}")
    
    def log_trade(self, action, details):
        """交易日志"""
        self.trade_count += 1
        self.logger.info(f"💎 {action}: {details}")
        
        # 记录到交易CSV文件
        self._log_to_csv(action, details)
    
    def log_signal(self, signal_type, strength, details):
        """信号日志"""
        emoji = "📈" if signal_type == "BUY" else "📉" if signal_type == "SELL" else "⚪"
        self.logger.info(f"{emoji} 信号: {signal_type} (强度: {strength}) | {details}")
    
    def log_risk(self, level, message):
        """风险日志"""
        if level == "HIGH":
            self.logger.error(f"🚨 {message}")
        elif level == "MEDIUM":
            self.logger.warning(f"⚠️  {message}")
        else:
            self.logger.info(f"📊 {message}")
    
    def log_error(self, error_type, message):
        """错误日志"""
        self.logger.error(f"❌ {error_type}: {message}")
    
    def log_price(self, symbol, bid, ask, spread):
        """价格日志（周期性记录）"""
        self.logger.debug(f"💰 {symbol}: {bid:.2f}/{ask:.2f} (点差: {spread:.2f})")
    
    def _log_to_csv(self, action, details):
        """记录到CSV文件"""
        try:
            csv_file = 'trades.csv'
            file_exists = os.path.exists(csv_file)
            
            with open(csv_file, 'a', encoding='utf-8') as f:
                if not file_exists:
                    f.write("时间,动作,详情,盈亏\n")
                
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"{timestamp},{action},{details},0\n")
                
        except Exception as e:
            self.logger.error(f"CSV记录失败: {e}")
    
    def get_daily_summary(self):
        """获取当日摘要"""
        win_rate = (self.win_count / self.trade_count * 100) if self.trade_count > 0 else 0
        
        summary = f"""
📊 当日交易摘要:
   交易次数: {self.trade_count}
   盈利次数: {self.win_count}
   亏损次数: {self.loss_count}
   胜率: {win_rate:.1f}%
   总盈亏: ${self.total_profit:.2f}
"""
        self.logger.info(summary)
        return summary
    
    def log_margin_check(self, equity, free_margin, margin_usage, positions):
        """保证金检查日志"""
        self.logger.info(f"💳 保证金检查: 净值${equity:.2f}, 可用${free_margin:.2f}, 使用率{margin_usage:.1f}%, 持仓{len(positions)}")
        
        if margin_usage > 70:
            self.logger.warning(f"⚠️  保证金使用率过高: {margin_usage:.1f}%")
        if free_margin < 50:
            self.logger.warning(f"⚠️  可用保证金不足: ${free_margin:.2f}")