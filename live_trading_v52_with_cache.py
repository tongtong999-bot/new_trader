#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v5.2策略实盘/模拟盘交易脚本（带数据缓存版本）
===========================================
修复：
1. 修复分批获取数据失败的问题
2. 添加数据缓存机制，避免每次都重新获取全部历史数据
3. 只获取新的K线数据，提高效率
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
# 数据缓存管理
# ============================================================================
class DataCache:
    """历史数据缓存管理"""
    
    def __init__(self, cache_dir: Path = None):
        if cache_dir is None:
            cache_dir = Path(__file__).parent / 'data_cache'
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def get_cache_file(self, symbol: str, timeframe: str) -> Path:
        """获取缓存文件路径"""
        # 清理symbol中的特殊字符
        safe_symbol = symbol.replace('/', '_').replace(':', '_')
        return self.cache_dir / f"{safe_symbol}_{timeframe}.pkl"
    
    def load(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """从缓存加载数据"""
        cache_file = self.get_cache_file(symbol, timeframe)
        if cache_file.exists():
            try:
                with open(cache_file, 'rb') as f:
                    data = pickle.load(f)
                    if isinstance(data, pd.DataFrame) and len(data) > 0:
                        logger.info(f"从缓存加载 {symbol} {timeframe} 数据: {len(data)} 条")
                        return data
            except Exception as e:
                logger.warning(f"加载缓存失败: {e}")
        return None
    
    def save(self, symbol: str, timeframe: str, data: pd.DataFrame):
        """保存数据到缓存"""
        cache_file = self.get_cache_file(symbol, timeframe)
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(data, f)
            logger.debug(f"数据已缓存: {cache_file}")
        except Exception as e:
            logger.warning(f"保存缓存失败: {e}")
    
    def get_last_timestamp(self, symbol: str, timeframe: str) -> Optional[int]:
        """获取缓存中最后一条数据的时间戳"""
        data = self.load(symbol, timeframe)
        if data is not None and len(data) > 0:
            last_ts = data['timestamp'].iloc[-1]
            return int(pd.Timestamp(last_ts).timestamp() * 1000)
        return None


# ============================================================================
# 配置管理（与原版相同）
# ============================================================================
# ... 这里省略配置类，使用原版的 LiveTradingConfig ...


# ============================================================================
# 实盘交易机器人（带缓存版本）
# ============================================================================
class LiveTradingBotV52WithCache:
    """实盘交易机器人（带数据缓存）"""
    
    def __init__(self, config):
        # 这里需要导入原版的配置类
        # 为了简化，假设config已经传入
        self.config = config
        self.data_cache = DataCache()
        # ... 其他初始化代码 ...
    
    def fetch_historical_data_with_cache(
        self, 
        symbol: str, 
        timeframe: str = '15m',
        min_days: int = 80,
        exchange: ccxt.Exchange = None
    ) -> Optional[pd.DataFrame]:
        """
        获取历史数据（带缓存机制）
        
        策略：
        1. 先从缓存加载已有数据
        2. 只获取缓存之后的新数据
        3. 合并新旧数据
        4. 保存到缓存
        """
        if exchange is None:
            logger.error("exchange参数不能为空")
            return None
        
        # 计算需要的数据量
        min_bars = min_days * 96  # 15分钟K线：每天96条
        
        # 1. 尝试从缓存加载
        cached_data = self.data_cache.load(symbol, timeframe)
        last_cached_ts = None
        
        if cached_data is not None and len(cached_data) > 0:
            last_cached_ts = int(pd.Timestamp(cached_data['timestamp'].iloc[-1]).timestamp() * 1000)
            logger.info(f"缓存中有 {len(cached_data)} 条数据，最后时间: {pd.Timestamp(last_cached_ts, unit='ms')}")
            
            # 检查缓存数据是否足够新（如果缓存数据是1小时内的，直接使用）
            cache_age_hours = (datetime.now().timestamp() * 1000 - last_cached_ts) / (1000 * 3600)
            if cache_age_hours < 1 and len(cached_data) >= min_bars:
                logger.info(f"缓存数据足够新（{cache_age_hours:.1f}小时前），直接使用缓存")
                return cached_data
        
        # 2. 获取新数据
        new_data_list = []
        current_ts = int(datetime.now().timestamp() * 1000)
        
        if last_cached_ts:
            # 从缓存最后时间开始获取新数据
            start_ts = last_cached_ts + (15 * 60 * 1000)  # 从下一条K线开始
            logger.info(f"从缓存最后时间开始获取新数据: {pd.Timestamp(start_ts, unit='ms')}")
        else:
            # 没有缓存，获取全部历史数据
            # 往前推 min_days 天
            start_ts = current_ts - (min_days * 24 * 60 * 60 * 1000)
            logger.info(f"无缓存，获取全部历史数据（从 {pd.Timestamp(start_ts, unit='ms')} 开始）")
        
        # 分批获取新数据（每次最多1000条）
        max_limit_per_request = 1000
        batch_num = 0
        
        while len(new_data_list) < min_bars or batch_num == 0:
            batch_num += 1
            batch_limit = min(max_limit_per_request, min_bars - len(new_data_list))
            
            try:
                if batch_num == 1 and last_cached_ts:
                    # 第一批：从缓存最后时间开始
                    batch_data = exchange.fetch_ohlcv(
                        symbol,
                        timeframe,
                        since=start_ts,
                        limit=batch_limit
                    )
                elif batch_num == 1:
                    # 第一批：从指定时间开始
                    batch_data = exchange.fetch_ohlcv(
                        symbol,
                        timeframe,
                        since=start_ts,
                        limit=batch_limit
                    )
                else:
                    # 后续批次：从上一批最早时间往前获取
                    if not new_data_list:
                        break
                    earliest_ts = min(item[0] for item in new_data_list)
                    # 往前推1毫秒，确保不重复
                    batch_start_ts = earliest_ts - 1
                    
                    batch_data = exchange.fetch_ohlcv(
                        symbol,
                        timeframe,
                        since=batch_start_ts,
                        limit=batch_limit
                    )
                
                if not batch_data:
                    logger.warning(f"批次 {batch_num}: 没有获取到数据")
                    break
                
                # 过滤重复数据
                existing_timestamps = {item[0] for item in new_data_list}
                new_items = [item for item in batch_data if item[0] not in existing_timestamps]
                
                if not new_items:
                    logger.info(f"批次 {batch_num}: 没有新数据，可能已获取完所有可用数据")
                    break
                
                new_data_list.extend(new_items)
                logger.info(f"批次 {batch_num}: 获取了 {len(new_items)} 条新数据（去重后）")
                
                # 如果获取的数据少于请求量，说明已经获取完
                if len(batch_data) < batch_limit:
                    logger.info(f"批次 {batch_num}: 获取的数据少于请求量，可能已获取完所有可用数据")
                    break
                
                time.sleep(0.2)  # 避免请求过快
                
            except Exception as e:
                logger.warning(f"批次 {batch_num} 获取失败: {e}")
                break
        
        # 3. 合并数据
        if cached_data is not None and len(cached_data) > 0:
            # 有缓存：合并新旧数据
            if new_data_list:
                new_df = pd.DataFrame(
                    new_data_list,
                    columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )
                new_df['timestamp'] = pd.to_datetime(new_df['timestamp'], unit='ms')
                
                # 合并：去重并排序
                combined = pd.concat([cached_data, new_df], ignore_index=True)
                combined = combined.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
                
                logger.info(f"合并数据: 缓存 {len(cached_data)} 条 + 新增 {len(new_df)} 条 = 总计 {len(combined)} 条")
                
                # 只保留最新的 min_bars 条（避免数据过多）
                if len(combined) > min_bars * 2:
                    combined = combined.tail(min_bars * 2).reset_index(drop=True)
                    logger.info(f"数据过多，只保留最新的 {len(combined)} 条")
                
                final_data = combined
            else:
                # 没有新数据，直接使用缓存
                logger.info("没有新数据，使用缓存数据")
                final_data = cached_data
        else:
            # 没有缓存：使用新获取的数据
            if new_data_list:
                final_data = pd.DataFrame(
                    new_data_list,
                    columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )
                final_data['timestamp'] = pd.to_datetime(final_data['timestamp'], unit='ms')
                final_data = final_data.sort_values('timestamp').reset_index(drop=True)
            else:
                logger.error("无法获取数据且无缓存")
                return None
        
        # 4. 保存到缓存
        self.data_cache.save(symbol, timeframe, final_data)
        
        logger.info(f"最终数据: {len(final_data)} 条，时间范围: {final_data['timestamp'].min()} 到 {final_data['timestamp'].max()}")
        
        return final_data
