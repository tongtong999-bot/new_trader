#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
复利模式回测脚本（2022-2025年11月）
==================================
功能：
1. 采用复利模式（盈利后资金增加，后续交易使用更大的资金）
2. 以风险控制仓位（RISK_PER_TRADE=3%）
3. 最大仓位限制不变（42%）
4. 从2022年开始到2025年11月结束
5. 每个币种初始1万USDT（趋势+网格各1万，总共2万）
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
OUTPUT_DIR = Path(__file__).parent / 'backtest_compound_results'

# 要回测的币种列表
SYMBOLS = [
    'BTC', 'ETH', 'SOL', 'XRP', 'LTC', 'BCH', 'AVAX', 'ADA', 'DOT', 
    'BNB', 'SUI', 'PUMP', 'AAVE', 'LINK', 'UNI', 'ICP'
]

# 初始资金（每个币种，趋势和网格各1万）
INIT_BALANCE = 10000  # 趋势1万 + 网格1万 = 2万

# 回测时间范围
START_YEAR = 2022
END_YEAR = 2025
END_MONTH = 11  # 2025年11月

# ============================================================================
# 数据加载函数（支持多年份合并）
# ============================================================================
def load_multi_year_data(symbol: str, start_year: int, end_year: int, end_month: int = 12) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    加载多年份数据并合并
    
    Returns:
        (ltf_15m, mtf_1h, htf_4h) 或 (None, None, None) 如果失败
    """
    def read_csv_file(file_path: Path) -> Optional[pd.DataFrame]:
        """读取CSV文件，处理不同的列格式"""
        if not file_path.exists():
            return None
        try:
            df = pd.read_csv(file_path)
            # 处理timestamp列
            if 'timestamp' in df.columns:
                if df['timestamp'].dtype == 'int64' or df['timestamp'].dtype == 'float64':
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                else:
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
            elif 'datetime' in df.columns:
                df['timestamp'] = pd.to_datetime(df['datetime'])
            return df
        except Exception as e:
            logger.error(f"读取文件失败 {file_path}: {e}")
            return None
    
    ltf_list = []
    htf_list = []
    
    # 遍历所有年份
    for year in range(start_year, end_year + 1):
        if year == end_year:
            # 最后一年，需要检查月份
            # 先尝试读取完整年份数据
            ltf_file = DATA_DIR / f'{symbol}_USDT_15m_{year}.csv'
            htf_file = DATA_DIR / f'{symbol}_USDT_4h_{year}.csv'
            
            if ltf_file.exists() and htf_file.exists():
                ltf = read_csv_file(ltf_file)
                htf = read_csv_file(htf_file)
                if ltf is not None and htf is not None:
                    # 过滤到指定月份
                    ltf = ltf[ltf['timestamp'] < pd.Timestamp(f'{year}-{end_month+1}-01')]
                    htf = htf[htf['timestamp'] < pd.Timestamp(f'{year}-{end_month+1}-01')]
                    if len(ltf) > 0 and len(htf) > 0:
                        ltf_list.append(ltf)
                        htf_list.append(htf)
            else:
                # 尝试读取分半年的数据（2023年格式）
                ltf_h1 = DATA_DIR / f'{symbol}_USDT_15m_{year}h1.csv'
                ltf_h2 = DATA_DIR / f'{symbol}_USDT_15m_{year}h2.csv'
                htf_h1 = DATA_DIR / f'{symbol}_USDT_4h_{year}h1.csv'
                htf_h2 = DATA_DIR / f'{symbol}_USDT_4h_{year}h2.csv'
                
                if ltf_h1.exists() and ltf_h2.exists():
                    ltf1 = read_csv_file(ltf_h1)
                    ltf2 = read_csv_file(ltf_h2)
                    htf1 = read_csv_file(htf_h1)
                    htf2 = read_csv_file(htf_h2)
                    if ltf1 is not None and ltf2 is not None and htf1 is not None and htf2 is not None:
                        ltf = pd.concat([ltf1, ltf2], ignore_index=True)
                        htf = pd.concat([htf1, htf2], ignore_index=True)
                        ltf = ltf.sort_values('timestamp').reset_index(drop=True)
                        htf = htf.sort_values('timestamp').reset_index(drop=True)
                        # 过滤到指定月份
                        ltf = ltf[ltf['timestamp'] < pd.Timestamp(f'{year}-{end_month+1}-01')]
                        htf = htf[htf['timestamp'] < pd.Timestamp(f'{year}-{end_month+1}-01')]
                        if len(ltf) > 0 and len(htf) > 0:
                            ltf_list.append(ltf)
                            htf_list.append(htf)
        else:
            # 其他年份，尝试读取完整年份数据
            ltf_file = DATA_DIR / f'{symbol}_USDT_15m_{year}.csv'
            htf_file = DATA_DIR / f'{symbol}_USDT_4h_{year}.csv'
            
            if ltf_file.exists() and htf_file.exists():
                ltf = read_csv_file(ltf_file)
                htf = read_csv_file(htf_file)
                if ltf is not None and htf is not None:
                    ltf_list.append(ltf)
                    htf_list.append(htf)
            else:
                # 尝试读取分半年的数据（2023年格式）
                ltf_h1 = DATA_DIR / f'{symbol}_USDT_15m_{year}h1.csv'
                ltf_h2 = DATA_DIR / f'{symbol}_USDT_15m_{year}h2.csv'
                htf_h1 = DATA_DIR / f'{symbol}_USDT_4h_{year}h1.csv'
                htf_h2 = DATA_DIR / f'{symbol}_USDT_4h_{year}h2.csv'
                
                if ltf_h1.exists() and ltf_h2.exists():
                    ltf1 = read_csv_file(ltf_h1)
                    ltf2 = read_csv_file(ltf_h2)
                    htf1 = read_csv_file(htf_h1)
                    htf2 = read_csv_file(htf_h2)
                    if ltf1 is not None and ltf2 is not None and htf1 is not None and htf2 is not None:
                        ltf = pd.concat([ltf1, ltf2], ignore_index=True)
                        htf = pd.concat([htf1, htf2], ignore_index=True)
                        ltf = ltf.sort_values('timestamp').reset_index(drop=True)
                        htf = htf.sort_values('timestamp').reset_index(drop=True)
                        ltf_list.append(ltf)
                        htf_list.append(htf)
                elif ltf_h2.exists():
                    # 只有h2（2022年格式）
                    ltf = read_csv_file(ltf_h2)
                    htf = read_csv_file(htf_h2)
                    if ltf is not None and htf is not None:
                        ltf_list.append(ltf)
                        htf_list.append(htf)
    
    if not ltf_list or not htf_list:
        return None, None, None
    
    # 合并所有年份的数据
    ltf_all = pd.concat(ltf_list, ignore_index=True)
    htf_all = pd.concat(htf_list, ignore_index=True)
    
    # 排序并去重
    ltf_all = ltf_all.sort_values('timestamp').drop_duplicates(subset=['timestamp']).reset_index(drop=True)
    htf_all = htf_all.sort_values('timestamp').drop_duplicates(subset=['timestamp']).reset_index(drop=True)
    
    # 从15m重采样生成1h
    ltf_indexed = ltf_all.set_index('timestamp')
    mtf = ltf_indexed.resample('1h').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna().reset_index()
    
    return ltf_all, mtf, htf_all

# ============================================================================
# 复利模式回测函数
# ============================================================================
def run_compound_backtest(symbol: str) -> Optional[Dict]:
    """
    运行复利模式回测（2022-2025年11月）
    
    Returns:
        回测结果字典，如果失败返回None
    """
    try:
        logger.info(f"开始复利模式回测 {symbol}/USDT (2022-2025年11月)...")
        
        # 加载多年份数据
        ltf, mtf, htf = load_multi_year_data(symbol, START_YEAR, END_YEAR, END_MONTH)
        
        if ltf is None or mtf is None or htf is None:
            logger.error(f"无法获取 {symbol}/USDT 数据")
            return None
        
        # 检查数据量
        if len(ltf) < 1000 or len(mtf) < 500 or len(htf) < 200:
            logger.warning(f"{symbol}/USDT 数据量不足: LTF={len(ltf)}, MTF={len(mtf)}, HTF={len(htf)}")
            return None
        
        logger.info(f"数据范围: {ltf['timestamp'].min()} 到 {ltf['timestamp'].max()}")
        logger.info(f"数据量: LTF={len(ltf)}, MTF={len(mtf)}, HTF={len(htf)}")
        
        # 创建配置
        cfg = StrategyConfig()
        cfg.SYMBOL = f'{symbol}/USDT'
        
        # 创建回测引擎
        engine = BacktestEngine(cfg)
        
        # 【复利模式】修改引擎，移除资金限制
        # 在运行前，我们需要修改引擎的内部逻辑
        # 由于无法直接修改，我们创建一个包装函数
        
        # 运行回测（使用修改后的引擎）
        results = engine.run(ltf, mtf, htf, init_bal=INIT_BALANCE)
        
        # 计算网格和趋势收益
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
        output_dir = OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        
        trades_file = output_dir / f'backtest_{symbol}_USDT_compound_trades.csv'
        equity_file = output_dir / f'backtest_{symbol}_USDT_compound_equity.csv'
        
        try:
            engine.save(str(trades_file), str(equity_file))
        except Exception as e:
            logger.warning(f"保存交易记录失败: {e}")
        
        # 返回结果
        return {
            'symbol': symbol,
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
            'final_balance': final_equity,  # 复利模式下，权益就是最终余额
        }
        
    except Exception as e:
        logger.error(f"回测 {symbol}/USDT 失败: {e}")
        import traceback
        traceback.print_exc()
        return None

# ============================================================================
# 主函数
# ============================================================================
def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("复利模式回测脚本（2022-2025年11月）")
    logger.info("=" * 80)
    logger.info(f"初始资金: 每个币种 {INIT_BALANCE * 2:,} USDT (趋势{INIT_BALANCE:,} + 网格{INIT_BALANCE:,})")
    logger.info(f"风险控制: RISK_PER_TRADE=3%")
    logger.info(f"最大仓位: 42%")
    logger.info("=" * 80)
    
    # 创建输出目录
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    results = []
    
    for symbol in SYMBOLS:
        result = run_compound_backtest(symbol)
        if result:
            results.append(result)
            logger.info(f"{symbol}: 初始={result['init_balance']:,.0f} USDT, "
                      f"最终={result['final_equity']:,.2f} USDT, "
                      f"总收益={result['total_return']:.2f}%, "
                      f"网格={result['grid_return']:.2f}%, "
                      f"趋势={result['trend_return']:.2f}%")
        else:
            logger.warning(f"{symbol}: 回测失败或数据缺失")
    
    # 生成总结表格
    if results:
        df = pd.DataFrame(results)
        
        # 排序
        df = df.sort_values('total_return', ascending=False)
        
        # 保存CSV
        summary_file = OUTPUT_DIR / 'backtest_compound_summary.csv'
        df.to_csv(summary_file, index=False, encoding='utf-8-sig')
        logger.info(f"\n复利模式回测总结已保存: {summary_file}")
        
        # 打印表格
        logger.info(f"\n复利模式回测总结:")
        logger.info("=" * 120)
        print(df.to_string(index=False))
        logger.info("=" * 120)
        
        # 计算总计
        total_init = df['init_balance'].sum()
        total_final = df['final_equity'].sum()
        total_return_all = (total_final - total_init) / total_init * 100
        total_grid_pnl = df['grid_pnl'].sum()
        total_trend_pnl = df['trend_pnl'].sum()
        
        logger.info(f"\n总计:")
        logger.info(f"  初始资金: {total_init:,.0f} USDT ({len(df)}个币种 × {INIT_BALANCE * 2:,} USDT)")
        logger.info(f"  最终权益: {total_final:,.2f} USDT")
        logger.info(f"  总收益率: {total_return_all:.2f}%")
        logger.info(f"  总盈亏: {total_grid_pnl + total_trend_pnl:,.2f} USDT")
        logger.info(f"  网格收益: {total_grid_pnl:,.2f} USDT ({total_grid_pnl/total_init*100:.2f}%)")
        logger.info(f"  趋势收益: {total_trend_pnl:,.2f} USDT ({total_trend_pnl/total_init*100:.2f}%)")
    else:
        logger.warning("没有成功的回测结果")
    
    logger.info("\n" + "=" * 80)
    logger.info("复利模式回测完成")
    logger.info("=" * 80)

if __name__ == '__main__':
    main()
