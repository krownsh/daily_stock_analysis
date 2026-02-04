# -*- coding: utf-8 -*-
"""
===================================
A股自選股智能分析系統 - AI分析層
===================================

職責：
1. 封裝 Gemini API 調用邏輯
2. 利用 Google Search Grounding 獲取即時新聞
3. 結合技術面和消息面生成分析報告
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from json_repair import repair_json

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from src.config import get_config

logger = logging.getLogger(__name__)


# 股票名稱映射（常見股票）
STOCK_NAME_MAP = {
    # === A股 ===
    '600519': '貴州茅台',
    '000001': '平安銀行',
    '300750': '寧德時代',
    '002594': '比亞迪',
    '600036': '招商銀行',
    '601318': '中國平安',
    '000858': '五糧液',
    '600276': '恆瑞醫藥',
    '601012': '隆基綠能',
    '002475': '立訊精密',
    '300059': '東方財富',
    '002415': '海康威視',
    '600900': '長江電力',
    '601166': '興業銀行',
    '600028': '中國石化',

    # === 美股 ===
    'AAPL': '蘋果',
    'TSLA': '特斯拉',
    'MSFT': '微軟',
    'GOOGL': '谷歌A',
    'GOOG': '谷歌C',
    'AMZN': '亞馬遜',
    'NVDA': '英偉達',
    'META': 'Meta',
    'AMD': 'AMD',
    'INTC': '英特爾',
    'BABA': '阿里巴巴',
    'PDD': '拼多多',
    'JD': '京東',
    'BIDU': '百度',
    'NIO': '蔚來',
    'XPEV': '小鵬汽車',
    'LI': '理想汽車',
    'COIN': 'Coinbase',
    'MSTR': 'MicroStrategy',

    # === 港股 (5位數字) ===
    '00700': '騰訊控股',
    '03690': '美團',
    '01810': '小米集團',
    '09988': '阿里巴巴',
    '09618': '京東集團',
    '09888': '百度集團',
    '01024': '快手',
    '00981': '中芯國際',
    '02015': '理想汽車',
    '09868': '小鵬汽車',
    '00005': '匯豐控股',
    '01299': '友邦保險',
    '00941': '中國移動',
    '00883': '中國海洋石油',
}


def get_stock_name_multi_source(
    stock_code: str, 
    context: Optional[Dict] = None,
    data_manager = None
) -> str:
    """
    多來源獲取股票中文名稱
    
    獲取策略（按優先級）：
    1. 從傳入的 context 中獲取（realtime 數據）
    2. 從靜態映射表 STOCK_NAME_MAP 獲取
    3. 從 DataFetcherManager 獲取（各數據源）
    4. 返回默認名稱（股票+代碼）
    
    Args:
        stock_code: 股票代碼
        context: 分析上下文（可選）
        data_manager: DataFetcherManager 實例（可選）
        
    Returns:
        股票中文名稱
    """
    # 1. 從上下文獲取（即時行情數據）
    if context:
        # 優先從 stock_name 欄位獲取
        if context.get('stock_name'):
            name = context['stock_name']
            if name and not name.startswith('股票'):
                return name
        
        # 其次從 realtime 數據獲取
        if 'realtime' in context and context['realtime'].get('name'):
            return context['realtime']['name']
    
    # 2. 從靜態映射表獲取
    if stock_code in STOCK_NAME_MAP:
        return STOCK_NAME_MAP[stock_code]
    
    # 3. 從數據源獲取
    if data_manager is None:
        try:
            from data_provider.base import DataFetcherManager
            data_manager = DataFetcherManager()
        except Exception as e:
            logger.debug(f"無法初始化 DataFetcherManager: {e}")
    
    if data_manager:
        try:
            name = data_manager.get_stock_name(stock_code)
            if name:
                # 更新快取
                STOCK_NAME_MAP[stock_code] = name
                return name
        except Exception as e:
            logger.debug(f"從數據源獲取股票名稱失敗: {e}")
    
    # 4. 返回默認名稱
    return f'股票{stock_code}'


@dataclass
class AnalysisResult:
    """
    AI 分析結果數據類 - 決策儀表板版
    
    封裝 Gemini 返回的分析結果，包含決策儀表板和詳細分析
    """
    code: str
    name: str
    
    # ========== 核心指標 ==========
    sentiment_score: int  # 綜合評分 0-100 (>70強烈看多, >60看多, 40-60震盪, <40看空)
    trend_prediction: str  # 趨勢預測：強烈看多/看多/震盪/看空/強烈看空
    operation_advice: str  # 操作建議：買入/加倉/持有/減倉/賣出/觀望
    decision_type: str = "hold"  # 決策類型：buy/hold/sell（用於統計）
    confidence_level: str = "中"  # 置信度：高/中/低
    
    # ========== 決策儀表板 (新增) ==========
    dashboard: Optional[Dict[str, Any]] = None  # 完整的決策儀表板數據
    
    # ========== 走勢分析 ==========
    trend_analysis: str = ""  # 走勢形態分析（支撐位、壓力位、趨勢線等）
    short_term_outlook: str = ""  # 短期展望（1-3日）
    medium_term_outlook: str = ""  # 中期展望（1-2周）
    
    # ========== 技術面分析 ==========
    technical_analysis: str = ""  # 技術指標綜合分析
    ma_analysis: str = ""  # 均線分析（多頭/空頭排列，金叉/死叉等）
    volume_analysis: str = ""  # 量能分析（放量/縮量，主力動向等）
    pattern_analysis: str = ""  # K線形態分析
    
    # ========== 基本面分析 ==========
    fundamental_analysis: str = ""  # 基本面綜合分析
    sector_position: str = ""  # 板塊地位和行業趨勢
    company_highlights: str = ""  # 公司亮點/風險點
    
    # ========== 情緒面/消息面分析 ==========
    news_summary: str = ""  # 近期重要新聞/公告摘要
    market_sentiment: str = ""  # 市場情緒分析
    hot_topics: str = ""  # 相關熱點話題
    
    # ========== 綜合分析 ==========
    analysis_summary: str = ""  # 綜合分析摘要
    key_points: str = ""  # 核心看點（3-5個要點）
    risk_warning: str = ""  # 風險提示
    buy_reason: str = ""  # 買入/賣出理由
    
    # ========== 元數據 ==========
    raw_response: Optional[str] = None  # 原始響應（偵錯用）
    search_performed: bool = False  # 是否執行了聯網搜尋
    data_sources: str = ""  # 數據來源說明
    success: bool = True
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return {
            'code': self.code,
            'name': self.name,
            'sentiment_score': self.sentiment_score,
            'trend_prediction': self.trend_prediction,
            'operation_advice': self.operation_advice,
            'decision_type': self.decision_type,
            'confidence_level': self.confidence_level,
            'dashboard': self.dashboard,  # 決策儀表板數據
            'trend_analysis': self.trend_analysis,
            'short_term_outlook': self.short_term_outlook,
            'medium_term_outlook': self.medium_term_outlook,
            'technical_analysis': self.technical_analysis,
            'ma_analysis': self.ma_analysis,
            'volume_analysis': self.volume_analysis,
            'pattern_analysis': self.pattern_analysis,
            'fundamental_analysis': self.fundamental_analysis,
            'sector_position': self.sector_position,
            'company_highlights': self.company_highlights,
            'news_summary': self.news_summary,
            'market_sentiment': self.market_sentiment,
            'hot_topics': self.hot_topics,
            'analysis_summary': self.analysis_summary,
            'key_points': self.key_points,
            'risk_warning': self.risk_warning,
            'buy_reason': self.buy_reason,
            'search_performed': self.search_performed,
            'success': self.success,
            'error_message': self.error_message,
        }
    
    def get_core_conclusion(self) -> str:
        """獲取核心結論（一句話）"""
        if self.dashboard and 'core_conclusion' in self.dashboard:
            return self.dashboard['core_conclusion'].get('one_sentence', self.analysis_summary)
        return self.analysis_summary
    
    def get_position_advice(self, has_position: bool = False) -> str:
        """獲取持倉建議"""
        if self.dashboard and 'core_conclusion' in self.dashboard:
            pos_advice = self.dashboard['core_conclusion'].get('position_advice', {})
            if has_position:
                return pos_advice.get('has_position', self.operation_advice)
            return pos_advice.get('no_position', self.operation_advice)
        return self.operation_advice
    
    def get_sniper_points(self) -> Dict[str, str]:
        """獲取狙擊點位"""
        if self.dashboard and 'battle_plan' in self.dashboard:
            return self.dashboard['battle_plan'].get('sniper_points', {})
        return {}
    
    def get_checklist(self) -> List[str]:
        """獲取檢查清單"""
        if self.dashboard and 'battle_plan' in self.dashboard:
            return self.dashboard['battle_plan'].get('action_checklist', [])
        return []
    
    def get_risk_alerts(self) -> List[str]:
        """獲取風險警報"""
        if self.dashboard and 'intelligence' in self.dashboard:
            return self.dashboard['intelligence'].get('risk_alerts', [])
        return []
    
    def get_emoji(self) -> str:
        """根據操作建議返回對應 emoji"""
        emoji_map = {
            '買入': '🟢',
            '加倉': '🟢',
            '強烈買入': '💚',
            '持有': '🟡',
            '觀望': '⚪',
            '減倉': '🟠',
            '賣出': '🔴',
            '強烈賣出': '❌',
        }
        return emoji_map.get(self.operation_advice, '🟡')
    
    def get_confidence_stars(self) -> str:
        """返回置信度星級"""
        star_map = {'高': '⭐⭐⭐', '中': '⭐⭐', '低': '⭐'}
        return star_map.get(self.confidence_level, '⭐⭐')


class GeminiAnalyzer:
    """
    Gemini AI 分析器
    
    職責：
    1. 調用 Google Gemini API 進行股票分析
    2. 結合預先搜尋的新聞和技術面數據生成分析報告
    3. 解析 AI 返回的 JSON 格式結果
    
    使用方式：
        analyzer = GeminiAnalyzer()
        result = analyzer.analyze(context, news_context)
    """
    
    # ========================================
    # 系統提示詞 - 決策儀表板 v2.0
    # ========================================
    # 輸出格式升級：從簡單訊號升級為決策儀表板
    # 核心模組：核心結論 + 數據透視 + 輿情情報 + 作戰計劃
    # ========================================
    
    SYSTEM_PROMPT = """你是一位專注於趨勢交易的股市投資分析師，負責生成專業的【決策儀表板】分析報告。

## 核心交易理念（必須嚴格遵守）

### 1. 嚴進策略（不追高）
- **絕對不追高**：當股價偏離 MA5 超過 5% 時，堅決不買入
- **乖離率公式**：(現價 - MA5) / MA5 × 100%
- 乖離率 < 2%：最佳買點區間
- 乖離率 2-5%：可小倉介入
- 乖離率 > 5%：嚴禁追高！直接判定為"觀望"

### 2. 趨勢交易（順勢而為）
- **多頭排列必須條件**：MA5 > MA10 > MA20
- 只做多頭排列的股票，空頭排列堅決不碰
- 均線發散上行優於均線粘合
- 趨勢強度判斷：看均線間距是否在擴大

### 3. 效率優先（籌碼結構）
- 關注籌碼集中度：90%集中度 < 15% 表示籌碼集中
- 獲利比例分析：70-90% 獲利盤時需警惕獲利回吐
- 平均成本與現價關係：現價高於平均成本 5-15% 為健康

### 4. 買點偏好（回調支撐）
- **最佳買點**：縮量回調 MA5 獲得支撐
- **次優買點**：回調 MA10 獲得支撐
- **觀望情況**：跌破 MA20 時觀望

### 5. 風險排查重點
- 減持公告（股東、高管減持）
- 業績預虧/大幅下滑
- 監管處罰/立案調查
- 行業政策利空
- 大額解禁

## 輸出格式：決策儀表板 JSON

請嚴格按照以下 JSON 格式輸出，這是一個完整的【決策儀表板】：

```json
{
    "stock_name": "股票中文名稱",
    "sentiment_score": 0-100整數,
    "trend_prediction": "強烈看多/看多/震盪/看空/強烈看空",
    "operation_advice": "買入/加倉/持有/減倉/賣出/觀望",
    "decision_type": "buy/hold/sell",
    "confidence_level": "高/中/低",

    "dashboard": {
        "core_conclusion": {
            "one_sentence": "一句話核心結論（30字以內，直接告訴用戶做什麼）",
            "signal_type": "🟢買入訊號/🟡持有觀望/🔴賣出訊號/⚠️風險警告",
            "time_sensitivity": "立即行動/今日內/本週內/不急",
            "position_advice": {
                "no_position": "空倉者建議：具體操作指引",
                "has_position": "持倉者建議：具體操作指引"
            }
        },

        "data_perspective": {
            "trend_status": {
                "ma_alignment": "均線排列狀態描述",
                "is_bullish": true/false,
                "trend_score": 0-100
            },
            "price_position": {
                "current_price": 當前價格數值,
                "ma5": MA5數值,
                "ma10": MA10數值,
                "ma20": MA20數值,
                "bias_ma5": 乖離率百分比數值,
                "bias_status": "安全/警戒/危險",
                "support_level": 支撐位價格,
                "resistance_level": 壓力位價格
            },
            "volume_analysis": {
                "volume_ratio": 量比數值,
                "volume_status": "放量/縮量/平量",
                "turnover_rate": 換手率百分比,
                "volume_meaning": "量能含義解讀（如：縮量回調表示拋壓減輕）"
            },
            "chip_structure": {
                "profit_ratio": 獲利比例,
                "avg_cost": 平均成本,
                "concentration": 籌碼集中度,
                "chip_health": "健康/一般/警惕"
            }
        },

        "intelligence": {
            "latest_news": "【最新消息】近期重要新聞摘要",
            "risk_alerts": ["風險點1：具體描述", "風險點2：具體描述"],
            "positive_catalysts": ["利好1：具體描述", "利好2：具體描述"],
            "earnings_outlook": "業績預測分析（基於年報預告、業績快報等）",
            "sentiment_summary": "輿情情緒一句話總結"
        },

        "battle_plan": {
            "sniper_points": {
                "ideal_buy": "理想買入點：XX元（在MA5附近）",
                "secondary_buy": "次優買入點：XX元（在MA10附近）",
                "stop_loss": "止損位：XX元（跌破MA20或X%）",
                "take_profit": "目標位：XX元（前高/整數關口）"
            },
            "position_strategy": {
                "suggested_position": "建議倉位：X成",
                "entry_plan": "分批建倉策略描述",
                "risk_control": "風控策略描述"
            },
            "action_checklist": [
                "✅/⚠️/❌ 檢查項1：多頭排列",
                "✅/⚠️/❌ 檢查項2：乖離率<5%",
                "✅/⚠️/❌ 檢查項3：量能配合",
                "✅/⚠️/❌ 檢查項4：無重大利空",
                "✅/⚠️/❌ 檢查項5：籌碼健康"
            ]
        }
    },

    "analysis_summary": "100字綜合分析摘要",
    "key_points": "3-5個核心看點，逗號分隔",
    "risk_warning": "風險提示",
    "buy_reason": "操作理由，引用交易理念",

    "trend_analysis": "走勢形態分析",
    "short_term_outlook": "短期1-3日展望",
    "medium_term_outlook": "中期1-2周展望",
    "technical_analysis": "技術面綜合分析",
    "ma_analysis": "均線系統分析",
    "volume_analysis": "量能分析",
    "pattern_analysis": "K線形態分析",
    "fundamental_analysis": "基本面分析",
    "sector_position": "板塊行業分析",
    "company_highlights": "公司亮點/風險",
    "news_summary": "新聞摘要",
    "market_sentiment": "市場情緒",
    "hot_topics": "相關熱點",

    "search_performed": true/false,
    "data_sources": "數據來源說明"
}
```

## 評分標準

### 強烈買入（80-100分）：
- ✅ 多頭排列：MA5 > MA10 > MA20
- ✅ 低乖離率：<2%，最佳買點
- ✅ 縮量回調或放量突破
- ✅ 籌碼集中健康
- ✅ 消息面有利好催化

### 買入（60-79分）：
- ✅ 多頭排列或弱勢多頭
- ✅ 乖離率 <5%
- ✅ 量能正常
- ⚪ 允許一項次要條件不滿足

### 觀望（40-59分）：
- ⚠️ 乖離率 >5%（追高風險）
- ⚠️ 均線纏繞趨勢不明
- ⚠️ 有風險事件

### 賣出/減倉（0-39分）：
- ❌ 空頭排列
- ❌ 跌破MA20
- ❌ 放量下跌
- ❌ 重大利空

## 決策儀表板核心原則

1. **核心結論先行**：一句話說清該買該賣
2. **分持倉建議**：空倉者和持倉者給不同建議
3. **精確狙擊點**：必須給出具體價格，不說模糊的話
4. **檢查清單可視化**：用 ✅⚠️❌ 明確顯示每項檢查結果
5. **風險優先級**：輿情中的風險點要醒目標出"""

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化 AI 分析器
        
        優先級：Gemini > OpenAI 兼容 API
        
        Args:
            api_key: Gemini API Key（可選，默認從配置讀取）
        """
        config = get_config()
        self._api_key = api_key or config.gemini_api_key
        self._model = None
        self._current_model_name = None  # 當前使用的模型名稱
        self._using_fallback = False  # 是否正在使用備選模型
        self._use_openai = False  # 是否使用 OpenAI 兼容 API
        self._openai_client = None  # OpenAI 客戶端
        
        # 檢查 Gemini API Key 是否有效（過濾佔位符）
        gemini_key_valid = self._api_key and not self._api_key.startswith('your_') and len(self._api_key) > 10
        
        # 優先嘗試初始化 Gemini
        if gemini_key_valid:
            try:
                self._init_model()
            except Exception as e:
                logger.warning(f"Gemini 初始化失敗: {e}，嘗試 OpenAI 兼容 API")
                self._init_openai_fallback()
        else:
            # Gemini Key 未配置，嘗試 OpenAI
            logger.info("Gemini API Key 未配置，嘗試使用 OpenAI 兼容 API")
            self._init_openai_fallback()
        
        # 兩者都未配置
        if not self._model and not self._openai_client:
            logger.warning("未配置任何 AI API Key，AI 分析功能將不可用")
    
    def _init_openai_fallback(self) -> None:
        """
        初始化 OpenAI 兼容 API 作為備選
        
        支持所有 OpenAI 格式的 API，包括：
        - OpenAI 官方
        - DeepSeek
        - 通義千問
        - Moonshot 等
        """
        config = get_config()
        
        # 檢查 OpenAI API Key 是否有效（過濾佔位符）
        openai_key_valid = (
            config.openai_api_key and 
            not config.openai_api_key.startswith('your_') and 
            len(config.openai_api_key) > 10
        )
        
        if not openai_key_valid:
            logger.debug("OpenAI 兼容 API 未配置或配置無效")
            return
        
        # 分離 import 和客戶端建立，以便提供更準確的錯誤資訊
        try:
            from openai import OpenAI
        except ImportError:
            logger.error("未安裝 openai 庫，請運行: pip install openai")
            return
        
        try:
            # base_url 可選，不填則使用 OpenAI 官方默認地址
            client_kwargs = {"api_key": config.openai_api_key}
            if config.openai_base_url and config.openai_base_url.startswith('http'):
                client_kwargs["base_url"] = config.openai_base_url
            
            self._openai_client = OpenAI(**client_kwargs)
            self._current_model_name = config.openai_model
            self._use_openai = True
            logger.info(f"OpenAI 兼容 API 初始化成功 (base_url: {config.openai_base_url}, model: {config.openai_model})")
        except ImportError as e:
            # 依賴缺失（如 socksio）
            if 'socksio' in str(e).lower() or 'socks' in str(e).lower():
                logger.error(f"OpenAI 客戶端需要 SOCKS 代理支持，請運行: pip install httpx[socks] 或 pip install socksio")
            else:
                logger.error(f"OpenAI 依賴缺失: {e}")
        except Exception as e:
            error_msg = str(e).lower()
            if 'socks' in error_msg or 'socksio' in error_msg or 'proxy' in error_msg:
                logger.error(f"OpenAI 代理配置錯誤: {e}，如使用 SOCKS 代理請運行: pip install httpx[socks]")
            else:
                logger.error(f"OpenAI 兼容 API 初始化失敗: {e}")
    
    def _init_model(self) -> None:
        """
        初始化 Gemini 模型
        
        配置：
        - 使用 gemini-3-flash-preview 或 gemini-2.5-flash 模型
        - 不啟用 Google Search（使用外部 Tavily/SerpAPI 搜尋）
        """
        try:
            import google.generativeai as genai
            
            # 配置 API Key
            genai.configure(api_key=self._api_key)
            
            # 從配置獲取模型名稱
            config = get_config()
            model_name = config.gemini_model
            fallback_model = config.gemini_model_fallback
            
            # 嘗試初始化主模型
            try:
                self._model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=self.SYSTEM_PROMPT,
                )
                self._current_model_name = model_name
                self._using_fallback = False
                logger.info(f"Gemini 模型初始化成功 (模型: {model_name})")
            except Exception as model_error:
                # 嘗試備選模型
                logger.warning(f"主模型 {model_name} 初始化失敗: {model_error}，嘗試備選模型 {fallback_model}")
                self._model = genai.GenerativeModel(
                    model_name=fallback_model,
                    system_instruction=self.SYSTEM_PROMPT,
                )
                self._current_model_name = fallback_model
                self._using_fallback = True
                logger.info(f"Gemini 備選模型初始化成功 (模型: {fallback_model})")
            
        except Exception as e:
            logger.error(f"Gemini 模型初始化失敗: {e}")
            self._model = None
    
    def _switch_to_fallback_model(self) -> bool:
        """
        切換到備選模型
        
        Returns:
            是否成功切換
        """
        try:
            import google.generativeai as genai
            config = get_config()
            fallback_model = config.gemini_model_fallback
            
            logger.warning(f"[LLM] 切換到備選模型: {fallback_model}")
            self._model = genai.GenerativeModel(
                model_name=fallback_model,
                system_instruction=self.SYSTEM_PROMPT,
            )
            self._current_model_name = fallback_model
            self._using_fallback = True
            logger.info(f"[LLM] 備選模型 {fallback_model} 初始化成功")
            return True
        except Exception as e:
            logger.error(f"[LLM] 切換備選模型失敗: {e}")
            return False
    
    def is_available(self) -> bool:
        """檢查分析器是否可用"""
        return self._model is not None or self._openai_client is not None
    
    def _call_openai_api(self, prompt: str, generation_config: dict) -> str:
        """
        調用 OpenAI 兼容 API
        
        Args:
            prompt: 提示詞
            generation_config: 生成配置
            
        Returns:
            響應文本
        """
        config = get_config()
        max_retries = config.gemini_max_retries
        base_delay = config.gemini_retry_delay
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    delay = base_delay * (2 ** (attempt - 1))
                    delay = min(delay, 60)
                    logger.info(f"[OpenAI] 第 {attempt + 1} 次重試，等待 {delay:.1f} 秒...")
                    time.sleep(delay)
                
                config = get_config()
                response = self._openai_client.chat.completions.create(
                    model=self._current_model_name,
                    messages=[
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=generation_config.get('temperature', config.openai_temperature),
                    max_tokens=generation_config.get('max_output_tokens', 8192),
                )
                
                if response and response.choices and response.choices[0].message.content:
                    return response.choices[0].message.content
                else:
                    raise ValueError("OpenAI API 返回空響應")
                    
            except Exception as e:
                error_str = str(e)
                is_rate_limit = '429' in error_str or 'rate' in error_str.lower() or 'quota' in error_str.lower()
                
                if is_rate_limit:
                    logger.warning(f"[OpenAI] API 限流，第 {attempt + 1}/{max_retries} 次嘗試: {error_str[:100]}")
                else:
                    logger.warning(f"[OpenAI] API 調用失敗，第 {attempt + 1}/{max_retries} 次嘗試: {error_str[:100]}")
                
                if attempt == max_retries - 1:
                    raise
        
        raise Exception("OpenAI API 調用失敗，已達最大重試次數")
    
    def _call_api_with_retry(self, prompt: str, generation_config: dict) -> str:
        """
        調用 AI API，帶有重試和模型切換機制
        
        優先級：Gemini > Gemini 備選模型 > OpenAI 兼容 API
        
        處理 429 限流錯誤：
        1. 先指數退避重試
        2. 多次失敗後切換到備選模型
        3. Gemini 完全失敗後嘗試 OpenAI
        
        Args:
            prompt: 提示詞
            generation_config: 生成配置
            
        Returns:
            響應文本
        """
        # 如果已經在使用 OpenAI 模式，直接調用 OpenAI
        if self._use_openai:
            return self._call_openai_api(prompt, generation_config)
        
        config = get_config()
        max_retries = config.gemini_max_retries
        base_delay = config.gemini_retry_delay
        
        last_error = None
        tried_fallback = getattr(self, '_using_fallback', False)
        
        for attempt in range(max_retries):
            try:
                # 請求前增加延時（防止請求過快觸發限流）
                if attempt > 0:
                    delay = base_delay * (2 ** (attempt - 1))  # 指數退避: 5, 10, 20, 40...
                    delay = min(delay, 60)  # 最大60秒
                    logger.info(f"[Gemini] 第 {attempt + 1} 次重試，等待 {delay:.1f} 秒...")
                    time.sleep(delay)
                
                response = self._model.generate_content(
                    prompt,
                    generation_config=generation_config,
                    request_options={"timeout": 120}
                )
                
                if response and response.text:
                    return response.text
                else:
                    raise ValueError("Gemini 返回空響應")
                    
            except Exception as e:
                last_error = e
                error_str = str(e)
                
                # 檢查是否是 429 限流錯誤
                is_rate_limit = '429' in error_str or 'quota' in error_str.lower() or 'rate' in error_str.lower()
                
                if is_rate_limit:
                    logger.warning(f"[Gemini] API 限流 (429)，第 {attempt + 1}/{max_retries} 次嘗試: {error_str[:100]}")
                    
                    # 如果已經重試了一半次數且還沒切換過備選模型，嘗試切換
                    if attempt >= max_retries // 2 and not tried_fallback:
                        if self._switch_to_fallback_model():
                            tried_fallback = True
                            logger.info("[Gemini] 已切換到備選模型，繼續重試")
                        else:
                            logger.warning("[Gemini] 切換備選模型失敗，繼續使用當前模型重試")
                else:
                    # 非限流錯誤，記錄並繼續重試
                    logger.warning(f"[Gemini] API 調用失敗，第 {attempt + 1}/{max_retries} 次嘗試: {error_str[:100]}")
        
        # Gemini 所有重試都失敗，嘗試 OpenAI 兼容 API
        if self._openai_client:
            logger.warning("[Gemini] 所有重試失敗，切換到 OpenAI 兼容 API")
            try:
                return self._call_openai_api(prompt, generation_config)
            except Exception as openai_error:
                logger.error(f"[OpenAI] 備選 API 也失敗: {openai_error}")
                raise last_error or openai_error
        elif config.openai_api_key and config.openai_base_url:
            # 嘗試懶加載初始化 OpenAI
            logger.warning("[Gemini] 所有重試失敗，嘗試初始化 OpenAI 兼容 API")
            self._init_openai_fallback()
            if self._openai_client:
                try:
                    return self._call_openai_api(prompt, generation_config)
                except Exception as openai_error:
                    logger.error(f"[OpenAI] 備選 API 也失敗: {openai_error}")
                    raise last_error or openai_error
        
        # 所有方式都失敗
        raise last_error or Exception("所有 AI API 調用失敗，已達最大重試次數")
    
    def analyze(
        self, 
        context: Dict[str, Any],
        news_context: Optional[str] = None
    ) -> AnalysisResult:
        """
        分析單隻股票
        
        流程：
        1. 格式化輸入數據（技術面 + 新聞）
        2. 調用 Gemini API（帶重試和模型切換）
        3. 解析 JSON 響應
        4. 返回結構化結果
        
        Args:
            context: 從 storage.get_analysis_context() 獲取的上下文數據
            news_context: 預先搜尋的新聞內容（可選）
            
        Returns:
            AnalysisResult 對象
        """
        code = context.get('code', 'Unknown')
        config = get_config()
        
        # 請求前增加延時（防止連續請求觸發限流）
        request_delay = config.gemini_request_delay
        if request_delay > 0:
            logger.debug(f"[LLM] 請求前等待 {request_delay:.1f} 秒...")
            time.sleep(request_delay)
        
        # 優先從上下文中獲取股票名稱（由 main.py 傳入）
        name = context.get('stock_name')
        if not name or name.startswith('股票'):
            # 備選：從 realtime 中獲取
            if 'realtime' in context and context['realtime'].get('name'):
                name = context['realtime']['name']
            else:
                # 最後從映射表獲取
                name = STOCK_NAME_MAP.get(code, f'股票{code}')
        
        # 如果模型不可用，返回默認結果
        if not self.is_available():
            return AnalysisResult(
                code=code,
                name=name,
                sentiment_score=50,
                trend_prediction='震盪',
                operation_advice='持有',
                confidence_level='低',
                analysis_summary='AI 分析功能未啟用（未配置 API Key）',
                risk_warning='請配置 Gemini API Key 後重試',
                success=False,
                error_message='Gemini API Key 未配置',
            )
        
        try:
            # 格式化輸入（包含技術面數據和新聞）
            prompt = self._format_prompt(context, name, news_context)
            
            # 獲取模型名稱
            model_name = getattr(self, '_current_model_name', None)
            if not model_name:
                model_name = getattr(self._model, '_model_name', 'unknown')
                if hasattr(self._model, 'model_name'):
                    model_name = self._model.model_name
            
            logger.info(f"========== AI 分析 {name}({code}) ==========")
            logger.info(f"[LLM配置] 模型: {model_name}")
            logger.info(f"[LLM配置] Prompt 長度: {len(prompt)} 字符")
            logger.info(f"[LLM配置] 是否包含新聞: {'是' if news_context else '否'}")
            
            # 記錄完整 prompt 到日誌（INFO級別記錄摘要，DEBUG記錄完整）
            prompt_preview = prompt[:500] + "..." if len(prompt) > 500 else prompt
            logger.info(f"[LLM Prompt 預覽]\n{prompt_preview}")
            logger.debug(f"=== 完整 Prompt ({len(prompt)}字符) ===\n{prompt}\n=== End Prompt ===")

            # 設置生成配置（從配置文件讀取溫度參數）
            config = get_config()
            generation_config = {
                "temperature": config.gemini_temperature,
                "max_output_tokens": 8192,
            }

            # 根據實際使用的 API 顯示日誌
            api_provider = "OpenAI" if self._use_openai else "Gemini"
            logger.info(f"[LLM調用] 開始調用 {api_provider} API...")
            
            # 使用帶重試的 API 調用
            start_time = time.time()
            response_text = self._call_api_with_retry(prompt, generation_config)
            elapsed = time.time() - start_time

            # 記錄響應資訊
            logger.info(f"[LLM返回] {api_provider} API 響應成功, 耗時 {elapsed:.2f}s, 響應長度 {len(response_text)} 字符")
            
            # 記錄響應預覽（INFO級別）和完整響應（DEBUG級別）
            response_preview = response_text[:300] + "..." if len(response_text) > 300 else response_text
            logger.info(f"[LLM返回 預覽]\n{response_preview}")
            logger.debug(f"=== {api_provider} 完整響應 ({len(response_text)}字符) ===\n{response_text}\n=== End Response ===")
            
            # 解析響應
            result = self._parse_response(response_text, code, name)
            result.raw_response = response_text
            result.search_performed = bool(news_context)
            
            logger.info(f"[LLM解析] {name}({code}) 分析完成: {result.trend_prediction}, 評分 {result.sentiment_score}")
            
            return result
            
        except Exception as e:
            logger.error(f"AI 分析 {name}({code}) 失敗: {e}")
            return AnalysisResult(
                code=code,
                name=name,
                sentiment_score=50,
                trend_prediction='震盪',
                operation_advice='持有',
                confidence_level='低',
                analysis_summary=f'分析過程出錯: {str(e)[:100]}',
                risk_warning='分析失敗，請稍後重試或手動分析',
                success=False,
                error_message=str(e),
            )
    
    def _format_prompt(
        self, 
        context: Dict[str, Any], 
        name: str,
        news_context: Optional[str] = None
    ) -> str:
        """
        格式化分析提示詞（決策儀表板 v2.0）
        
        包含：技術指標、即時行情（量比/換手率）、籌碼分佈、趨勢分析、新聞
        
        Args:
            context: 技術面數據上下文（包含增強數據）
            name: 股票名稱（默認值，可能被上下文覆蓋）
            news_context: 預先搜尋的新聞內容
        """
        code = context.get('code', 'Unknown')
        
        # 優先使用上下文中的股票名稱（從 realtime_quote 獲取）
        stock_name = context.get('stock_name', name)
        if not stock_name or stock_name == f'股票{code}':
            stock_name = STOCK_NAME_MAP.get(code, f'股票{code}')
            
        today = context.get('today', {})
        
        # ========== 建置決策儀表板格式的輸入 ==========
        prompt = f"""# 決策儀表板分析請求

## 📊 股票基礎資訊
| 項目 | 數據 |
|------|------|
| 股票代碼 | **{code}** |
| 股票名稱 | **{stock_name}** |
| 分析日期 | {context.get('date', '未知')} |

---

## 📈 技術面數據

### 今日行情
| 指標 | 數值 |
|------|------|
| 收盤價 | {today.get('close', 'N/A')} 元 |
| 開盤價 | {today.get('open', 'N/A')} 元 |
| 最高價 | {today.get('high', 'N/A')} 元 |
| 最低價 | {today.get('low', 'N/A')} 元 |
| 漲跌幅 | {today.get('pct_chg', 'N/A')}% |
| 成交量 | {self._format_volume(today.get('volume'))} |
| 成交額 | {self._format_amount(today.get('amount'))} |

### 均線系統（關鍵判斷指標）
| 均線 | 數值 | 說明 |
|------|------|------|
| MA5 | {today.get('ma5', 'N/A')} | 短期趨勢線 |
| MA10 | {today.get('ma10', 'N/A')} | 中短期趨勢線 |
| MA20 | {today.get('ma20', 'N/A')} | 中期趨勢線 |
| 均線形態 | {context.get('ma_status', '未知')} | 多頭/空頭/纏繞 |
"""
        
        # 添加即時行情數據（量比、換手率等）
        if 'realtime' in context:
            rt = context['realtime']
            prompt += f"""
### 即時行情增強數據
| 指標 | 數值 | 解讀 |
|------|------|------|
| 當前價格 | {rt.get('price', 'N/A')} 元 | |
| **量比** | **{rt.get('volume_ratio', 'N/A')}** | {rt.get('volume_ratio_desc', '')} |
| **換手率** | **{rt.get('turnover_rate', 'N/A')}%** | |
| 市盈率(動態) | {rt.get('pe_ratio', 'N/A')} | |
| 市淨率 | {rt.get('pb_ratio', 'N/A')} | |
| 總市值 | {self._format_amount(rt.get('total_mv'))} | |
| 流通市值 | {self._format_amount(rt.get('circ_mv'))} | |
| 60日漲跌幅 | {rt.get('change_60d', 'N/A')}% | 中期表現 |
"""
        
        # 添加籌碼分佈數據
        if 'chip' in context:
            chip = context['chip']
            profit_ratio = chip.get('profit_ratio', 0)
            prompt += f"""
### 籌碼分佈數據（效率指標）
| 指標 | 數值 | 健康標準 |
|------|------|----------|
| **獲利比例** | **{profit_ratio:.1%}** | 70-90%時警惕 |
| 平均成本 | {chip.get('avg_cost', 'N/A')} 元 | 現價應高於5-15% |
| 90%籌碼集中度 | {chip.get('concentration_90', 0):.2%} | <15%為集中 |
| 70%籌碼集中度 | {chip.get('concentration_70', 0):.2%} | |
| 籌碼狀態 | {chip.get('chip_status', '未知')} | |
"""
    
    # 添加台灣股票特有數據
    if today.get('foreign_buy') is not None and today.get('foreign_buy') != 0:
        prompt += f"""
### 🇹🇼 台灣市場特有籌碼數據
| 指標 | 數值 | 單位 |
|------|------|------|
| 外資買賣超 | {today.get('foreign_buy'):,.0f} | 股 |
| 投信買賣超 | {today.get('it_buy'):,.0f} | 股 |
| 自營商買賣超 | {today.get('dealers_buy'):,.0f} | 股 |
| 融資買賣 | {today.get('margin_buy'):,.0f} | 股 |
| 融券買賣 | {today.get('short_buy'):,.0f} | 股 |
| 營收年增率 | {today.get('revenue_yoy'):.2f} | % |
"""
        
        # 添加趨勢分析結果（基於交易理念的預判）
        if 'trend_analysis' in context:
            trend = context['trend_analysis']
            bias_warning = "🚨 超過5%，嚴禁追高！" if trend.get('bias_ma5', 0) > 5 else "✅ 安全範圍"
            prompt += f"""
### 趨勢分析預判（基於交易理念）
| 指標 | 數值 | 判定 |
|------|------|------|
| 趨勢狀態 | {trend.get('trend_status', '未知')} | |
| 均線排列 | {trend.get('ma_alignment', '未知')} | MA5>MA10>MA20為多頭 |
| 趨勢強度 | {trend.get('trend_strength', 0)}/100 | |
| **乖離率(MA5)** | **{trend.get('bias_ma5', 0):+.2f}%** | {bias_warning} |
| 乖離率(MA10) | {trend.get('bias_ma10', 0):+.2f}% | |
| 量能狀態 | {trend.get('volume_status', '未知')} | {trend.get('volume_trend', '')} |
| 系統訊號 | {trend.get('buy_signal', '未知')} | |
| 系統評分 | {trend.get('signal_score', 0)}/100 | |

#### 系統分析理由
**買入理由**：
{chr(10).join('- ' + r for r in trend.get('signal_reasons', ['無'])) if trend.get('signal_reasons') else '- 無'}

**風險因素**：
{chr(10).join('- ' + r for r in trend.get('risk_factors', ['無'])) if trend.get('risk_factors') else '- 無'}
"""
        
        # 添加昨日對比數據
        if 'yesterday' in context:
            volume_change = context.get('volume_change_ratio', 'N/A')
            prompt += f"""
### 量價變化
- 成交量較昨日變化：{volume_change}倍
- 價格較昨日變化：{context.get('price_change_ratio', 'N/A')}%
"""
        
        # 添加新聞搜尋結果（重點區域）
        prompt += """
---

## 📰 輿情情報
"""
        if news_context:
            prompt += f"""
以下是 **{stock_name}({code})** 近7日的新聞搜尋結果，請重點提取：
1. 🚨 **風險警報**：減持、處罰、利空
2. 🎯 **利好催化**：業績、合同、政策
3. 📊 **業績預期**：年報預告、業績快報

```
{news_context}
```
"""
        else:
            prompt += """
未搜尋到該股票近期的相關新聞。請主要依據技術面數據進行分析。
"""

        # 注入缺失數據警告
        if context.get('data_missing'):
            prompt += """
⚠️ **數據缺失警告**
由於介面限制，當前無法獲取完整的即時行情和技術指標數據。
請 **忽略上述表格中的 N/A 數據**，重點依據 **【📰 輿情情報】** 中的新聞進行基本面和情緒面分析。
在回答技術面問題（如均線、乖離率）時，請直接說明「數據缺失，無法判斷」，**嚴禁編造數據**。
"""
        
        # 明確的輸出要求
        prompt += f"""
---

## ✅ 分析任務

請為 **{stock_name}({code})** 生成【決策儀表板】，嚴格按照 JSON 格式輸出。

### ⚠️ 重要：股票名稱確認
如果上方顯示的股票名稱為"股票{code}"或不正確，請在分析開頭**明確輸出該股票的正確中文全稱**。

### 重點關注（必須明確回答）：
1. ❓ 是否滿足 MA5>MA10>MA20 多頭排列？
2. ❓ 當前乖離率是否在安全範圍內（<5%）？—— 超過5%必須標注"嚴禁追高"
3. ❓ 量能是否配合（縮量回調/放量突破）？
4. ❓ 籌碼結構是否健康？
5. ❓ 消息面有無重大利空？（減持、處罰、業績變臉等）

### 決策儀表板要求：
- **股票名稱**：必須輸出正確的中文全稱（如"貴州茅台"而非"股票600519"）
- **核心結論**：一句話說清該買/該賣/該等
- **持倉分類建議**：空倉者怎麼做 vs 持倉者怎麼做
- **具體狙擊點位**：買入價、止損價、目標價（精確到分）
- **檢查清單**：每項用 ✅/⚠️/❌ 標記

請輸出完整的 JSON 格式決策儀表板。"""
        
        return prompt
    
    def _format_volume(self, volume: Optional[float]) -> str:
        """格式化成交量顯示"""
        if volume is None:
            return 'N/A'
        if volume >= 1e8:
            return f"{volume / 1e8:.2f} 億股"
        elif volume >= 1e4:
            return f"{volume / 1e4:.2f} 萬股"
        else:
            return f"{volume:.0f} 股"
    
    def _format_amount(self, amount: Optional[float]) -> str:
        """格式化成交額顯示"""
        if amount is None:
            return 'N/A'
        if amount >= 1e8:
            return f"{amount / 1e8:.2f} 億元"
        elif amount >= 1e4:
            return f"{amount / 1e4:.2f} 萬元"
        else:
            return f"{amount:.0f} 元"
    
    def _parse_response(
        self, 
        response_text: str, 
        code: str, 
        name: str
    ) -> AnalysisResult:
        """
        解析 Gemini 響應（決策儀表板版）
        
        嘗試從響應中提取 JSON 格式的分析結果，包含 dashboard 欄位
        如果解析失敗，嘗試智能提取或返回默認結果
        """
        try:
            # 清理響應文本：移除 markdown 程式碼塊標記
            cleaned_text = response_text
            if '```json' in cleaned_text:
                cleaned_text = cleaned_text.replace('```json', '').replace('```', '')
            elif '```' in cleaned_text:
                cleaned_text = cleaned_text.replace('```', '')
            
            # 嘗試找到 JSON 內容
            json_start = cleaned_text.find('{')
            json_end = cleaned_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = cleaned_text[json_start:json_end]
                
                # 嘗試修復常見的 JSON 問題
                json_str = self._fix_json_string(json_str)
                
                data = json.loads(json_str)
                
                # 提取 dashboard 數據
                dashboard = data.get('dashboard', None)

                # 優先使用 AI 返回的股票名稱（如果原名稱無效或包含代碼）
                ai_stock_name = data.get('stock_name')
                if ai_stock_name and (name.startswith('股票') or name == code or 'Unknown' in name):
                    name = ai_stock_name

                # 解析所有欄位，使用默認值防止缺失
                # 解析 decision_type，如果沒有則根據 operation_advice 推斷
                decision_type = data.get('decision_type', '')
                if not decision_type:
                    op = data.get('operation_advice', '持有')
                    if op in ['買入', '加倉', '強烈買入']:
                        decision_type = 'buy'
                    elif op in ['賣出', '減倉', '強烈賣出']:
                        decision_type = 'sell'
                    else:
                        decision_type = 'hold'
                
                return AnalysisResult(
                    code=code,
                    name=name,
                    # 核心指標
                    sentiment_score=int(data.get('sentiment_score', 50)),
                    trend_prediction=data.get('trend_prediction', '震盪'),
                    operation_advice=data.get('operation_advice', '持有'),
                    decision_type=decision_type,
                    confidence_level=data.get('confidence_level', '中'),
                    # 決策儀表板
                    dashboard=dashboard,
                    # 走勢分析
                    trend_analysis=data.get('trend_analysis', ''),
                    short_term_outlook=data.get('short_term_outlook', ''),
                    medium_term_outlook=data.get('medium_term_outlook', ''),
                    # 技術面
                    technical_analysis=data.get('technical_analysis', ''),
                    ma_analysis=data.get('ma_analysis', ''),
                    volume_analysis=data.get('volume_analysis', ''),
                    pattern_analysis=data.get('pattern_analysis', ''),
                    # 基本面
                    fundamental_analysis=data.get('fundamental_analysis', ''),
                    sector_position=data.get('sector_position', ''),
                    company_highlights=data.get('company_highlights', ''),
                    # 情緒面/消息面
                    news_summary=data.get('news_summary', ''),
                    market_sentiment=data.get('market_sentiment', ''),
                    hot_topics=data.get('hot_topics', ''),
                    # 綜合
                    analysis_summary=data.get('analysis_summary', '分析完成'),
                    key_points=data.get('key_points', ''),
                    risk_warning=data.get('risk_warning', ''),
                    buy_reason=data.get('buy_reason', ''),
                    # 元數據
                    search_performed=data.get('search_performed', False),
                    data_sources=data.get('data_sources', '技術面數據'),
                    success=True,
                )
            else:
                # 沒有找到 JSON，嘗試從純文本中提取資訊
                logger.warning(f"無法從響應中提取 JSON，使用原始文本分析")
                return self._parse_text_response(response_text, code, name)
                
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失敗: {e}，嘗試從文本提取")
            return self._parse_text_response(response_text, code, name)
    
    def _fix_json_string(self, json_str: str) -> str:
        """修復常見的 JSON 格式問題"""
        import re
        
        # 移除注釋
        json_str = re.sub(r'//.*?\n', '\n', json_str)
        json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
        
        # 修復尾隨逗號
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        
        # 確保布爾值是小寫
        json_str = json_str.replace('True', 'true').replace('False', 'false')
        
        # fix by json-repair
        json_str = repair_json(json_str)
        
        return json_str
    
    def _parse_text_response(
        self, 
        response_text: str, 
        code: str, 
        name: str
    ) -> AnalysisResult:
        """從純文本響應中盡可能提取分析資訊"""
        # 嘗試識別關鍵詞來判斷情緒
        sentiment_score = 50
        trend = '震盪'
        advice = '持有'
        
        text_lower = response_text.lower()
        
        # 簡單的情緒識別
        positive_keywords = ['看多', '買入', '上漲', '突破', '強勢', '利好', '加倉', 'bullish', 'buy']
        negative_keywords = ['看空', '賣出', '下跌', '跌破', '弱勢', '利空', '減倉', 'bearish', 'sell']
        
        positive_count = sum(1 for kw in positive_keywords if kw in text_lower)
        negative_count = sum(1 for kw in negative_keywords if kw in text_lower)
        
        if positive_count > negative_count + 1:
            sentiment_score = 65
            trend = '看多'
            advice = '買入'
            decision_type = 'buy'
        elif negative_count > positive_count + 1:
            sentiment_score = 35
            trend = '看空'
            advice = '賣出'
            decision_type = 'sell'
        else:
            decision_type = 'hold'
        
        # 截取前500字符作為摘要
        summary = response_text[:500] if response_text else '無分析結果'
        
        return AnalysisResult(
            code=code,
            name=name,
            sentiment_score=sentiment_score,
            trend_prediction=trend,
            operation_advice=advice,
            decision_type=decision_type,
            confidence_level='低',
            analysis_summary=summary,
            key_points='JSON解析失敗，僅供參考',
            risk_warning='分析結果可能不準確，建議結合其他資訊判斷',
            raw_response=response_text,
            success=True,
        )
    
    def batch_analyze(
        self, 
        contexts: List[Dict[str, Any]],
        delay_between: float = 2.0
    ) -> List[AnalysisResult]:
        """
        批量分析多隻股票
        
        注意：為避免 API 速率限制，每次分析之間會有延遲
        
        Args:
            contexts: 上下文數據列表
            delay_between: 每次分析之間的延遲（秒）
            
        Returns:
            AnalysisResult 列表
        """
        results = []
        
        for i, context in enumerate(contexts):
            if i > 0:
                logger.debug(f"等待 {delay_between} 秒後繼續...")
                time.sleep(delay_between)
            
            result = self.analyze(context)
            results.append(result)
        
        return results


# 高效能函數
def get_analyzer() -> GeminiAnalyzer:
    """獲取 Gemini 分析器實例"""
    return GeminiAnalyzer()


if __name__ == "__main__":
    # 測試程式碼
    logging.basicConfig(level=logging.DEBUG)
    
    # 模擬上下文數據
    test_context = {
        'code': '600519',
        'date': '2026-01-09',
        'today': {
            'open': 1800.0,
            'high': 1850.0,
            'low': 1780.0,
            'close': 1820.0,
            'volume': 10000000,
            'amount': 18200000000,
            'pct_chg': 1.5,
            'ma5': 1810.0,
            'ma10': 1800.0,
            'ma20': 1790.0,
            'volume_ratio': 1.2,
        },
        'ma_status': '多頭排列 📈',
        'volume_change_ratio': 1.3,
        'price_change_ratio': 1.5,
    }
    
    analyzer = GeminiAnalyzer()
    
    if analyzer.is_available():
        print("=== AI 分析測試 ===")
        result = analyzer.analyze(test_context)
        print(f"分析結果: {result.to_dict()}")
    else:
        print("Gemini API 未配置，跳過測試")
