#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查最近BTC交易信号
==================
功能：
1. 从币安获取上个月到现在的BTC数据
2. 运行策略，检查最近三天是否有开单信号
3. 输出详细的信号信息，帮助诊断为什么没有开单
"""

import sys
import os
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import ccxt
from typing import Dict, List, Optional, Tuple

# 添加策略路径
sys.path.insert(0, str(Path(__file__).parent / 'strategies'))

from box_strategy_v5_2 import StrategyConfig, BacktestEngine, MarketRegime, BigTrend

# ============================================================================
# 日志配置
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# 数据获取函数
# ============================================================================
def fetch_recent_data(symbol: str = 'BTC/USDT', days: int = 60) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    从币安获取最近的数据
    
    Args:
        symbol: 交易对
        days: 获取最近多少天的数据
    
    Returns:
        (ltf_15m, mtf_1h, htf_4h)
    """
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        
        # 计算时间范围
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        start_ts = int(start_date.timestamp() * 1000)
        end_ts = int(end_date.timestamp() * 1000)
        
        logger.info(f"从币安获取 {symbol} 最近 {days} 天数据...")
        logger.info(f"时间范围: {start_date.strftime('%Y-%m-%d %H:%M:%S')} 到 {end_date.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 下载15m数据
        ltf_data = []
        current_ts = start_ts
        while current_ts < end_ts:
            ohlcv = exchange.fetch_ohlcv(symbol, '15m', since=current_ts, limit=1000)
            if not ohlcv:
                break
            ltf_data.extend(ohlcv)
            current_ts = ohlcv[-1][0] + 1
            if len(ohlcv) < 1000:
                break
        
        if not ltf_data:
            logger.error(f"未获取到 {symbol} 15m 数据")
            return None, None, None
        
        ltf = pd.DataFrame(ltf_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        ltf['timestamp'] = pd.to_datetime(ltf['timestamp'], unit='ms')
        ltf = ltf[ltf['timestamp'] < pd.to_datetime(end_ts, unit='ms')]
        ltf = ltf.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
        
        logger.info(f"15m数据: {len(ltf)} 条，时间范围: {ltf['timestamp'].min()} 到 {ltf['timestamp'].max()}")
        
        # 下载4h数据
        htf_data = []
        current_ts = start_ts
        while current_ts < end_ts:
            ohlcv = exchange.fetch_ohlcv(symbol, '4h', since=current_ts, limit=1000)
            if not ohlcv:
                break
            htf_data.extend(ohlcv)
            current_ts = ohlcv[-1][0] + 1
            if len(ohlcv) < 1000:
                break
        
        if not htf_data:
            logger.error(f"未获取到 {symbol} 4h 数据")
            return None, None, None
        
        htf = pd.DataFrame(htf_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        htf['timestamp'] = pd.to_datetime(htf['timestamp'], unit='ms')
        htf = htf[htf['timestamp'] < pd.to_datetime(end_ts, unit='ms')]
        htf = htf.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
        
        logger.info(f"4h数据: {len(htf)} 条，时间范围: {htf['timestamp'].min()} 到 {htf['timestamp'].max()}")
        
        # 从15m重采样生成1h数据
        ltf_indexed = ltf.set_index('timestamp')
        mtf = ltf_indexed.resample('1h').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna().reset_index()
        
        logger.info(f"1h数据: {len(mtf)} 条")
        
        return ltf, mtf, htf
        
    except Exception as e:
        logger.error(f"获取数据失败: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None

# ============================================================================
# 信号检查函数
# ============================================================================
def check_recent_signals(symbol: str = 'BTC/USDT', days: int = 60, check_days: int = 3):
    """
    检查最近几天的交易信号
    
    Args:
        symbol: 交易对
        days: 获取多少天的历史数据
        check_days: 检查最近几天的信号
    """
    logger.info("=" * 80)
    logger.info(f"检查 {symbol} 最近 {check_days} 天的交易信号")
    logger.info("=" * 80)
    
    # 获取数据
    ltf, mtf, htf = fetch_recent_data(symbol, days)
    
    if ltf is None or mtf is None or htf is None:
        logger.error("数据获取失败")
        return
    
    # 检查数据时间范围
    latest_time = ltf['timestamp'].max()
    check_start_time = latest_time - timedelta(days=check_days)
    
    logger.info(f"\n数据最新时间: {latest_time}")
    logger.info(f"检查时间范围: {check_start_time} 到 {latest_time}")
    
    # 创建配置
    cfg = StrategyConfig()
    cfg.SYMBOL = symbol
    
    # 创建回测引擎
    engine = BacktestEngine(cfg)
    
    # 预计算指标
    engine._precalc(ltf, mtf, htf)
    
    # 找到检查时间范围的起始索引
    check_start_idx = ltf[ltf['timestamp'] >= check_start_time].index[0] if len(ltf[ltf['timestamp'] >= check_start_time]) > 0 else len(ltf) - 100
    
    logger.info(f"\n开始检查信号（从索引 {check_start_idx} 开始，共 {len(ltf) - check_start_idx} 根K线）...")
    logger.info("=" * 80)
    
    signals = []
    min_bar = max(cfg.BOX_LOOKBACK_PERIODS, cfg.ATR_PERCENTILE_PERIOD, cfg.EMA_SLOW_PERIOD) + 10
    
    for i in range(max(min_bar, check_start_idx), len(ltf) - 1):
        row = ltf.iloc[i]
        ts = row['timestamp']
        price = row['close']
        
        # 获取索引和状态
        htf_idx = engine._idx(ts, engine._cache['htf_ts'])
        mtf_idx = engine._idx(ts, engine._cache['mtf_ts'])
        
        if htf_idx is None or mtf_idx is None:
            continue
        
        regime = engine._get_market_regime(htf_idx, i)
        big_trend = engine._get_big_trend(htf_idx)
        
        # 获取箱体信息
        box_high = engine._cache['box_h'].iloc[i] if i < len(engine._cache['box_h']) else None
        box_low = engine._cache['box_l'].iloc[i] if i < len(engine._cache['box_l']) else None
        atr = engine._cache['atr'].iloc[i] if i < len(engine._cache['atr']) else 0
        
        # 检查网格信号
        grid_signal = None
        if regime == MarketRegime.RANGE_BOUND and cfg.ENABLE_GRID_TRADING:
            if box_high and box_low and not pd.isna(atr) and atr > 0:
                grid_balance = 10000  # 假设有1万网格资金
                grid_layers = engine.grid_sg.calculate_grid(
                    box_high, box_low, price, atr, big_trend, grid_balance
                )
                
                if grid_layers:
                    existing_grid_positions = {}
                    grid_signal = engine.grid_sg.check_grid_signal(
                        price, box_high, box_low, grid_layers, existing_grid_positions
                    )
        
        # 检查趋势信号
        trend_signal = None
        if regime == MarketRegime.TRENDING_UP:
            mtf_ema20 = engine._cache['mtf_ema20'].iloc[mtf_idx]
            mtf_ema100 = engine._cache['mtf_ema100'].iloc[mtf_idx]
            
            if mtf_ema20 > mtf_ema100:
                price_ratio = (price - mtf_ema20) / mtf_ema20
                price_pullback = 0 <= price_ratio <= 0.015
                has_bull_rev = engine._cache['bull'].iloc[i]
                
                if price_pullback or (price_ratio < 0.03 and has_bull_rev):
                    trend_signal = {
                        'type': 'LONG',
                        'reason': 'TRENDING_UP',
                        'price_ratio': price_ratio,
                        'price_pullback': price_pullback,
                        'has_bull_rev': has_bull_rev
                    }
        
        elif regime == MarketRegime.TRENDING_DOWN:
            mtf_ema20 = engine._cache['mtf_ema20'].iloc[mtf_idx]
            mtf_ema100 = engine._cache['mtf_ema100'].iloc[mtf_idx]
            
            if mtf_ema20 < mtf_ema100:
                price_ratio = (mtf_ema20 - price) / mtf_ema20
                price_bounce = 0 <= price_ratio <= 0.015
                has_bear_rev = engine._cache['bear'].iloc[i]
                
                if price_bounce or (price_ratio < 0.03 and has_bear_rev):
                    trend_signal = {
                        'type': 'SHORT',
                        'reason': 'TRENDING_DOWN',
                        'price_ratio': price_ratio,
                        'price_bounce': price_bounce,
                        'has_bear_rev': has_bear_rev
                    }
        
        # 记录信号
        if grid_signal or trend_signal:
            signal_info = {
                'timestamp': ts,
                'price': price,
                'regime': regime.value,
                'big_trend': big_trend.value,
                'box_high': box_high,
                'box_low': box_low,
                'box_range_pct': ((box_high - box_low) / box_low * 100) if box_high and box_low else None,
                'price_in_box': (box_low <= price <= box_high) if box_high and box_low else None,
                'grid_signal': grid_signal,
                'trend_signal': trend_signal
            }
            signals.append(signal_info)
            
            # 立即输出信号
            logger.info(f"\n{'='*80}")
            logger.info(f"发现信号 @ {ts}")
            logger.info(f"价格: {price:.2f}")
            logger.info(f"市场状态: {regime.value}")
            logger.info(f"大趋势: {big_trend.value}")
            
            if box_high and box_low:
                logger.info(f"箱体: [{box_low:.2f}, {box_high:.2f}] (范围: {((box_high - box_low) / box_low * 100):.2f}%)")
                logger.info(f"价格在箱体内: {box_low <= price <= box_high}")
            
            if grid_signal:
                logger.info(f"网格信号: {grid_signal}")
                if grid_signal.get('type') == 'grid_entry':
                    logger.info(f"  类型: 网格开仓")
                    logger.info(f"  方向: {grid_signal.get('side')}")
                    logger.info(f"  层数: {grid_signal.get('layer')}")
                    logger.info(f"  价格: {grid_signal.get('price'):.2f}")
                    logger.info(f"  止损: {grid_signal.get('sl_price'):.2f}")
                    logger.info(f"  止盈: {grid_signal.get('tp_price'):.2f}")
            
            if trend_signal:
                logger.info(f"趋势信号: {trend_signal}")
                logger.info(f"  类型: {trend_signal.get('type')}")
                logger.info(f"  原因: {trend_signal.get('reason')}")
    
    # 总结
    logger.info("\n" + "=" * 80)
    logger.info("信号检查总结")
    logger.info("=" * 80)
    
    if signals:
        logger.info(f"共发现 {len(signals)} 个信号")
        
        grid_signals = [s for s in signals if s['grid_signal']]
        trend_signals = [s for s in signals if s['trend_signal']]
        
        logger.info(f"  网格信号: {len(grid_signals)} 个")
        logger.info(f"  趋势信号: {len(trend_signals)} 个")
        
        # 显示最近的信号
        logger.info(f"\n最近3个信号:")
        for i, sig in enumerate(signals[-3:], 1):
            logger.info(f"\n{i}. {sig['timestamp']}")
            logger.info(f"   价格: {sig['price']:.2f}, 市场状态: {sig['regime']}, 大趋势: {sig['big_trend']}")
            if sig['grid_signal']:
                logger.info(f"   网格信号: {sig['grid_signal'].get('type')} - {sig['grid_signal'].get('side')}")
            if sig['trend_signal']:
                logger.info(f"   趋势信号: {sig['trend_signal'].get('type')}")
    else:
        logger.warning(f"最近 {check_days} 天内没有发现任何交易信号！")
        logger.info("\n可能的原因:")
        logger.info("1. 市场状态不符合开仓条件（不是RANGE_BOUND或TRENDING）")
        logger.info("2. 网格条件不满足（箱体范围、价格位置等）")
        logger.info("3. 趋势条件不满足（回调幅度、反转K线等）")
        logger.info("4. 大趋势方向不符合网格方向要求")
        
        # 输出最近的状态信息
        if len(ltf) > 0:
            last_row = ltf.iloc[-1]
            last_ts = last_row['timestamp']
            last_price = last_row['close']
            
            last_htf_idx = engine._idx(last_ts, engine._cache['htf_ts'])
            last_mtf_idx = engine._idx(last_ts, engine._cache['mtf_ts'])
            
            if last_htf_idx is not None and last_mtf_idx is not None:
                last_regime = engine._get_market_regime(last_htf_idx, len(ltf) - 1)
                last_big_trend = engine._get_big_trend(last_htf_idx)
                last_box_high = engine._cache['box_h'].iloc[-1] if len(engine._cache['box_h']) > 0 else None
                last_box_low = engine._cache['box_l'].iloc[-1] if len(engine._cache['box_l']) > 0 else None
                
                logger.info(f"\n最新状态 ({last_ts}):")
                logger.info(f"  价格: {last_price:.2f}")
                logger.info(f"  市场状态: {last_regime.value}")
                logger.info(f"  大趋势: {last_big_trend.value}")
                if last_box_high and last_box_low:
                    logger.info(f"  箱体: [{last_box_low:.2f}, {last_box_high:.2f}]")
                    logger.info(f"  价格在箱体内: {last_box_low <= last_price <= last_box_high}")
                    logger.info(f"  箱体范围: {((last_box_high - last_box_low) / last_box_low * 100):.2f}%")

# ============================================================================
# 主函数
# ============================================================================
def main():
    """主函数"""
    import argparse
    parser = argparse.ArgumentParser(description='检查最近BTC交易信号')
    parser.add_argument('--symbol', default='BTC/USDT', help='交易对')
    parser.add_argument('--days', type=int, default=60, help='获取多少天的历史数据')
    parser.add_argument('--check-days', type=int, default=3, help='检查最近几天的信号')
    args = parser.parse_args()
    
    check_recent_signals(args.symbol, args.days, args.check_days)

if __name__ == '__main__':
    main()
