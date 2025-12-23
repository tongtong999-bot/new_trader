#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动态箱体均值回归策略 v5.2
========================
基于v5.1的优化：
1. 提高风险：RISK_PER_TRADE 1% → 2%
2. 延长持仓：FULL_TP_R_MULTIPLE 3R → 5R
3. 放宽移动止损：TRAILING_STOP_DISTANCE 1倍ATR → 1.5倍ATR
4. 禁用箱体交易：只做趋势交易（箱体交易累计亏损-$1,763）
5. 取消分批建仓：一次性建仓提高资金利用率

预期改进：年化收益率 4.88% → 10-12%

作者：Trading Assistant
日期：2024
"""

import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import logging
import json
import time
import os

# ============================================================================
# 日志配置
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# 枚举类型
# ============================================================================
class TrendDirection(Enum):
    UP = "up"
    DOWN = "down"
    NEUTRAL = "neutral"


class SignalType(Enum):
    LONG = "long"
    SHORT = "short"
    NONE = "none"


class PositionPhase(Enum):
    NONE = 0
    BATCH1 = 1
    BATCH2 = 2
    BATCH3 = 3


class MarketRegime(Enum):
    """市场状态"""
    RANGE_BOUND = "range_bound"      # 震荡箱体 - 做均值回归
    TRENDING_UP = "trending_up"      # 上升趋势 - 顺势做多
    TRENDING_DOWN = "trending_down"  # 下降趋势 - 顺势做空
    UNCERTAIN = "uncertain"          # 不确定 - 观望


class BigTrend(Enum):
    """大趋势方向（用于顺势交易过滤）"""
    BULLISH = "bullish"   # 牛市 - 只做多
    BEARISH = "bearish"   # 熊市 - 只做空
    NEUTRAL = "neutral"   # 中性 - 双向


class RejectReason(Enum):
    NONE = "none"
    MARKET_REGIME = "market_regime"
    TREND_NOT_CONFIRMED = "trend_not_confirmed"
    PRICE_NOT_IN_ZONE = "price_not_in_zone"
    VOLATILITY_FILTER = "volatility_filter"
    SCORE_TOO_LOW = "score_too_low"
    DAILY_LIMIT = "daily_limit"
    INSUFFICIENT_DATA = "insufficient_data"
    NO_SIGNAL = "no_signal"
    AGAINST_BIG_TREND = "against_big_trend"  # 逆大势


class TradingMode(Enum):
    CONSERVATIVE = "conservative"
    STANDARD = "standard"
    AGGRESSIVE = "aggressive"


class CoinTier(Enum):
    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3
    BLACKLIST = 99


COIN_TIERS: Dict[str, CoinTier] = {
    "TAO/USDT": CoinTier.TIER_1, "PUMP/USDT": CoinTier.TIER_1,
    "FET/USDT": CoinTier.TIER_1, "INJ/USDT": CoinTier.TIER_1,
    "BTC/USDT": CoinTier.TIER_2, "ETH/USDT": CoinTier.TIER_2,
    "SOL/USDT": CoinTier.TIER_2, "DOGE/USDT": CoinTier.TIER_3,
}


# ============================================================================
# 策略配置
# ============================================================================
@dataclass
class StrategyConfig:
    EXCHANGE_ID: str = 'binance'
    API_KEY: str = ''
    API_SECRET: str = ''
    SANDBOX_MODE: bool = True
    SYMBOL: str = 'BTC/USDT'
    
    LTF_TIMEFRAME: str = '15m'
    MTF_TIMEFRAME: str = '1h'
    HTF_TIMEFRAME: str = '4h'
    
    # 箱体参数
    BOX_LOOKBACK_PERIODS: int = 70
    BOX_MIN_RANGE_PCT: float = 2.0
    BOX_MAX_RANGE_PCT: float = 15.0
    
    # 【v5.1新增】固定箱体参数
    USE_FIXED_BOX: bool = True                # 使用固定箱体
    BOX_ESCAPE_ATR_MULT: float = 2.0          # 价格远离多少ATR后重新计算箱体
    BOX_ESCAPE_BARS: int = 3                   # 连续多少根K线在箱体外才重新计算
    
    # 【v5.1新增】顺大势参数
    TREND_FOLLOWING_MODE: bool = True         # 启用顺势模式
    BIG_TREND_EMA_FAST: int = 20              # 大趋势判断：快线周期
    BIG_TREND_EMA_SLOW: int = 100             # 大趋势判断：慢线周期
    
    # 入场区域：做多0-0.20，做空0.80-1
    DISCOUNT_ZONE_MIN: float = 0.0
    DISCOUNT_ZONE_MAX: float = 0.20
    PREMIUM_ZONE_MIN: float = 0.80
    PREMIUM_ZONE_MAX: float = 1.0
    
    # 趋势判断EMA周期
    EMA_FAST_PERIOD: int = 20
    EMA_MID_PERIOD: int = 50
    EMA_SLOW_PERIOD: int = 100
    
    # 趋势确认：连续N根K线不触碰EMA
    TREND_CONFIRMATION_BARS: int = 3
    
    # ATR参数
    ATR_PERIOD: int = 14
    ATR_PERCENTILE_PERIOD: int = 100
    ATR_PERCENTILE_MIN: float = 15.0
    ATR_PERCENTILE_MAX: float = 85.0
    
    # 信号评分配置
    TRADING_MODE: TradingMode = TradingMode.STANDARD
    SCORE_THRESHOLD_CONSERVATIVE: int = 75
    SCORE_THRESHOLD_STANDARD: int = 999  # v5.2: 禁用箱体交易（设为极高值）
    SCORE_THRESHOLD_AGGRESSIVE: int = 50
    
    # v5.2: 禁用箱体交易
    DISABLE_BOX_TRADING: bool = True
    
    # 【v5.3新增】网格策略参数
    ENABLE_GRID_TRADING: bool = True  # 启用网格，但弱化风险/频次
    GRID_MIN_INTERVAL_PCT: float = 4.0  # 更大间隔，降低频率
    GRID_MIN_BOX_RANGE_PCT: float = 5.0  # 箱体最小区间（5%）
    GRID_MAX_LAYERS: int = 8  # 限制层数
    GRID_RISK_PER_LAYER: float = 1.5  # 单层风险 1.5%
    GRID_MAX_POSITION_PCT: float = 90.0  # 总网格风险不超90%
    GRID_SL_MULTIPLIER: float = 1.5  # 【优化】网格止损倍数（1.5倍间隔，从1倍提升）
    
    SCORE_WEIGHT_TREND_DIRECTION: int = 25
    SCORE_WEIGHT_TREND_STRENGTH: int = 20
    SCORE_WEIGHT_PRICE_POSITION: int = 25
    SCORE_WEIGHT_MTF_CONFIRMATION: int = 10
    SCORE_WEIGHT_REVERSAL_CANDLE: int = 10
    SCORE_WEIGHT_VOLATILITY: int = 10
    
    RISK_PER_TRADE: float = 15.0  # 趋势单风险 15%
    LONG_RISK_MULTIPLIER: float = 1.0  # 多头风险系数
    SHORT_RISK_MULTIPLIER: float = 1.3  # 空头风险系数（适度更激进）
    
    # 止损：2倍ATR
    STOP_LOSS_ATR_MULTIPLIER: float = 2.5
    TRAILING_STOP_ACTIVATION: float = 2.0
    TRAILING_STOP_DISTANCE: float = 1.5  # v5.2: 放宽移动止损 1.0 → 1.5
    
    # 分批建仓参数 v5.2: 一次性建仓，提高资金利用率
    BATCH1_RATIO: float = 1.0  # 一次性建仓100%
    BATCH2_RATIO: float = 0.0
    BATCH3_RATIO: float = 0.0
    ADD_POSITION_THRESHOLD: float = 999.0  # 禁用加仓
    
    # 分批止盈参数
    PARTIAL_TP_R_MULTIPLE: float = 2.5
    PARTIAL_TP_RATIO: float = 0.3  # v5.2: 部分止盈只平30%，保留更多仓位
    FULL_TP_R_MULTIPLE: float = 5.0  # v5.2: 延长持仓 3R → 5R
    
    # 每日限制 v5.2: 放宽限制
    MAX_DAILY_TRADES: int = 5  # 提高每日交易上限
    MAX_DAILY_LOSS_PCT: float = 5.0  # 提高每日亏损上限
    MAX_CONSECUTIVE_LOSSES: int = 4  # 允许更多连续亏损
    COOLDOWN_AFTER_LOSS: int = 1  # 缩短冷却时间
    
    # 无时间止损
    MAX_HOLDING_BARS: int = 99999
    
    # 币种层级仓位限制：统一为90%
    TIER1_MAX_POSITION: float = 90.0
    TIER2_MAX_POSITION: float = 90.0
    TIER3_MAX_POSITION: float = 90.0
    
    TRADING_FEE: float = 0.0004
    MIN_DATA_BARS: int = 200
    STATE_FILE: str = 'strategy_state.json'
    
    def get_score_threshold(self) -> int:
        thresholds = {
            TradingMode.CONSERVATIVE: self.SCORE_THRESHOLD_CONSERVATIVE,
            TradingMode.STANDARD: self.SCORE_THRESHOLD_STANDARD,
            TradingMode.AGGRESSIVE: self.SCORE_THRESHOLD_AGGRESSIVE
        }
        return thresholds.get(self.TRADING_MODE, self.SCORE_THRESHOLD_STANDARD)
    
    def get_tier_max_position(self, tier: CoinTier) -> float:
        limits = {
            CoinTier.TIER_1: self.TIER1_MAX_POSITION,
            CoinTier.TIER_2: self.TIER2_MAX_POSITION,
            CoinTier.TIER_3: self.TIER3_MAX_POSITION
        }
        return limits.get(tier, 0.0)


# ============================================================================
# 工具函数
# ============================================================================
def timeframe_to_minutes(tf: str) -> int:
    unit, val = tf[-1], int(tf[:-1])
    return {'m': val, 'h': val*60, 'd': val*1440, 'w': val*10080}.get(unit, val)


def get_aligned_timestamp(ts: datetime, tf: str) -> datetime:
    mins = timeframe_to_minutes(tf)
    aligned = (ts.timestamp() // (mins * 60)) * (mins * 60)
    return datetime.fromtimestamp(aligned)


# ============================================================================
# 技术指标
# ============================================================================
class TechnicalIndicators:
    
    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        h, l, c = df['high'], df['low'], df['close']
        tr = pd.concat([h - l, abs(h - c.shift(1)), abs(l - c.shift(1))], axis=1).max(axis=1)
        return tr.ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def calculate_atr_percentile(atr: pd.Series, period: int = 100) -> pd.Series:
        def pct(x):
            return 50.0 if len(x) < 2 else (x.iloc[-1] > x.iloc[:-1]).sum() / (len(x) - 1) * 100
        return atr.rolling(period, min_periods=2).apply(pct, raw=False).fillna(50.0)
    
    @staticmethod
    def calculate_box(df: pd.DataFrame, lookback: int) -> Tuple[pd.Series, pd.Series]:
        """滚动箱体（原始方法）"""
        return (df['high'].rolling(lookback, min_periods=lookback).max(),
                df['low'].rolling(lookback, min_periods=lookback).min())
    
    @staticmethod
    def calculate_ema(s: pd.Series, period: int) -> pd.Series:
        return s.ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def calculate_price_position(close: pd.Series, high: pd.Series, low: pd.Series) -> pd.Series:
        rng = (high - low).replace(0, np.nan)
        return ((close - low) / rng).clip(0, 1).fillna(0.5)
    
    @staticmethod
    def detect_reversal_candles(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        o, h, l, c = df['open'], df['high'], df['low'], df['close']
        body = abs(c - o)
        upper = h - pd.concat([c, o], axis=1).max(axis=1)
        lower = pd.concat([c, o], axis=1).min(axis=1) - l
        rng = (h - l).replace(0, np.nan)
        
        bull = ((lower > body * 2) & (lower > rng * 0.6) & (c >= o)).fillna(False)
        bear = ((upper > body * 2) & (upper > rng * 0.6) & (c <= o)).fillna(False)
        return bull, bear
    
    @staticmethod
    def check_ema_cross(ema_fast: pd.Series, ema_slow: pd.Series) -> Tuple[pd.Series, pd.Series]:
        """检测EMA金叉和死叉"""
        golden_cross = (ema_fast > ema_slow) & (ema_fast.shift(1) <= ema_slow.shift(1))
        death_cross = (ema_fast < ema_slow) & (ema_fast.shift(1) >= ema_slow.shift(1))
        return golden_cross.fillna(False), death_cross.fillna(False)
    
    @staticmethod
    def check_price_touches_ema(df: pd.DataFrame, ema: pd.Series) -> pd.Series:
        """检测K线是否触碰EMA"""
        touches = (df['low'] <= ema) & (df['high'] >= ema)
        return touches.fillna(False)


# ============================================================================
# 【v5.1新增】固定箱体计算器
# ============================================================================
class FixedBoxCalculator:
    """
    固定箱体计算器
    
    逻辑：
    1. 初始箱体由lookback周期的高低点确定
    2. 只有当价格远离当前箱体（超过N倍ATR且连续M根K线）时，才重新计算箱体
    3. 避免箱体随价格波动频繁变化，提供更稳定的交易区间
    """
    
    def __init__(self, escape_atr_mult: float = 2.0, escape_bars: int = 3):
        """
        Args:
            escape_atr_mult: 价格远离箱体多少倍ATR后触发重新计算
            escape_bars: 需要连续多少根K线在箱体外才重新计算
        """
        self.escape_atr_mult = escape_atr_mult
        self.escape_bars = escape_bars
    
    def calculate(self, df: pd.DataFrame, atr: pd.Series, lookback: int = 70) -> Tuple[pd.Series, pd.Series]:
        """
        计算固定箱体
        
        Args:
            df: OHLCV数据
            atr: ATR序列
            lookback: 初始箱体计算周期
        
        Returns:
            (box_high, box_low) - 与滚动箱体相同格式的Series
        """
        box_h_list = []
        box_l_list = []
        
        current_box_h = None
        current_box_l = None
        escape_count = 0
        
        for i in range(len(df)):
            if i < lookback:
                # 数据不足，使用滚动计算
                h = df['high'].iloc[:i+1].max() if i > 0 else df['high'].iloc[0]
                l = df['low'].iloc[:i+1].min() if i > 0 else df['low'].iloc[0]
                box_h_list.append(h)
                box_l_list.append(l)
                continue
            
            price = df['close'].iloc[i]
            curr_atr = atr.iloc[i] if i < len(atr) and not pd.isna(atr.iloc[i]) else 0
            
            # 初始化箱体
            if current_box_h is None:
                current_box_h = df['high'].iloc[i-lookback+1:i+1].max()
                current_box_l = df['low'].iloc[i-lookback+1:i+1].min()
                escape_count = 0
            else:
                # 检查是否远离箱体
                escape_dist = curr_atr * self.escape_atr_mult
                
                price_above_box = price > current_box_h + escape_dist
                price_below_box = price < current_box_l - escape_dist
                
                if price_above_box or price_below_box:
                    escape_count += 1
                else:
                    escape_count = 0
                
                # 如果连续多根K线在箱体外，重新计算箱体
                if escape_count >= self.escape_bars:
                    current_box_h = df['high'].iloc[i-lookback+1:i+1].max()
                    current_box_l = df['low'].iloc[i-lookback+1:i+1].min()
                    escape_count = 0
                    logger.debug(f"箱体重新计算 @ {df.index[i]}: [{current_box_l:.2f}, {current_box_h:.2f}]")
            
            box_h_list.append(current_box_h)
            box_l_list.append(current_box_l)
        
        return pd.Series(box_h_list, index=df.index), pd.Series(box_l_list, index=df.index)


# ============================================================================
# 【v5.1新增】大趋势检测器
# ============================================================================
class BigTrendDetector:
    """
    大趋势检测器
    
    使用4H级别EMA排列判断大趋势：
    - EMA20 > EMA100 = 牛市（只做多）
    - EMA20 < EMA100 = 熊市（只做空）
    - 交叉区域 = 中性（可双向，但谨慎）
    """
    
    def __init__(self, config: StrategyConfig):
        self.cfg = config
    
    def detect(self, htf_data: pd.DataFrame, current_idx: int) -> BigTrend:
        """
        检测大趋势
        
        Args:
            htf_data: 4H级别数据
            current_idx: 当前索引
        
        Returns:
            BigTrend枚举
        """
        if current_idx < self.cfg.BIG_TREND_EMA_SLOW + 10:
            return BigTrend.NEUTRAL
        
        ema_fast = TechnicalIndicators.calculate_ema(htf_data['close'], self.cfg.BIG_TREND_EMA_FAST)
        ema_slow = TechnicalIndicators.calculate_ema(htf_data['close'], self.cfg.BIG_TREND_EMA_SLOW)
        
        ef = ema_fast.iloc[current_idx]
        es = ema_slow.iloc[current_idx]
        
        # 使用宽松判断：只看EMA排列
        if ef > es:
            return BigTrend.BULLISH
        elif ef < es:
            return BigTrend.BEARISH
        else:
            return BigTrend.NEUTRAL


# ============================================================================
# 市场状态检测器
# ============================================================================
class MarketRegimeDetector:
    """
    市场状态检测器
    
    使用4H级别EMA20/50/100判断：
    - 震荡箱体：K线在EMA上下穿越（触碰）
    - 趋势确认：连续3根K线完全在EMA20同一侧
    """
    
    def __init__(self, config: StrategyConfig):
        self.cfg = config
    
    def detect_regime(self, htf_data: pd.DataFrame, 
                      box_high: float = None, box_low: float = None) -> MarketRegime:
        """检测市场状态"""
        if htf_data.empty or len(htf_data) < self.cfg.EMA_SLOW_PERIOD + 10:
            return MarketRegime.UNCERTAIN
        
        ema20 = TechnicalIndicators.calculate_ema(htf_data['close'], self.cfg.EMA_FAST_PERIOD)
        
        n = self.cfg.TREND_CONFIRMATION_BARS
        recent_data = htf_data.tail(n)
        recent_ema20 = ema20.tail(n)
        
        all_above_ema20 = True
        all_below_ema20 = True
        
        for i in range(len(recent_data)):
            low = recent_data['low'].iloc[i]
            high = recent_data['high'].iloc[i]
            e20 = recent_ema20.iloc[i]
            
            if low <= e20:
                all_above_ema20 = False
            if high >= e20:
                all_below_ema20 = False
        
        current_close = htf_data['close'].iloc[-1]
        
        broke_up = box_high is not None and current_close > box_high
        broke_down = box_low is not None and current_close < box_low
        
        if all_above_ema20:
            if broke_up:
                return MarketRegime.TRENDING_UP
            else:
                return MarketRegime.RANGE_BOUND
        elif all_below_ema20:
            if broke_down:
                return MarketRegime.TRENDING_DOWN
            else:
                return MarketRegime.RANGE_BOUND
        else:
            return MarketRegime.RANGE_BOUND
    
    def get_regime_for_backtest(self, htf_data: pd.DataFrame, 
                                 current_idx: int,
                                 box_high: float = None,
                                 box_low: float = None) -> MarketRegime:
        """回测专用：根据当前索引获取市场状态"""
        if current_idx < self.cfg.EMA_SLOW_PERIOD + 10:
            return MarketRegime.UNCERTAIN
        
        available_data = htf_data.iloc[:current_idx + 1].copy()
        return self.detect_regime(available_data, box_high, box_low)


# ============================================================================
# 趋势交易信号生成器
# ============================================================================
class TrendSignalGenerator:
    """
    趋势行情的顺势交易
    
    - 上涨趋势：在1H级别EMA20和EMA100金叉时做多
    - 下跌趋势：在1H级别EMA20和EMA100死叉时做空
    """
    
    def __init__(self, config: StrategyConfig):
        self.cfg = config
    
    def generate_signal(self, mtf_data: pd.DataFrame, 
                        regime: MarketRegime,
                        current_idx: int) -> Tuple[SignalType, RejectReason]:
        """生成趋势交易信号"""
        if current_idx < self.cfg.EMA_SLOW_PERIOD + 5:
            return SignalType.NONE, RejectReason.INSUFFICIENT_DATA
        
        ema20 = TechnicalIndicators.calculate_ema(mtf_data['close'], self.cfg.EMA_FAST_PERIOD)
        ema100 = TechnicalIndicators.calculate_ema(mtf_data['close'], self.cfg.EMA_SLOW_PERIOD)
        
        golden_cross, death_cross = TechnicalIndicators.check_ema_cross(ema20, ema100)
        
        if current_idx >= len(golden_cross):
            return SignalType.NONE, RejectReason.INSUFFICIENT_DATA
        
        is_golden = golden_cross.iloc[current_idx]
        is_death = death_cross.iloc[current_idx]
        
        if regime == MarketRegime.TRENDING_UP and is_golden:
            return SignalType.LONG, RejectReason.NONE
        elif regime == MarketRegime.TRENDING_DOWN and is_death:
            return SignalType.SHORT, RejectReason.NONE
        else:
            return SignalType.NONE, RejectReason.NO_SIGNAL


# ============================================================================
# 箱体回归信号评分
# ============================================================================
@dataclass
class SignalScore:
    total: int = 0
    trend_dir: int = 0
    trend_str: int = 0
    price_pos: int = 0
    mtf_conf: int = 0
    reversal: int = 0
    volatility: int = 0


class SignalScorer:
    def __init__(self, config: StrategyConfig):
        self.cfg = config
    
    def score(self, sig: SignalType, price_pos: float, 
              has_rev: bool, atr_pct: float,
              mtf_ema_aligned: bool) -> SignalScore:
        """评分逻辑（针对箱体回归）"""
        s = SignalScore()
        
        # 价格位置评分
        if sig == SignalType.LONG:
            if price_pos <= 0.10:
                s.price_pos = self.cfg.SCORE_WEIGHT_PRICE_POSITION
            elif price_pos <= 0.15:
                s.price_pos = int(self.cfg.SCORE_WEIGHT_PRICE_POSITION * 0.9)
            elif price_pos <= 0.20:
                s.price_pos = int(self.cfg.SCORE_WEIGHT_PRICE_POSITION * 0.8)
            elif price_pos <= 0.25:
                s.price_pos = int(self.cfg.SCORE_WEIGHT_PRICE_POSITION * 0.7)
        else:
            if price_pos >= 0.90:
                s.price_pos = self.cfg.SCORE_WEIGHT_PRICE_POSITION
            elif price_pos >= 0.85:
                s.price_pos = int(self.cfg.SCORE_WEIGHT_PRICE_POSITION * 0.9)
            elif price_pos >= 0.80:
                s.price_pos = int(self.cfg.SCORE_WEIGHT_PRICE_POSITION * 0.8)
            elif price_pos >= 0.75:
                s.price_pos = int(self.cfg.SCORE_WEIGHT_PRICE_POSITION * 0.7)
        
        # MTF确认
        if mtf_ema_aligned:
            s.mtf_conf = self.cfg.SCORE_WEIGHT_MTF_CONFIRMATION
        
        # 反转K线
        if has_rev:
            s.reversal = self.cfg.SCORE_WEIGHT_REVERSAL_CANDLE
        
        # 波动率评分
        if self.cfg.ATR_PERCENTILE_MIN <= atr_pct <= self.cfg.ATR_PERCENTILE_MAX:
            if 30 <= atr_pct <= 70:
                s.volatility = self.cfg.SCORE_WEIGHT_VOLATILITY
            else:
                s.volatility = int(self.cfg.SCORE_WEIGHT_VOLATILITY * 0.7)
        
        # 基础分数
        s.trend_dir = int(self.cfg.SCORE_WEIGHT_TREND_DIRECTION * 0.5)
        s.trend_str = int(self.cfg.SCORE_WEIGHT_TREND_STRENGTH * 0.5)
        
        s.total = s.trend_dir + s.trend_str + s.price_pos + s.mtf_conf + s.reversal + s.volatility
        return s


# ============================================================================
# 【v5.3新增】网格策略生成器
# ============================================================================
class GridStrategyGenerator:
    """
    网格策略生成器（用于震荡区间）
    
    逻辑：
    1. 只在震荡区间（RANGE_BOUND）使用
    2. 根据大趋势方向：牛市只做多网格，熊市只做空网格
    3. 网格参数动态计算：基于箱体大小、ATR、币种特点
    4. 要求：网格间隔>=1%，箱体区间>=5%
    5. 止损距离 = 网格间隔（1%），避免被市场噪音触发
    6. 只在箱体内交易，止盈也在箱体内
    """
    
    def __init__(self, config: StrategyConfig):
        self.cfg = config
        self.grid_layers: Dict[str, List[Dict]] = {}  # 每个币种的网格层
    
    def calculate_grid(self, box_high: float, box_low: float, 
                      current_price: float, atr: float,
                      big_trend: BigTrend, grid_balance: float) -> Optional[List[Dict]]:
        """
        计算网格参数
        
        Args:
            box_high: 箱体上沿
            box_low: 箱体下沿
            current_price: 当前价格
            atr: ATR值
            big_trend: 大趋势方向
            balance: 账户余额
        
        Returns:
            网格层列表，每个层包含：price, side, size, tp_price
        """
        if box_high is None or box_low is None:
            return None
        
        # 检查箱体区间是否>=最小要求
        if box_low <= 0:
            return None
        box_range_pct = (box_high - box_low) / box_low * 100
        if box_range_pct < self.cfg.GRID_MIN_BOX_RANGE_PCT:
            return None  # 箱体太小，不适合网格
        
        # 根据大趋势决定网格方向和交易区间
        # 定义箱体内相对位置 [0,1]
        box_range = box_high - box_low
        if box_range <= 0:
            return None
        # 默认整个箱体
        zone_low = box_low
        zone_high = box_high

        if big_trend == BigTrend.BULLISH:
            # 牛市：只做多网格，区间为箱体底部0~0.8
            grid_side = SignalType.LONG
            zone_low = box_low
            zone_high = box_low + box_range * 0.8
        elif big_trend == BigTrend.BEARISH:
            # 熊市：只做空网格，区间为箱体底部0.2~顶部1
            grid_side = SignalType.SHORT
            zone_low = box_low + box_range * 0.2
            zone_high = box_high
        else:
            # 中性：不交易
            return None

        # 检查当前价格是否在对应交易区间内
        if current_price < zone_low or current_price > zone_high:
            return None
        
        # 动态计算网格间隔（改为百分比驱动，避免币价差异导致 size 跳变）
        available_range = zone_high - zone_low
        if current_price <= 0:
            return None
        box_range_pct = (available_range / current_price) * 100

        # 方法1：按最大层数均分得到的间隔百分比
        interval_by_max_layers_pct = box_range_pct / self.cfg.GRID_MAX_LAYERS
        # 方法2：配置的最小网格间隔百分比
        min_interval_from_box_pct = self.cfg.GRID_MIN_INTERVAL_PCT
        # 方法3：ATR 折算的百分比（0.5*ATR 相对当前价）
        atr_interval_pct = (atr * 0.5 / current_price) * 100 if current_price > 0 else 0

        # 取“不要太小”的百分比
        min_interval_pct = max(min_interval_from_box_pct, atr_interval_pct)

        # 最大合理间隔百分比：箱体高度的一半百分比（保证至少能分成两层）
        max_reasonable_interval_pct = box_range_pct / 2

        # 如果最小要求已经大于一半箱体，视为箱体太小
        if min_interval_pct > max_reasonable_interval_pct:
            return None

        # 最终网格间隔百分比：在“按层数均分”和“最小要求”里取大的，但不超过一半箱体
        grid_interval_pct = min(max(interval_by_max_layers_pct, min_interval_pct), max_reasonable_interval_pct)
        grid_interval = current_price * grid_interval_pct / 100  # 折算为价格间隔

        # 计算网格层数（在箱体内，至少2层）
        max_layers = min(int(available_range / grid_interval), self.cfg.GRID_MAX_LAYERS)
        
        if max_layers < 2:
            return None  # 层数太少，不适合网格
        
        # 生成网格层
        grid_layers = []
        total_risk = 0
        
        if grid_side == SignalType.LONG:
            # 做多网格：从交易区间下沿向上
            base_price = zone_low
            for i in range(max_layers):
                layer_price = base_price + i * grid_interval
                
                # 确保在交易区间内
                if layer_price > zone_high:
                    break
                if layer_price < zone_low:
                    continue
                
                # 计算止盈价（上一层或箱体上沿）
                if i < max_layers - 1:
                    tp_price = min(layer_price + grid_interval, zone_high)
                else:
                    tp_price = zone_high  # 最后一层止盈在交易区间上沿
                
                # 确保止盈在交易区间内
                tp_price = min(tp_price, zone_high)
                
                # 计算仓位（每层风险 = GRID_RISK_PER_LAYER%，按方向加权，止损距离按百分比）
                layer_risk = grid_balance * self.cfg.GRID_RISK_PER_LAYER / 100
                if grid_side == SignalType.SHORT:
                    layer_risk *= self.cfg.SHORT_RISK_MULTIPLIER
                else:
                    layer_risk *= self.cfg.LONG_RISK_MULTIPLIER
                sl_pct = grid_interval_pct * self.cfg.GRID_SL_MULTIPLIER
                sl_distance = layer_price * sl_pct / 100
                if sl_distance <= 0:
                    continue
                layer_size = layer_risk / sl_distance
                
                grid_layers.append({
                    'price': layer_price,
                    'side': SignalType.LONG,
                    'size': layer_size,
                    'tp_price': tp_price,
                    'sl_price': layer_price - sl_distance,  # 止损在下一层下方
                    'layer': i + 1
                })
                total_risk += layer_risk
        
        else:  # SHORT
            # 做空网格：从交易区间上沿向下
            base_price = zone_high
            for i in range(max_layers):
                layer_price = base_price - i * grid_interval
                
                # 确保在交易区间内
                if layer_price < zone_low:
                    break
                if layer_price > zone_high:
                    continue
                
                # 计算止盈价（下一层或箱体下沿）
                if i < max_layers - 1:
                    tp_price = max(layer_price - grid_interval, zone_low)
                else:
                    tp_price = zone_low  # 最后一层止盈在交易区间下沿
                
                # 确保止盈在交易区间内
                tp_price = max(tp_price, zone_low)
                
                # 计算仓位（每层风险 = GRID_RISK_PER_LAYER%，按方向加权，止损距离按百分比）
                layer_risk = grid_balance * self.cfg.GRID_RISK_PER_LAYER / 100
                if grid_side == SignalType.SHORT:
                    layer_risk *= self.cfg.SHORT_RISK_MULTIPLIER
                else:
                    layer_risk *= self.cfg.LONG_RISK_MULTIPLIER
                sl_pct = grid_interval_pct * self.cfg.GRID_SL_MULTIPLIER
                sl_distance = layer_price * sl_pct / 100
                if sl_distance <= 0:
                    continue
                layer_size = layer_risk / sl_distance
                
                grid_layers.append({
                    'price': layer_price,
                    'side': SignalType.SHORT,
                    'size': layer_size,
                    'tp_price': tp_price,
                    'sl_price': layer_price + sl_distance,  # 止损在上一层上方
                    'layer': i + 1
                })
                total_risk += layer_risk
        
        # 检查总风险是否超过限制（使用网格专用仓位限制和网格资金池）
        # 【修复】使用grid_balance计算，但限制在初始资金内（防止复利无限增长）
        max_total_risk = grid_balance * self.cfg.GRID_MAX_POSITION_PCT / 100
        if total_risk > max_total_risk:
            # 按比例缩减每层仓位
            scale = max_total_risk / total_risk
            for layer in grid_layers:
                layer['size'] *= scale
        
        return grid_layers if grid_layers else None
    
    def check_grid_signal(self, current_price: float, box_high: float, box_low: float,
                         grid_layers: List[Dict], existing_positions: Dict) -> Optional[Dict]:
        """
        检查是否有网格交易信号
        
        Args:
            current_price: 当前价格
            box_high: 箱体上沿
            box_low: 箱体下沿
            grid_layers: 网格层列表
            existing_positions: 已有持仓（key=layer, value=position）
        
        Returns:
            交易信号或None
        """
        if not grid_layers:
            return None
        
        # 检查价格是否在箱体内
        if current_price < box_low or current_price > box_high:
            return None  # 价格不在箱体内，不交易
        
        # 检查是否有网格层被触发
        for layer in grid_layers:
            layer_price = layer['price']
            layer_num = layer['layer']
            
            # 如果该层已有持仓，跳过
            if layer_num in existing_positions:
                continue
            
            # 检查是否触发（价格接近网格层价格，容差1%）
            price_tolerance = layer_price * 0.01
            if abs(current_price - layer_price) <= price_tolerance:
                return {
                    'type': 'grid_entry',
                    'side': layer['side'],
                    'price': layer_price,
                    'size': layer['size'],
                    'tp_price': layer['tp_price'],
                    'sl_price': layer['sl_price'],
                    'layer': layer_num
                }
        
        # 检查是否有持仓需要止盈
        for layer_num, pos in existing_positions.items():
            # 找到对应的网格层
            layer = next((l for l in grid_layers if l['layer'] == layer_num), None)
            if not layer:
                continue
            
            # 检查是否达到止盈价
            if layer['side'] == SignalType.LONG:
                if current_price >= layer['tp_price']:
                    return {
                        'type': 'grid_exit',
                        'side': SignalType.LONG,
                        'price': layer['tp_price'],
                        'layer': layer_num,
                        'reason': '止盈'
                    }
            else:  # SHORT
                if current_price <= layer['tp_price']:
                    return {
                        'type': 'grid_exit',
                        'side': SignalType.SHORT,
                        'price': layer['tp_price'],
                        'layer': layer_num,
                        'reason': '止盈'
                    }
        
        return None


# ============================================================================
# 【v5.1修改】箱体回归信号生成器（顺势过滤）
# ============================================================================
class BoxSignalGenerator:
    """
    箱体回归信号生成
    
    【v5.1改进】增加顺势过滤：
    - 牛市（EMA20 > EMA100）：只生成做多信号
    - 熊市（EMA20 < EMA100）：只生成做空信号
    """
    
    def __init__(self, config: StrategyConfig):
        self.cfg = config
        self.scorer = SignalScorer(config)
    
    def generate_signal(self, row: pd.Series, price_pos: float, 
                        box_h: float, box_l: float,
                        atr: float, atr_pct: float,
                        bull_rev: bool, bear_rev: bool,
                        mtf_ema_aligned: bool,
                        big_trend: BigTrend = BigTrend.NEUTRAL) -> Tuple[SignalType, Optional[SignalScore], RejectReason]:
        """
        生成箱体回归信号
        
        Args:
            row: 当前K线数据
            price_pos: 价格在箱体中的位置
            box_h: 箱体高点
            box_l: 箱体低点
            atr: ATR值
            atr_pct: ATR百分位
            bull_rev: 是否有看涨反转K线
            bear_rev: 是否有看跌反转K线
            mtf_ema_aligned: 1H EMA是否对齐
            big_trend: 大趋势方向
        
        Returns:
            (信号类型, 评分, 拒绝原因)
        """
        if pd.isna(price_pos) or pd.isna(atr) or pd.isna(box_h) or pd.isna(box_l):
            return SignalType.NONE, None, RejectReason.INSUFFICIENT_DATA
        
        price = row['close']
        box_pct = (box_h - box_l) / price * 100
        
        # 箱体范围检查
        if not (self.cfg.BOX_MIN_RANGE_PCT <= box_pct <= self.cfg.BOX_MAX_RANGE_PCT):
            return SignalType.NONE, None, RejectReason.VOLATILITY_FILTER
        
        # 确定信号类型
        sig = SignalType.NONE
        
        # 入场区域：0-0.20做多，0.80-1做空
        if self.cfg.DISCOUNT_ZONE_MIN <= price_pos <= self.cfg.DISCOUNT_ZONE_MAX:
            sig = SignalType.LONG
        elif self.cfg.PREMIUM_ZONE_MIN <= price_pos <= self.cfg.PREMIUM_ZONE_MAX:
            sig = SignalType.SHORT
        
        if sig == SignalType.NONE:
            return SignalType.NONE, None, RejectReason.PRICE_NOT_IN_ZONE
        
        # 【v5.1新增】顺势过滤
        if self.cfg.TREND_FOLLOWING_MODE:
            if big_trend == BigTrend.BULLISH and sig == SignalType.SHORT:
                # 牛市禁止做空
                return SignalType.NONE, None, RejectReason.AGAINST_BIG_TREND
            elif big_trend == BigTrend.BEARISH and sig == SignalType.LONG:
                # 熊市禁止做多
                return SignalType.NONE, None, RejectReason.AGAINST_BIG_TREND
        
        # 检查反转K线
        has_rev = (sig == SignalType.LONG and bull_rev) or (sig == SignalType.SHORT and bear_rev)
        
        # 计算评分
        score = self.scorer.score(sig, price_pos, has_rev, atr_pct, mtf_ema_aligned)
        
        # 评分阈值检查
        if score.total < self.cfg.get_score_threshold():
            return SignalType.NONE, score, RejectReason.SCORE_TOO_LOW
        
        return sig, score, RejectReason.NONE


# ============================================================================
# 风险管理
# ============================================================================
@dataclass
class RiskMetrics:
    daily_trades: int = 0
    daily_pnl: float = 0.0
    consec_losses: int = 0
    last_trade: Optional[datetime] = None
    trade_date: Optional[str] = None


class RiskManager:
    def __init__(self, config: StrategyConfig):
        self.cfg = config
        self.metrics = RiskMetrics()
    
    def calc_size(self, balance: float, entry: float, sl: float, tier: CoinTier, side: SignalType = None) -> float:
        risk = balance * self.cfg.RISK_PER_TRADE / 100
        if side == SignalType.SHORT:
            risk *= self.cfg.SHORT_RISK_MULTIPLIER
        elif side == SignalType.LONG:
            risk *= self.cfg.LONG_RISK_MULTIPLIER
        sl_pct = abs(entry - sl) / entry
        if sl_pct == 0:
            return 0
        size = risk / sl_pct
        max_size = balance * self.cfg.get_tier_max_position(tier) / 100
        return min(size, max_size)
    
    def calc_sl(self, entry: float, atr: float, sig: SignalType) -> float:
        """使用2倍ATR止损"""
        dist = atr * self.cfg.STOP_LOSS_ATR_MULTIPLIER
        return entry - dist if sig == SignalType.LONG else entry + dist
    
    def calc_tp(self, entry: float, atr: float, sig: SignalType, r: float = None) -> float:
        """计算止盈价格，r默认使用配置的FULL_TP_R_MULTIPLE"""
        if r is None:
            r = self.cfg.FULL_TP_R_MULTIPLE
        dist = atr * self.cfg.STOP_LOSS_ATR_MULTIPLIER * r
        return entry + dist if sig == SignalType.LONG else entry - dist
    
    def check_limits(self, ts: datetime) -> Tuple[bool, str]:
        date = ts.strftime('%Y-%m-%d')
        if self.metrics.trade_date != date:
            self.metrics.trade_date = date
            self.metrics.daily_trades = 0
            self.metrics.daily_pnl = 0.0
        
        if self.metrics.daily_trades >= self.cfg.MAX_DAILY_TRADES:
            return False, "每日交易上限"
        if self.metrics.daily_pnl <= -self.cfg.MAX_DAILY_LOSS_PCT:
            return False, "每日亏损上限"
        if self.metrics.consec_losses >= self.cfg.MAX_CONSECUTIVE_LOSSES:
            if self.metrics.last_trade:
                end = self.metrics.last_trade + timedelta(hours=self.cfg.COOLDOWN_AFTER_LOSS)
                if ts < end:
                    return False, "冷却中"
                self.metrics.consec_losses = 0
        return True, "OK"
    
    def update(self, pnl_pct: float, ts: datetime):
        self.metrics.daily_trades += 1
        self.metrics.daily_pnl += pnl_pct
        self.metrics.last_trade = ts
        self.metrics.consec_losses = self.metrics.consec_losses + 1 if pnl_pct < 0 else 0


# ============================================================================
# 仓位管理
# ============================================================================
@dataclass
class Position:
    symbol: str = ""
    side: SignalType = SignalType.NONE
    entry: float = 0.0
    size: float = 0.0
    qty: float = 0.0
    full_size: float = 0.0
    sl: float = 0.0
    sl_initial: float = 0.0
    tp: float = 0.0
    atr: float = 0.0
    phase: PositionPhase = PositionPhase.NONE
    entry_time: Optional[datetime] = None
    entry_bar: int = 0
    partial_done: bool = False
    trailing_on: bool = False
    b2_done: bool = False
    b3_done: bool = False
    high: float = 0.0
    low: float = float('inf')
    realized: float = 0.0
    cost: float = 0.0
    trade_type: str = ""  # "box" or "trend"
    big_trend: str = ""   # 记录入场时的大趋势


class PositionManager:
    def __init__(self, config: StrategyConfig):
        self.cfg = config
        self.positions: Dict[str, Position] = {}
    
    def has(self, sym: str) -> bool:
        return sym in self.positions
    
    def get(self, sym: str) -> Optional[Position]:
        return self.positions.get(sym)
    
    def open(self, sym: str, side: SignalType, entry: float, size: float,
             sl: float, tp: float, atr: float, ts: datetime, bar: int,
             trade_type: str = "box", big_trend: str = "neutral") -> Tuple[Position, float]:
        fee = size * self.cfg.TRADING_FEE
        cost = size + fee
        qty = size / entry
        
        pos = Position(
            symbol=sym, side=side, 
            entry=entry, size=size, qty=qty,
            full_size=size / self.cfg.BATCH1_RATIO,
            sl=sl, sl_initial=sl, tp=tp, atr=atr, 
            phase=PositionPhase.BATCH1,
            entry_time=ts, entry_bar=bar, 
            high=entry, low=entry, cost=cost,
            trade_type=trade_type,
            big_trend=big_trend
        )
        self.positions[sym] = pos
        
        logger.info(
            f"开仓 {sym} {side.value} ({trade_type}) | "
            f"大趋势={big_trend} | 价格={entry:.2f} 金额=${size:.2f} | "
            f"SL={sl:.2f} TP={tp:.2f}"
        )
        return pos, cost
    
    def add_b2(self, sym: str, price: float, balance: float) -> Tuple[bool, float]:
        pos = self.positions.get(sym)
        if not pos or pos.b2_done:
            return False, 0
        
        if pos.side == SignalType.LONG:
            chg = (price - pos.entry) / pos.entry * 100
        else:
            chg = (pos.entry - price) / pos.entry * 100
        
        if chg < self.cfg.ADD_POSITION_THRESHOLD:
            return False, 0
        
        add_size = min(pos.full_size * self.cfg.BATCH2_RATIO, balance * 0.95)
        if add_size <= 0:
            return False, 0
        
        fee = add_size * self.cfg.TRADING_FEE
        add_qty = add_size / price
        
        old_notional = pos.entry * pos.qty
        new_notional = price * add_qty
        new_qty = pos.qty + add_qty
        new_entry = (old_notional + new_notional) / new_qty
        
        pos.entry = new_entry
        pos.qty = new_qty
        pos.size += add_size
        pos.cost += add_size + fee
        pos.phase = PositionPhase.BATCH2
        pos.b2_done = True
        
        new_sl = self._calc_sl_from_entry(pos.entry, pos.atr, pos.side)
        pos.sl = max(pos.sl, new_sl) if pos.side == SignalType.LONG else min(pos.sl, new_sl)
        
        logger.info(f"加仓2 {sym} | 加仓价={price:.2f} | 新均价={new_entry:.2f}")
        return True, add_size + fee
    
    def add_b3(self, sym: str, price: float, balance: float) -> Tuple[bool, float]:
        pos = self.positions.get(sym)
        if not pos or pos.b3_done or not pos.b2_done:
            return False, 0
        
        if pos.side == SignalType.LONG:
            chg = (price - pos.entry) / pos.entry * 100
        else:
            chg = (pos.entry - price) / pos.entry * 100
        
        if chg < self.cfg.ADD_POSITION_THRESHOLD:
            return False, 0
        
        add_size = min(pos.full_size * self.cfg.BATCH3_RATIO, balance * 0.95)
        if add_size <= 0:
            return False, 0
        
        fee = add_size * self.cfg.TRADING_FEE
        add_qty = add_size / price
        
        old_notional = pos.entry * pos.qty
        new_notional = price * add_qty
        new_qty = pos.qty + add_qty
        new_entry = (old_notional + new_notional) / new_qty
        
        pos.entry = new_entry
        pos.qty = new_qty
        pos.size += add_size
        pos.cost += add_size + fee
        pos.phase = PositionPhase.BATCH3
        pos.b3_done = True
        
        new_sl = self._calc_sl_from_entry(pos.entry, pos.atr, pos.side)
        pos.sl = max(pos.sl, new_sl) if pos.side == SignalType.LONG else min(pos.sl, new_sl)
        
        logger.info(f"加仓3 {sym} | 加仓价={price:.2f} | 新均价={new_entry:.2f} (满仓)")
        return True, add_size + fee
    
    def _calc_sl_from_entry(self, entry: float, atr: float, side: SignalType) -> float:
        dist = atr * self.cfg.STOP_LOSS_ATR_MULTIPLIER
        return entry - dist if side == SignalType.LONG else entry + dist
    
    def calc_r(self, pos: Position, price: float) -> float:
        risk_price = pos.atr * self.cfg.STOP_LOSS_ATR_MULTIPLIER
        if risk_price == 0:
            return 0
        if pos.side == SignalType.LONG:
            pnl = price - pos.entry
        else:
            pnl = pos.entry - price
        return pnl / risk_price
    
    def check_partial_tp(self, sym: str, price: float) -> Tuple[bool, float]:
        pos = self.positions.get(sym)
        if not pos or pos.partial_done:
            return False, 0
        
        r = self.calc_r(pos, price)
        if r < self.cfg.PARTIAL_TP_R_MULTIPLE:
            return False, 0
        
        close_qty = pos.qty * self.cfg.PARTIAL_TP_RATIO
        close_size = pos.size * self.cfg.PARTIAL_TP_RATIO
        
        if pos.side == SignalType.LONG:
            pnl = (price - pos.entry) * close_qty
        else:
            pnl = (pos.entry - price) * close_qty
        
        fee = close_size * self.cfg.TRADING_FEE
        net = pnl - fee
        cash = close_size + net
        
        pos.qty -= close_qty
        pos.size -= close_size
        pos.partial_done = True
        pos.realized += net
        pos.sl = pos.entry
        
        logger.info(f"部分止盈 {sym} @ {price:.2f} | 盈亏=${net:.2f} R={r:.2f}")
        return True, cash
    
    def check_full_tp(self, sym: str, price: float) -> bool:
        pos = self.positions.get(sym)
        if not pos:
            return False
        return self.calc_r(pos, price) >= self.cfg.FULL_TP_R_MULTIPLE
    
    def check_sl(self, sym: str, price: float) -> bool:
        pos = self.positions.get(sym)
        if not pos:
            return False
        return price <= pos.sl if pos.side == SignalType.LONG else price >= pos.sl
    
    def update_trailing(self, sym: str, price: float):
        pos = self.positions.get(sym)
        if not pos:
            return
        
        r = self.calc_r(pos, price)
        if not pos.trailing_on and r >= self.cfg.TRAILING_STOP_ACTIVATION:
            pos.trailing_on = True
        
        if pos.trailing_on:
            dist = pos.atr * self.cfg.TRAILING_STOP_DISTANCE
            if pos.side == SignalType.LONG:
                pos.high = max(pos.high, price)
                new_sl = pos.high - dist
                if new_sl > pos.sl:
                    pos.sl = new_sl
            else:
                pos.low = min(pos.low, price)
                new_sl = pos.low + dist
                if new_sl < pos.sl:
                    pos.sl = new_sl
    
    def close(self, sym: str, price: float, reason: str) -> Optional[Dict]:
        pos = self.positions.get(sym)
        if not pos:
            return None
        
        if pos.side == SignalType.LONG:
            pnl = (price - pos.entry) * pos.qty
        else:
            pnl = (pos.entry - price) * pos.qty
        
        fee = pos.size * self.cfg.TRADING_FEE
        net = pnl - fee
        cash = pos.size + net
        
        total_pnl = pos.realized + net
        total_pct = total_pnl / pos.cost * 100 if pos.cost > 0 else 0
        
        r = self.calc_r(pos, price)
        
        result = {
            'symbol': sym,
            'side': pos.side.value,
            'entry': pos.entry,
            'exit': price,
            'qty': pos.qty,
            'cash_return': cash,
            'remaining_pnl': net,
            'total_pnl': total_pnl,
            'total_pct': total_pct,
            'r': r,
            'reason': reason,
            'phase': pos.phase.value,
            'entry_time': pos.entry_time,
            'cost': pos.cost,
            'trade_type': pos.trade_type,
            'big_trend': pos.big_trend
        }
        
        del self.positions[sym]
        
        logger.info(
            f"平仓 {sym} @ {price:.2f} | "
            f"盈亏=${total_pnl:.2f} ({total_pct:.1f}%) R={r:.2f} | {reason}"
        )
        return result


# ============================================================================
# 回测引擎
# ============================================================================
class BacktestEngine:
    def __init__(self, config: StrategyConfig):
        self.cfg = config
        self.pm = PositionManager(config)
        self.rm = RiskManager(config)
        self.box_sg = BoxSignalGenerator(config)
        self.trend_sg = TrendSignalGenerator(config)
        self.regime_detector = MarketRegimeDetector(config)
        self.big_trend_detector = BigTrendDetector(config)
        self.grid_sg = GridStrategyGenerator(config)  # 【v5.3】网格策略
        self.fixed_box_calc = FixedBoxCalculator(
            escape_atr_mult=config.BOX_ESCAPE_ATR_MULT,
            escape_bars=config.BOX_ESCAPE_BARS
        )
        
        self.trades: List[Dict] = []
        self.equity: List[Dict] = []
        self._cache: Dict[str, Any] = {}
        self.grid_positions: Dict[int, Dict] = {}  # 【v5.3】网格持仓（key=layer, value=position）
        self.grid_pm = PositionManager(config)  # 【v5.3修复】网格独立持仓管理
        self.trend_pm = PositionManager(config)  # 【v5.3修复】趋势独立持仓管理
    
    def _precalc(self, ltf: pd.DataFrame, mtf: pd.DataFrame, htf: pd.DataFrame):
        """预计算指标"""
        logger.info("预计算指标...")
        
        # LTF指标
        self._cache['atr'] = TechnicalIndicators.calculate_atr(ltf, self.cfg.ATR_PERIOD).reset_index(drop=True)
        self._cache['atr_pct'] = TechnicalIndicators.calculate_atr_percentile(
            self._cache['atr'], self.cfg.ATR_PERCENTILE_PERIOD
        ).reset_index(drop=True)
        
        # 【v5.1】根据配置选择箱体计算方式
        if self.cfg.USE_FIXED_BOX:
            bh, bl = self.fixed_box_calc.calculate(ltf, self._cache['atr'], self.cfg.BOX_LOOKBACK_PERIODS)
            logger.info("使用固定箱体计算")
        else:
            bh, bl = TechnicalIndicators.calculate_box(ltf, self.cfg.BOX_LOOKBACK_PERIODS)
            logger.info("使用滚动箱体计算")
        
        self._cache['box_h'] = bh.reset_index(drop=True)
        self._cache['box_l'] = bl.reset_index(drop=True)
        self._cache['price_pos'] = TechnicalIndicators.calculate_price_position(
            ltf['close'], bh, bl
        ).reset_index(drop=True)
        
        bull, bear = TechnicalIndicators.detect_reversal_candles(ltf)
        self._cache['bull'] = bull.reset_index(drop=True)
        self._cache['bear'] = bear.reset_index(drop=True)
        
        # MTF指标（1H）
        mtf_ema20 = TechnicalIndicators.calculate_ema(mtf['close'], self.cfg.EMA_FAST_PERIOD)
        mtf_ema100 = TechnicalIndicators.calculate_ema(mtf['close'], self.cfg.EMA_SLOW_PERIOD)
        
        golden, death = TechnicalIndicators.check_ema_cross(mtf_ema20, mtf_ema100)
        self._cache['mtf_golden'] = golden.reset_index(drop=True)
        self._cache['mtf_death'] = death.reset_index(drop=True)
        self._cache['mtf_ema20'] = mtf_ema20.reset_index(drop=True)
        self._cache['mtf_ema100'] = mtf_ema100.reset_index(drop=True)
        self._cache['mtf_ts'] = mtf['timestamp'].reset_index(drop=True)
        
        # HTF指标（4H）
        htf_ema20 = TechnicalIndicators.calculate_ema(htf['close'], self.cfg.EMA_FAST_PERIOD)
        htf_ema50 = TechnicalIndicators.calculate_ema(htf['close'], self.cfg.EMA_MID_PERIOD)
        htf_ema100 = TechnicalIndicators.calculate_ema(htf['close'], self.cfg.EMA_SLOW_PERIOD)
        
        self._cache['htf_ema20'] = htf_ema20.reset_index(drop=True)
        self._cache['htf_ema50'] = htf_ema50.reset_index(drop=True)
        self._cache['htf_ema100'] = htf_ema100.reset_index(drop=True)
        self._cache['htf_ts'] = htf['timestamp'].reset_index(drop=True)
        self._cache['htf_data'] = htf.reset_index(drop=True)
        
        logger.info("指标预计算完成")
    
    def _idx(self, ts: datetime, ts_series: pd.Series) -> Optional[int]:
        mask = ts_series <= ts
        return np.where(mask)[0][-1] if mask.any() else None
    
    def _get_market_regime(self, htf_idx: int, ltf_idx: int) -> MarketRegime:
        """获取当前市场状态"""
        if htf_idx < self.cfg.EMA_SLOW_PERIOD + 10:
            return MarketRegime.UNCERTAIN
        
        htf_data = self._cache['htf_data']
        
        box_high = self._cache['box_h'].iloc[ltf_idx] if ltf_idx < len(self._cache['box_h']) else None
        box_low = self._cache['box_l'].iloc[ltf_idx] if ltf_idx < len(self._cache['box_l']) else None
        
        return self.regime_detector.get_regime_for_backtest(htf_data, htf_idx, box_high, box_low)
    
    def _get_big_trend(self, htf_idx: int) -> BigTrend:
        """【v5.1】获取大趋势方向"""
        if htf_idx < self.cfg.BIG_TREND_EMA_SLOW + 10:
            return BigTrend.NEUTRAL
        
        htf_data = self._cache['htf_data']
        return self.big_trend_detector.detect(htf_data, htf_idx)
    
    def _recalc_grid_size(self, grid_signal: Dict, grid_balance: float,
                          box_high: float, box_low: float, atr: float,
                          big_trend: BigTrend) -> float:
        """【v5.3修复】重新计算网格仓位（使用网格资金池）"""
        # 重新计算网格层，获取正确的仓位
        grid_layers = self.grid_sg.calculate_grid(
            box_high, box_low, grid_signal['price'], atr, big_trend, grid_balance
        )
        if grid_layers:
            for layer in grid_layers:
                if layer['layer'] == grid_signal.get('layer'):
                    return layer['size']
        return 0
    
    def run(self, ltf: pd.DataFrame, mtf: pd.DataFrame, htf: pd.DataFrame,
            init_bal: float = 10000, use_compound: bool = False) -> Dict:
        
        ltf = ltf.reset_index(drop=True)
        mtf = mtf.reset_index(drop=True)
        htf = htf.reset_index(drop=True)
        
        self._precalc(ltf, mtf, htf)
        
        # 【调整】分离资金池：总本金=init_bal，趋势/网格各一半
        trend_balance = init_bal * 0.5  # 趋势交易资金池
        grid_balance = init_bal * 0.5   # 网格交易资金池
        # 【复利模式】网格资金允许随收益无限增长（按风险百分比控制），不再限制上限
        grid_balance_max = float('inf')
        balance = trend_balance + grid_balance
        
        pending = None
        pending_type = None
        pending_big_trend = None
        pending_grid_info = None  # 【v5.3】网格信号信息
        
        min_bar = max(self.cfg.BOX_LOOKBACK_PERIODS, self.cfg.ATR_PERCENTILE_PERIOD, 
                      self.cfg.EMA_SLOW_PERIOD) + 10
        
        for i in range(min_bar, len(ltf) - 1):
            row = ltf.iloc[i]
            nxt = ltf.iloc[i + 1]
            ts = row['timestamp']
            price = row['close']
            sym = self.cfg.SYMBOL
            
            if i % 500 == 0:
                pct = (i - min_bar) / (len(ltf) - min_bar - 1) * 100
                logger.info(f"回测进度: {pct:.1f}%")
            
            # 权益计算（包含趋势和网格持仓）
            eq = balance
            # 趋势持仓
            for s, p in self.trend_pm.positions.items():
                if p.side == SignalType.LONG:
                    pos_value = p.qty * price
                else:
                    pos_value = p.size + (p.entry - price) * p.qty
                eq += pos_value
            # 网格持仓（使用grid_symbol从PositionManager获取）
            for layer_num, layer_info in self.grid_positions.items():
                grid_symbol = layer_info.get('grid_symbol', f"{sym}-layer{layer_num}")
                pos = self.grid_pm.get(grid_symbol)  # 【修复】使用grid_symbol获取持仓
                if pos:
                    if pos.side == SignalType.LONG:
                        pos_value = pos.qty * price
                    else:
                        pos_value = pos.size + (pos.entry - price) * pos.qty
                    eq += pos_value
            self.equity.append({'ts': ts, 'equity': eq, 'balance': balance})
            
            # 获取索引和状态
            htf_idx = self._idx(ts, self._cache['htf_ts'])
            mtf_idx = self._idx(ts, self._cache['mtf_ts'])
            
            if htf_idx is None or mtf_idx is None:
                continue
            
            regime = self._get_market_regime(htf_idx, i)
            big_trend = self._get_big_trend(htf_idx)  # 【v5.1】获取大趋势
            
            # 【v5.3修复】持仓管理：分离网格和趋势
            # 检查网格持仓（多层）
            grid_positions_for_symbol = {k: v for k, v in self.grid_positions.items() if v.get('symbol') == sym}
            if grid_positions_for_symbol:
                # 处理网格持仓（可能有多个层）
                for grid_layer_num, grid_layer_info in list(grid_positions_for_symbol.items()):
                    pos = grid_layer_info.get('position')
                    if not pos:
                        continue
                    
                    grid_tp = grid_layer_info.get('tp_price', pos.tp)
                    bar_high = row['high']
                    bar_low = row['low']
                    
                    # 网格止盈检查（使用网格的止盈价）
                    grid_symbol = grid_layer_info.get('grid_symbol', f"{sym}-layer{grid_layer_num}")  # 【修复】使用独立的grid_symbol
                    if pos.side == SignalType.LONG:
                        if bar_high >= grid_tp:
                            # 网格止盈
                            r = self.grid_pm.close(grid_symbol, grid_tp, f"网格止盈-{grid_layer_num}")  # 【修复】使用grid_symbol
                            if r:
                                grid_balance += r['cash_return']
                                if not use_compound:
                                    grid_balance = min(grid_balance, grid_balance_max)  # 【修复】限制网格资金池不超过初始资金
                                balance = trend_balance + grid_balance  # 更新总余额
                                self.trades.append({**r, 'close_time': ts, 'regime': regime.value, 'grid_layer': grid_layer_num})
                                self.rm.update(r['total_pct'], ts)
                                del self.grid_positions[grid_layer_num]
                            continue
                    else:  # SHORT
                        if bar_low <= grid_tp:
                            # 网格止盈
                            r = self.grid_pm.close(grid_symbol, grid_tp, f"网格止盈-{grid_layer_num}")  # 【修复】使用grid_symbol
                            if r:
                                grid_balance += r['cash_return']
                                if not use_compound:
                                    grid_balance = min(grid_balance, grid_balance_max)  # 【修复】限制网格资金池不超过初始资金
                                balance = trend_balance + grid_balance  # 更新总余额
                                self.trades.append({**r, 'close_time': ts, 'regime': regime.value, 'grid_layer': grid_layer_num})
                                self.rm.update(r['total_pct'], ts)
                                del self.grid_positions[grid_layer_num]
                            continue
                    
                    # 网格止损检查
                    sl_check_price = bar_low if pos.side == SignalType.LONG else bar_high
                    if self.grid_pm.check_sl(grid_symbol, sl_check_price):  # 【修复】使用grid_symbol
                        sl_price = pos.sl
                        r = self.grid_pm.close(grid_symbol, sl_price, f"网格止损-{grid_layer_num}")  # 【修复】使用grid_symbol
                        if r:
                            grid_balance += r['cash_return']
                            grid_balance = min(grid_balance, grid_balance_max)  # 【修复】限制网格资金池不超过初始资金
                            balance = trend_balance + grid_balance  # 更新总余额
                            self.trades.append({**r, 'close_time': ts, 'regime': regime.value, 'grid_layer': grid_layer_num})
                            self.rm.update(r['total_pct'], ts)
                            if grid_layer_num in self.grid_positions:
                                del self.grid_positions[grid_layer_num]
                        continue
                
            # 检查趋势持仓
            if self.trend_pm.has(sym):
                pos = self.trend_pm.get(sym)
                
                # 获取K线高低价用于精确检查止损止盈
                bar_high = row['high']
                bar_low = row['low']
                
                # 止损检查：做多用最低价，做空用最高价
                sl_check_price = bar_low if pos.side == SignalType.LONG else bar_high
                if self.trend_pm.check_sl(sym, sl_check_price):
                    # 用止损价平仓，而非收盘价
                    sl_price = pos.sl
                    r = self.trend_pm.close(sym, sl_price, "止损")
                    if r:
                        trend_balance += r['cash_return']
                        balance = trend_balance + grid_balance  # 更新总余额
                        self.trades.append({**r, 'close_time': ts, 'regime': regime.value})
                        self.rm.update(r['total_pct'], ts)
                    continue
                
                # 完全止盈检查：做多用最高价，做空用最低价
                tp_check_price = bar_high if pos.side == SignalType.LONG else bar_low
                if self.trend_pm.check_full_tp(sym, tp_check_price):
                    # 用止盈价平仓
                    tp_price = pos.tp
                    r = self.trend_pm.close(sym, tp_price, "止盈")
                    if r:
                        trend_balance += r['cash_return']
                        balance = trend_balance + grid_balance  # 更新总余额
                        self.trades.append({**r, 'close_time': ts, 'regime': regime.value})
                        self.rm.update(r['total_pct'], ts)
                    continue
                
                # 部分止盈检查
                ok, cash = self.trend_pm.check_partial_tp(sym, tp_check_price)
                if ok:
                    trend_balance += cash
                    balance = trend_balance + grid_balance  # 更新总余额
                
                # 移动止损（用收盘价更新最高/最低点）
                self.trend_pm.update_trailing(sym, price)
                
                # 加仓检查（仅限箱体交易）
                if pos.trade_type == "box":
                    if not pos.b2_done:
                        ok, cost = self.trend_pm.add_b2(sym, price, trend_balance)
                        if ok:
                            trend_balance -= cost
                            balance = trend_balance + grid_balance  # 更新总余额
                    elif not pos.b3_done:
                        ok, cost = self.trend_pm.add_b3(sym, price, trend_balance)
                        if ok:
                            trend_balance -= cost
                            balance = trend_balance + grid_balance  # 更新总余额
                
                continue
            
            # 执行待处理信号
            if pending:
                exec_price = nxt['open']
                ok, _ = self.rm.check_limits(ts)
                if ok:
                    atr = self._cache['atr'].iloc[i]
                    if not pd.isna(atr) and atr > 0:
                        # 【v5.3】网格策略特殊处理
                        if pending_type == 'grid' and pending_grid_info:
                            # 网格开仓：使用网格信号中的价格、止损、止盈
                            grid_info = pending_grid_info
                            grid_price = grid_info['price']
                            grid_size = grid_info['size']
                            grid_sl = grid_info['sl_price']
                            grid_tp = grid_info['tp_price']
                            grid_layer = grid_info['layer']
                            
                            # 检查价格是否仍在箱体内
                            box_high = self._cache['box_h'].iloc[i] if i < len(self._cache['box_h']) else None
                            box_low = self._cache['box_l'].iloc[i] if i < len(self._cache['box_l']) else None
                            if box_high and box_low:
                                if grid_price < box_low or grid_price > box_high:
                                    # 价格不在箱体内，取消网格信号
                                    pending = None
                                    pending_type = None
                                    pending_big_trend = None
                                    pending_grid_info = None
                                    continue
                            
                            # 【v5.3修复】检查是否有足够资金（使用网格资金池）
                            if grid_size > 0 and grid_size * (1 + self.cfg.TRADING_FEE) <= grid_balance:
                                # 【修复】为每个网格层创建独立的symbol，避免PositionManager覆盖问题
                                grid_symbol = f"{sym}-layer{grid_layer}"
                                pos, cost = self.grid_pm.open(
                                    grid_symbol, pending, grid_price, grid_size, grid_sl, grid_tp,
                                    atr, ts, i, 'grid',
                                    pending_big_trend.value if pending_big_trend else "neutral"
                                )
                                grid_balance -= cost
                                balance = trend_balance + grid_balance  # 更新总余额
                                
                                # 记录网格持仓
                                self.grid_positions[grid_layer] = {
                                    'symbol': sym,
                                    'grid_symbol': grid_symbol,  # 用于PositionManager
                                    'position': pos,
                                    'layer': grid_layer,
                                    'tp_price': grid_tp
                                }
                        else:
                            # 普通趋势交易
                            sl = self.rm.calc_sl(exec_price, atr, pending)
                            tp = self.rm.calc_tp(exec_price, atr, pending)
                            tier = COIN_TIERS.get(sym, CoinTier.TIER_2)
                            size = self.rm.calc_size(trend_balance, exec_price, sl, tier, pending)  # 使用趋势资金池，按方向加权风险
                            b1 = size * self.cfg.BATCH1_RATIO
                            
                            if b1 > 0 and b1 * (1 + self.cfg.TRADING_FEE) <= trend_balance:
                                _, cost = self.trend_pm.open(
                                    sym, pending, exec_price, b1, sl, tp, 
                                    atr, ts, i, pending_type,
                                    pending_big_trend.value if pending_big_trend else "neutral"
                                )
                                trend_balance -= cost
                                balance = trend_balance + grid_balance  # 更新总余额
                pending = None
                pending_type = None
                pending_big_trend = None
                pending_grid_info = None
            
            # 检查每日限制
            ok, _ = self.rm.check_limits(ts)
            if not ok:
                continue
            
            # 根据市场状态生成信号
            if regime == MarketRegime.RANGE_BOUND:
                # 【v5.3】震荡市场：使用网格策略
                if self.cfg.ENABLE_GRID_TRADING:
                    box_high = self._cache['box_h'].iloc[i] if i < len(self._cache['box_h']) else None
                    box_low = self._cache['box_l'].iloc[i] if i < len(self._cache['box_l']) else None
                    atr = self._cache['atr'].iloc[i] if i < len(self._cache['atr']) else 0
                    
                    if box_high and box_low and not pd.isna(atr) and atr > 0:
                        # 【v5.3修复】计算网格：使用网格资金池（限制在初始资金内）
                        grid_balance_for_calc = min(grid_balance, grid_balance_max) if not use_compound else grid_balance  # 【修复】限制网格资金池（复利模式不限制）
                        grid_layers = self.grid_sg.calculate_grid(
                            box_high, box_low, price, atr, big_trend, grid_balance_for_calc
                        )
                        
                        if grid_layers:
                            # 【v5.3修复】检查网格信号：使用网格资金池和网格持仓
                            existing_grid_positions = {}
                            for layer_num, layer_info in self.grid_positions.items():
                                if layer_info.get('symbol') == sym:
                                    existing_grid_positions[layer_num] = layer_info.get('position')
                            
                            grid_signal = self.grid_sg.check_grid_signal(
                                price, box_high, box_low, grid_layers, existing_grid_positions
                            )
                            
                            if grid_signal:
                                if grid_signal['type'] == 'grid_entry':
                                    # 【v5.3修复】网格开仓：检查该层是否已有持仓（不检查币种）
                                    grid_layer = grid_signal.get('layer')
                                    if grid_layer not in self.grid_positions:
                                        # 使用网格资金池重新计算仓位（限制在初始资金内）
                                        grid_balance_for_calc = min(grid_balance, grid_balance_max) if not use_compound else grid_balance  # 【修复】限制网格资金池（复利模式不限制）
                                        grid_signal['size'] = self._recalc_grid_size(
                                            grid_signal, grid_balance_for_calc, box_high, box_low, atr, big_trend
                                        )
                                        if grid_signal['size'] > 0:
                                            pending = grid_signal['side']
                                            pending_type = 'grid'
                                            pending_big_trend = big_trend
                                            pending_grid_info = grid_signal
                                elif grid_signal['type'] == 'grid_exit':
                                    # 网格平仓（已在持仓管理中处理，这里不需要）
                                    pass
                # v5.2旧逻辑：震荡市场不交易（已禁用）
                # pass
                    
            elif regime == MarketRegime.TRENDING_UP:
                # 上升趋势：回调做多
                mtf_ema20 = self._cache['mtf_ema20'].iloc[mtf_idx]
                mtf_ema100 = self._cache['mtf_ema100'].iloc[mtf_idx]
                
                if mtf_ema20 > mtf_ema100:
                    price_ratio = (price - mtf_ema20) / mtf_ema20
                    price_pullback = 0 <= price_ratio <= 0.015
                    has_bull_rev = self._cache['bull'].iloc[i]
                    
                    if price_pullback or (price_ratio < 0.03 and has_bull_rev):
                        pending = SignalType.LONG
                        pending_type = "trend"
                        pending_big_trend = big_trend
                    
            elif regime == MarketRegime.TRENDING_DOWN:
                # 下降趋势：反弹做空
                mtf_ema20 = self._cache['mtf_ema20'].iloc[mtf_idx]
                mtf_ema100 = self._cache['mtf_ema100'].iloc[mtf_idx]
                
                if mtf_ema20 < mtf_ema100:
                    price_ratio = (mtf_ema20 - price) / mtf_ema20
                    price_bounce = 0 <= price_ratio <= 0.015
                    has_bear_rev = self._cache['bear'].iloc[i]
                    
                    if price_bounce or (price_ratio < 0.03 and has_bear_rev):
                        pending = SignalType.SHORT
                        pending_type = "trend"
                        pending_big_trend = big_trend
        
        # 【v5.3修复】计算最终余额：趋势余额 + 网格余额
        final_balance = trend_balance + grid_balance
        # 【修复】初始资金使用传入的单一本金（已拆分为两池）
        total_init_bal = init_bal
        # 【修复】使用最终权益而不是余额计算收益率（权益包含未平仓持仓价值）
        final_equity = self.equity[-1]['equity'] if self.equity else final_balance
        return self._results(total_init_bal, final_equity)
    
    def _results(self, init: float, final: float) -> Dict:
        if not self.trades:
            return {'trades': 0, 'win_rate': 0, 'pf': 0, 'ret': 0, 'dd': 0, 'sharpe': 0}
        
        wins = [t for t in self.trades if t['total_pnl'] > 0]
        losses = [t for t in self.trades if t['total_pnl'] <= 0]
        
        wr = len(wins) / len(self.trades) * 100
        aw = np.mean([t['total_pct'] for t in wins]) if wins else 0
        al = abs(np.mean([t['total_pct'] for t in losses])) if losses else 1
        pf = aw / al if al > 0 else 0
        
        ret = (final - init) / init * 100
        
        eq = pd.Series([e['equity'] for e in self.equity])
        dd = ((eq - eq.expanding().max()) / eq.expanding().max() * 100).min()
        
        rets = eq.pct_change().dropna()
        sharpe = rets.mean() / rets.std() * np.sqrt(252*24*4) if len(rets) > 0 and rets.std() > 0 else 0
        
        # 按交易类型统计
        box_trades = [t for t in self.trades if t.get('trade_type') == 'box']
        trend_trades = [t for t in self.trades if t.get('trade_type') == 'trend']
        grid_trades = [t for t in self.trades if t.get('trade_type') == 'grid']  # 【v5.3】网格交易
        
        # 按方向统计
        long_trades = [t for t in self.trades if t.get('side') == 'long']
        short_trades = [t for t in self.trades if t.get('side') == 'short']
        
        return {
            'trades': len(self.trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': wr,
            'avg_win': aw,
            'avg_loss': al,
            'pf': pf,
            'avg_r': np.mean([t['r'] for t in self.trades]),
            'ret': ret,
            'dd': abs(dd) if pd.notna(dd) else 0,
            'sharpe': sharpe,
            'init': init,
            'final': final,
            'box_trades': len(box_trades),
            'trend_trades': len(trend_trades),
            'grid_trades': len(grid_trades),  # 【v5.3】网格交易数量
            'box_pnl': sum(t['total_pnl'] for t in box_trades),
            'trend_pnl': sum(t['total_pnl'] for t in trend_trades),
            'grid_pnl': sum(t['total_pnl'] for t in grid_trades),  # 【v5.3】网格交易盈亏
            'box_win_rate': len([t for t in box_trades if t['total_pnl'] > 0]) / len(box_trades) * 100 if box_trades else 0,
            'trend_win_rate': len([t for t in trend_trades if t['total_pnl'] > 0]) / len(trend_trades) * 100 if trend_trades else 0,
            'grid_win_rate': len([t for t in grid_trades if t['total_pnl'] > 0]) / len(grid_trades) * 100 if grid_trades else 0,  # 【v5.3】网格交易胜率
            'long_trades': len(long_trades),
            'short_trades': len(short_trades),
            'long_pnl': sum(t['total_pnl'] for t in long_trades),
            'short_pnl': sum(t['total_pnl'] for t in short_trades),
        }
    
    def save(self, trades_file: str = 'trades.csv', equity_file: str = 'equity.csv'):
        if self.trades:
            pd.DataFrame(self.trades).to_csv(trades_file, index=False)
            logger.info(f"交易记录已保存: {trades_file}")
        if self.equity:
            pd.DataFrame(self.equity).to_csv(equity_file, index=False)
            logger.info(f"权益曲线已保存: {equity_file}")


# ============================================================================
# 主函数
# ============================================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description='趋势跟踪策略 v5.2')
    parser.add_argument('--mode', choices=['backtest', 'live'], default='backtest')
    parser.add_argument('--symbol', default='BTC/USDT')
    parser.add_argument('--trading-mode', choices=['conservative', 'standard', 'aggressive'], default='standard')
    args = parser.parse_args()
    
    cfg = StrategyConfig()
    cfg.SYMBOL = args.symbol
    cfg.TRADING_MODE = TradingMode(args.trading_mode)
    
    logger.info("=" * 60)
    logger.info(f"策略 v5.2 | {cfg.SYMBOL} | {cfg.TRADING_MODE.value}")
    logger.info("改进: 纯趋势交易 + 2%风险 + 5R止盈 + 一次性建仓")
    logger.info("=" * 60)
    
    if args.mode == 'backtest':
        ex = ccxt.binance({'enableRateLimit': True})
        
        from pathlib import Path
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        logger.info("获取历史数据...")
        
        def fetch_ohlcv(symbol, tf, limit=500):
            try:
                data = ex.fetch_ohlcv(symbol, tf, limit=limit)
                if not data:
                    return pd.DataFrame()
                df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                return df.reset_index(drop=True)
            except Exception as e:
                logger.error(f"获取数据失败 {symbol} {tf}: {e}")
                return pd.DataFrame()
        
        ltf = fetch_ohlcv(cfg.SYMBOL, cfg.LTF_TIMEFRAME, 2000)
        mtf = fetch_ohlcv(cfg.SYMBOL, cfg.MTF_TIMEFRAME, 500)
        htf = fetch_ohlcv(cfg.SYMBOL, cfg.HTF_TIMEFRAME, 200)
        
        if ltf.empty or mtf.empty or htf.empty:
            logger.error("数据获取失败")
            return
        
        logger.info(f"数据量: LTF={len(ltf)}, MTF={len(mtf)}, HTF={len(htf)}")
        
        engine = BacktestEngine(cfg)
        r = engine.run(ltf, mtf, htf)
        
        logger.info("=" * 60)
        logger.info("回测结果")
        logger.info("=" * 60)
        logger.info(f"交易次数: {r['trades']} (胜{r['wins']}/负{r['losses']})")
        logger.info(f"  - 箱体交易: {r['box_trades']} (盈亏${r['box_pnl']:.0f}, 胜率{r['box_win_rate']:.1f}%)")
        logger.info(f"  - 趋势交易: {r['trend_trades']} (盈亏${r['trend_pnl']:.0f}, 胜率{r['trend_win_rate']:.1f}%)")
        logger.info(f"  - 做多: {r['long_trades']} (盈亏${r['long_pnl']:.0f})")
        logger.info(f"  - 做空: {r['short_trades']} (盈亏${r['short_pnl']:.0f})")
        logger.info(f"胜率: {r['win_rate']:.1f}%")
        logger.info(f"平均盈利: {r['avg_win']:.2f}% | 平均亏损: {r['avg_loss']:.2f}%")
        logger.info(f"盈亏比: {r['pf']:.2f}")
        logger.info(f"平均R: {r['avg_r']:.2f}")
        logger.info(f"总收益: {r['ret']:.2f}%")
        logger.info(f"最大回撤: {r['dd']:.2f}%")
        logger.info(f"夏普比率: {r['sharpe']:.2f}")
        logger.info(f"最终资金: ${r['final']:.2f}")
        logger.info("=" * 60)
        
        engine.save()


if __name__ == '__main__':
    main()
