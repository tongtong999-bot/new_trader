#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按年份回测脚本（2022, 2023, 2024）
==================================
功能：
1. 按年份分别回测各个币种
2. 每个年份生成独立的总结表格
3. 网格和趋势交易收益分开统计
4. 总收益统计
5. 如果数据缺失，从币安下载
"""

import sys
import os
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime
import logging
import ccxt
from typing import Dict, List, Optional, Tuple

# 添加策略路径
sys.path.insert(0, str(Path(__file__).parent / 'strategies'))

from box_strategy_v5_2 import StrategyConfig, BacktestEngine

# ============================================================================
# 日志配置
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# 配置
# ============================================================================
DATA_DIR = Path(__file__).parent.parent / 'data'
OUTPUT_DIR = Path(__file__).parent / 'backtest_yearly_results'

# 要回测的币种列表
SYMBOLS = [
    'BTC', 'ETH', 'SOL', 'XRP', 'LTC', 'BCH', 'AVAX', 'ADA', 'DOT', 
    'BNB', 'SUI', 'PUMP', 'AAVE', 'LINK', 'UNI', 'ICP', 'HYPE'
]

# 如果只想测试部分币种，可以修改为：
# SYMBOLS = ['BTC', 'ETH']  # 测试用

# 要回测的年份
YEARS = [2022, 2023, 2024]

# 初始资金（每个币种）
INIT_BALANCE = 10000  # 趋势1万 + 网格1万 = 2万

# ============================================================================
# 数据下载函数
# ============================================================================
def download_data(symbol: str, year: int, timeframe_15m: str = '15m', timeframe_4h: str = '4h') -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    从币安下载数据
    
    Returns:
        (ltf_15m, mtf_1h, htf_4h) 或 (None, None, None) 如果失败
    """
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        
        # 计算时间范围
        if year == 2022:
            start_date = datetime(2022, 1, 1)
            end_date = datetime(2023, 1, 1)
        elif year == 2023:
            start_date = datetime(2023, 1, 1)
            end_date = datetime(2024, 1, 1)
        elif year == 2024:
            start_date = datetime(2024, 1, 1)
            end_date = datetime(2025, 1, 1)
        else:
            return None, None, None
        
        start_ts = int(start_date.timestamp() * 1000)
        end_ts = int(end_date.timestamp() * 1000)
        
        logger.info(f"下载 {symbol}/USDT {year}年数据...")
        
        # 下载15m数据
        ltf_data = []
        current_ts = start_ts
        while current_ts < end_ts:
            ohlcv = exchange.fetch_ohlcv(f'{symbol}/USDT', timeframe_15m, since=current_ts, limit=1000)
            if not ohlcv:
                break
            ltf_data.extend(ohlcv)
            current_ts = ohlcv[-1][0] + 1
            if len(ohlcv) < 1000:
                break
        
        if not ltf_data:
            logger.warning(f"未获取到 {symbol}/USDT {year}年 15m 数据")
            return None, None, None
        
        ltf = pd.DataFrame(ltf_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        ltf['timestamp'] = pd.to_datetime(ltf['timestamp'], unit='ms')
        ltf = ltf[ltf['timestamp'] < pd.to_datetime(end_ts, unit='ms')]
        
        # 下载4h数据
        htf_data = []
        current_ts = start_ts
        while current_ts < end_ts:
            ohlcv = exchange.fetch_ohlcv(f'{symbol}/USDT', timeframe_4h, since=current_ts, limit=1000)
            if not ohlcv:
                break
            htf_data.extend(ohlcv)
            current_ts = ohlcv[-1][0] + 1
            if len(ohlcv) < 1000:
                break
        
        if not htf_data:
            logger.warning(f"未获取到 {symbol}/USDT {year}年 4h 数据")
            return None, None, None
        
        htf = pd.DataFrame(htf_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        htf['timestamp'] = pd.to_datetime(htf['timestamp'], unit='ms')
        htf = htf[htf['timestamp'] < pd.to_datetime(end_ts, unit='ms')]
        
        # 从15m数据重采样生成1h数据
        ltf_indexed = ltf.set_index('timestamp')
        mtf = ltf_indexed.resample('1h').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna().reset_index()
        
        # 保存数据
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        ltf_file = DATA_DIR / f'{symbol}_USDT_15m_{year}.csv'
        mtf_file = DATA_DIR / f'{symbol}_USDT_1h_{year}.csv'
        htf_file = DATA_DIR / f'{symbol}_USDT_4h_{year}.csv'
        
        ltf.to_csv(ltf_file, index=False)
        mtf.to_csv(mtf_file, index=False)
        htf.to_csv(htf_file, index=False)
        
        logger.info(f"数据已保存: {ltf_file}, {mtf_file}, {htf_file}")
        
        return ltf, mtf, htf
        
    except Exception as e:
        logger.error(f"下载 {symbol}/USDT {year}年数据失败: {e}")
        return None, None, None

# ============================================================================
# 数据加载函数
# ============================================================================
def load_data(symbol: str, year: int) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    加载数据文件
    
    Returns:
        (ltf_15m, mtf_1h, htf_4h) 或 (None, None, None) 如果文件不存在
    """
    def read_csv_file(file_path: Path) -> Optional[pd.DataFrame]:
        """读取CSV文件，处理不同的列格式"""
        if not file_path.exists():
            return None
        try:
            df = pd.read_csv(file_path)
            # 处理timestamp列（可能是datetime字符串或毫秒时间戳）
            if 'timestamp' in df.columns:
                if df['timestamp'].dtype == 'int64' or df['timestamp'].dtype == 'float64':
                    # 毫秒时间戳
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                else:
                    # 字符串格式
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
            elif 'datetime' in df.columns:
                df['timestamp'] = pd.to_datetime(df['datetime'])
            return df
        except Exception as e:
            logger.error(f"读取文件失败 {file_path}: {e}")
            return None
    
    # 检查2023年是否需要合并h1和h2
    if year == 2023:
        ltf_h1 = DATA_DIR / f'{symbol}_USDT_15m_2023h1.csv'
        ltf_h2 = DATA_DIR / f'{symbol}_USDT_15m_2023h2.csv'
        htf_h1 = DATA_DIR / f'{symbol}_USDT_4h_2023h1.csv'
        htf_h2 = DATA_DIR / f'{symbol}_USDT_4h_2023h2.csv'
        
        if ltf_h1.exists() and ltf_h2.exists():
            # 合并h1和h2
            ltf1 = read_csv_file(ltf_h1)
            ltf2 = read_csv_file(ltf_h2)
            if ltf1 is None or ltf2 is None:
                return None, None, None
            ltf = pd.concat([ltf1, ltf2], ignore_index=True)
            ltf = ltf.sort_values('timestamp').reset_index(drop=True)
            
            htf1 = read_csv_file(htf_h1)
            htf2 = read_csv_file(htf_h2)
            if htf1 is None or htf2 is None:
                return None, None, None
            htf = pd.concat([htf1, htf2], ignore_index=True)
            htf = htf.sort_values('timestamp').reset_index(drop=True)
            
            # 从15m重采样生成1h
            ltf_indexed = ltf.set_index('timestamp')
            mtf = ltf_indexed.resample('1h').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna().reset_index()
            
            return ltf, mtf, htf
        elif ltf_h1.exists():
            # 只有h1
            ltf = read_csv_file(ltf_h1)
            htf = read_csv_file(htf_h1)
            if ltf is None or htf is None:
                return None, None, None
        elif ltf_h2.exists():
            # 只有h2
            ltf = read_csv_file(ltf_h2)
            htf = read_csv_file(htf_h2)
            if ltf is None or htf is None:
                return None, None, None
        else:
            return None, None, None
    else:
        # 2022或2024年
        # 先尝试完整年份文件
        ltf_file = DATA_DIR / f'{symbol}_USDT_15m_{year}.csv'
        htf_file = DATA_DIR / f'{symbol}_USDT_4h_{year}.csv'
        
        # 如果2022年没有完整文件，尝试合并h2
        if year == 2022 and not ltf_file.exists():
            ltf_h2 = DATA_DIR / f'{symbol}_USDT_15m_2022h2.csv'
            htf_h2 = DATA_DIR / f'{symbol}_USDT_4h_2022h2.csv'
            if ltf_h2.exists() and htf_h2.exists():
                ltf = read_csv_file(ltf_h2)
                htf = read_csv_file(htf_h2)
                if ltf is None or htf is None:
                    return None, None, None
            else:
                return None, None, None
        elif not ltf_file.exists() or not htf_file.exists():
            return None, None, None
        else:
            ltf = read_csv_file(ltf_file)
            htf = read_csv_file(htf_file)
            if ltf is None or htf is None:
                return None, None, None
    
    # 确保timestamp是datetime类型
    if 'timestamp' not in ltf.columns:
        if 'datetime' in ltf.columns:
            ltf['timestamp'] = pd.to_datetime(ltf['datetime'])
        else:
            logger.error(f"数据文件缺少timestamp或datetime列: {symbol} {year}")
            return None, None, None
    
    if 'timestamp' not in htf.columns:
        if 'datetime' in htf.columns:
            htf['timestamp'] = pd.to_datetime(htf['datetime'])
        else:
            logger.error(f"数据文件缺少timestamp或datetime列: {symbol} {year}")
            return None, None, None
    
    ltf['timestamp'] = pd.to_datetime(ltf['timestamp'])
    htf['timestamp'] = pd.to_datetime(htf['timestamp'])
    
    # 从15m重采样生成1h
    ltf_indexed = ltf.set_index('timestamp')
    mtf = ltf_indexed.resample('1h').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna().reset_index()
    
    return ltf, mtf, htf

# ============================================================================
# 回测函数
# ============================================================================
def run_backtest(symbol: str, year: int) -> Optional[Dict]:
    """
    运行单个币种的回测
    
    Returns:
        回测结果字典，如果失败返回None
    """
    try:
        logger.info(f"开始回测 {symbol}/USDT {year}年...")
        
        # 加载数据
        ltf, mtf, htf = load_data(symbol, year)
        
        # 如果数据不存在，尝试下载
        if ltf is None or mtf is None or htf is None:
            logger.warning(f"{symbol}/USDT {year}年数据不存在，尝试下载...")
            ltf, mtf, htf = download_data(symbol, year)
            if ltf is None or mtf is None or htf is None:
                logger.error(f"无法获取 {symbol}/USDT {year}年数据")
                return None
        
        # 检查数据量
        if len(ltf) < 500 or len(mtf) < 200 or len(htf) < 100:
            logger.warning(f"{symbol}/USDT {year}年数据量不足: LTF={len(ltf)}, MTF={len(mtf)}, HTF={len(htf)}")
            return None
        
        # 创建配置
        cfg = StrategyConfig()
        cfg.SYMBOL = f'{symbol}/USDT'
        
        # 创建回测引擎
        engine = BacktestEngine(cfg)
        
        # 运行回测
        results = engine.run(ltf, mtf, htf, init_bal=INIT_BALANCE)
        
        # 计算网格和趋势收益（从results中获取，已修复）
        grid_pnl = results.get('grid_pnl', 0)
        trend_pnl = results.get('trend_pnl', 0)
        grid_trades_count = results.get('grid_trades', 0)
        trend_trades_count = results.get('trend_trades', 0)
        
        # 计算收益率
        total_init = INIT_BALANCE * 2  # 趋势1万 + 网格1万
        final_equity = results['final']
        total_return = (final_equity - total_init) / total_init * 100
        
        grid_return = (grid_pnl / INIT_BALANCE * 100) if INIT_BALANCE > 0 else 0
        trend_return = (trend_pnl / INIT_BALANCE * 100) if INIT_BALANCE > 0 else 0
        
        # 保存交易记录
        output_dir = OUTPUT_DIR / str(year)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        trades_file = output_dir / f'backtest_{symbol}_USDT_{year}_trades.csv'
        equity_file = output_dir / f'backtest_{symbol}_USDT_{year}_equity.csv'
        
        try:
            engine.save(str(trades_file), str(equity_file))
        except Exception as e:
            logger.warning(f"保存交易记录失败: {e}")
        
        # 返回结果
        return {
            'symbol': symbol,
            'year': year,
            'total_trades': results['trades'],
            'grid_trades': grid_trades_count,
            'trend_trades': trend_trades_count,
            'grid_pnl': grid_pnl,
            'trend_pnl': trend_pnl,
            'grid_return': grid_return,
            'trend_return': trend_return,
            'total_return': total_return,
            'total_pnl': grid_pnl + trend_pnl,
            'win_rate': results['win_rate'],
            'grid_win_rate': results.get('grid_win_rate', 0),
            'trend_win_rate': results.get('trend_win_rate', 0),
            'max_drawdown': results['dd'],
            'sharpe': results['sharpe'],
            'profit_factor': results['pf'],
            'init_balance': total_init,
            'final_equity': final_equity,
        }
        
    except Exception as e:
        logger.error(f"回测 {symbol}/USDT {year}年失败: {e}")
        import traceback
        traceback.print_exc()
        return None

# ============================================================================
# 主函数
# ============================================================================
def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("按年份回测脚本（2022, 2023, 2024）")
    logger.info("=" * 80)
    
    # 创建输出目录
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 按年份分别回测
    for year in YEARS:
        logger.info(f"\n{'='*80}")
        logger.info(f"开始回测 {year}年数据")
        logger.info(f"{'='*80}\n")
        
        year_results = []
        
        for symbol in SYMBOLS:
            result = run_backtest(symbol, year)
            if result:
                year_results.append(result)
                logger.info(f"{symbol}: 总收益={result['total_return']:.2f}%, "
                          f"网格={result['grid_return']:.2f}%, "
                          f"趋势={result['trend_return']:.2f}%")
            else:
                logger.warning(f"{symbol}: 回测失败或数据缺失")
        
        # 生成总结表格
        if year_results:
            df = pd.DataFrame(year_results)
            
            # 排序
            df = df.sort_values('total_return', ascending=False)
            
            # 保存CSV
            summary_file = OUTPUT_DIR / f'backtest_summary_{year}.csv'
            df.to_csv(summary_file, index=False, encoding='utf-8-sig')
            logger.info(f"\n{year}年回测总结已保存: {summary_file}")
            
            # 打印表格
            logger.info(f"\n{year}年回测总结:")
            logger.info("=" * 120)
            print(df.to_string(index=False))
            logger.info("=" * 120)
            
            # 计算总计
            total_init = df['init_balance'].sum()
            total_final = df['final_equity'].sum()
            total_return_all = (total_final - total_init) / total_init * 100
            total_grid_pnl = df['grid_pnl'].sum()
            total_trend_pnl = df['trend_pnl'].sum()
            
            logger.info(f"\n{year}年总计:")
            logger.info(f"  初始资金: {total_init:,.0f} USDT")
            logger.info(f"  最终权益: {total_final:,.0f} USDT")
            logger.info(f"  总收益: {total_return_all:.2f}%")
            logger.info(f"  网格收益: {total_grid_pnl:,.2f} USDT ({total_grid_pnl/total_init*100:.2f}%)")
            logger.info(f"  趋势收益: {total_trend_pnl:,.2f} USDT ({total_trend_pnl/total_init*100:.2f}%)")
            logger.info(f"  总盈亏: {total_grid_pnl + total_trend_pnl:,.2f} USDT")
        else:
            logger.warning(f"{year}年没有成功的回测结果")
    
    logger.info("\n" + "=" * 80)
    logger.info("所有年份回测完成")
    logger.info("=" * 80)

if __name__ == '__main__':
    main()
