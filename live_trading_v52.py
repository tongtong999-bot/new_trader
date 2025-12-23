#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v5.2策略实盘/模拟盘交易脚本
===========================

功能：
1. 支持OKX交易所（现货/合约）
2. 集成v5.2策略逻辑（纯趋势交易）
3. 支持模拟盘（真实行情，模拟下单）和实盘模式
4. 使用最新参数：RISK=3%, 仓位上限42%

使用前准备：
1. 配置API密钥（见下方配置部分）
2. 选择交易对（默认BTC/USDT）
3. 选择模式：模拟盘（推荐先测试）或实盘

警告：
- 实盘交易有风险，可能导致资金损失
- 请先在模拟盘充分测试
"""

import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import time
import os
import sys
import logging
import argparse
import requests
from pathlib import Path
import pickle
import json

# 添加策略路径
sys.path.insert(0, str(Path(__file__).parent / 'strategies'))

from box_strategy_v5_2 import (
    StrategyConfig,
    BacktestEngine,
    MarketRegime,
    SignalType,
    BigTrend
)

# ============================================================================
# 日志配置
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('live_trading_v52.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ============================================================================
# 配置管理
# ============================================================================
class LiveTradingConfig:
    """实盘交易配置"""
    
    def __init__(self):
        # ========== 交易所配置 ==========
        # 支持币安和OKX（从环境变量读取）
        self.exchange_id = os.getenv('EXCHANGE', 'okx').lower()  # 默认OKX，可改为binance
        
        if self.exchange_id == 'binance':
            # 币安API密钥
            self.api_key = os.getenv('BINANCE_API_KEY', '')
            self.api_secret = os.getenv('BINANCE_SECRET_KEY', '')
            self.passphrase = None  # 币安不需要passphrase
        elif self.exchange_id == 'okx':
            # OKX API密钥
            self.api_key = os.getenv('OKX_API_KEY', '')
            self.api_secret = os.getenv('OKX_API_SECRET', '')
            # OKX Passphrase（如有则配置；注意：使用半角字符，避免编码问题）
            self.passphrase = os.getenv('OKX_PASSPHRASE', '')
        else:
            raise ValueError(f"不支持的交易所: {self.exchange_id}，支持: binance, okx")
        
        # ========== OKX模拟交易配置 ==========
        # OKX模拟交易（Demo Trading）需要启用sandbox模式
        self.use_demo_trading = True  # 使用OKX模拟交易（Demo Trading）
        
        # ========== 交易配置 ==========
        # OKX模拟盘对交易对格式比较敏感，尝试使用标准格式
        self.symbol = 'BTC/USDT:USDT'  # OKX永续合约标准格式
        # 如果失败，可以尝试: 'BTC/USDT' (现货) 或 'BTC-USDT-SWAP' (OKX专用格式)
        self.use_swap = True  # 使用永续合约（推荐）或现货
        
        # ========== 杠杆配置 ==========
        # 杠杆倍数（仅永续合约有效）：从环境变量读取，默认不设置（使用账户默认杠杆）
        leverage_env = os.getenv('LEVERAGE', '')
        try:
            self.leverage = int(leverage_env) if leverage_env else None
        except (ValueError, TypeError):
            self.leverage = None  # 不设置杠杆，使用账户默认
        
        # ========== 模式选择 ==========
        # 注意：即使use_demo_trading=True，这里也可以控制是否真实下单
        # 如果use_demo_trading=True，会使用OKX模拟交易环境（真实下单但用模拟资金）
        self.paper_trading = False  # False=使用OKX模拟交易（真实下单，模拟资金）
        
        # ========== 策略参数（使用v5.2默认值）==========
        self.strategy_config = StrategyConfig()
        # 确保使用最新参数
        self.strategy_config.RISK_PER_TRADE = 3.0
        self.strategy_config.TIER1_MAX_POSITION = 42.0
        self.strategy_config.TIER2_MAX_POSITION = 42.0
        self.strategy_config.TIER3_MAX_POSITION = 42.0
        
        # ========== 运行配置 ==========
        self.check_interval = 60  # 检查信号间隔（秒）
        # 最大运行时长（小时）：从环境变量读取，默认24小时；设置为0或负数表示无限制
        max_runtime_env = os.getenv('MAX_RUNTIME_HOURS', '24')
        try:
            self.max_runtime_hours = float(max_runtime_env)
        except (ValueError, TypeError):
            self.max_runtime_hours = 24  # 默认24小时


# ============================================================================
# 实盘交易机器人
# ============================================================================
class LiveTradingBotV52:
    """v5.2策略实盘交易机器人"""
    
    def __init__(self, config: LiveTradingConfig):
        self.config = config
        self.exchange = None
        self.strategy_engine = None
        self._init_data_cache()  # 初始化数据缓存
        self.current_position = None
        self.trades_history = []
        self.running = False
        self.grid_positions = {}  # 网格持仓管理：{layer: position_info}
        
        # 通知配置（PushPlus Webhook）
        self.notification_webhook = os.getenv('PUSHPLUS_WEBHOOK', '')
        self.notification_topic = os.getenv('PUSHPLUS_TOPIC', '')  # 群组ID或群组名称
        self.notification_enabled = bool(self.notification_webhook)
        
        # 初始化交易所
        self._init_exchange()
        
        # 初始化策略引擎（用于信号生成）
        self._init_strategy_engine()
        
        logger.info(f"交易机器人初始化完成")
        if config.use_demo_trading:
            logger.info(f"模式: OKX模拟交易（Demo Trading）- 真实下单，模拟资金")
        else:
            logger.info(f"模式: {'模拟盘（本地模拟）' if config.paper_trading else '实盘'}")
        logger.info(f"交易对: {config.symbol}")
        logger.info(f"风险: {config.strategy_config.RISK_PER_TRADE}%")
        logger.info(f"仓位上限: {config.strategy_config.TIER1_MAX_POSITION}%")
        if config.use_swap:
            if config.leverage:
                logger.info(f"杠杆倍数: {config.leverage}x")
            else:
                logger.info(f"杠杆倍数: 使用账户默认（未配置）")
        if self.notification_enabled:
            logger.info(f"通知: 已启用 PushPlus Webhook")
            if self.notification_topic:
                logger.info(f"通知群组: {self.notification_topic}")
        else:
            logger.info(f"通知: 未配置（设置 PUSHPLUS_WEBHOOK 环境变量启用）")
    
    def _init_exchange(self):
        """初始化交易所连接"""
        try:
            exchange_class = getattr(ccxt, self.config.exchange_id)
            
            exchange_config = {
                'apiKey': self.config.api_key,
                'secret': self.config.api_secret,
                'enableRateLimit': True,
                'timeout': 60000,  # 增加到60秒
                'options': {
                    'defaultType': 'swap' if self.config.use_swap else 'spot',
                    # 关键修复：禁用fetch_currencies（OKX模拟盘不支持）
                    'fetchCurrencies': False,  # 不获取币种信息
                }
            }
            
            # OKX需要passphrase
            if self.config.exchange_id == 'okx' and self.config.passphrase:
                # OKX的passphrase在签名时使用，ccxt会自动处理编码
                # 直接传递即可，ccxt会在需要时进行正确的编码
                exchange_config['password'] = self.config.passphrase
            
            # OKX模拟交易（Demo Trading）配置
            # OKX模拟交易需要特殊header
            if self.config.exchange_id == 'okx' and self.config.use_demo_trading:
                if 'headers' not in exchange_config:
                    exchange_config['headers'] = {}
                exchange_config['headers']['x-simulated-trading'] = '1'  # 启用模拟交易模式
                logger.info("=" * 60)
                logger.info("✓ 已启用OKX模拟交易模式（Demo Trading）")
                logger.info("✓ 已添加模拟交易header: x-simulated-trading=1")
                logger.info("✓ 将连接到OKX模拟交易账户，不是实盘账户")
                logger.info("=" * 60)
            
            # 币安不需要特殊header
            
            # 代理配置（需要在header配置之后）
            http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
            https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
            
            # 显示代理配置状态
            if http_proxy or https_proxy:
                logger.info(f"代理配置: {https_proxy or http_proxy}")
                exchange_config['proxies'] = {
                    'http': http_proxy,
                    'https': https_proxy or http_proxy,
                }
            else:
                logger.warning("未配置代理，如果连接失败可能需要配置代理")
            
            self.exchange = exchange_class(exchange_config)
            
            # 币安不需要特殊处理，OKX需要覆盖fetch_currencies和load_markets
            if self.config.exchange_id == 'okx':
                # 关键修复：覆盖fetch_currencies和load_markets（OKX模拟盘不支持）
                # 问题1：即使设置fetchCurrencies=False，load_markets()仍会强制调用fetch_currencies()
                # 问题2：load_markets()解析市场数据时，base/quote可能是None，导致TypeError
                # 解决：直接覆盖这两个函数，避免调用API和解析错误
            
                def empty_fetch_currencies(params={}):
                    """覆盖fetch_currencies，返回空结果，避免OKX模拟盘的50038错误"""
                    logger.debug("fetch_currencies被调用，但已禁用（OKX模拟盘不支持）")
                    return {}
                
                def safe_load_markets(params={}, reload=False):
                    """覆盖load_markets，返回空markets，避免解析错误"""
                    logger.debug("load_markets被调用，但已禁用（OKX模拟盘不支持）")
                    # 初始化markets和markets_by_id为空字典
                    if not hasattr(self.exchange, 'markets') or self.exchange.markets is None:
                        self.exchange.markets = {}
                    if not hasattr(self.exchange, 'markets_by_id') or self.exchange.markets_by_id is None:
                        self.exchange.markets_by_id = {}
                    return self.exchange.markets
                
                def safe_market(symbol):
                    """覆盖market函数，手动创建market信息，使用正确的OKX格式"""
                    # 如果markets为空或symbol不存在，手动创建market信息
                    if not self.exchange.markets or symbol not in self.exchange.markets:
                        # 解析symbol，手动创建market
                        # ccxt格式: BTC/USDT:USDT
                        # OKX格式: BTC-USDT-SWAP（关键！）
                        
                        base = None
                        quote = 'USDT'
                        inst_type = 'SWAP'
                        
                        if ':' in symbol:
                            # BTC/USDT:USDT 格式（永续合约）
                            main_part = symbol.split(':')[0]  # BTC/USDT
                            parts = main_part.split('/')
                            base = parts[0]  # BTC
                            quote = parts[1] if len(parts) > 1 else 'USDT'  # USDT
                            inst_type = 'SWAP'
                        elif '/' in symbol:
                            # BTC/USDT 格式（现货）
                            parts = symbol.split('/')
                            base = parts[0]  # BTC
                            quote = parts[1] if len(parts) > 1 else 'USDT'  # USDT
                            inst_type = 'SPOT'
                        else:
                            # 未知格式
                            return {}
                        
                        if not base:
                            return {}
                        
                        # OKX格式的ID（关键：必须使用这个格式）
                        okx_id = f"{base}-{quote}-{inst_type}"
                        
                        market_info = {
                            'id': okx_id,  # OKX格式: BTC-USDT-SWAP（这是关键！）
                            'symbol': symbol,  # ccxt格式: BTC/USDT:USDT
                            'base': base,
                            'quote': quote,
                            'type': 'swap' if inst_type == 'SWAP' else 'spot',
                            'active': True,
                        }
                        
                        # 添加到markets
                        if not self.exchange.markets:
                            self.exchange.markets = {}
                        if not self.exchange.markets_by_id:
                            self.exchange.markets_by_id = {}
                        
                        self.exchange.markets[symbol] = market_info
                        self.exchange.markets_by_id[okx_id] = market_info
                        
                        logger.debug(f"创建market: {symbol} -> {okx_id}")
                        return market_info
                    
                    # 如果markets中有，直接返回
                    return self.exchange.markets.get(symbol, {})
                
                # 覆盖market方法
                self.exchange.market = safe_market
                
                # 覆盖函数
                self.exchange.fetch_currencies = empty_fetch_currencies
                self.exchange.load_markets = safe_load_markets
                
                # 初始化markets和markets_by_id为空字典（避免后续调用时出错）
                if not hasattr(self.exchange, 'markets') or self.exchange.markets is None:
                    self.exchange.markets = {}
                if not hasattr(self.exchange, 'markets_by_id') or self.exchange.markets_by_id is None:
                    self.exchange.markets_by_id = {}
                
                # 同时设置选项
                try:
                    self.exchange.options['fetchCurrencies'] = False
                    self.exchange.options['loadMarketsOnStartup'] = False
                except:
                    pass
                
                logger.info("✓ 已覆盖fetch_currencies和load_markets函数（避免OKX模拟盘错误）")
            
            # 测试连接（带重试机制）
            max_retries = 3
            retry_delay = 5
            
            for attempt in range(max_retries):
                try:
                    logger.info(f"测试连接... (尝试 {attempt + 1}/{max_retries})")
                    
                    # 显示当前配置
                    if self.config.use_demo_trading:
                        logger.info("模式: OKX模拟交易（Demo Trading）")
                        logger.info("Header: x-simulated-trading=1")
                    
                    # 获取余额
                    balance = self.exchange.fetch_balance()
                    usdt_balance = balance.get('USDT', {}).get('free', 0)
                    logger.info(f"✓ 交易所连接成功")
                    if self.config.exchange_id == 'binance':
                        if self.config.use_demo_trading:
                            logger.info(f"✓ 币安测试网余额: {usdt_balance:.2f} USDT")
                        else:
                            logger.info(f"✓ 币安实盘余额: {usdt_balance:.2f} USDT")
                    elif self.config.exchange_id == 'okx':
                        if self.config.use_demo_trading:
                            logger.info(f"✓ 模拟资金余额: {usdt_balance:.2f} USDT（Demo Trading）")
                            logger.info("✓ 确认：已连接到OKX模拟交易账户，不是实盘账户")
                        else:
                            logger.info(f"USDT余额: {usdt_balance:.2f}")
                    break  # 成功，退出重试循环
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"连接失败，{retry_delay}秒后重试... ({e})")
                        time.sleep(retry_delay)
                    else:
                        logger.error(f"连接失败（已重试{max_retries}次）: {e}")
                        # 如果是网络超时，提供解决建议
                        if 'timeout' in str(e).lower() or 'timed out' in str(e).lower():
                            logger.error("=" * 60)
                            logger.error("网络连接超时，可能的原因：")
                            logger.error("1. 网络连接不稳定")
                            logger.error("2. 需要配置代理（如果在中国大陆）")
                            logger.error("3. 防火墙阻止连接")
                            logger.error("4. OKX API暂时不可用")
                            logger.error("=" * 60)
                            logger.error("建议：")
                            logger.error("1. 检查网络连接")
                            logger.error("2. 尝试配置代理（设置HTTP_PROXY环境变量）")
                            logger.error("3. 稍后重试")
                            logger.error("4. 或使用本地模拟盘模式（选项2）")
                            logger.error("=" * 60)
                        if not self.config.paper_trading:
                            raise
                        else:
                            logger.warning("模拟盘模式：无法获取余额（仅获取行情）")
                
        except Exception as e:
            logger.error(f"初始化交易所失败: {e}")
            raise
    
    def _init_strategy_engine(self):
        """初始化策略引擎（用于信号生成）"""
        cfg = self.config.strategy_config
        cfg.SYMBOL = self.config.symbol
        self.strategy_engine = BacktestEngine(cfg)
        logger.info("策略引擎初始化完成")
    
    def _init_data_cache(self):
        """初始化数据缓存"""
        cache_dir = Path(__file__).parent / 'data_cache'
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir = cache_dir
        logger.info(f"数据缓存目录: {cache_dir}")
    
    def _get_cache_file(self, symbol: str, timeframe: str) -> Path:
        """获取缓存文件路径"""
        safe_symbol = symbol.replace('/', '_').replace(':', '_')
        return self.cache_dir / f"{safe_symbol}_{timeframe}.pkl"
    
    def _load_cache(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """从缓存加载数据"""
        cache_file = self._get_cache_file(symbol, timeframe)
        if cache_file.exists():
            try:
                with open(cache_file, 'rb') as f:
                    data = pickle.load(f)
                    if isinstance(data, pd.DataFrame) and len(data) > 0:
                        logger.info(f"从缓存加载 {symbol} {timeframe} 数据: {len(data)} 条，最后时间: {data['timestamp'].iloc[-1]}")
                        return data
            except Exception as e:
                logger.warning(f"加载缓存失败: {e}")
        return None
    
    def _save_cache(self, symbol: str, timeframe: str, data: pd.DataFrame):
        """保存数据到缓存"""
        cache_file = self._get_cache_file(symbol, timeframe)
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(data, f)
            logger.debug(f"数据已缓存: {cache_file} ({len(data)} 条)")
        except Exception as e:
            logger.warning(f"保存缓存失败: {e}")
    
    def _send_notification(self, title: str, content: str, trade_type: str = 'info'):
        """发送 PushPlus Webhook 通知"""
        if not self.notification_enabled:
            return
        
        try:
            # 构造消息内容
            mode_text = "模拟交易" if self.config.use_demo_trading else ("本地模拟盘" if self.config.paper_trading else "实盘")
            full_content = f"""【交易通知】{title}

交易对: {self.config.symbol}
模式: {mode_text}
时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{content}"""
            
            webhook_url = self.notification_webhook
            
            # 判断是 PushPlus Token 还是自定义 Webhook URL
            if not webhook_url.startswith('http'):
                # PushPlus Token 格式，使用 PushPlus API
                pushplus_api_url = "http://www.pushplus.plus/send"
                payload = {
                    'token': webhook_url,
                    'title': title,
                    'content': full_content,
                    'template': 'txt'
                }
                # 如果配置了群组（topic），添加到payload
                if self.notification_topic:
                    payload['topic'] = self.notification_topic
                response = requests.post(pushplus_api_url, json=payload, timeout=10)
            else:
                # 自定义 Webhook URL（POST JSON）
                payload = {
                    'title': title,
                    'content': full_content,
                    'type': trade_type,
                    'symbol': self.config.symbol,
                    'mode': mode_text,
                    'timestamp': datetime.now().isoformat()
                }
                response = requests.post(webhook_url, json=payload, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('code') == 200:  # PushPlus 成功返回 code=200
                    logger.debug(f"通知发送成功: {title}")
                else:
                    logger.warning(f"通知发送失败: {result.get('msg', 'Unknown error')}")
            else:
                logger.warning(f"通知发送失败: HTTP {response.status_code} - {response.text}")
        except Exception as e:
            logger.warning(f"发送通知失败: {e}")
    
    def fetch_historical_data(self, limit: int = None) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame]]:
        """
        获取历史K线数据（15m, 1h, 4h）- 带缓存机制
        
        Args:
            limit: 获取多少条K线（None时自动计算，确保至少有70天数据用于计算箱体）
        
        策略：
        1. 先从缓存加载已有数据
        2. 只获取缓存之后的新数据
        3. 合并新旧数据
        4. 保存到缓存
        """
        # 【修复】自动计算需要的K线数量
        # 策略需要至少70天数据来计算箱体（BOX_LOOKBACK_PERIODS = 70）
        # 70天 * 96条/天（15分钟K线） = 6,720条
        # 为了安全，获取更多数据：80天 * 96 = 7,680条
        min_required = 70 * 96  # 至少需要的数据量
        if limit is None:
            min_days = 80  # 至少80天数据
            limit = min_days * 96  # 15分钟K线：每天96条（24小时 * 4）
            logger.info(f"自动计算历史数据量: {limit}条（约{min_days}天），用于计算箱体等指标")
        
        # 【新增】尝试从缓存加载
        cached_15m = self._load_cache(self.config.symbol, '15m')
        last_cached_ts = None
        
        if cached_15m is not None and len(cached_15m) > 0:
            last_cached_ts = int(pd.Timestamp(cached_15m['timestamp'].iloc[-1]).timestamp() * 1000)
            cache_age_hours = (datetime.now().timestamp() * 1000 - last_cached_ts) / (1000 * 3600)
            logger.info(f"缓存中有 {len(cached_15m)} 条15m数据，最后时间: {cached_15m['timestamp'].iloc[-1]}（{cache_age_hours:.1f}小时前）")
            
            # 如果缓存数据足够新（1小时内）且数据量足够，直接使用缓存
            if cache_age_hours < 1 and len(cached_15m) >= min_required:
                logger.info(f"缓存数据足够新且数据量足够，直接使用缓存（跳过数据获取）")
                # 从15m重采样生成1h和4h
                cached_15m_indexed = cached_15m.set_index('timestamp')
                cached_1h = cached_15m_indexed.resample('1h').agg({
                    'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
                }).dropna().reset_index()
                cached_4h = cached_15m_indexed.resample('4h').agg({
                    'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
                }).dropna().reset_index()
                return cached_15m, cached_1h, cached_4h
        try:
            # 确保markets已初始化（避免fetch_ohlcv触发load_markets）
            if not hasattr(self.exchange, 'markets') or not self.exchange.markets:
                self.exchange.markets = {}
            
            # 转换symbol格式：ccxt格式 -> OKX格式
            # BTC/USDT:USDT -> BTC-USDT-SWAP
            okx_symbol = self.config.symbol.replace('/', '-').replace(':USDT', '-SWAP')
            
            # 如果markets中没有，手动创建
            if self.config.symbol not in self.exchange.markets:
                self.exchange.markets[self.config.symbol] = {
                    'id': okx_symbol,
                    'symbol': self.config.symbol,
                    'base': self.config.symbol.split('/')[0],
                    'quote': 'USDT',
                    'type': 'swap',
                    'active': True,
                }
            
            # 获取15分钟数据
            timeframe_15m = '15m'
            
            # 【新增】如果有缓存，只获取新数据
            new_data_list = []
            if last_cached_ts:
                # 从缓存最后时间开始获取新数据
                start_ts = last_cached_ts + (15 * 60 * 1000)  # 从下一条K线开始
                logger.info(f"从缓存最后时间开始获取新数据: {pd.Timestamp(start_ts, unit='ms')}")
                
                try:
                    # 获取新数据（最多1000条，通常只需要几条新K线）
                    new_ohlcv = self.exchange.fetch_ohlcv(
                        self.config.symbol,
                        timeframe_15m,
                        since=start_ts,
                        limit=1000  # 获取最多1000条新数据
                    )
                    
                    if new_ohlcv:
                        # 过滤掉缓存中已有的数据（使用毫秒时间戳比较）
                        cached_timestamps = set()
                        if cached_15m is not None:
                            for ts in cached_15m['timestamp']:
                                cached_timestamps.add(int(pd.Timestamp(ts).timestamp() * 1000))
                        
                        # 【修复Bug 6】使用更宽松的时间戳比较条件
                        new_items = [
                            item for item in new_ohlcv 
                            if item[0] not in cached_timestamps and item[0] >= last_cached_ts
                        ]
                        
                        if new_items:
                            new_data_list = new_items
                            logger.info(f"获取了 {len(new_items)} 条新15m数据")
                        else:
                            logger.info("没有新数据，使用缓存数据")
                    else:
                        logger.info("没有获取到新数据，使用缓存数据")
                except Exception as e:
                    logger.warning(f"获取新数据失败，使用缓存: {e}")
                    if cached_15m is not None and len(cached_15m) >= min_required:
                        # 使用缓存数据
                        cached_15m_indexed = cached_15m.set_index('timestamp')
                        cached_1h = cached_15m_indexed.resample('1h').agg({
                            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
                        }).dropna().reset_index()
                        cached_4h = cached_15m_indexed.resample('4h').agg({
                            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
                        }).dropna().reset_index()
                        return cached_15m, cached_1h, cached_4h
            
            # 【修复】如果limit很大，需要分批获取
            # 币安/OKX的fetch_ohlcv limit最大通常是1000-1500
            max_limit_per_request = 1000
            ohlcv_15m = []
            
            # 如果有缓存，先使用缓存数据
            if cached_15m is not None and len(cached_15m) > 0:
                ohlcv_15m = []
                for idx, row in cached_15m.iterrows():
                    ts_ms = int(pd.Timestamp(row['timestamp']).timestamp() * 1000)
                    ohlcv_15m.append([
                        ts_ms,
                        row['open'], row['high'], row['low'], row['close'], row['volume']
                    ])
                logger.info(f"使用缓存数据作为基础: {len(ohlcv_15m)} 条")
            
            # 如果有新数据，添加到列表
            if new_data_list:
                ohlcv_15m.extend(new_data_list)
                logger.info(f"合并新数据: 总计 {len(ohlcv_15m)} 条")
            
            # 如果已经有足够的数据（从缓存+新数据），直接使用
            if len(ohlcv_15m) >= min_required:
                # 转换为DataFrame
                df_15m = pd.DataFrame(
                    ohlcv_15m,
                    columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )
                df_15m['timestamp'] = pd.to_datetime(df_15m['timestamp'], unit='ms')
                df_15m = df_15m.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
                
                # 只保留最新的数据（避免数据过多）
                if len(df_15m) > limit * 2:
                    df_15m = df_15m.tail(limit * 2).reset_index(drop=True)
                
                # 保存到缓存
                self._save_cache(self.config.symbol, '15m', df_15m)
                
                # 重采样生成1h和4h
                df_15m_indexed = df_15m.set_index('timestamp')
                df_1h = df_15m_indexed.resample('1h').agg({
                    'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
                }).dropna().reset_index()
                df_4h = df_15m_indexed.resample('4h').agg({
                    'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
                }).dropna().reset_index()
                
                logger.info(f"使用缓存+新数据: 总计 {len(df_15m)} 条15m数据")
                return df_15m, df_1h, df_4h
            
            # 如果没有缓存或数据不足，需要获取全部历史数据
            if limit <= max_limit_per_request:
                # 【修复】明确指定时间范围，确保获取足够的历史数据
                # 计算起始时间：从当前时间往前推 limit * 15分钟
                end_ts = int(datetime.now().timestamp() * 1000)
                # 往前推 limit * 15分钟，确保获取足够的历史数据
                start_ts = end_ts - (limit * 15 * 60 * 1000)
                
                # 使用since参数明确指定起始时间
                ohlcv_15m = self.exchange.fetch_ohlcv(
                    self.config.symbol,
                    timeframe_15m,
                    since=start_ts,  # 【关键】明确指定起始时间
                    limit=limit
                )
                logger.info(f"获取了 {len(ohlcv_15m)} 条15m数据（请求{limit}条，时间范围：{datetime.fromtimestamp(start_ts/1000)} 到 {datetime.fromtimestamp(end_ts/1000)}）")
                
                # 【重要】检查实际获取的数据量
                if len(ohlcv_15m) < limit:
                    logger.warning(f"⚠️ 实际获取的数据量（{len(ohlcv_15m)}条）少于请求量（{limit}条）！")
                    logger.warning(f"   这可能导致指标计算不准确。可能需要分批获取或检查API限制。")
            else:
                # 分批获取历史数据
                # fetch_ohlcv的since参数：从指定时间点开始往前获取limit条数据
                # 策略：从最新开始，逐步往前获取
                num_batches = (limit + max_limit_per_request - 1) // max_limit_per_request
                logger.info(f"数据量较大（需要{limit}条），分{num_batches}批获取...")
                
                # 第一批：从最新开始获取（明确指定时间范围）
                try:
                    end_ts = int(datetime.now().timestamp() * 1000)
                    first_batch_limit = min(max_limit_per_request, limit)
                    # 往前推 first_batch_limit * 15分钟
                    start_ts = end_ts - (first_batch_limit * 15 * 60 * 1000)
                    
                    first_batch = self.exchange.fetch_ohlcv(
                        self.config.symbol,
                        timeframe_15m,
                        since=start_ts,  # 【关键】明确指定起始时间
                        limit=first_batch_limit
                    )
                    if first_batch:
                        ohlcv_15m.extend(first_batch)
                        logger.info(f"批次 1/{num_batches}: 获取了 {len(first_batch)} 条数据（请求{first_batch_limit}条）")
                        
                        # 检查实际获取量
                        if len(first_batch) < first_batch_limit:
                            logger.warning(f"⚠️ 第一批实际获取 {len(first_batch)} 条，少于请求的 {first_batch_limit} 条")
                except Exception as e:
                    logger.error(f"第一批数据获取失败: {e}")
                    raise
                
                # 后续批次：从上一批的最早时间往前获取
                for batch in range(1, num_batches):
                    if len(ohlcv_15m) >= limit:
                        break
                    
                    # 获取上一批的最早时间
                    if not ohlcv_15m:
                        break
                    
                    earliest_ts = min(item[0] for item in ohlcv_15m)
                    batch_limit = min(max_limit_per_request, limit - len(ohlcv_15m))
                    
                    try:
                        # 【修复】从最早时间往前推更多时间，确保能获取到更早的数据
                        # fetch_ohlcv的since参数：从指定时间点开始往前获取limit条数据
                        # 关键：需要从足够早的时间点开始，才能获取到更早的数据
                        # 往前推 batch_limit * 15分钟，确保能获取到更早的数据
                        batch_start_ts = earliest_ts - (batch_limit * 15 * 60 * 1000)  # 往前推足够的时间
                        
                        logger.debug(f"批次 {batch+1}: 从 {pd.Timestamp(batch_start_ts, unit='ms')} 开始获取（最早数据: {pd.Timestamp(earliest_ts, unit='ms')}）")
                        
                        batch_data = self.exchange.fetch_ohlcv(
                            self.config.symbol,
                            timeframe_15m,
                            since=batch_start_ts,  # 【修复】从更早的时间点开始
                            limit=batch_limit
                        )
                        
                        if batch_data:
                            # 过滤掉重复的数据（时间戳已存在的）
                            existing_timestamps = {item[0] for item in ohlcv_15m}
                            # 只保留时间戳小于earliest_ts的数据（更早的数据）
                            new_data = [
                                item for item in batch_data 
                                if item[0] not in existing_timestamps and item[0] < earliest_ts
                            ]
                            
                            if new_data:
                                ohlcv_15m.extend(new_data)
                                logger.info(f"批次 {batch+1}/{num_batches}: 获取了 {len(new_data)} 条新数据（去重后，时间范围：{pd.Timestamp(min(item[0] for item in new_data), unit='ms')} 到 {pd.Timestamp(max(item[0] for item in new_data), unit='ms')}）")
                            else:
                                # 没有新数据，可能原因：
                                # 1. 时间范围重叠（batch_start_ts到earliest_ts之间没有新数据）
                                # 2. 已经获取完所有可用历史数据
                                # 尝试从更早的时间点获取
                                if batch < num_batches - 1:  # 不是最后一批，继续尝试
                                    logger.info(f"批次 {batch+1}: 没有新数据，尝试从更早的时间点获取...")
                                    # 往前推更多时间
                                    batch_start_ts = earliest_ts - (batch_limit * 15 * 60 * 1000 * 2)  # 往前推2倍时间
                                    continue
                                else:
                                    logger.warning(f"批次 {batch+1}: 没有新数据，可能已获取完所有可用历史数据")
                                    break
                        else:
                            logger.warning(f"批次 {batch+1}: 获取失败，返回空数据")
                            if batch < num_batches - 1:
                                continue
                            else:
                                break
                        
                        time_module.sleep(0.2)  # 避免请求过快
                    except Exception as e:
                        logger.warning(f"批次 {batch+1} 获取失败: {e}")
                        # 如果已经获取了足够的数据，继续使用
                        min_required_for_calc = 70 * 96  # 至少需要70天数据
                        if len(ohlcv_15m) >= min_required_for_calc:
                            logger.info(f"已获取 {len(ohlcv_15m)} 条数据，虽然未达到目标{limit}条，但已满足最低要求（{min_required_for_calc}条）")
                            break
                        else:
                            raise
                
                # 排序（按时间从旧到新）
                ohlcv_15m = sorted(ohlcv_15m, key=lambda x: x[0])
                # 去重（按时间戳）
                seen_ts = set()
                unique_ohlcv = []
                for item in ohlcv_15m:
                    if item[0] not in seen_ts:
                        seen_ts.add(item[0])
                        unique_ohlcv.append(item)
                ohlcv_15m = unique_ohlcv
                
                # 只保留最新的limit条（避免数据过多）
                if len(ohlcv_15m) > limit * 2:
                    ohlcv_15m = ohlcv_15m[-limit * 2:]
                    logger.info(f"数据过多，只保留最新的 {len(ohlcv_15m)} 条")
                
                logger.info(f"总共获取了 {len(ohlcv_15m)} 条15m数据（最终，去重后）")
            
            df_15m = pd.DataFrame(
                ohlcv_15m,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            df_15m['timestamp'] = pd.to_datetime(df_15m['timestamp'], unit='ms')
            
            # 重采样到1h和4h
            df_15m_indexed = df_15m.set_index('timestamp')
            df_1h = df_15m_indexed.resample('1h').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna().reset_index()
            
            df_4h = df_15m_indexed.resample('4h').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna().reset_index()
            
            # 【新增】保存到缓存
            self._save_cache(self.config.symbol, '15m', df_15m)
            logger.info(f"数据已保存到缓存: {len(df_15m)} 条15m数据")
            
            return df_15m, df_1h, df_4h
            
        except Exception as e:
            logger.error(f"获取历史数据失败: {e}")
            return None, None, None
    
    def get_current_position(self) -> Optional[Dict]:
        """获取当前持仓"""
        # 如果使用本地模拟盘，返回模拟持仓
        if self.config.paper_trading and not self.config.use_demo_trading:
            return self.current_position
        
        # OKX模拟交易或实盘：从交易所获取真实持仓
        try:
            # 方法1: 尝试使用ccxt的fetch_positions
            try:
                positions = self.exchange.fetch_positions([self.config.symbol])
                for pos in positions:
                    if pos.get('contracts') and float(pos['contracts']) != 0:
                        return {
                            'side': 'long' if float(pos['contracts']) > 0 else 'short',
                            'size': abs(float(pos['contracts'])),
                            'entry_price': float(pos['entryPrice']) if pos.get('entryPrice') else 0,
                            'unrealized_pnl': float(pos['unrealizedPnl']) if pos.get('unrealizedPnl') else 0,
                        }
            except Exception as e1:
                logger.debug(f"ccxt fetch_positions失败，尝试OKX原生API: {e1}")
                
                # 方法2: 使用OKX原生API
                try:
                    # 获取OKX格式的ID
                    market_info = self.exchange.market(self.config.symbol)
                    okx_id = market_info.get('id', '')
                    
                    if okx_id:
                        # 直接调用OKX API
                        response = self.exchange.private_get_account_positions({'instId': okx_id})
                        if response and 'data' in response and response['data']:
                            for pos_data in response['data']:
                                pos_size = float(pos_data.get('pos', 0))
                                if pos_size != 0:
                                    # OKX返回的pos: 正数=做多，负数=做空
                                    return {
                                        'side': 'long' if pos_size > 0 else 'short',
                                        'size': abs(pos_size),
                                        'entry_price': float(pos_data.get('avgPx', 0)) if pos_data.get('avgPx') else 0,
                                        'unrealized_pnl': float(pos_data.get('upl', 0)) if pos_data.get('upl') else 0,
                                    }
                except Exception as e2:
                    logger.debug(f"OKX原生API也失败: {e2}")
                    
                    # 方法3: 获取所有持仓，然后过滤
                    try:
                        response = self.exchange.private_get_account_positions({})
                        if response and 'data' in response and response['data']:
                            market_info = self.exchange.market(self.config.symbol)
                            okx_id = market_info.get('id', '')
                            
                            for pos_data in response['data']:
                                if pos_data.get('instId') == okx_id:
                                    pos_size = float(pos_data.get('pos', 0))
                                    if pos_size != 0:
                                        return {
                                            'side': 'long' if pos_size > 0 else 'short',
                                            'size': abs(pos_size),
                                            'entry_price': float(pos_data.get('avgPx', 0)) if pos_data.get('avgPx') else 0,
                                            'unrealized_pnl': float(pos_data.get('upl', 0)) if pos_data.get('upl') else 0,
                                        }
                    except Exception as e3:
                        logger.error(f"所有方法都失败: {e3}")
                        raise e3
            
            # 没有持仓
            return None
            
        except Exception as e:
            logger.error(f"获取持仓失败: {e}")
            # 不抛出异常，返回None，允许程序继续运行
            return None
    
    def check_signals(self) -> Optional[Dict]:
        """检查交易信号"""
        # 【修复】不指定limit，使用自动计算（确保有足够的历史数据）
        df_15m, df_1h, df_4h = self.fetch_historical_data(limit=None)
        if df_15m is None:
            logger.warning("数据获取失败，无法生成信号")
            return None
        
        # 【修复】检查数据量是否足够（至少需要70天用于计算箱体）
        min_required = 70 * 96  # 70天 * 96条/天
        if len(df_15m) < min_required:
            logger.warning(f"数据不足（{len(df_15m)}条），至少需要{min_required}条（70天）用于计算箱体等指标")
            logger.warning("这可能导致市场状态判断不准确，建议检查数据获取逻辑")
            # 【修复Bug 8】数据不足时，不生成信号，避免错误交易
            logger.error("数据不足，跳过本次信号检查")
            return None
        
        try:
            # 使用策略引擎生成信号
            # 注意：策略引擎需要预处理数据
            self.strategy_engine._precalc(df_15m.copy(), df_1h.copy(), df_4h.copy())
            
            # 获取当前索引
            current_idx = len(df_15m) - 1
            current_time = df_15m['timestamp'].iloc[current_idx]
            current_price = df_15m['close'].iloc[current_idx]
            
            # 获取市场状态
            htf_idx = self.strategy_engine._idx(current_time, self.strategy_engine._cache['htf_ts'])
            mtf_idx = self.strategy_engine._idx(current_time, self.strategy_engine._cache['mtf_ts'])
            
            if htf_idx is None or mtf_idx is None:
                return None
            
            regime = self.strategy_engine._get_market_regime(htf_idx, current_idx)
            big_trend = self.strategy_engine._get_big_trend(htf_idx)
            
            logger.info(f"市场状态: {regime.value}, 大趋势: {big_trend.value}")
            
            # 【v5.3】震荡市场：使用网格策略（如果启用）
            if regime == MarketRegime.RANGE_BOUND:
                if self.config.strategy_config.ENABLE_GRID_TRADING:
                    # 获取箱体信息
                    box_high = None
                    box_low = None
                    atr = None
                    try:
                        # 从策略引擎缓存获取箱体
                        if hasattr(self.strategy_engine, '_cache'):
                            current_idx = len(df_15m) - 1
                            if current_idx < len(self.strategy_engine._cache.get('box_h', [])):
                                box_high = self.strategy_engine._cache['box_h'].iloc[current_idx]
                                box_low = self.strategy_engine._cache['box_l'].iloc[current_idx]
                                atr = self.strategy_engine._cache['atr'].iloc[current_idx]
                    except:
                        pass
                    
                    if box_high and box_low and atr and not pd.isna(atr) and atr > 0:
                        # 获取余额
                        # 【修复Bug 5】余额获取失败时，不使用默认值，返回None
                        if self.config.paper_trading and not self.config.use_demo_trading:
                            balance = 10000  # 本地模拟盘默认资金
                        else:
                            try:
                                balance_info = self.exchange.fetch_balance()
                                balance = balance_info.get('USDT', {}).get('free', 0)
                                if balance <= 0:
                                    logger.error(f"余额获取失败或余额为0: {balance}")
                                    return None
                            except Exception as e:
                                logger.error(f"余额获取失败: {e}，跳过本次信号检查")
                                return None
                        
                        # 计算网格
                        if hasattr(self.strategy_engine, 'grid_sg'):
                            grid_layers = self.strategy_engine.grid_sg.calculate_grid(
                                box_high, box_low, current_price, atr, big_trend, balance
                            )
                            
                            if grid_layers:
                                # 【修复Bug 3】检查网格信号：使用实际网格持仓
                                # 从本地维护的网格持仓字典获取
                                existing_grid_positions = self.grid_positions.copy()
                                
                                grid_signal = self.strategy_engine.grid_sg.check_grid_signal(
                                    current_price, box_high, box_low, grid_layers, existing_grid_positions
                                )
                                
                                if grid_signal and grid_signal['type'] == 'grid_entry':
                                    # 返回网格开仓信号
                                    return {
                                        'side': 'long' if grid_signal['side'] == SignalType.LONG else 'short',
                                        'entry_price': grid_signal['price'],
                                        'size': grid_signal['size'],
                                        'stop_loss': grid_signal['sl_price'],
                                        'take_profit': grid_signal['tp_price'],
                                        'atr': atr,
                                        'regime': regime.value,
                                        'big_trend': big_trend.value,
                                        'grid_layer': grid_signal['layer'],
                                        'trade_type': 'grid'
                                    }
                
                # v5.2旧逻辑：震荡市场不交易
                return None
            
            # 趋势交易信号
            if regime == MarketRegime.TRENDING_UP:
                mtf_ema20 = self.strategy_engine._cache['mtf_ema20'].iloc[mtf_idx]
                mtf_ema100 = self.strategy_engine._cache['mtf_ema100'].iloc[mtf_idx]
                
                if mtf_ema20 > mtf_ema100:
                    price_ratio = (current_price - mtf_ema20) / mtf_ema20
                    price_pullback = 0 <= price_ratio <= 0.015
                    has_bull_rev = self.strategy_engine._cache['bull'].iloc[current_idx]
                    
                    if price_pullback or (price_ratio < 0.03 and has_bull_rev):
                        # 计算仓位
                        atr = self.strategy_engine._cache['atr'].iloc[current_idx]
                        if pd.isna(atr) or atr <= 0:
                            return None
                        
                        # 【修复Bug 5】获取余额：失败时返回None
                        if self.config.paper_trading and not self.config.use_demo_trading:
                            balance = 10000  # 本地模拟盘默认资金
                        else:
                            # OKX模拟交易或实盘：从交易所获取
                            try:
                                balance_info = self.exchange.fetch_balance()
                                balance = balance_info.get('USDT', {}).get('free', 0)
                                if balance <= 0:
                                    logger.error(f"余额获取失败或余额为0: {balance}")
                                    return None
                            except Exception as e:
                                logger.error(f"余额获取失败: {e}，跳过本次信号检查")
                                return None
                        
                        # 计算止损和仓位
                        sl = self.strategy_engine.rm.calc_sl(current_price, atr, SignalType.LONG)
                        tp = self.strategy_engine.rm.calc_tp(current_price, atr, SignalType.LONG)
                        
                        # 计算仓位大小
                        tier = self.strategy_engine.rm.get_tier(self.config.symbol)
                        size = self.strategy_engine.rm.calc_size(balance, current_price, sl, tier)
                        
                        if size > 0:
                            return {
                                'side': 'long',
                                'entry_price': current_price,
                                'size': size,
                                'stop_loss': sl,
                                'take_profit': tp,
                                'atr': atr,
                                'regime': regime.value,
                                'big_trend': big_trend.value
                            }
            
            elif regime == MarketRegime.TRENDING_DOWN:
                mtf_ema20 = self.strategy_engine._cache['mtf_ema20'].iloc[mtf_idx]
                mtf_ema100 = self.strategy_engine._cache['mtf_ema100'].iloc[mtf_idx]
                
                if mtf_ema20 < mtf_ema100:
                    price_ratio = (mtf_ema20 - current_price) / mtf_ema20
                    price_bounce = 0 <= price_ratio <= 0.015
                    has_bear_rev = self.strategy_engine._cache['bear'].iloc[current_idx]
                    
                    if price_bounce or (price_ratio < 0.03 and has_bear_rev):
                        # 计算仓位
                        atr = self.strategy_engine._cache['atr'].iloc[current_idx]
                        if pd.isna(atr) or atr <= 0:
                            return None
                        
                        # 【修复Bug 5】获取余额：失败时返回None
                        if self.config.paper_trading and not self.config.use_demo_trading:
                            balance = 10000  # 本地模拟盘默认资金
                        else:
                            # OKX模拟交易或实盘：从交易所获取
                            try:
                                balance_info = self.exchange.fetch_balance()
                                balance = balance_info.get('USDT', {}).get('free', 0)
                                if balance <= 0:
                                    logger.error(f"余额获取失败或余额为0: {balance}")
                                    return None
                            except Exception as e:
                                logger.error(f"余额获取失败: {e}，跳过本次信号检查")
                                return None
                        
                        # 计算止损和仓位
                        sl = self.strategy_engine.rm.calc_sl(current_price, atr, SignalType.SHORT)
                        tp = self.strategy_engine.rm.calc_tp(current_price, atr, SignalType.SHORT)
                        
                        tier = self.strategy_engine.rm.get_tier(self.config.symbol)
                        size = self.strategy_engine.rm.calc_size(balance, current_price, sl, tier)
                        
                        if size > 0:
                            return {
                                'side': 'short',
                                'entry_price': current_price,
                                'size': size,
                                'stop_loss': sl,
                                'take_profit': tp,
                                'atr': atr,
                                'regime': regime.value,
                                'big_trend': big_trend.value
                            }
            
            return None
            
        except Exception as e:
            logger.error(f"检查信号失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def execute_trade(self, signal: Dict, is_entry: bool = True):
        """执行交易（模拟或实盘）"""
        trade_record = {
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'symbol': self.config.symbol,
            'signal': signal,
            'is_entry': is_entry,
            'status': 'pending'
        }
        # 本地模拟盘：只记录，不下单
        if self.config.paper_trading and not self.config.use_demo_trading:
            # 模拟盘：只记录，不下单
            if is_entry:
                logger.info(f"\n{'='*60}")
                logger.info(f"[模拟盘] 开仓信号")
                logger.info(f"方向: {signal['side'].upper()}")
                logger.info(f"入场价: {signal['entry_price']:.4f}")
                logger.info(f"止损: {signal['stop_loss']:.4f}")
                logger.info(f"止盈: {signal['take_profit']:.4f}")
                logger.info(f"仓位: {signal['size']:.4f}")
                logger.info(f"市场状态: {signal.get('regime', 'N/A')}")
                logger.info(f"{'='*60}")
                
                # 发送开仓通知
                content = f"""方向: {signal['side'].upper()}
入场价: {signal['entry_price']:.4f}
止损: {signal['stop_loss']:.4f}
止盈: {signal['take_profit']:.4f}
仓位: {signal['size']:.4f} USDT
市场状态: {signal.get('regime', 'N/A')}
大趋势: {signal.get('big_trend', 'N/A')}"""
                self._send_notification(f"📈 开仓信号 - {self.config.symbol}", content, 'entry')
                self.current_position = {
                    **signal,
                    'entry_time': datetime.now()
                }
                trade_record.update({
                    'status': 'simulated',
                    'side': signal['side'],
                    'price': signal['entry_price'],
                    'quantity': signal['size'],
                    'stop_loss': signal['stop_loss'],
                    'take_profit': signal['take_profit'],
                })
                self.trades_history.append(trade_record)
            else:
                logger.info(f"\n{'='*60}")
                logger.info(f"[模拟盘] 平仓信号")
                logger.info(f"原因: {signal.get('reason', 'N/A')}")
                if self.current_position:
                    logger.info(f"入场价: {self.current_position['entry_price']:.4f}")
                    logger.info(f"出场价: {signal.get('exit_price', 0):.4f}")
                logger.info(f"{'='*60}")
                
                # 发送平仓通知
                if self.current_position:
                    exit_price = signal.get('exit_price', 0)
                    entry_price = self.current_position.get('entry_price', 0)
                    pnl = exit_price - entry_price
                    pnl_pct = (pnl / entry_price * 100) if entry_price > 0 else 0
                    pnl_emoji = "✅" if pnl > 0 else "❌"
                    content = f"""原因: {signal.get('reason', 'N/A')}
入场价: {entry_price:.4f}
出场价: {exit_price:.4f}
盈亏: {pnl_emoji} {pnl:+.4f} ({pnl_pct:+.2f}%)"""
                    self._send_notification(f"📉 平仓 - {self.config.symbol}", content, 'exit')
                if self.current_position:
                    trade_record.update({
                        'status': 'closed',
                        'exit_price': signal.get('exit_price', 0),
                        'reason': signal.get('reason', 'signal'),
                        'pnl': signal.get('exit_price', 0) - self.current_position.get('entry_price', 0)
                    })
                    self.trades_history.append(trade_record)
                self.current_position = None
        else:
            # OKX模拟交易或实盘：真实下单
            try:
                if is_entry:
                    side = 'buy' if signal['side'] == 'long' else 'sell'
                    # OKX合约交易需要指定合约数量
                    # size是USDT金额，需要转换为合约数量
                    current_price = signal['entry_price']
                    
                    # 【修复Bug 1】考虑杠杆倍数
                    leverage = self.config.leverage if self.config.leverage else 1
                    if self.config.use_swap and leverage > 1:
                        # 合约交易：size是USDT金额，需要乘以杠杆
                        contract_size = (signal['size'] * leverage) / current_price
                    else:
                        # 现货或1倍杠杆：直接计算
                        contract_size = signal['size'] / current_price
                    
                    # OKX合约参数
                    params = {}
                    if self.config.use_swap:
                        params['tdMode'] = 'isolated'  # 逐仓模式
                        # 如果配置了杠杆倍数，先设置杠杆（OKX需要在开仓前设置）
                        if self.config.leverage is not None:
                            try:
                                # OKX 设置杠杆的 API
                                market_info = self.exchange.market(self.config.symbol)
                                okx_id = market_info.get('id', '')
                                if okx_id:
                                    self.exchange.private_post_account_set_leverage({
                                        'instId': okx_id,
                                        'lever': str(self.config.leverage),
                                        'mgnMode': 'isolated'  # 逐仓模式
                                    })
                                    logger.info(f"已设置杠杆: {self.config.leverage}x")
                            except Exception as e:
                                logger.warning(f"设置杠杆失败: {e}，将使用账户默认杠杆")
                    
                    # 【v5.3】网格策略：使用网格信号中的价格（限价单）或市价单
                    if signal.get('trade_type') == 'grid':
                        # 网格策略：尝试使用限价单（更精确），如果失败则用市价单
                        grid_price = signal['entry_price']
                        try:
                            # OKX限价单
                            order = self.exchange.create_order(
                                self.config.symbol,
                                'limit',
                                side,
                                contract_size,
                                grid_price,
                                params
                            )
                            mode_text = "模拟交易" if self.config.use_demo_trading else "实盘"
                            logger.info(f"[{mode_text}] 网格开仓（限价单）: 订单ID={order.get('id', 'N/A')}, 价格={grid_price:.4f}, 数量={contract_size:.4f}, 层={signal.get('grid_layer', 'N/A')}")
                        except Exception as e:
                            # 限价单失败，使用市价单
                            logger.warning(f"网格限价单失败，使用市价单: {e}")
                            order = self.exchange.create_market_order(
                                self.config.symbol,
                                side,
                                contract_size,
                                None,
                                params,
                            )
                            mode_text = "模拟交易" if self.config.use_demo_trading else "实盘"
                            logger.info(f"[{mode_text}] 网格开仓（市价单）: 订单ID={order.get('id', 'N/A')}, 数量={contract_size:.4f}, 层={signal.get('grid_layer', 'N/A')}")
                    else:
                        # 普通趋势交易：使用市价单
                        order = self.exchange.create_market_order(
                            self.config.symbol,
                            side,
                            contract_size,  # 合约数量
                            None,
                            params,
                        )
                        mode_text = "模拟交易" if self.config.use_demo_trading else "实盘"
                        logger.info(f"[{mode_text}] 开仓成功: 订单ID={order.get('id', 'N/A')}, 数量={contract_size:.4f}")
                    
                    # 发送开仓通知
                    if signal.get('trade_type') == 'grid':
                        content = f"""类型: 网格策略
方向: {signal['side'].upper()}
订单ID: {order.get('id', 'N/A')}
网格层: {signal.get('grid_layer', 'N/A')}
入场价: {signal['entry_price']:.4f}
数量: {contract_size:.4f}
止损: {signal['stop_loss']:.4f}
止盈: {signal['take_profit']:.4f}
仓位: {signal['size']:.4f} USDT
市场状态: {signal.get('regime', 'N/A')}
大趋势: {signal.get('big_trend', 'N/A')}"""
                        self._send_notification(f"🔷 网格开仓 - {self.config.symbol}", content, 'entry')
                    else:
                        content = f"""方向: {signal['side'].upper()}
订单ID: {order.get('id', 'N/A')}
入场价: {current_price:.4f}
数量: {contract_size:.4f}
止损: {signal['stop_loss']:.4f}
止盈: {signal['take_profit']:.4f}
仓位: {signal['size']:.4f} USDT
市场状态: {signal.get('regime', 'N/A')}
大趋势: {signal.get('big_trend', 'N/A')}"""
                        self._send_notification(f"📈 开仓成功 - {self.config.symbol}", content, 'entry')
                    
                    # 记录交易
                    entry_price = signal.get('entry_price', current_price) if signal.get('trade_type') == 'grid' else current_price
                    trade_record.update({
                        'status': 'filled',
                        'order_id': order.get('id', 'N/A'),
                        'side': side,
                        'price': entry_price,
                        'quantity': contract_size,
                        'stop_loss': signal['stop_loss'],
                        'take_profit': signal['take_profit'],
                        'trade_type': signal.get('trade_type', 'trend'),
                        'grid_layer': signal.get('grid_layer', None)
                    })
                    self.trades_history.append(trade_record)
                    self.current_position = {
                        **signal,
                        'entry_time': datetime.now(),
                        'order_id': order.get('id', 'N/A'),
                        'entry_price': entry_price,
                        'contract_size': contract_size  # 【修复Bug 2】保存合约数量，用于平仓
                    }
                    
                    # 【修复Bug 3】如果是网格交易，记录到网格持仓字典
                    if signal.get('trade_type') == 'grid':
                        layer = signal.get('grid_layer')
                        if layer:
                            self.grid_positions[layer] = {
                                'entry_price': entry_price,
                                'size': contract_size,  # 合约数量
                                'side': signal['side'],
                                'order_id': order.get('id', 'N/A'),
                                'stop_loss': signal['stop_loss'],
                                'take_profit': signal['take_profit']
                            }
                            logger.info(f"网格持仓已记录: 层={layer}, 数量={contract_size:.4f}")
                    
                    # 【修复Bug 4】设置止损止盈（OKX支持条件单）- 添加重试机制
                    max_retries = 3
                    sl_order = None
                    for attempt in range(max_retries):
                        try:
                            # 止损单
                            sl_order = self.exchange.create_order(
                                self.config.symbol,
                                'market',
                                'sell' if side == 'buy' else 'buy',
                                contract_size,
                                None,
                                {
                                    'stopPrice': signal['stop_loss'],
                                    'tdMode': 'isolated',
                                    'triggerPrice': signal['stop_loss'],
                                }
                            )
                            mode_text = "模拟交易" if self.config.use_demo_trading else "实盘"
                            logger.info(f"[{mode_text}] 止损单设置成功: {sl_order.get('id', 'N/A')}")
                            break
                        except Exception as e:
                            if attempt < max_retries - 1:
                                mode_text = "模拟交易" if self.config.use_demo_trading else "实盘"
                                logger.warning(f"[{mode_text}] 止损单设置失败（尝试 {attempt+1}/{max_retries}）: {e}")
                                time.sleep(1)  # 等待1秒后重试
                            else:
                                mode_text = "模拟交易" if self.config.use_demo_trading else "实盘"
                                logger.error(f"[{mode_text}] 止损单设置失败（已重试{max_retries}次）: {e}")
                                # 发送严重警告通知
                                self._send_notification(
                                    f"⚠️ 止损单设置失败 - {self.config.symbol}",
                                    f"开仓成功但止损单设置失败，请手动设置止损！\n订单ID: {order.get('id', 'N/A')}\n止损价: {signal['stop_loss']:.4f}\n错误: {str(e)}",
                                    'error'
                                )
                    
                    # 设置止盈单（如果止损单成功）
                    if sl_order:
                        try:
                            tp_order = self.exchange.create_order(
                                self.config.symbol,
                                'market',
                                'sell' if side == 'buy' else 'buy',
                                contract_size,
                                None,
                                {
                                    'stopPrice': signal['take_profit'],
                                    'tdMode': 'isolated',
                                    'triggerPrice': signal['take_profit'],
                                }
                            )
                            mode_text = "模拟交易" if self.config.use_demo_trading else "实盘"
                            logger.info(f"[{mode_text}] 止盈单设置成功: {tp_order.get('id', 'N/A')}")
                        except Exception as e:
                            mode_text = "模拟交易" if self.config.use_demo_trading else "实盘"
                            logger.warning(f"[{mode_text}] 止盈单设置失败（可手动设置）: {e}")
                    
                else:
                    # 平仓：反向操作
                    current_pos = self.get_current_position()
                    if current_pos:
                        side = 'sell' if current_pos['side'] == 'long' else 'buy'
                        # 【修复Bug 2】使用实际持仓数量（合约数量）
                        # 如果current_pos中有contract_size，优先使用；否则使用size
                        size = current_pos.get('contract_size', current_pos.get('size', 0))
                        if size <= 0:
                            logger.error(f"平仓失败：持仓数量无效 ({size})")
                            raise ValueError(f"持仓数量无效: {size}")
                        
                        params = {}
                        if self.config.use_swap:
                            params['tdMode'] = 'isolated'
                            # 平仓时不需要设置杠杆，使用持仓的杠杆
                        
                        order = self.exchange.create_market_order(
                            self.config.symbol,
                            side,
                            size,
                            None,
                            params,
                        )
                        mode_text = "模拟交易" if self.config.use_demo_trading else "实盘"
                        logger.info(f"[{mode_text}] 平仓成功: 订单ID={order['id']}")
                        
                        # 发送平仓通知
                        exit_price = signal.get('exit_price', current_pos.get('entry_price', 0))
                        entry_price = current_pos.get('entry_price', 0)
                        pnl = exit_price - entry_price
                        pnl_pct = (pnl / entry_price * 100) if entry_price > 0 else 0
                        pnl_emoji = "✅" if pnl > 0 else "❌"
                        content = f"""原因: {signal.get('reason', 'signal')}
订单ID: {order['id']}
入场价: {entry_price:.4f}
出场价: {exit_price:.4f}
盈亏: {pnl_emoji} {pnl:+.4f} ({pnl_pct:+.2f}%)"""
                        self._send_notification(f"📉 平仓成功 - {self.config.symbol}", content, 'exit')
                        
                        # 记录平仓
                        trade_record.update({
                            'status': 'closed',
                            'order_id': order['id'],
                            'exit_price': signal.get('exit_price', current_pos.get('entry_price', 0)),
                            'reason': signal.get('reason', 'signal')
                        })
                        self.trades_history.append(trade_record)
                        self.current_position = None
                        
                        # 【修复Bug 3】如果是网格交易，从网格持仓字典中删除
                        if signal.get('trade_type') == 'grid':
                            layer = signal.get('grid_layer')
                            if layer and layer in self.grid_positions:
                                del self.grid_positions[layer]
                                logger.info(f"网格持仓已清除: 层={layer}")
            except Exception as e:
                mode_text = "模拟交易" if self.config.use_demo_trading else "实盘"
                logger.error(f"[{mode_text}] 交易失败: {e}")
                import traceback
                traceback.print_exc()
    
    def run(self):
        """运行交易机器人"""
        logger.info("=" * 60)
        logger.info("v5.2策略交易机器人启动")
        logger.info("=" * 60)
        
        self.running = True
        start_time = time.time()
        last_check_time = 0
        
        try:
            while self.running:
                current_time = time.time()
                
                # 检查运行时长（如果 max_runtime_hours > 0）
                if self.config.max_runtime_hours > 0:
                    if current_time - start_time > self.config.max_runtime_hours * 3600:
                        logger.info(f"达到最大运行时长（{self.config.max_runtime_hours}小时），停止交易")
                        break
                
                # 定期检查信号
                if current_time - last_check_time >= self.config.check_interval:
                    last_check_time = current_time
                    
                    logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查交易信号...")
                    
                    # 【修复Bug 7】每次检查信号前，从交易所获取实际持仓并更新本地持仓信息
                    # 获取当前持仓
                    position = self.get_current_position()
                    if position:
                        # 更新本地持仓信息，确保和实际持仓一致
                        self.current_position = position
                        # 如果是网格持仓，同步到grid_positions
                        if position.get('trade_type') == 'grid' and position.get('grid_layer'):
                            layer = position['grid_layer']
                            if layer not in self.grid_positions:
                                self.grid_positions[layer] = {
                                    'entry_price': position.get('entry_price', 0),
                                    'size': position.get('size', 0),
                                    'side': position.get('side', 'long'),
                                    'order_id': position.get('order_id', 'N/A')
                                }
                    
                    # 检查出场
                    if position:
                        # 【修复】检查出场时也需要足够的数据来计算指标
                        df_15m, _, _ = self.fetch_historical_data(limit=None)
                        if df_15m is not None and len(df_15m) > 0:
                            current_price = df_15m['close'].iloc[-1]
                            current_bar = df_15m.iloc[-1]
                            
                            # 检查止损
                            if position['side'] == 'long':
                                if current_bar['low'] <= position['stop_loss']:
                                    # 发送止损通知
                                    entry_price = position.get('entry_price', 0)
                                    sl_price = position['stop_loss']
                                    pnl = sl_price - entry_price
                                    pnl_pct = (pnl / entry_price * 100) if entry_price > 0 else 0
                                    content = f"""触发: 止损
入场价: {entry_price:.4f}
止损价: {sl_price:.4f}
盈亏: ❌ {pnl:+.4f} ({pnl_pct:+.2f}%)"""
                                    self._send_notification(f"🛑 止损触发 - {self.config.symbol}", content, 'stop_loss')
                                    
                                    self.execute_trade({
                                        'reason': '止损',
                                        'exit_price': position['stop_loss']
                                    }, is_entry=False)
                                    continue
                                # 检查止盈
                                if current_bar['high'] >= position['take_profit']:
                                    # 发送止盈通知
                                    entry_price = position.get('entry_price', 0)
                                    tp_price = position['take_profit']
                                    pnl = tp_price - entry_price
                                    pnl_pct = (pnl / entry_price * 100) if entry_price > 0 else 0
                                    content = f"""触发: 止盈
入场价: {entry_price:.4f}
止盈价: {tp_price:.4f}
盈亏: ✅ {pnl:+.4f} ({pnl_pct:+.2f}%)"""
                                    self._send_notification(f"🎯 止盈触发 - {self.config.symbol}", content, 'take_profit')
                                    
                                    self.execute_trade({
                                        'reason': '止盈',
                                        'exit_price': position['take_profit']
                                    }, is_entry=False)
                                    continue
                            else:  # short
                                if current_bar['high'] >= position['stop_loss']:
                                    # 发送止损通知
                                    entry_price = position.get('entry_price', 0)
                                    sl_price = position['stop_loss']
                                    pnl = entry_price - sl_price  # 做空：入场价 - 止损价
                                    pnl_pct = (pnl / entry_price * 100) if entry_price > 0 else 0
                                    content = f"""触发: 止损
入场价: {entry_price:.4f}
止损价: {sl_price:.4f}
盈亏: ❌ {pnl:+.4f} ({pnl_pct:+.2f}%)"""
                                    self._send_notification(f"🛑 止损触发 - {self.config.symbol}", content, 'stop_loss')
                                    
                                    self.execute_trade({
                                        'reason': '止损',
                                        'exit_price': position['stop_loss']
                                    }, is_entry=False)
                                    continue
                                # 检查止盈
                                if current_bar['low'] <= position['take_profit']:
                                    # 发送止盈通知
                                    entry_price = position.get('entry_price', 0)
                                    tp_price = position['take_profit']
                                    pnl = entry_price - tp_price  # 做空：入场价 - 止盈价
                                    pnl_pct = (pnl / entry_price * 100) if entry_price > 0 else 0
                                    content = f"""触发: 止盈
入场价: {entry_price:.4f}
止盈价: {tp_price:.4f}
盈亏: ✅ {pnl:+.4f} ({pnl_pct:+.2f}%)"""
                                    self._send_notification(f"🎯 止盈触发 - {self.config.symbol}", content, 'take_profit')
                                    
                                    self.execute_trade({
                                        'reason': '止盈',
                                        'exit_price': position['take_profit']
                                    }, is_entry=False)
                                    continue
                            
                            # TODO: 检查移动止损（需要记录最高/最低价）
                    
                    # 检查入场
                    if not position:
                        signal = self.check_signals()
                        if signal:
                            self.execute_trade(signal, is_entry=True)
                        else:
                            logger.debug("无交易信号")
                
                time.sleep(5)  # 短暂休眠
                
        except KeyboardInterrupt:
            logger.info("收到停止信号，正在关闭...")
        finally:
            self.running = False
            self._print_summary()
    
    def _print_summary(self):
        """打印交易总结"""
        logger.info("=" * 60)
        logger.info("交易总结")
        logger.info("=" * 60)
        logger.info(f"总交易次数: {len(self.trades_history)}")
        
        if self.trades_history:
            closed_trades = [t for t in self.trades_history if t.get('status') == 'closed']
            open_trades = [t for t in self.trades_history if t.get('status') in ['filled', 'simulated']]
            
            logger.info(f"已平仓: {len(closed_trades)}")
            logger.info(f"持仓中: {len(open_trades)}")
            
            if closed_trades:
                total_pnl = sum(t.get('pnl', 0) for t in closed_trades)
                winning = [t for t in closed_trades if t.get('pnl', 0) > 0]
                losing = [t for t in closed_trades if t.get('pnl', 0) < 0]
                
                logger.info(f"总盈亏: {total_pnl:+.2f} USDT")
                logger.info(f"盈利交易: {len(winning)}")
                logger.info(f"亏损交易: {len(losing)}")
                if len(closed_trades) > 0:
                    win_rate = len(winning) / len(closed_trades) * 100
                    logger.info(f"胜率: {win_rate:.1f}%")


# ============================================================================
# 主函数
# ============================================================================
def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='v5.2策略实盘/模拟盘交易')
    parser.add_argument('--symbol', type=str, default=None,
                        help='交易对，例如: BTC/USDT:USDT (默认从环境变量TRADING_SYMBOL或配置读取)')
    parser.add_argument('--demo', action='store_true', default=None,
                        help='使用OKX模拟交易（Demo Trading）')
    parser.add_argument('--paper', action='store_true', default=None,
                        help='使用本地模拟盘（不下单）')
    parser.add_argument('--live', action='store_true', default=None,
                        help='使用实盘模式（谨慎使用）')
    parser.add_argument('--non-interactive', action='store_true',
                        help='非交互模式（用于Docker/云端部署，跳过所有input()）')
    
    args = parser.parse_args()
    
    # 创建配置
    config = LiveTradingConfig()
    
    # 默认非交互模式（适合云端部署）
    # 非交互模式：从环境变量或命令行参数读取配置
    non_interactive = args.non_interactive or os.getenv('NON_INTERACTIVE', '1').lower() in ('1', 'true', 'yes')
    if non_interactive:
        # 从环境变量读取交易对
        if args.symbol:
            config.symbol = args.symbol
        elif os.getenv('TRADING_SYMBOL'):
            config.symbol = os.getenv('TRADING_SYMBOL')
        
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
        # 否则使用默认配置（OKX模拟交易）
        
        logger.info("=" * 60)
        logger.info("v5.2策略实盘/模拟盘交易（非交互模式）")
        logger.info("=" * 60)
        logger.info(f"交易所: {config.exchange_id.upper()}")
        logger.info(f"交易对: {config.symbol}")
        if config.use_demo_trading:
            logger.info("模式: OKX模拟交易（Demo Trading）- 真实下单，模拟资金")
        else:
            logger.info(f"模式: {'本地模拟盘（不下单）' if config.paper_trading else '实盘'}")
        logger.info(f"风险: {config.strategy_config.RISK_PER_TRADE}%")
        logger.info(f"仓位上限: {config.strategy_config.TIER1_MAX_POSITION}%")
        logger.info(f"Passphrase: {'已配置' if config.passphrase else '未配置'}")
        logger.info("=" * 60)
    else:
        # 交互模式（保持向后兼容）
        print("\n" + "=" * 60)
        print("v5.2策略实盘/模拟盘交易")
        print("=" * 60)
        
        print("\n当前配置:")
        print(f"  交易所: {config.exchange_id.upper()}")
        print(f"  交易对: {config.symbol}")
        if config.use_demo_trading:
            print(f"  模式: OKX模拟交易（Demo Trading）- 真实下单，模拟资金")
        else:
            print(f"  模式: {'本地模拟盘（不下单）' if config.paper_trading else '实盘'}")
        print(f"  风险: {config.strategy_config.RISK_PER_TRADE}%")
        print(f"  仓位上限: {config.strategy_config.TIER1_MAX_POSITION}%")
        print(f"  Passphrase: {'已配置' if config.passphrase else '未配置'}")
        
        print("\n请选择:")
        print("  1. 使用当前配置启动（OKX模拟交易）")
        print("  2. 切换到本地模拟盘（不下单）")
        print("  3. 修改交易对")
        print("  4. 退出")
        
        choice = input("\n请选择 (1-4): ").strip()
        
        if choice == '1':
            config.use_demo_trading = True
            config.paper_trading = False
            print("\n使用OKX模拟交易模式（Demo Trading）")
            print("真实下单，但使用模拟资金，安全测试")
        elif choice == '2':
            config.use_demo_trading = False
            config.paper_trading = True
            print("\n使用本地模拟盘模式（不下单，仅记录）")
        elif choice == '3':
            symbol = input(f"请输入交易对 (默认{config.symbol}): ").strip()
            if symbol:
                config.symbol = symbol
        elif choice == '4':
            print("退出")
            return
        else:
            print("无效选择")
            return
    
    # 启动机器人
    try:
        bot = LiveTradingBotV52(config)
        bot.run()
    except Exception as e:
        logger.error(f"启动失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
