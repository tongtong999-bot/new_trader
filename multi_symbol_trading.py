#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v5.2策略多币种同时交易脚本
==========================

功能：
- 同时监控和交易多个币种
- 每个币种独立运行策略
- 统一日志和交易记录

使用方法：
python3 multi_symbol_trading.py
"""

import os
import sys
import time
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict
import threading

# 添加策略路径
sys.path.insert(0, str(Path(__file__).parent / 'strategies'))

from live_trading_v52 import LiveTradingBotV52, LiveTradingConfig

# ============================================================================
# 日志配置
# ============================================================================
log_dir = Path(__file__).parent / 'logs'
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / f'multi_symbol_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ============================================================================
# 多币种交易管理器
# ============================================================================
class MultiSymbolTradingManager:
    """多币种交易管理器"""
    
    def __init__(self, symbols: List[str], config_template: LiveTradingConfig = None):
        self.symbols = symbols
        self.bots: Dict[str, LiveTradingBotV52] = {}
        self.threads: Dict[str, threading.Thread] = {}
        self.running = False
        
        # 使用默认配置模板
        if config_template is None:
            config_template = LiveTradingConfig()
        
        self.config_template = config_template
    
    def create_bot_for_symbol(self, symbol: str) -> LiveTradingBotV52:
        """为指定币种创建交易机器人"""
        config = LiveTradingConfig()
        
        # 复制模板配置
        config.exchange_id = self.config_template.exchange_id
        config.api_key = self.config_template.api_key
        config.api_secret = self.config_template.api_secret
        config.passphrase = self.config_template.passphrase
        config.use_demo_trading = self.config_template.use_demo_trading
        config.paper_trading = self.config_template.paper_trading
        config.use_swap = self.config_template.use_swap
        config.check_interval = self.config_template.check_interval
        config.max_runtime_hours = self.config_template.max_runtime_hours
        
        # 设置币种
        config.symbol = symbol
        config.strategy_config = self.config_template.strategy_config
        config.strategy_config.SYMBOL = symbol
        
        # 创建机器人
        bot = LiveTradingBotV52(config)
        return bot
    
    def run_bot(self, symbol: str):
        """在单独线程中运行单个币种的交易机器人"""
        try:
            logger.info(f"[{symbol}] 启动交易机器人...")
            bot = self.bots[symbol]
            bot.run()
        except Exception as e:
            logger.error(f"[{symbol}] 运行出错: {e}")
            import traceback
            traceback.print_exc()
        finally:
            logger.info(f"[{symbol}] 交易机器人已停止")
    
    def start_all(self):
        """启动所有币种的交易"""
        logger.info("=" * 60)
        logger.info("多币种交易管理器启动")
        logger.info("=" * 60)
        logger.info(f"交易币种: {', '.join(self.symbols)}")
        logger.info(f"总币种数: {len(self.symbols)}")
        logger.info("")
        
        self.running = True
        
        # 为每个币种创建机器人
        for symbol in self.symbols:
            try:
                bot = self.create_bot_for_symbol(symbol)
                self.bots[symbol] = bot
                
                # 在单独线程中运行
                thread = threading.Thread(
                    target=self.run_bot,
                    args=(symbol,),
                    name=f"Trading-{symbol}",
                    daemon=True
                )
                self.threads[symbol] = thread
                thread.start()
                
                logger.info(f"[{symbol}] 已启动")
                
                # 短暂延迟，避免同时启动造成API限流
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"[{symbol}] 启动失败: {e}")
        
        logger.info("")
        logger.info("所有币种交易机器人已启动")
        logger.info("按 Ctrl+C 停止所有交易")
        logger.info("")
    
    def stop_all(self):
        """停止所有币种的交易"""
        logger.info("正在停止所有交易机器人...")
        self.running = False
        
        for symbol, bot in self.bots.items():
            try:
                bot.running = False
                logger.info(f"[{symbol}] 已发送停止信号")
            except Exception as e:
                logger.error(f"[{symbol}] 停止失败: {e}")
        
        # 等待所有线程结束
        for symbol, thread in self.threads.items():
            thread.join(timeout=10)
            if thread.is_alive():
                logger.warning(f"[{symbol}] 线程未在10秒内结束")
        
        logger.info("所有交易机器人已停止")
    
    def print_summary(self):
        """打印所有币种的交易总结"""
        logger.info("=" * 60)
        logger.info("多币种交易总结")
        logger.info("=" * 60)
        
        for symbol, bot in self.bots.items():
            logger.info(f"\n[{symbol}]")
            logger.info(f"  交易次数: {len(bot.trades_history)}")
            # TODO: 添加更多统计信息


# ============================================================================
# 主函数
# ============================================================================
def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='v5.2策略多币种交易')
    parser.add_argument('--symbols', type=str, nargs='+', default=None,
                        help='交易币种列表，例如: --symbols BTC/USDT:USDT ETH/USDT:USDT')
    parser.add_argument('--symbols-env', type=str, default=None,
                        help='从环境变量读取币种列表（逗号分隔）')
    parser.add_argument('--demo', action='store_true', default=None,
                        help='使用OKX模拟交易（Demo Trading）')
    parser.add_argument('--paper', action='store_true', default=None,
                        help='使用本地模拟盘（不下单）')
    parser.add_argument('--live', action='store_true', default=None,
                        help='使用实盘模式（谨慎使用）')
    parser.add_argument('--non-interactive', action='store_true',
                        help='非交互模式（用于Docker/云端部署，跳过所有input()）')
    
    args = parser.parse_args()
    
    # 默认交易币种列表
    default_symbols = [
        'BTC/USDT:USDT',
        'ETH/USDT:USDT',
        'SOL/USDT:USDT',
        'LINK/USDT:USDT',
        'AVAX/USDT:USDT',
        'XRP/USDT:USDT',
    ]
    
    # 默认非交互模式（适合云端部署）
    # 非交互模式：从环境变量或命令行参数读取配置
    non_interactive = args.non_interactive or os.getenv('NON_INTERACTIVE', '1').lower() in ('1', 'true', 'yes')
    if non_interactive:
        # 币种列表：命令行参数 > 环境变量 > 默认列表
        if args.symbols:
            symbols = args.symbols
        elif args.symbols_env and os.getenv(args.symbols_env):
            symbols = [s.strip() for s in os.getenv(args.symbols_env).split(',') if s.strip()]
        elif os.getenv('TRADING_SYMBOLS'):
            symbols = [s.strip() for s in os.getenv('TRADING_SYMBOLS').split(',') if s.strip()]
        else:
            symbols = default_symbols
        
        # 创建配置模板
        config = LiveTradingConfig()
        
        # 模式选择：命令行参数 > 环境变量 > 默认配置
        if args.live:
            config.use_demo_trading = False
            config.paper_trading = False
        elif args.paper:
            config.use_demo_trading = False
            config.paper_trading = True
        elif args.demo:
            config.use_demo_trading = True
            config.paper_trading = False
        elif os.getenv('TRADING_MODE') == 'live':
            config.use_demo_trading = False
            config.paper_trading = False
        elif os.getenv('TRADING_MODE') == 'paper':
            config.use_demo_trading = False
            config.paper_trading = True
        elif os.getenv('TRADING_MODE') == 'demo':
            config.use_demo_trading = True
            config.paper_trading = False
        
        logger.info("=" * 60)
        logger.info("v5.2策略多币种交易（非交互模式）")
        logger.info("=" * 60)
        logger.info(f"交易所: {config.exchange_id.upper()}")
        logger.info(f"模式: {'OKX模拟交易' if config.use_demo_trading else '本地模拟盘' if config.paper_trading else '实盘'}")
        logger.info(f"风险: {config.strategy_config.RISK_PER_TRADE}%")
        logger.info(f"仓位上限: {config.strategy_config.TIER1_MAX_POSITION}%")
        logger.info(f"交易币种数: {len(symbols)}")
        logger.info(f"币种列表: {', '.join(symbols)}")
        logger.info("=" * 60)
    else:
        # 交互模式（保持向后兼容）
        print("\n" + "=" * 60)
        print("v5.2策略多币种交易")
        print("=" * 60)
        
        print("\n当前配置的交易币种:")
        for i, sym in enumerate(default_symbols, 1):
            print(f"  {i}. {sym}")
        
        print("\n请选择:")
        print("  1. 使用默认币种列表启动")
        print("  2. 自定义币种列表")
        print("  3. 退出")
        
        choice = input("\n请选择 (1-3): ").strip()
        
        if choice == '1':
            symbols = default_symbols
        elif choice == '2':
            print("\n请输入币种（每行一个，输入空行结束）:")
            print("格式示例: BTC/USDT:USDT")
            symbols = []
            while True:
                sym = input("币种: ").strip()
                if not sym:
                    break
                if '/' in sym:
                    symbols.append(sym)
                else:
                    symbols.append(f"{sym}/USDT:USDT")
            
            if not symbols:
                print("未输入任何币种，退出")
                return
        elif choice == '3':
            print("退出")
            return
        else:
            print("无效选择")
            return
        
        # 创建配置模板
        config = LiveTradingConfig()
        
        print(f"\n配置信息:")
        print(f"  交易所: {config.exchange_id.upper()}")
        print(f"  模式: {'OKX模拟交易' if config.use_demo_trading else '本地模拟盘'}")
        print(f"  风险: {config.strategy_config.RISK_PER_TRADE}%")
        print(f"  仓位上限: {config.strategy_config.TIER1_MAX_POSITION}%")
        print(f"  交易币种数: {len(symbols)}")
        
        confirm = input("\n确认启动? (y/n): ").strip().lower()
        if confirm != 'y':
            print("已取消")
            return
    
    # 创建管理器并启动
    manager = MultiSymbolTradingManager(symbols, config)
    
    try:
        manager.start_all()
        
        # 保持主线程运行
        while manager.running:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("\n收到停止信号...")
    finally:
        manager.stop_all()
        manager.print_summary()


if __name__ == "__main__":
    main()
