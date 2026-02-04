# -*- coding: utf-8 -*-
"""
===================================
A股自選股智能分析系統 - 分析服務層
===================================

職責：
1. 封裝核心分析邏輯，支援多調用方（CLI、WebUI、Bot）
2. 提供清晰的 API 介面，不依賴於命令行參數
3. 支援依賴注入，便於測試和擴展
4. 統一管理分析流程和配置
"""

import uuid
from typing import List, Optional

from src.analyzer import AnalysisResult
from src.config import get_config, Config
from src.notification import NotificationService
from src.enums import ReportType
from src.core.pipeline import StockAnalysisPipeline
from src.core.market_review import run_market_review



def analyze_stock(
    stock_code: str,
    config: Config = None,
    full_report: bool = False,
    notifier: Optional[NotificationService] = None
) -> Optional[AnalysisResult]:
    """
    分析單隻股票
    
    Args:
        stock_code: 股票代碼
        config: 配置物件（可選，默認使用單例）
        full_report: 是否生成完整報告
        notifier: 通知服務（可選）
        
    Returns:
        分析結果物件
    """
    if config is None:
        config = get_config()
    
    # 建立分析流水線
    pipeline = StockAnalysisPipeline(
        config=config,
        query_id=uuid.uuid4().hex,
        query_source="cli"
    )
    
    # 使用通知服務（如果提供）
    if notifier:
        pipeline.notifier = notifier
    
    # 根據 full_report 參數設置報告類型
    report_type = ReportType.FULL if full_report else ReportType.SIMPLE
    
    # 運行單隻股票分析
    result = pipeline.process_single_stock(
        code=stock_code,
        skip_analysis=False,
        single_stock_notify=notifier is not None,
        report_type=report_type
    )
    
    return result

def analyze_stocks(
    stock_codes: List[str],
    config: Config = None,
    full_report: bool = False,
    notifier: Optional[NotificationService] = None
) -> List[AnalysisResult]:
    """
    分析多隻股票
    
    Args:
        stock_codes: 股票代碼列表
        config: 配置物件（可選，默認使用單例）
        full_report: 是否生成完整報告
        notifier: 通知服務（可選）
        
    Returns:
        分析結果列表
    """
    if config is None:
        config = get_config()
    
    results = []
    for stock_code in stock_codes:
        result = analyze_stock(stock_code, config, full_report, notifier)
        if result:
            results.append(result)
    
    return results

def perform_market_review(
    config: Config = None,
    notifier: Optional[NotificationService] = None
) -> Optional[str]:
    """
    執行大盤複盤
    
    Args:
        config: 配置物件（可選，默認使用單例）
        notifier: 通知服務（可選）
        
    Returns:
        複盤報告內容
    """
    if config is None:
        config = get_config()
    
    # 建立分析流水線以獲取 analyzer 和 search_service
    pipeline = StockAnalysisPipeline(
        config=config,
        query_id=uuid.uuid4().hex,
        query_source="cli"
    )
    
    # 使用提供的通知服務或建立新的
    review_notifier = notifier or pipeline.notifier
    
    # 調用大盤複盤函數
    return run_market_review(
        notifier=review_notifier,
        analyzer=pipeline.analyzer,
        search_service=pipeline.search_service
    )
