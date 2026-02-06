# -*- coding: utf-8 -*-
"""
===================================
A股自選股智能分析系統 - 核心分析流水線
===================================

職責：
1. 管理整個分析流程
2. 協調數據獲取、存儲、搜索、分析、通知等模組
3. 實現併發控制和異常處理
4. 提供股票分析的核心功能
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import List, Dict, Any, Optional, Tuple

from src.config import get_config, Config
from src.storage import get_db
from data_provider import DataFetcherManager
from data_provider.realtime_types import ChipDistribution
from src.analyzer import GeminiAnalyzer, AnalysisResult, STOCK_NAME_MAP
from src.notification import NotificationService, NotificationChannel
from src.search_service import SearchService
from src.enums import ReportType
from src.stock_analyzer import StockTrendAnalyzer, TrendAnalysisResult
from bot.models import BotMessage


logger = logging.getLogger(__name__)


class StockAnalysisPipeline:
    """
    股票分析主流程調度器
    
    職責：
    1. 管理整個分析流程
    2. 協調數據獲取、存儲、搜索、分析、通知等模組
    3. 實現併發控制和異常處理
    """
    
    def __init__(
        self,
        config: Optional[Config] = None,
        max_workers: Optional[int] = None,
        source_message: Optional[BotMessage] = None,
        query_id: Optional[str] = None,
        query_source: Optional[str] = None,
        save_context_snapshot: Optional[bool] = None
    ):
        """
        初始化調度器
        
        Args:
            config: 配置物件（可選，默認使用全域配置）
            max_workers: 最大併發執行緒數（可選，默認從配置讀取）
        """
        self.config = config or get_config()
        self.max_workers = max_workers or self.config.max_workers
        self.source_message = source_message
        self.query_id = query_id
        self.query_source = self._resolve_query_source(query_source)
        self.save_context_snapshot = (
            self.config.save_context_snapshot if save_context_snapshot is None else save_context_snapshot
        )
        
        # 初始化各模組
        self.db = get_db()
        self.fetcher_manager = DataFetcherManager()
        # 不再單獨建立 akshare_fetcher，統一使用 fetcher_manager 獲取增強數據
        self.trend_analyzer = StockTrendAnalyzer()  # 趨勢分析器
        self.analyzer = GeminiAnalyzer()
        self.notifier = NotificationService(source_message=source_message)
        
        # 初始化搜尋服務
        self.search_service = SearchService(
            bocha_keys=self.config.bocha_api_keys,
            tavily_keys=self.config.tavily_api_keys,
            serpapi_keys=self.config.serpapi_keys,
        )
        
        logger.info(f"調度器初始化完成，最大併發數: {self.max_workers}")
        logger.info("已啟用趨勢分析器 (MA5>MA10>MA20 多頭判斷)")
        # 打印即時行情/籌碼配置狀態
        if self.config.enable_realtime_quote:
            logger.info(f"即時行情已啟用 (優先級: {self.config.realtime_source_priority})")
        else:
            logger.info("即時行情已禁用，將使用歷史收盤價")
        if self.config.enable_chip_distribution:
            logger.info("籌碼分佈分析已啟用")
        else:
            logger.info("籌碼分佈分析已禁用")
        if self.search_service.is_available:
            logger.info("搜尋服務已啟用 (Tavily/SerpAPI)")
        else:
            logger.warning("搜尋服務未啟用（未配置 API Key）")
    
    def fetch_and_save_stock_data(
        self, 
        code: str,
        force_refresh: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        獲取並保存單隻股票數據
        
        斷點續傳邏輯：
        1. 檢查資料庫是否已有今日數據
        2. 如果有且不強制刷新，則跳過網路請求
        3. 否則從數據源獲取並保存
        
        Args:
            code: 股票代碼
            force_refresh: 是否強制刷新（忽略本地快取）
            
        Returns:
            Tuple[是否成功, 錯誤資訊]
        """
        try:
            today = date.today()
            
            # 斷點續傳檢查：如果今日數據已存在，跳過
            if not force_refresh and self.db.has_today_data(code, today):
                logger.info(f"[{code}] 今日數據已存在，跳過獲取（斷點續傳）")
                return True, None
            
            # 從數據源獲取數據
            logger.info(f"[{code}] 開始從數據源獲取數據...")
            df, source_name = self.fetcher_manager.get_daily_data(code, days=30)
            
            if df is None or df.empty:
                return False, "獲取數據為空"
            
            # 保存到資料庫
            saved_count = self.db.save_daily_data(df, code, source_name)
            logger.info(f"[{code}] 數據保存成功（來源: {source_name}，新增 {saved_count} 條）")
            
            return True, None
            
        except Exception as e:
            error_msg = f"獲取/保存數據失敗: {str(e)}"
            logger.error(f"[{code}] {error_msg}")
            return False, error_msg
    
    def analyze_stock(self, code: str, report_type: ReportType) -> Optional[AnalysisResult]:
        """
        分析單隻股票（增強版：含量比、換手率、籌碼分析、多維度情報）
        
        流程：
        1. 獲取即時行情（量比、換手率）- 通過 DataFetcherManager 自動故障切換
        2. 獲取籌碼分佈 - 通過 DataFetcherManager 帶熔斷保護
        3. 進行趨勢分析（基於交易理念）
        4. 多維度情報搜尋（最新消息+風險排查+業績預期）
        5. 從資料庫獲取分析上下文
        6. 調用 AI 進行綜合分析
        
        Args:
            code: 股票代碼
            report_type: 報告類型
            
        Returns:
            AnalysisResult 或 None（如果分析失敗）
        """
        try:
            # 獲取股票名稱（優先從即時行情獲取真實名稱）
            stock_name = STOCK_NAME_MAP.get(code, '')
            
            # Step 1: 獲取即時行情（量比、換手率等）- 使用統一入口，自動故障切換
            realtime_quote = None
            try:
                realtime_quote = self.fetcher_manager.get_realtime_quote(code)
                if realtime_quote:
                    # 使用即時行情返回的真實股票名稱
                    if realtime_quote.name:
                        stock_name = realtime_quote.name
                    
                    # 獲取英文名稱（用於搜尋補強）
                    english_name = getattr(realtime_quote, 'english_name', None)
                    
                    # 相容不同數據源的欄位（有些數據源可能沒有 volume_ratio）
                    volume_ratio = getattr(realtime_quote, 'volume_ratio', None)
                    turnover_rate = getattr(realtime_quote, 'turnover_rate', None)
                    logger.info(f"[{code}] {stock_name}({english_name}) 即時行情: 價格={realtime_quote.price}, "
                              f"量比={volume_ratio}, 換手率={turnover_rate}% "
                              f"(來源: {realtime_quote.source.value if hasattr(realtime_quote, 'source') else 'unknown'})")
                else:
                    logger.info(f"[{code}] 即時行情獲取失敗或已禁用，將使用歷史數據進行分析")
            except Exception as e:
                logger.warning(f"[{code}] 獲取即時行情失敗: {e}")
                english_name = None
            
            # 如果還是沒有名稱，使用代碼作為名稱
            if not stock_name:
                stock_name = f'股票{code}'
            
            # Step 2: 獲取籌碼分佈 - 使用統一入口，帶熔斷保護
            chip_data = None
            try:
                chip_data = self.fetcher_manager.get_chip_distribution(code)
                if chip_data:
                    logger.info(f"[{code}] 籌碼分佈: 獲利比例={chip_data.profit_ratio:.1%}, "
                              f"90%集中度={chip_data.concentration_90:.2%}")
                else:
                    logger.debug(f"[{code}] 籌碼分佈獲取失敗或已禁用")
            except Exception as e:
                logger.warning(f"[{code}] 獲取籌碼分佈失敗: {e}")
            
            # Step 3: 趨勢分析（基於交易理念）
            trend_result: Optional[TrendAnalysisResult] = None
            try:
                # 獲取歷史數據進行趨勢分析
                context = self.db.get_analysis_context(code)
                if context and 'raw_data' in context:
                    import pandas as pd
                    raw_data = context['raw_data']
                    if isinstance(raw_data, list) and len(raw_data) > 0:
                        df = pd.DataFrame(raw_data)
                        trend_result = self.trend_analyzer.analyze(df, code)
                        logger.info(f"[{code}] 趨勢分析: {trend_result.trend_status.value}, "
                                  f"買入信號={trend_result.buy_signal.value}, 評分={trend_result.signal_score}")
            except Exception as e:
                logger.warning(f"[{code}] 趨勢分析失敗: {e}")
            
            # Step 4: 多維度情報搜尋（最新消息+風險排查+業績預期）
            news_context = None
            if self.search_service.is_available:
                logger.info(f"[{code}] 開始多維度情報搜尋...")
                
                # 使用多維度搜尋（最多5次搜尋）
                intel_results = self.search_service.search_comprehensive_intel(
                    stock_code=code,
                    stock_name=stock_name,
                    english_name=english_name,
                    max_searches=5
                )
                
                # 格式化情報報告
                if intel_results:
                    news_context = self.search_service.format_intel_report(intel_results, stock_name)
                    total_results = sum(
                        len(r.results) for r in intel_results.values() if r.success
                    )
                    logger.info(f"[{code}] 情報搜尋完成: 共 {total_results} 條結果")
                    logger.debug(f"[{code}] 情報搜尋結果:\n{news_context}")

                    # 保存新聞情報到資料庫（用於後續複盤與查詢）
                    try:
                        query_context = self._build_query_context()
                        for dim_name, response in intel_results.items():
                            if response and response.success and response.results:
                                self.db.save_news_intel(
                                    code=code,
                                    name=stock_name,
                                    dimension=dim_name,
                                    query=response.query,
                                    response=response,
                                    query_context=query_context
                                )
                    except Exception as e:
                        logger.warning(f"[{code}] 保存新聞情報失敗: {e}")
            else:
                logger.info(f"[{code}] 搜尋服務不可用，跳過情報搜尋")
            
            # Step 5: 獲取分析上下文（技術面數據）
            context = self.db.get_analysis_context(code)
            
            if context is None:
                logger.warning(f"[{code}] 無法獲取歷史行情數據，將僅基於新聞和即時行情分析")
                from datetime import date
                context = {
                    'code': code,
                    'stock_name': stock_name,
                    'date': date.today().isoformat(),
                    'data_missing': True,
                    'today': {},
                    'yesterday': {}
                }
            
            # Step 6: 增強上下文數據（添加即時行情、籌碼、趨勢分析結果、股票名稱）
            enhanced_context = self._enhance_context(
                context, 
                realtime_quote, 
                chip_data, 
                trend_result,
                stock_name  # 傳入股票名稱
            )
            
            # Step 7: 調用 AI 分析（傳入增強的上下文和新聞）
            result = self.analyzer.analyze(enhanced_context, news_context=news_context)

            # Step 8: 保存分析歷史記錄
            if result:
                try:
                    context_snapshot = self._build_context_snapshot(
                        enhanced_context=enhanced_context,
                        news_content=news_context,
                        realtime_quote=realtime_quote,
                        chip_data=chip_data
                    )
                    self.db.save_analysis_history(
                        result=result,
                        query_id=self.query_id or "",
                        report_type=report_type.value,
                        news_content=news_context,
                        context_snapshot=context_snapshot,
                        save_snapshot=self.save_context_snapshot
                    )
                except Exception as e:
                    logger.warning(f"[{code}] 保存分析歷史失敗: {e}")

            return result
            
        except Exception as e:
            logger.error(f"[{code}] 分析失敗: {e}")
            logger.exception(f"[{code}] 詳細錯誤資訊:")
            return None
    
    def _enhance_context(
        self,
        context: Dict[str, Any],
        realtime_quote,
        chip_data: Optional[ChipDistribution],
        trend_result: Optional[TrendAnalysisResult],
        stock_name: str = ""
    ) -> Dict[str, Any]:
        """
        增強分析上下文
        
        將即時行情、籌碼分佈、趨勢分析結果、股票名稱添加到上下文中
        
        Args:
            context: 原始上下文
            realtime_quote: 即時行情數據（UnifiedRealtimeQuote 或 None）
            chip_data: 籌碼分佈數據
            trend_result: 趨勢分析結果
            stock_name: 股票名稱
            
        Returns:
            增強後的上下文
        """
        enhanced = context.copy()
        
        # 添加股票名稱
        if stock_name:
            enhanced['stock_name'] = stock_name
        elif realtime_quote and getattr(realtime_quote, 'name', None):
            enhanced['stock_name'] = realtime_quote.name
        
        # 添加即時行情（相容不同數據源的欄位差異）
        if realtime_quote:
            # 使用 getattr 安全獲取欄位，缺失欄位返回 None 或默認值
            volume_ratio = getattr(realtime_quote, 'volume_ratio', None)
            enhanced['realtime'] = {
                'name': getattr(realtime_quote, 'name', ''),
                'price': getattr(realtime_quote, 'price', None),
                'volume_ratio': volume_ratio,
                'volume_ratio_desc': self._describe_volume_ratio(volume_ratio) if volume_ratio else '無數據',
                'turnover_rate': getattr(realtime_quote, 'turnover_rate', None),
                'pe_ratio': getattr(realtime_quote, 'pe_ratio', None),
                'pb_ratio': getattr(realtime_quote, 'pb_ratio', None),
                'total_mv': getattr(realtime_quote, 'total_mv', None),
                'circ_mv': getattr(realtime_quote, 'circ_mv', None),
                'change_60d': getattr(realtime_quote, 'change_60d', None),
                'source': getattr(realtime_quote, 'source', None),
            }
            # 移除 None 值以減少上下文大小
            enhanced['realtime'] = {k: v for k, v in enhanced['realtime'].items() if v is not None}
        
        # 添加籌碼分佈
        if chip_data:
            current_price = getattr(realtime_quote, 'price', 0) if realtime_quote else 0
            enhanced['chip'] = {
                'profit_ratio': chip_data.profit_ratio,
                'avg_cost': chip_data.avg_cost,
                'concentration_90': chip_data.concentration_90,
                'concentration_70': chip_data.concentration_70,
                'chip_status': chip_data.get_chip_status(current_price or 0),
            }
        
        # 添加趨勢分析結果
        if trend_result:
            enhanced['trend_analysis'] = {
                'trend_status': trend_result.trend_status.value,
                'ma_alignment': trend_result.ma_alignment,
                'trend_strength': trend_result.trend_strength,
                'bias_ma5': trend_result.bias_ma5,
                'bias_ma10': trend_result.bias_ma10,
                'volume_status': trend_result.volume_status.value,
                'volume_trend': trend_result.volume_trend,
                'buy_signal': trend_result.buy_signal.value,
                'signal_score': trend_result.signal_score,
                'signal_reasons': trend_result.signal_reasons,
                'risk_factors': trend_result.risk_factors,
            }
        
        return enhanced
    
    def _describe_volume_ratio(self, volume_ratio: float) -> str:
        """
        量比描述
        
        量比 = 當前成交量 / 過去 5 日平均成交量
        """
        if volume_ratio < 0.5:
            return "極度萎縮"
        elif volume_ratio < 0.8:
            return "明顯萎縮"
        elif volume_ratio < 1.2:
            return "正常"
        elif volume_ratio < 2.0:
            return "溫和放量"
        elif volume_ratio < 3.0:
            return "明顯放量"
        else:
            return "巨量"

    def _build_context_snapshot(
        self,
        enhanced_context: Dict[str, Any],
        news_content: Optional[str],
        realtime_quote: Any,
        chip_data: Optional[ChipDistribution]
    ) -> Dict[str, Any]:
        """
        構建分析上下文快照
        """
        return {
            "enhanced_context": enhanced_context,
            "news_content": news_content,
            "realtime_quote_raw": self._safe_to_dict(realtime_quote),
            "chip_distribution_raw": self._safe_to_dict(chip_data),
        }

    @staticmethod
    def _safe_to_dict(value: Any) -> Optional[Dict[str, Any]]:
        """
        安全轉換為字典
        """
        if value is None:
            return None
        if hasattr(value, "to_dict"):
            try:
                return value.to_dict()
            except Exception:
                return None
        if hasattr(value, "__dict__"):
            try:
                return dict(value.__dict__)
            except Exception:
                return None
        return None

    def _resolve_query_source(self, query_source: Optional[str]) -> str:
        """
        解析請求來源。

        優先級（從高到低）：
        1. 顯式傳入的 query_source：調用方明確指定時優先使用，便於覆蓋推斷結果或相容未來 source_message 來自非 bot 的場景
        2. 存在 source_message 時推斷為 "bot"：當前約定為機器人會話上下文
        3. 存在 query_id 時推斷為 "web"：Web 觸發的請求會帶上 query_id
        4. 默認 "system"：定時任務或 CLI 等無上述上下文時

        Args:
            query_source: 調用方顯式指定的來源，如 "bot" / "web" / "cli" / "system"

        Returns:
            歸一化後的來源標識字串，如 "bot" / "web" / "cli" / "system"
        """
        if query_source:
            return query_source
        if self.source_message:
            return "bot"
        if self.query_id:
            return "web"
        return "system"

    def _build_query_context(self) -> Dict[str, str]:
        """
        生成用戶查詢關聯資訊
        """
        context: Dict[str, str] = {
            "query_id": self.query_id or "",
            "query_source": self.query_source or "",
        }

        if self.source_message:
            context.update({
                "requester_platform": self.source_message.platform or "",
                "requester_user_id": self.source_message.user_id or "",
                "requester_user_name": self.source_message.user_name or "",
                "requester_chat_id": self.source_message.chat_id or "",
                "requester_message_id": self.source_message.message_id or "",
                "requester_query": self.source_message.content or "",
            })

        return context
    
    def process_single_stock(
        self,
        code: str,
        skip_analysis: bool = False,
        single_stock_notify: bool = False,
        report_type: ReportType = ReportType.SIMPLE
    ) -> Optional[AnalysisResult]:
        """
        處理單隻股票的完整流程

        包括：
        1. 獲取數據
        2. 保存數據
        3. AI 分析
        4. 單股推送（可選，#55）

        此方法會被執行緒池調用，需要處理好異常

        Args:
            code: 股票代碼
            skip_analysis: 是否跳過 AI 分析
            single_stock_notify: 是否啟用單股推送模式（每分析完一隻立即推送）
            report_type: 報告類型枚舉（從配置讀取，Issue #119）

        Returns:
            AnalysisResult 或 None
        """
        logger.info(f"========== 開始處理 {code} ==========")
        
        try:
            # Step 1: 獲取並保存數據
            success, error = self.fetch_and_save_stock_data(code)
            
            if not success:
                logger.warning(f"[{code}] 數據獲取失敗: {error}")
                # 即使獲取失敗，也嘗試用已有數據分析
            
            # Step 2: AI 分析
            if skip_analysis:
                logger.info(f"[{code}] 跳過 AI 分析（dry-run 模式）")
                return None
            
            result = self.analyze_stock(code, report_type)
            
            if result:
                logger.info(
                    f"[{code}] 分析完成: {result.operation_advice}, "
                    f"評分 {result.sentiment_score}"
                )
                
                # 單股推送模式（#55）：從配置讀取
                if single_stock_notify and self.notifier.is_available():
                    try:
                        # 根據報告類型選擇生成方法
                        if report_type == ReportType.FULL:
                            # 完整報告：使用決策儀表盤格式
                            report_content = self.notifier.generate_dashboard_report([result])
                            logger.info(f"[{code}] 使用完整報告格式")
                        else:
                            # 精簡報告：使用單股報告格式（默認）
                            report_content = self.notifier.generate_single_stock_report(result)
                            logger.info(f"[{code}] 使用精簡報告格式")
                        
                        if self.notifier.send(report_content):
                            logger.info(f"[{code}] 單股推送成功")
                        else:
                            logger.warning(f"[{code}] 單股推送失敗")
                    except Exception as e:
                        logger.error(f"[{code}] 單股推送異常: {e}")
            
            return result
            
        except Exception as e:
            # 捕獲所有異常，確保單股失敗不影響整體
            logger.exception(f"[{code}] 處理過程發生未知異常: {e}")
            return None
    
    def run(
        self, 
        stock_codes: Optional[List[str]] = None,
        dry_run: bool = False,
        send_notification: bool = True
    ) -> List[AnalysisResult]:
        """
        運行完整的分析流程
        
        流程：
        1. 獲獲取待分析的股票列表
        2. 使用執行緒池併發處理
        3. 收集分析結果
        4. 發送通知
        
        Args:
            stock_codes: 股票代碼列表（可選，默認使用配置中的自選股）
            dry_run: 是否僅獲取數據不分析
            send_notification: 是否發送推送通知
            
        Returns:
            分析結果列表
        """
        start_time = time.time()
        
        # 使用配置中的股票列表
        if stock_codes is None:
            self.config.refresh_stock_list()
            stock_codes = self.config.stock_list
        
        if not stock_codes:
            logger.error("未配置自選股列表，請在 .env 文件中設置 STOCK_LIST")
            return []
        
        logger.info(f"===== 開始分析 {len(stock_codes)} 只股票 =====")
        logger.info(f"股票列表: {', '.join(stock_codes)}")
        logger.info(f"併發數: {self.max_workers}, 模式: {'僅獲取數據' if dry_run else '完整分析'}")
        
        # === 批量預取即時行情（優化：避免每隻股票都觸發全量拉取）===
        # 只有股票數量 >= 5 時才進行預取，少量股票直接逐個查詢更高效
        if len(stock_codes) >= 5:
            prefetch_count = self.fetcher_manager.prefetch_realtime_quotes(stock_codes)
            if prefetch_count > 0:
                logger.info(f"已啟用批量預取架構：一次拉取全市場數據，{len(stock_codes)} 只股票共享快取")
        
        # 單股推送模式（#55）：從配置讀取
        single_stock_notify = getattr(self.config, 'single_stock_notify', False)
        # Issue #119: 從配置讀取報告類型
        report_type_str = getattr(self.config, 'report_type', 'simple').lower()
        report_type = ReportType.FULL if report_type_str == 'full' else ReportType.SIMPLE
        # Issue #128: 從配置讀取分析間隔
        analysis_delay = getattr(self.config, 'analysis_delay', 0)

        if single_stock_notify:
            logger.info(f"已啟用單股推送模式：每分析完一隻股票立即推送（報告類型: {report_type_str}）")
        
        results: List[AnalysisResult] = []
        
        # 使用執行緒池併發處理
        # 注意：max_workers 設置較低（默認 3）以避免觸發反爬
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交任務
            future_to_code = {
                executor.submit(
                    self.process_single_stock,
                    code,
                    skip_analysis=dry_run,
                    single_stock_notify=single_stock_notify and send_notification,
                    report_type=report_type  # Issue #119: 傳遞報告類型
                ): code
                for code in stock_codes
            }
            
            # 收集結果
            for idx, future in enumerate(as_completed(future_to_code)):
                code = future_to_code[future]
                try:
                    result = future.result()
                    if result:
                        results.append(result)

                    # Issue #128: 分析間隔 - 在個股分析和大盤分析之間添加延遲
                    if idx < len(stock_codes) - 1 and analysis_delay > 0:
                        logger.debug(f"等待 {analysis_delay} 秒後繼續下一隻股票...")
                        time.sleep(analysis_delay)

                except Exception as e:
                    logger.error(f"[{code}] 任務執行失敗: {e}")
        
        # 統計
        elapsed_time = time.time() - start_time
        
        # dry-run 模式下，數據獲取成功即視為成功
        if dry_run:
            # 檢查哪些股票的數據今天已存在
            success_count = sum(1 for code in stock_codes if self.db.has_today_data(code))
            fail_count = len(stock_codes) - success_count
        else:
            success_count = len(results)
            fail_count = len(stock_codes) - success_count
        
        logger.info("===== 分析完成 =====")
        logger.info(f"成功: {success_count}, 失敗: {fail_count}, 耗時: {elapsed_time:.2f} 秒")
        
        # 發送通知（單股推送模式下跳過匯總推送，避免重複）
        if results and send_notification and not dry_run:
            if single_stock_notify:
                # 單股推送模式：只保存匯總報告，不再重複推送
                logger.info("單股推送模式：跳過匯總推送，僅保存報告到本地")
                self._send_notifications(results, skip_push=True)
            else:
                self._send_notifications(results)
        
        return results
    
    def _send_notifications(self, results: List[AnalysisResult], skip_push: bool = False) -> None:
        """
        發送分析結果通知
        
        生成決策儀表盤格式的報告
        
        Args:
            results: 分析結果列表
            skip_push: 是否跳過推送（僅保存到本地，用於單股推送模式）
        """
        try:
            logger.info("生成決策儀表盤日報...")
            
            # 生成決策儀表盤格式的詳細日報
            report = self.notifier.generate_dashboard_report(results)
            
            # 保存到本地
            filepath = self.notifier.save_report_to_file(report)
            logger.info(f"決策儀表盤日報已保存: {filepath}")
            
            # 跳過推送（單股推送模式）
            if skip_push:
                return
            
            # 推送通知
            if self.notifier.is_available():
                channels = self.notifier.get_available_channels()
                context_success = self.notifier.send_to_context(report)

                # 企業微信：只發精簡版（平台限制）
                wechat_success = False
                if NotificationChannel.WECHAT in channels:
                    dashboard_content = self.notifier.generate_wechat_dashboard(results)
                    logger.info(f"企業微信儀表盤長度: {len(dashboard_content)} 字元")
                    logger.debug(f"企業微信推送內容:\n{dashboard_content}")
                    wechat_success = self.notifier.send_to_wechat(dashboard_content)

                # 其他管道：發完整報告（避免自定義 Webhook 被 wechat 截斷邏輯污染）
                non_wechat_success = False
                for channel in channels:
                    if channel == NotificationChannel.WECHAT:
                        continue
                    if channel == NotificationChannel.FEISHU:
                        non_wechat_success = self.notifier.send_to_feishu(report) or non_wechat_success
                    elif channel == NotificationChannel.TELEGRAM:
                        non_wechat_success = self.notifier.send_to_telegram(report) or non_wechat_success
                    elif channel == NotificationChannel.EMAIL:
                        non_wechat_success = self.notifier.send_to_email(report) or non_wechat_success
                    elif channel == NotificationChannel.CUSTOM:
                        non_wechat_success = self.notifier.send_to_custom(report) or non_wechat_success
                    elif channel == NotificationChannel.PUSHPLUS:
                        non_wechat_success = self.notifier.send_to_pushplus(report) or non_wechat_success
                    elif channel == NotificationChannel.DISCORD:
                        non_wechat_success = self.notifier.send_to_discord(report) or non_wechat_success
                    elif channel == NotificationChannel.PUSHOVER:
                        non_wechat_success = self.notifier.send_to_pushover(report) or non_wechat_success
                    elif channel == NotificationChannel.ASTRBOT:
                        non_wechat_success = self.notifier.send_to_astrbot(report) or non_wechat_success
                    else:
                        logger.warning(f"未知通知管道: {channel}")

                success = wechat_success or non_wechat_success or context_success
                if success:
                    logger.info("決策儀表盤推送成功")
                else:
                    logger.warning("決策儀表盤推送失敗")
            else:
                logger.info("通知管道未配置，跳過推送")
                
        except Exception as e:
            logger.error(f"發送通知失敗: {e}")
