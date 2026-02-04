# -*- coding: utf-8 -*-
"""
===================================
趨勢交易分析器 - 基於用戶交易理念
===================================

交易理念核心原則：
1. 嚴進策略 - 不追高，追求每筆交易成功率
2. 趨勢交易 - MA5>MA10>MA20 多頭排列，順勢而為
3. 效率優先 - 關注籌碼結構好的股票
4. 買點偏好 - 在 MA5/MA10 附近回踩買入

技術標準：
- 多頭排列：MA5 > MA10 > MA20
- 乖離率：(Close - MA5) / MA5 < 5%（不追高）
- 量能形態：縮量回調優先
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class TrendStatus(Enum):
    """趨勢狀態枚舉"""
    STRONG_BULL = "強勢多頭"      # MA5 > MA10 > MA20，且間距擴大
    BULL = "多頭排列"             # MA5 > MA10 > MA20
    WEAK_BULL = "弱勢多頭"        # MA5 > MA10，但 MA10 < MA20
    CONSOLIDATION = "盤整"        # 均線纏繞
    WEAK_BEAR = "弱勢空頭"        # MA5 < MA10，但 MA10 > MA20
    BEAR = "空頭排列"             # MA5 < MA10 < MA20
    STRONG_BEAR = "強勢空頭"      # MA5 < MA10 < MA20，且間距擴大


class VolumeStatus(Enum):
    """量能狀態枚舉"""
    HEAVY_VOLUME_UP = "放量上漲"       # 量價齊升
    HEAVY_VOLUME_DOWN = "放量下跌"     # 放量殺跌
    SHRINK_VOLUME_UP = "縮量上漲"      # 無量上漲
    SHRINK_VOLUME_DOWN = "縮量回調"    # 縮量回調（好）
    NORMAL = "量能正常"


class BuySignal(Enum):
    """買入信號枚舉"""
    STRONG_BUY = "強烈買入"       # 多條件滿足
    BUY = "買入"                  # 基本條件滿足
    HOLD = "持有"                 # 已持有可繼續
    WAIT = "觀望"                 # 等待更好時機
    SELL = "賣出"                 # 趨勢轉弱
    STRONG_SELL = "強烈賣出"      # 趨勢破壞


class MACDStatus(Enum):
    """MACD狀態枚舉"""
    GOLDEN_CROSS_ZERO = "零軸上金叉"      # DIF上穿DEA，且在零軸上方
    GOLDEN_CROSS = "金叉"                # DIF上穿DEA
    BULLISH = "多頭"                    # DIF>DEA>0
    CROSSING_UP = "上穿零軸"             # DIF上穿零軸
    CROSSING_DOWN = "下穿零軸"           # DIF下穿零軸
    BEARISH = "空頭"                    # DIF<DEA<0
    DEATH_CROSS = "死叉"                # DIF下穿DEA


class RSIStatus(Enum):
    """RSI狀態枚舉"""
    OVERBOUGHT = "超買"        # RSI > 70
    STRONG_BUY = "強勢買入"    # 50 < RSI < 70
    NEUTRAL = "中性"          # 40 <= RSI <= 60
    WEAK = "弱勢"             # 30 < RSI < 40
    OVERSOLD = "超賣"         # RSI < 30


@dataclass
class TrendAnalysisResult:
    """趨勢分析結果"""
    code: str
    
    # 趨勢判斷
    trend_status: TrendStatus = TrendStatus.CONSOLIDATION
    ma_alignment: str = ""           # 均線排列描述
    trend_strength: float = 0.0      # 趨勢強度 0-100
    
    # 均線數據
    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0
    ma60: float = 0.0
    current_price: float = 0.0
    
    # 乖離率（與 MA5 的偏離度）
    bias_ma5: float = 0.0            # (Close - MA5) / MA5 * 100
    bias_ma10: float = 0.0
    bias_ma20: float = 0.0
    
    # 量能分析
    volume_status: VolumeStatus = VolumeStatus.NORMAL
    volume_ratio_5d: float = 0.0     # 當日成交量/5日均量
    volume_trend: str = ""           # 量能趨勢描述
    
    # 支撐壓力
    support_ma5: bool = False        # MA5 是否構成支撐
    support_ma10: bool = False       # MA10 是否構成支撐
    resistance_levels: List[float] = field(default_factory=list)
    support_levels: List[float] = field(default_factory=list)

    # MACD 指標
    macd_dif: float = 0.0          # DIF 快線
    macd_dea: float = 0.0          # DEA 慢線
    macd_bar: float = 0.0           # MACD 柱狀圖
    macd_status: MACDStatus = MACDStatus.BULLISH
    macd_signal: str = ""            # MACD 信號描述

    # RSI 指標
    rsi_6: float = 0.0              # RSI(6) 短期
    rsi_12: float = 0.0             # RSI(12) 中期
    rsi_24: float = 0.0             # RSI(24) 長期
    rsi_status: RSIStatus = RSIStatus.NEUTRAL
    rsi_signal: str = ""              # RSI 信號描述

    # 買入信號
    buy_signal: BuySignal = BuySignal.WAIT
    signal_score: int = 0            # 綜合評分 0-100
    signal_reasons: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'code': self.code,
            'trend_status': self.trend_status.value,
            'ma_alignment': self.ma_alignment,
            'trend_strength': self.trend_strength,
            'ma5': self.ma5,
            'ma10': self.ma10,
            'ma20': self.ma20,
            'ma60': self.ma60,
            'current_price': self.current_price,
            'bias_ma5': self.bias_ma5,
            'bias_ma10': self.bias_ma10,
            'bias_ma20': self.bias_ma20,
            'volume_status': self.volume_status.value,
            'volume_ratio_5d': self.volume_ratio_5d,
            'volume_trend': self.volume_trend,
            'support_ma5': self.support_ma5,
            'support_ma10': self.support_ma10,
            'buy_signal': self.buy_signal.value,
            'signal_score': self.signal_score,
            'signal_reasons': self.signal_reasons,
            'risk_factors': self.risk_factors,
            'macd_dif': self.macd_dif,
            'macd_dea': self.macd_dea,
            'macd_bar': self.macd_bar,
            'macd_status': self.macd_status.value,
            'macd_signal': self.macd_signal,
            'rsi_6': self.rsi_6,
            'rsi_12': self.rsi_12,
            'rsi_24': self.rsi_24,
            'rsi_status': self.rsi_status.value,
            'rsi_signal': self.rsi_signal,
        }


class StockTrendAnalyzer:
    """
    股票趨勢分析器

    基於用戶交易理念實現：
    1. 趨勢判斷 - MA5>MA10>MA20 多頭排列
    2. 乖離率檢測 - 不追高，偏離 MA5 超過 5% 不買
    3. 量能分析 - 偏好縮量回調
    4. 買點識別 - 回踩 MA5/MA10 支撐
    5. MACD 指標 - 趨勢確認和金叉死叉信號
    6. RSI 指標 - 超買超賣判斷
    """
    
    # 交易參數配置
    BIAS_THRESHOLD = 5.0        # 乖離率閾值（%），超過此值不買入
    VOLUME_SHRINK_RATIO = 0.7   # 縮量判斷閾值（當日量/5日均量）
    VOLUME_HEAVY_RATIO = 1.5    # 放量判斷閾值
    MA_SUPPORT_TOLERANCE = 0.02  # MA 支撐判斷容忍度（2%）

    # MACD 參數（標準12/26/9）
    MACD_FAST = 12              # 快線週期
    MACD_SLOW = 26             # 慢線週期
    MACD_SIGNAL = 9             # 信號線週期

    # RSI 參數
    RSI_SHORT = 6               # 短期RSI週期
    RSI_MID = 12               # 中期RSI週期
    RSI_LONG = 24              # 長期RSI週期
    RSI_OVERBOUGHT = 70        # 超買閾值
    RSI_OVERSOLD = 30          # 超賣閾值
    
    def __init__(self):
        """初始化分析器"""
        pass
    
    def analyze(self, df: pd.DataFrame, code: str) -> TrendAnalysisResult:
        """
        分析股票趨勢
        
        Args:
            df: 包含 OHLCV 數據的 DataFrame
            code: 股票代碼
            
        Returns:
            TrendAnalysisResult 分析結果
        """
        result = TrendAnalysisResult(code=code)
        
        if df is None or df.empty or len(df) < 20:
            logger.warning(f"{code} 數據不足，無法進行趨勢分析")
            result.risk_factors.append("數據不足，無法完成分析")
            return result
        
        # 確保數據按日期排序
        df = df.sort_values('date').reset_index(drop=True)
        
        # 計算均線
        df = self._calculate_mas(df)

        # 計算 MACD 和 RSI
        df = self._calculate_macd(df)
        df = self._calculate_rsi(df)

        # 獲取最新數據
        latest = df.iloc[-1]
        result.current_price = float(latest['close'])
        result.ma5 = float(latest['MA5'])
        result.ma10 = float(latest['MA10'])
        result.ma20 = float(latest['MA20'])
        result.ma60 = float(latest.get('MA60', 0))

        # 1. 趨勢判斷
        self._analyze_trend(df, result)

        # 2. 乖離率計算
        self._calculate_bias(result)

        # 3. 量能分析
        self._analyze_volume(df, result)

        # 4. 支撐壓力分析
        self._analyze_support_resistance(df, result)

        # 5. MACD 分析
        self._analyze_macd(df, result)

        # 6. RSI 分析
        self._analyze_rsi(df, result)

        # 7. 生成買入信號
        self._generate_signal(result)

        return result
    
    def _calculate_mas(self, df: pd.DataFrame) -> pd.DataFrame:
        """計算均線"""
        df = df.copy()
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA10'] = df['close'].rolling(window=10).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        if len(df) >= 60:
            df['MA60'] = df['close'].rolling(window=60).mean()
        else:
            df['MA60'] = df['MA20']  # 數據不足時使用 MA20 替代
        return df

    def _calculate_macd(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        計算 MACD 指標

        公式：
        - EMA(12)：12日指數移動平均
        - EMA(26)：26日指數移動平均
        - DIF = EMA(12) - EMA(26)
        - DEA = EMA(DIF, 9)
        - MACD = (DIF - DEA) * 2
        """
        df = df.copy()

        # 計算快慢線 EMA
        ema_fast = df['close'].ewm(span=self.MACD_FAST, adjust=False).mean()
        ema_slow = df['close'].ewm(span=self.MACD_SLOW, adjust=False).mean()

        # 計算快線 DIF
        df['MACD_DIF'] = ema_fast - ema_slow

        # 計算信號線 DEA
        df['MACD_DEA'] = df['MACD_DIF'].ewm(span=self.MACD_SIGNAL, adjust=False).mean()

        # 計算柱狀圖
        df['MACD_BAR'] = (df['MACD_DIF'] - df['MACD_DEA']) * 2

        return df

    def _calculate_rsi(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        計算 RSI 指標

        公式：
        - RS = 平均上漲幅度 / 平均下跌幅度
        - RSI = 100 - (100 / (1 + RS))
        """
        df = df.copy()

        for period in [self.RSI_SHORT, self.RSI_MID, self.RSI_LONG]:
            # 計算價格變化
            delta = df['close'].diff()

            # 分離上漲和下跌
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)

            # 計算平均漲跌幅
            avg_gain = gain.rolling(window=period).mean()
            avg_loss = loss.rolling(window=period).mean()

            # 計算 RS 和 RSI
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

            # 填充 NaN 值
            rsi = rsi.fillna(50)  # 默認中性值

            # 添加到 DataFrame
            col_name = f'RSI_{period}'
            df[col_name] = rsi

        return df
    
    def _analyze_trend(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        """
        分析趨勢狀態
        
        核心邏輯：判斷均線排列和趨勢強度
        """
        ma5, ma10, ma20 = result.ma5, result.ma10, result.ma20
        
        # 判斷均線排列
        if ma5 > ma10 > ma20:
            # 檢查間距是否在擴大（強勢）
            prev = df.iloc[-5] if len(df) >= 5 else df.iloc[-1]
            prev_spread = (prev['MA5'] - prev['MA20']) / prev['MA20'] * 100 if prev['MA20'] > 0 else 0
            curr_spread = (ma5 - ma20) / ma20 * 100 if ma20 > 0 else 0
            
            if curr_spread > prev_spread and curr_spread > 5:
                result.trend_status = TrendStatus.STRONG_BULL
                result.ma_alignment = "強勢多頭排列，均線發散上行"
                result.trend_strength = 90
            else:
                result.trend_status = TrendStatus.BULL
                result.ma_alignment = "多頭排列 MA5>MA10>MA20"
                result.trend_strength = 75
                
        elif ma5 > ma10 and ma10 <= ma20:
            result.trend_status = TrendStatus.WEAK_BULL
            result.ma_alignment = "弱勢多頭，MA5>MA10 但 MA10≤MA20"
            result.trend_strength = 55
            
        elif ma5 < ma10 < ma20:
            prev = df.iloc[-5] if len(df) >= 5 else df.iloc[-1]
            prev_spread = (prev['MA20'] - prev['MA5']) / prev['MA5'] * 100 if prev['MA5'] > 0 else 0
            curr_spread = (ma20 - ma5) / ma5 * 100 if ma5 > 0 else 0
            
            if curr_spread > prev_spread and curr_spread > 5:
                result.trend_status = TrendStatus.STRONG_BEAR
                result.ma_alignment = "強勢空頭排列，均線發散下行"
                result.trend_strength = 10
            else:
                result.trend_status = TrendStatus.BEAR
                result.ma_alignment = "空頭排列 MA5<MA10<MA20"
                result.trend_strength = 25
                
        elif ma5 < ma10 and ma10 >= ma20:
            result.trend_status = TrendStatus.WEAK_BEAR
            result.ma_alignment = "弱勢空頭，MA5<MA10 但 MA10≥MA20"
            result.trend_strength = 40
            
        else:
            result.trend_status = TrendStatus.CONSOLIDATION
            result.ma_alignment = "均線纏繞，趨勢不明"
            result.trend_strength = 50
    
    def _calculate_bias(self, result: TrendAnalysisResult) -> None:
        """
        計算乖離率
        
        乖離率 = (現價 - 均線) / 均線 * 100%
        
        嚴進策略：乖離率超過 5% 不追高
        """
        price = result.current_price
        
        if result.ma5 > 0:
            result.bias_ma5 = (price - result.ma5) / result.ma5 * 100
        if result.ma10 > 0:
            result.bias_ma10 = (price - result.ma10) / result.ma10 * 100
        if result.ma20 > 0:
            result.bias_ma20 = (price - result.ma20) / result.ma20 * 100
    
    def _analyze_volume(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        """
        分析量能
        
        偏好：縮量回調 > 放量上漲 > 縮量上漲 > 放量下跌
        """
        if len(df) < 5:
            return
        
        latest = df.iloc[-1]
        vol_5d_avg = df['volume'].iloc[-6:-1].mean()
        
        if vol_5d_avg > 0:
            result.volume_ratio_5d = float(latest['volume']) / vol_5d_avg
        
        # 判斷價格變化
        prev_close = df.iloc[-2]['close']
        price_change = (latest['close'] - prev_close) / prev_close * 100
        
        # 量能狀態判斷
        if result.volume_ratio_5d >= self.VOLUME_HEAVY_RATIO:
            if price_change > 0:
                result.volume_status = VolumeStatus.HEAVY_VOLUME_UP
                result.volume_trend = "放量上漲，多頭力量強勁"
            else:
                result.volume_status = VolumeStatus.HEAVY_VOLUME_DOWN
                result.volume_trend = "放量下跌，注意風險"
        elif result.volume_ratio_5d <= self.VOLUME_SHRINK_RATIO:
            if price_change > 0:
                result.volume_status = VolumeStatus.SHRINK_VOLUME_UP
                result.volume_trend = "縮量上漲，上攻動能不足"
            else:
                result.volume_status = VolumeStatus.SHRINK_VOLUME_DOWN
                result.volume_trend = "縮量回調，洗盤特徵明顯（好）"
        else:
            result.volume_status = VolumeStatus.NORMAL
            result.volume_trend = "量能正常"
    
    def _analyze_support_resistance(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        """
        分析支撐壓力位
        
        買點偏好：回踩 MA5/MA10 獲得支撐
        """
        price = result.current_price
        
        # 檢查是否在 MA5 附近獲得支撐
        if result.ma5 > 0:
            ma5_distance = abs(price - result.ma5) / result.ma5
            if ma5_distance <= self.MA_SUPPORT_TOLERANCE and price >= result.ma5:
                result.support_ma5 = True
                result.support_levels.append(result.ma5)
        
        # 檢查是否在 MA10 附近獲得支撐
        if result.ma10 > 0:
            ma10_distance = abs(price - result.ma10) / result.ma10
            if ma10_distance <= self.MA_SUPPORT_TOLERANCE and price >= result.ma10:
                result.support_ma10 = True
                if result.ma10 not in result.support_levels:
                    result.support_levels.append(result.ma10)
        
        # MA20 作為重要支撐
        if result.ma20 > 0 and price >= result.ma20:
            result.support_levels.append(result.ma20)
        
        # 近期高點作為壓力
        if len(df) >= 20:
            recent_high = df['high'].iloc[-20:].max()
            if recent_high > price:
                result.resistance_levels.append(recent_high)

    def _analyze_macd(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        """
        分析 MACD 指標

        核心信號：
        - 零軸上金叉：最強買入信號
        - 金叉：DIF 上穿 DEA
        - 死叉：DIF 下穿 DEA
        """
        if len(df) < self.MACD_SLOW:
            result.macd_signal = "數據不足"
            return

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # 獲取 MACD 數據
        result.macd_dif = float(latest['MACD_DIF'])
        result.macd_dea = float(latest['MACD_DEA'])
        result.macd_bar = float(latest['MACD_BAR'])

        # 判斷金叉死叉
        prev_dif_dea = prev['MACD_DIF'] - prev['MACD_DEA']
        curr_dif_dea = result.macd_dif - result.macd_dea

        # 金叉：DIF 上穿 DEA
        is_golden_cross = prev_dif_dea <= 0 and curr_dif_dea > 0

        # 死叉：DIF 下穿 DEA
        is_death_cross = prev_dif_dea >= 0 and curr_dif_dea < 0

        # 零軸穿越
        prev_zero = prev['MACD_DIF']
        curr_zero = result.macd_dif
        is_crossing_up = prev_zero <= 0 and curr_zero > 0
        is_crossing_down = prev_zero >= 0 and curr_zero < 0

        # 判斷 MACD 狀態
        if is_golden_cross and curr_zero > 0:
            result.macd_status = MACDStatus.GOLDEN_CROSS_ZERO
            result.macd_signal = "⭐ 零軸上金叉，強烈買入信號！"
        elif is_crossing_up:
            result.macd_status = MACDStatus.CROSSING_UP
            result.macd_signal = "⚡ DIF上穿零軸，趨勢轉強"
        elif is_golden_cross:
            result.macd_status = MACDStatus.GOLDEN_CROSS
            result.macd_signal = "✅ 金叉，趨勢向上"
        elif is_death_cross:
            result.macd_status = MACDStatus.DEATH_CROSS
            result.macd_signal = "❌ 死叉，趨勢向下"
        elif is_crossing_down:
            result.macd_status = MACDStatus.CROSSING_DOWN
            result.macd_signal = "⚠️ DIF下穿零軸，趨勢轉弱"
        elif result.macd_dif > 0 and result.macd_dea > 0:
            result.macd_status = MACDStatus.BULLISH
            result.macd_signal = "✓ 多頭排列，持續上漲"
        elif result.macd_dif < 0 and result.macd_dea < 0:
            result.macd_status = MACDStatus.BEARISH
            result.macd_signal = "⚠ 空頭排列，持續下跌"
        else:
            result.macd_status = MACDStatus.BULLISH
            result.macd_signal = " MACD 中性區域"

    def _analyze_rsi(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        """
        分析 RSI 指標

        核心判斷：
        - RSI > 70：超買，謹慎追高
        - RSI < 30：超賣，關注反彈
        - 40-60：中性區域
        """
        if len(df) < self.RSI_LONG:
            result.rsi_signal = "數據不足"
            return

        latest = df.iloc[-1]

        # 獲取 RSI 數據
        result.rsi_6 = float(latest[f'RSI_{self.RSI_SHORT}'])
        result.rsi_12 = float(latest[f'RSI_{self.RSI_MID}'])
        result.rsi_24 = float(latest[f'RSI_{self.RSI_LONG}'])

        # 以中期 RSI(12) 為主進行判斷
        rsi_mid = result.rsi_12

        # 判斷 RSI 狀態
        if rsi_mid > self.RSI_OVERBOUGHT:
            result.rsi_status = RSIStatus.OVERBOUGHT
            result.rsi_signal = f"⚠️ RSI超買({rsi_mid:.1f}>70)，短期回調風險高"
        elif rsi_mid > 60:
            result.rsi_status = RSIStatus.STRONG_BUY
            result.rsi_signal = f"✅ RSI強勢({rsi_mid:.1f})，多頭力量充足"
        elif rsi_mid >= 40:
            result.rsi_status = RSIStatus.NEUTRAL
            result.rsi_signal = f" RSI中性({rsi_mid:.1f})，震盪整理中"
        elif rsi_mid >= self.RSI_OVERSOLD:
            result.rsi_status = RSIStatus.WEAK
            result.rsi_signal = f"⚡ RSI弱勢({rsi_mid:.1f})，關注反彈"
        else:
            result.rsi_status = RSIStatus.OVERSOLD
            result.rsi_signal = f"⭐ RSI超賣({rsi_mid:.1f}<30)，反彈機會大"

    def _generate_signal(self, result: TrendAnalysisResult) -> None:
        """
        生成買入信號

        綜合評分系統：
        - 趨勢（30分）：多頭排列得分高
        - 乖離率（20分）：接近 MA5 得分高
        - 量能（15分）：縮量回調得分高
        - 支撐（10分）：獲得均線支撐得分高
        - MACD（15分）：金叉和多頭得分高
        - RSI（10分）：超賣和強勢得分高
        """
        score = 0
        reasons = []
        risks = []

        # === 趨勢評分（30分）===
        trend_scores = {
            TrendStatus.STRONG_BULL: 30,
            TrendStatus.BULL: 26,
            TrendStatus.WEAK_BULL: 18,
            TrendStatus.CONSOLIDATION: 12,
            TrendStatus.WEAK_BEAR: 8,
            TrendStatus.BEAR: 4,
            TrendStatus.STRONG_BEAR: 0,
        }
        trend_score = trend_scores.get(result.trend_status, 12)
        score += trend_score

        if result.trend_status in [TrendStatus.STRONG_BULL, TrendStatus.BULL]:
            reasons.append(f"✅ {result.trend_status.value}，順勢做多")
        elif result.trend_status in [TrendStatus.BEAR, TrendStatus.STRONG_BEAR]:
            risks.append(f"⚠️ {result.trend_status.value}，不宜做多")

        # === 乖離率評分（20分）===
        bias = result.bias_ma5
        if bias < 0:
            # 價格在 MA5 下方（回調中）
            if bias > -3:
                score += 20
                reasons.append(f"✅ 價格略低於MA5({bias:.1f}%)，回踩買點")
            elif bias > -5:
                score += 16
                reasons.append(f"✅ 價格回踩MA5({bias:.1f}%)，觀察支撐")
            else:
                score += 8
                risks.append(f"⚠️ 乖離率過大({bias:.1f}%)，可能破位")
        elif bias < 2:
            score += 18
            reasons.append(f"✅ 價格貼近MA5({bias:.1f}%)，介入好時機")
        elif bias < self.BIAS_THRESHOLD:
            score += 14
            reasons.append(f"⚡ 價格略高於MA5({bias:.1f}%)，可小倉介入")
        else:
            score += 4
            risks.append(f"❌ 乖離率過高({bias:.1f}%>5%)，嚴禁追高！")

        # === 量能評分（15分）===
        volume_scores = {
            VolumeStatus.SHRINK_VOLUME_DOWN: 15,  # 縮量回調最佳
            VolumeStatus.HEAVY_VOLUME_UP: 12,     # 放量上漲次之
            VolumeStatus.NORMAL: 10,
            VolumeStatus.SHRINK_VOLUME_UP: 6,     # 無量上漲較差
            VolumeStatus.HEAVY_VOLUME_DOWN: 0,    # 放量下跌最差
        }
        vol_score = volume_scores.get(result.volume_status, 8)
        score += vol_score

        if result.volume_status == VolumeStatus.SHRINK_VOLUME_DOWN:
            reasons.append("✅ 縮量回調，主力洗盤")
        elif result.volume_status == VolumeStatus.HEAVY_VOLUME_DOWN:
            risks.append("⚠️ 放量下跌，注意風險")

        # === 支撐評分（10分）===
        if result.support_ma5:
            score += 5
            reasons.append("✅ MA5支撐有效")
        if result.support_ma10:
            score += 5
            reasons.append("✅ MA10支撐有效")

        # === MACD 評分（15分）===
        macd_scores = {
            MACDStatus.GOLDEN_CROSS_ZERO: 15,  # 零軸上金叉最強
            MACDStatus.GOLDEN_CROSS: 12,      # 金叉
            MACDStatus.CROSSING_UP: 10,       # 上穿零軸
            MACDStatus.BULLISH: 8,            # 多頭
            MACDStatus.BEARISH: 2,            # 空頭
            MACDStatus.CROSSING_DOWN: 0,       # 下穿零軸
            MACDStatus.DEATH_CROSS: 0,        # 死叉
        }
        macd_score = macd_scores.get(result.macd_status, 5)
        score += macd_score

        if result.macd_status in [MACDStatus.GOLDEN_CROSS_ZERO, MACDStatus.GOLDEN_CROSS]:
            reasons.append(f"✅ {result.macd_signal}")
        elif result.macd_status in [MACDStatus.DEATH_CROSS, MACDStatus.CROSSING_DOWN]:
            risks.append(f"⚠️ {result.macd_signal}")
        else:
            reasons.append(result.macd_signal)

        # === RSI 評分（10分）===
        rsi_scores = {
            RSIStatus.OVERSOLD: 10,       # 超賣最佳
            RSIStatus.STRONG_BUY: 8,     # 強勢
            RSIStatus.NEUTRAL: 5,        # 中性
            RSIStatus.WEAK: 3,            # 弱勢
            RSIStatus.OVERBOUGHT: 0,       # 超買最差
        }
        rsi_score = rsi_scores.get(result.rsi_status, 5)
        score += rsi_score

        if result.rsi_status in [RSIStatus.OVERSOLD, RSIStatus.STRONG_BUY]:
            reasons.append(f"✅ {result.rsi_signal}")
        elif result.rsi_status == RSIStatus.OVERBOUGHT:
            risks.append(f"⚠️ {result.rsi_signal}")
        else:
            reasons.append(result.rsi_signal)

        # === 綜合判斷 ===
        result.signal_score = score
        result.signal_reasons = reasons
        result.risk_factors = risks

        # 生成買入信號（調整閾值以適應新的100分制）
        if score >= 75 and result.trend_status in [TrendStatus.STRONG_BULL, TrendStatus.BULL]:
            result.buy_signal = BuySignal.STRONG_BUY
        elif score >= 60 and result.trend_status in [TrendStatus.STRONG_BULL, TrendStatus.BULL, TrendStatus.WEAK_BULL]:
            result.buy_signal = BuySignal.BUY
        elif score >= 45:
            result.buy_signal = BuySignal.HOLD
        elif score >= 30:
            result.buy_signal = BuySignal.WAIT
        elif result.trend_status in [TrendStatus.BEAR, TrendStatus.STRONG_BEAR]:
            result.buy_signal = BuySignal.STRONG_SELL
        else:
            result.buy_signal = BuySignal.SELL
    
    def format_analysis(self, result: TrendAnalysisResult) -> str:
        """
        格式化分析結果為文本

        Args:
            result: 分析結果

        Returns:
            格式化的分析文本
        """
        lines = [
            f"=== {result.code} 趨勢分析 ===",
            f"",
            f"📊 趨勢判斷: {result.trend_status.value}",
            f"   均線排列: {result.ma_alignment}",
            f"   趨勢強度: {result.trend_strength}/100",
            f"",
            f"📈 均線數據:",
            f"   現價: {result.current_price:.2f}",
            f"   MA5:  {result.ma5:.2f} (乖離 {result.bias_ma5:+.2f}%)",
            f"   MA10: {result.ma10:.2f} (乖離 {result.bias_ma10:+.2f}%)",
            f"   MA20: {result.ma20:.2f} (乖離 {result.bias_ma20:+.2f}%)",
            f"",
            f"📊 量能分析: {result.volume_status.value}",
            f"   量比(vs5日): {result.volume_ratio_5d:.2f}",
            f"   量能趨勢: {result.volume_trend}",
            f"",
            f"📈 MACD指標: {result.macd_status.value}",
            f"   DIF: {result.macd_dif:.4f}",
            f"   DEA: {result.macd_dea:.4f}",
            f"   MACD: {result.macd_bar:.4f}",
            f"   信號: {result.macd_signal}",
            f"",
            f"📊 RSI指標: {result.rsi_status.value}",
            f"   RSI(6): {result.rsi_6:.1f}",
            f"   RSI(12): {result.rsi_12:.1f}",
            f"   RSI(24): {result.rsi_24:.1f}",
            f"   信號: {result.rsi_signal}",
            f"",
            f"🎯 操作建議: {result.buy_signal.value}",
            f"   綜合評分: {result.signal_score}/100",
        ]

        if result.signal_reasons:
            lines.append(f"")
            lines.append(f"✅ 買入理由:")
            for reason in result.signal_reasons:
                lines.append(f"   {reason}")

        if result.risk_factors:
            lines.append(f"")
            lines.append(f"⚠️ 風險因素:")
            for risk in result.risk_factors:
                lines.append(f"   {risk}")

        return "\n".join(lines)


def analyze_stock(df: pd.DataFrame, code: str) -> TrendAnalysisResult:
    """
    便捷函數：分析單隻股票
    
    Args:
        df: 包含 OHLCV 數據的 DataFrame
        code: 股票代碼
        
    Returns:
        TrendAnalysisResult 分析結果
    """
    analyzer = StockTrendAnalyzer()
    return analyzer.analyze(df, code)


if __name__ == "__main__":
    # 測試代碼
    logging.basicConfig(level=logging.INFO)
    
    # 模擬數據測試
    import numpy as np
    
    dates = pd.date_range(start='2025-01-01', periods=60, freq='D')
    # 這裡可以加入模擬數據進行測試
    print("StockTrendAnalyzer 測試模組")
