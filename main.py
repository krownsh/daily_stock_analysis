# -*- coding: utf-8 -*-
"""
===================================
A股自選股智能分析系統 - 主調度程序
===================================

職責：
1. 協調各模組完成股票分析流程
2. 實現低併發的線程池調度
3. 全域異常處理，確保單股失敗不影響整體
4. 提供命令行入口

使用方式：
    python main.py              # 正常運行
    python main.py --debug      # 偵錯模式
    python main.py --dry-run    # 僅獲取數據不分析

交易理念（已融入分析）：
- 嚴進策略：不追高，乖離率 > 5% 不買入
- 趨勢交易：只做 MA5>MA10>MA20 多頭排列
- 效率優先：關注籌碼集中度好的股票
- 買點偏好：縮量回調至 MA5/MA10 支撐
"""
import os
from src.config import setup_env
setup_env()

# 代理配置 - 通過 USE_PROXY 環境變數控制，默認關閉
# GitHub Actions 環境自動跳過代理配置
if os.getenv("GITHUB_ACTIONS") != "true" and os.getenv("USE_PROXY", "false").lower() == "true":
    # 本地開發環境，啟用代理（可在 .env 中配置 PROXY_HOST 和 PROXY_PORT）
    proxy_host = os.getenv("PROXY_HOST", "127.0.0.1")
    proxy_port = os.getenv("PROXY_PORT", "10809")
    proxy_url = f"http://{proxy_host}:{proxy_port}"
    os.environ["http_proxy"] = proxy_url
    os.environ["https_proxy"] = proxy_url

import argparse
import logging
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Optional
from src.feishu_doc import FeishuDocManager

from src.config import get_config, Config
from src.notification import NotificationService
from src.core.pipeline import StockAnalysisPipeline
from src.core.market_review import run_market_review
from src.search_service import SearchService
from src.analyzer import GeminiAnalyzer

# 配置日誌格式
LOG_FORMAT = '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


def setup_logging(debug: bool = False, log_dir: str = "./logs") -> None:
    """
    配置日誌系統（同時輸出到控制台和文件）
    
    Args:
        debug: 是否啟用偵錯模式
        log_dir: 日誌文件目錄
    """
    level = logging.DEBUG if debug else logging.INFO
    
    # 建立日誌目錄
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    # 日誌文件路徑（按日期分文件）
    today_str = datetime.now().strftime('%Y%m%d')
    log_file = log_path / f"stock_analysis_{today_str}.log"
    debug_log_file = log_path / f"stock_analysis_debug_{today_str}.log"
    
    # 建立根 logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # 根 logger 設為 DEBUG，由 handler 控制輸出級別
    
    # Handler 1: 控制台輸出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root_logger.addHandler(console_handler)
    
    # Handler 2: 常規日誌文件（INFO 級別，10MB 輪轉）
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root_logger.addHandler(file_handler)
    
    # Handler 3: 偵錯日誌文件（DEBUG 級別，包含所有詳細資訊）
    debug_handler = RotatingFileHandler(
        debug_log_file,
        maxBytes=50 * 1024 * 1024,  # 50MB
        backupCount=3,
        encoding='utf-8'
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root_logger.addHandler(debug_handler)
    
    # 降低第三方庫的日誌級別
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
    logging.getLogger('google').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    
    logging.info(f"日誌系統初始化完成，日誌目錄: {log_path.absolute()}")
    logging.info(f"常規日誌: {log_file}")
    logging.info(f"偵錯日誌: {debug_log_file}")


logger = logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    """解析命令行參數"""
    parser = argparse.ArgumentParser(
        description='A股自選股智能分析系統',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python main.py                    # 正常運行
  python main.py --debug            # 偵錯模式
  python main.py --dry-run          # 僅獲取數據，不進行 AI 分析
  python main.py --stocks 600519,000001  # 指定分析特定股票
  python main.py --no-notify        # 不發送推送通知
  python main.py --single-notify    # 啟用單股推送模式（每分析完一隻立即推送）
  python main.py --schedule         # 啟用定時任務模式
  python main.py --market-review    # 僅運行大盤複盤
        '''
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='啟用偵錯模式，輸出詳細日誌'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='僅獲取數據，不進行 AI 分析'
    )
    
    parser.add_argument(
        '--stocks',
        type=str,
        help='指定要分析的股票代碼，逗號分隔（覆蓋配置文件）'
    )
    
    parser.add_argument(
        '--no-notify',
        action='store_true',
        help='不發送推送通知'
    )
    
    parser.add_argument(
        '--single-notify',
        action='store_true',
        help='啟用單股推送模式：每分析完一隻股票立即推送，而不是匯總推送'
    )
    
    parser.add_argument(
        '--workers',
        type=int,
        default=None,
        help='併發執行緒數（默認使用配置值）'
    )
    
    parser.add_argument(
        '--schedule',
        action='store_true',
        help='啟用定時任務模式，每日定時執行'
    )
    
    parser.add_argument(
        '--market-review',
        action='store_true',
        help='僅運行大盤複盤分析'
    )
    
    parser.add_argument(
        '--no-market-review',
        action='store_true',
        help='跳過大盤複盤分析'
    )
    
    parser.add_argument(
        '--webui',
        action='store_true',
        help='啟動本地配置 WebUI'
    )
    
    parser.add_argument(
        '--webui-only',
        action='store_true',
        help='僅啟動 WebUI 服務，不自動執行分析（通過 /analysis API 手動觸發）'
    )

    parser.add_argument(
        '--no-context-snapshot',
        action='store_true',
        help='不保存分析上下文快照'
    )
    
    return parser.parse_args()


def run_full_analysis(
    config: Config,
    args: argparse.Namespace,
    stock_codes: Optional[List[str]] = None
):
    """
    執行完整的分析流程（個股 + 大盤複盤）
    
    這是定時任務調用的主函數
    """
    try:
        # 命令行參數 --single-notify 覆蓋配置 (#55)
        if getattr(args, 'single_notify', False):
            config.single_stock_notify = True
        
        # 建立調度器
        save_context_snapshot = None
        if getattr(args, 'no_context_snapshot', False):
            save_context_snapshot = False
        query_id = uuid.uuid4().hex
        pipeline = StockAnalysisPipeline(
            config=config,
            max_workers=args.workers,
            query_id=query_id,
            query_source="cli",
            save_context_snapshot=save_context_snapshot
        )
        
        # 1. 運行個股分析
        results = pipeline.run(
            stock_codes=stock_codes,
            dry_run=args.dry_run,
            send_notification=not args.no_notify
        )

        # Issue #128: 分析間隔 - 在個股分析和大盤分析之間添加延遲
        analysis_delay = getattr(config, 'analysis_delay', 0)
        if analysis_delay > 0 and config.market_review_enabled and not args.no_market_review:
            logger.info(f"等待 {analysis_delay} 秒後執行大盤複盤（避免 API 限流）...")
            time.sleep(analysis_delay)

        # 2. 運行大盤複盤（如果啟用且不是僅個股模式）
        market_report = ""
        if config.market_review_enabled and not args.no_market_review:
            # 只調用一次，並獲取結果
            review_result = run_market_review(
                notifier=pipeline.notifier,
                analyzer=pipeline.analyzer,
                search_service=pipeline.search_service,
                send_notification=not args.no_notify
            )
            # 如果有結果，賦值給 market_report 用於後續飛書文檔生成
            if review_result:
                market_report = review_result
        
        # 輸出摘要
        if results:
            logger.info("\n===== 分析結果摘要 =====")
            for r in sorted(results, key=lambda x: x.sentiment_score, reverse=True):
                emoji = r.get_emoji()
                logger.info(
                    f"{emoji} {r.name}({r.code}): {r.operation_advice} | "
                    f"評分 {r.sentiment_score} | {r.trend_prediction}"
                )
        
        logger.info("\n任務執行完成")

        # === 新增：生成飛書雲文件 ===
        try:
            feishu_doc = FeishuDocManager()
            if feishu_doc.is_configured() and (results or market_report):
                logger.info("正在建立飛書雲文件...")

                # 1. 準備標題 "01-01 13:01 大盤複盤"
                tz_cn = timezone(timedelta(hours=8))
                now = datetime.now(tz_cn)
                doc_title = f"{now.strftime('%Y-%m-%d %H:%M')} 大盤複盤"

                # 2. 準備內容 (拼接個股分析和大盤複盤)
                full_content = ""

                # 添加大盤複盤內容（如果有）
                if market_report:
                    full_content += f"# 📈 大盤複盤\n\n{market_report}\n\n---\n\n"

                # 添加個股決策儀表盤（使用 NotificationService 生成）
                if results:
                    dashboard_content = pipeline.notifier.generate_dashboard_report(results)
                    full_content += f"# 🚀 個股決策儀表盤\n\n{dashboard_content}"

                # 3. 建立文件
                doc_url = feishu_doc.create_daily_doc(doc_title, full_content)
                if doc_url:
                    logger.info(f"飛書雲文件建立成功: {doc_url}")
                    # 可選：將文件連結也推送到群裡
                    if not args.no_notify:
                        pipeline.notifier.send(f"[{now.strftime('%Y-%m-%d %H:%M')}] 複盤文件建立成功: {doc_url}")

        except Exception as e:
            logger.error(f"飛書文件生成失敗: {e}")
        
    except Exception as e:
        logger.exception(f"分析流程執行失敗: {e}")


def start_bot_stream_clients(config: Config) -> None:
    """啟用 bot stream 客戶端（如果在配置中啟用）。"""
    # 啟動釘釘 Stream 客戶端
    if config.dingtalk_stream_enabled:
        try:
            from bot.platforms import start_dingtalk_stream_background, DINGTALK_STREAM_AVAILABLE
            if DINGTALK_STREAM_AVAILABLE:
                if start_dingtalk_stream_background():
                    logger.info("[Main] Dingtalk Stream client started in background.")
                else:
                    logger.warning("[Main] Dingtalk Stream client failed to start.")
            else:
                logger.warning("[Main] Dingtalk Stream enabled but SDK is missing.")
                logger.warning("[Main] Run: pip install dingtalk-stream")
        except Exception as exc:
            logger.error(f"[Main] Failed to start Dingtalk Stream client: {exc}")

    # 啟動飛書 Stream 客戶端
    if getattr(config, 'feishu_stream_enabled', False):
        try:
            from bot.platforms import start_feishu_stream_background, FEISHU_SDK_AVAILABLE
            if FEISHU_SDK_AVAILABLE:
                if start_feishu_stream_background():
                    logger.info("[Main] Feishu Stream client started in background.")
                else:
                    logger.warning("[Main] Feishu Stream client failed to start.")
            else:
                logger.warning("[Main] Feishu Stream enabled but SDK is missing.")
                logger.warning("[Main] Run: pip install lark-oapi")
        except Exception as exc:
            logger.error(f"[Main] Failed to start Feishu Stream client: {exc}")


def main() -> int:
    """
    主入口函數
    
    Returns:
        退出碼（0 表示成功）
    """
    # 解析命令行參數
    args = parse_arguments()
    
    # 載入配置（在設置日誌前載入，以獲取日誌目錄）
    config = get_config()
    
    # 配置日誌（輸出到控制台和文件）
    setup_logging(debug=args.debug, log_dir=config.log_dir)
    
    logger.info("=" * 60)
    logger.info("A股自選股智能分析系統 啟動")
    logger.info(f"運行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    # 驗證配置
    warnings = config.validate()
    for warning in warnings:
        logger.warning(warning)
    
    # 解析股票列表
    stock_codes = None
    if args.stocks:
        stock_codes = [code.strip() for code in args.stocks.split(',') if code.strip()]
        logger.info(f"使用命令行指定的股票列表: {stock_codes}")
    
    # === 啟動 WebUI (如果啟用) ===
    # 優先級: 命令行參數 > 配置文件
    start_webui = (args.webui or args.webui_only or config.webui_enabled) and os.getenv("GITHUB_ACTIONS") != "true"
    
    if start_webui:
        try:
            from webui import run_server_in_thread
            run_server_in_thread(host=config.webui_host, port=config.webui_port)
            start_bot_stream_clients(config)
        except Exception as e:
            logger.error(f"啟動 WebUI 失敗: {e}")
    
    # === 僅 WebUI 模式：不自動執行分析 ===
    if args.webui_only:
        logger.info("模式: 僅 WebUI 服務")
        logger.info(f"WebUI 運行中: http://{config.webui_host}:{config.webui_port}")
        logger.info("通過 /analysis?code=xxx 介面手動觸發分析")
        logger.info("按 Ctrl+C 退出...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\n用戶中斷，程序退出")
        return 0

    try:
        # 模式1: 僅大盤複盤
        if args.market_review:
            logger.info("模式: 僅大盤複盤")
            notifier = NotificationService()
            
            # 初始化搜尋服務和分析器（如果有配置）
            search_service = None
            analyzer = None
            
            if config.bocha_api_keys or config.tavily_api_keys or config.serpapi_keys:
                search_service = SearchService(
                    bocha_keys=config.bocha_api_keys,
                    tavily_keys=config.tavily_api_keys,
                    serpapi_keys=config.serpapi_keys
                )
            
            if config.gemini_api_key or config.openai_api_key:
                analyzer = GeminiAnalyzer(api_key=config.gemini_api_key)
                if not analyzer.is_available():
                    logger.warning("AI 分析器初始化後不可用，請檢查 API Key 配置")
                    analyzer = None
            else:
                logger.warning("未檢測到 API Key (Gemini/OpenAI)，將僅使用模板生成報告")
            
            run_market_review(
                notifier=notifier, 
                analyzer=analyzer, 
                search_service=search_service,
                send_notification=not args.no_notify
            )
            return 0
        
        # 模式2: 定時任務模式
        if args.schedule or config.schedule_enabled:
            logger.info("模式: 定時任務")
            logger.info(f"每日執行時間: {config.schedule_time}")
            
            from src.scheduler import run_with_schedule
            
            def scheduled_task():
                run_full_analysis(config, args, stock_codes)
            
            run_with_schedule(
                task=scheduled_task,
                schedule_time=config.schedule_time,
                run_immediately=True  # 啟動時先執行一次
            )
            return 0
        
        # 模式3: 正常單次運行
        run_full_analysis(config, args, stock_codes)
        
        logger.info("\n程序執行完成")
        
        # 如果啟用了 WebUI 且是非定時任務模式，保持程序運行以便訪問 WebUI
        if start_webui and not (args.schedule or config.schedule_enabled):
            logger.info("WebUI 運行中 (按 Ctrl+C 退出)...")
            try:
                # 簡單的保持活躍迴圈
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("\n用戶中斷，程序退出")
        return 130
        
    except Exception as e:
        logger.exception(f"程序執行失敗: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
