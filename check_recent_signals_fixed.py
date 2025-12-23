#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查最近BTC交易信号（修复版）
==================
修复问题：
1. 确保获取足够的历史数据（至少70天，用于计算箱体）
2. 添加数据完整性检查
3. 添加时区处理
4. 添加更详细的诊断信息
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
# 数据获取函数（修复版）
# ============================================================================
def fetch_recent_data(symbol: str = 'BTC/USDT', days: int = 60) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    从币安获取最近的数据（确保有足够的历史数据）
    
    Args:
        symbol: 交易对
        days: 获取最近多少天的数据（至少需要70天用于计算箱体）
    
    Returns:
        (ltf_15m, mtf_1h, htf_4h)
    """
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        
        # 【修复】确保至少有70天数据用于计算箱体
        min_days = 70
        actual_days = max(days, min_days)
        
        # 计算时间范围
        end_date = datetime.now()
        start_date = end_date - timedelta(days=actual_days)
        
        start_ts = int(start_date.timestamp() * 1000)
        end_ts = int(end_date.timestamp() * 1000)
        
        logger.info(f"从币安获取 {symbol} 最近 {actual_days} 天数据（至少需要{min_days}天用于计算指标）...")
        logger.info(f"时间范围: {start_date.strftime('%Y-%m-%d %H:%M:%S')} 到 {end_date.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 下载15m数据
        ltf_data = []
        current_ts = start_ts
        max_iterations = 100  # 防止无限循环
        iteration = 0
        
        while current_ts < end_ts and iteration < max_iterations:
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, '15m', since=current_ts, limit=1000)
                if not ohlcv or len(ohlcv) == 0:
                    break
                ltf_data.extend(ohlcv)
                new_ts = ohlcv[-1][0] + 1
                if new_ts <= current_ts:  # 防止死循环
                    break
                current_ts = new_ts
                if len(ohlcv) < 1000:
                    break
                iteration += 1
            except Exception as e:
                logger.warning(f"获取15m数据时出错: {e}")
                break
        
        if not ltf_data:
            logger.error(f"未获取到 {symbol} 15m 数据")
            return None, None, None
        
        ltf = pd.DataFrame(ltf_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        ltf['timestamp'] = pd.to_datetime(ltf['timestamp'], unit='ms')
        # 【修复】不过滤end_ts，保留所有数据
        ltf = ltf.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
        
        logger.info(f"15m数据: {len(ltf)} 条，时间范围: {ltf['timestamp'].min()} 到 {ltf['timestamp'].max()}")
        
        # 检查数据量是否足够
        if len(ltf) < 500:
            logger.warning(f"15m数据量不足（{len(ltf)}条），可能影响指标计算")
        
        # 下载4h数据
        htf_data = []
        current_ts = start_ts
        iteration = 0
        
        while current_ts < end_ts and iteration < max_iterations:
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, '4h', since=current_ts, limit=1000)
                if not ohlcv or len(ohlcv) == 0:
                    break
                htf_data.extend(ohlcv)
                new_ts = ohlcv[-1][0] + 1
                if new_ts <= current_ts:
                    break
                current_ts = new_ts
                if len(ohlcv) < 1000:
                    break
                iteration += 1
            except Exception as e:
                logger.warning(f"获取4h数据时出错: {e}")
                break
        
        if not htf_data:
            logger.error(f"未获取到 {symbol} 4h 数据")
            return None, None, None
        
        htf = pd.DataFrame(htf_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        htf['timestamp'] = pd.to_datetime(htf['timestamp'], unit='ms')
        htf = htf.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
        
        logger.info(f"4h数据: {len(htf)} 条，时间范围: {htf['timestamp'].min()} 到 {htf['timestamp'].max()}")
        
        # 检查数据量是否足够
        if len(htf) < 100:
            logger.warning(f"4h数据量不足（{len(htf)}条），可能影响指标计算")
        
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
        
        # 【修复】检查数据完整性
        logger.info(f"\n数据完整性检查:")
        logger.info(f"  15m数据: {len(ltf)} 条，最新: {ltf['timestamp'].max()}")
        logger.info(f"  1h数据: {len(mtf)} 条，最新: {mtf['timestamp'].max()}")
        logger.info(f"  4h数据: {len(htf)} 条，最新: {htf['timestamp'].max()}")
        logger.info(f"  当前时间: {datetime.now()}")
        
        # 检查数据是否足够新（应该在最近1小时内）
        latest_15m = ltf['timestamp'].max()
        time_diff = (datetime.now() - latest_15m).total_seconds() / 3600
        if time_diff > 2:
            logger.warning(f"15m数据可能不是最新的（最新数据是 {time_diff:.1f} 小时前）")
        
        return ltf, mtf, htf
        
    except Exception as e:
        logger.error(f"获取数据失败: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None

# ============================================================================
# 信号检查函数（修复版）
# ============================================================================
def check_recent_signals(symbol: str = 'BTC/USDT', days: int = 60, check_days: int = 3):
    """
    检查最近几天的交易信号
    
    Args:
        symbol: 交易对
        days: 获取多少天的历史数据（至少70天）
        check_days: 检查最近几天的信号
    """
    logger.info("=" * 80)
    logger.info(f"检查 {symbol} 最近 {check_days} 天的交易信号")
    logger.info("=" * 80)
    
    # 【修复】确保至少有70天数据
    min_days = 70
    actual_days = max(days, min_days)
    if days < min_days:
        logger.warning(f"数据天数不足，自动调整为 {actual_days} 天（至少需要{min_days}天用于计算箱体等指标）")
    
    # 获取数据
    ltf, mtf, htf = fetch_recent_data(symbol, actual_days)
    
    if ltf is None or mtf is None or htf is None:
        logger.error("数据获取失败")
        return
    
    # 检查数据量
    if len(ltf) < 500 or len(mtf) < 200 or len(htf) < 100:
        logger.error(f"数据量不足: LTF={len(ltf)}, MTF={len(mtf)}, HTF={len(htf)}")
        logger.error("这可能导致指标计算不准确，建议获取更多历史数据")
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
    logger.info("预计算指标...")
    try:
        engine._precalc(ltf, mtf, htf)
        logger.info("指标预计算完成")
    except Exception as e:
        logger.error(f"指标预计算失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 找到检查时间范围的起始索引
    check_start_idx = ltf[ltf['timestamp'] >= check_start_time].index[0] if len(ltf[ltf['timestamp'] >= check_start_time]) > 0 else len(ltf) - 100
    
    logger.info(f"\n开始检查信号（从索引 {check_start_idx} 开始，共 {len(ltf) - check_start_idx} 根K线）...")
    logger.info("=" * 80)
    
    signals = []
    min_bar = max(cfg.BOX_LOOKBACK_PERIODS, cfg.ATR_PERCENTILE_PERIOD, cfg.EMA_SLOW_PERIOD) + 10
    
    logger.info(f"最小K线数要求: {min_bar} (用于指标计算)")
    
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
        logger.info("5. 【重要】数据量不足，导致指标计算不准确")
        
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
                    logger.info(f"  箱体范围是否满足要求（>=5%）: {((last_box_high - last_box_low) / last_box_low * 100) >= 5.0}")
                
                # 【新增】诊断信息
                logger.info(f"\n诊断信息:")
                logger.info(f"  数据量: LTF={len(ltf)}, MTF={len(mtf)}, HTF={len(htf)}")
                logger.info(f"  数据最新时间: {last_ts}")
                logger.info(f"  当前时间: {datetime.now()}")
                logger.info(f"  时间差: {(datetime.now() - last_ts).total_seconds() / 3600:.1f} 小时")
                
                # 检查为什么没有信号
                if last_regime == MarketRegime.UNCERTAIN:
                    logger.warning("  市场状态是UNCERTAIN，这可能是数据不足导致的！")
                    logger.warning("  建议获取至少70天的历史数据用于计算指标")
                elif last_regime == MarketRegime.RANGE_BOUND:
                    if last_box_high and last_box_low:
                        box_range = ((last_box_high - last_box_low) / last_box_low * 100)
                        if box_range < 5.0:
                            logger.warning(f"  箱体范围 {box_range:.2f}% < 5%，不满足网格交易要求")
                        if not (last_box_low <= last_price <= last_box_high):
                            logger.warning(f"  价格不在箱体内")
                        if last_big_trend == BigTrend.NEUTRAL:
                            logger.warning("  大趋势是NEUTRAL，可能无法确定网格方向")

# ============================================================================
# 主函数
# ============================================================================
def main():
    """主函数"""
    import argparse
    parser = argparse.ArgumentParser(description='检查最近BTC交易信号（修复版）')
    parser.add_argument('--symbol', default='BTC/USDT', help='交易对')
    parser.add_argument('--days', type=int, default=70, help='获取多少天的历史数据（至少70天）')
    parser.add_argument('--check-days', type=int, default=3, help='检查最近几天的信号')
    args = parser.parse_args()
    
    check_recent_signals(args.symbol, args.days, args.check_days)

if __name__ == '__main__':
    main()
