# -*- coding: utf-8 -*-
"""
===================================
WebUI 入口文件 (向後相容)
===================================

本文件保持向後相容，實際實作已遷移到 web/ 包

結構說明:
    web/
    ├── __init__.py    - 包初始化
    ├── server.py      - HTTP 伺服器
    ├── router.py      - 路由分發
    ├── handlers.py    - 請求處理器
    ├── services.py    - 業務服務層
    └── templates.py   - HTML 模板

API Endpoints:
  GET  /              - 配置頁面
  GET  /health        - 健康檢查
  GET  /analysis?code=xxx - 觸發單隻股票非同步分析
  GET  /tasks         - 查詢任務列表
  GET  /task?id=xxx   - 查詢任務狀態
  POST /update        - 更新配置

Usage:
  python webui.py
  WEBUI_HOST=0.0.0.0 WEBUI_PORT=8000 python webui.py
"""

from __future__ import annotations

import os
import logging

# 從 web 包導入（新架構）
from web.server import WebServer, run_server_in_thread, run_server
from web.router import Router, get_router
from web.services import ConfigService, AnalysisService, get_config_service, get_analysis_service
from web.handlers import PageHandler, ApiHandler
from web.templates import render_config_page, render_error_page

logger = logging.getLogger(__name__)

# 導出所有公共介面（保持向後相容）
__all__ = [
    # 伺服器
    'WebServer',
    'run_server_in_thread',
    'run_server',
    # 路由
    'Router',
    'get_router',
    # 服務
    'ConfigService',
    'AnalysisService',
    'get_config_service',
    'get_analysis_service',
    # 處理器
    'PageHandler',
    'ApiHandler',
    # 模板
    'render_config_page',
    'render_error_page',
]


def _start_bot_stream_clients() -> None:
    """啟動 Bot Stream 模式客戶端（如果已配置）"""
    from src.config import get_config
    config = get_config()
    
    # 釘釘 Stream 模式
    if config.dingtalk_stream_enabled:
        try:
            from bot.platforms import start_dingtalk_stream_background, DINGTALK_STREAM_AVAILABLE
            if DINGTALK_STREAM_AVAILABLE:
                if start_dingtalk_stream_background():
                    logger.info("[WebUI] 釘釘 Stream 客戶端已在後台啟動")
                else:
                    logger.warning("[WebUI] 釘釘 Stream 客戶端啟動失敗")
            else:
                logger.warning("[WebUI] 釘釘 Stream 模式已啟用但 SDK 未安裝")
                logger.warning("[WebUI] 請執行: pip install dingtalk-stream")
        except Exception as e:
            logger.error(f"[WebUI] 啟動釘釘 Stream 客戶端失敗: {e}")

    # 飛書 Stream 模式
    if getattr(config, 'feishu_stream_enabled', False):
        try:
            from bot.platforms import start_feishu_stream_background, FEISHU_SDK_AVAILABLE
            if FEISHU_SDK_AVAILABLE:
                if start_feishu_stream_background():
                    logger.info("[WebUI] 飛書 Stream 客戶端已在後台啟動")
                else:
                    logger.warning("[WebUI] 飛書 Stream 客戶端啟動失敗")
            else:
                logger.warning("[WebUI] 飛書 Stream 模式已啟用但 SDK 未安裝")
                logger.warning("[WebUI] 請執行: pip install lark-oapi")
        except Exception as e:
            logger.error(f"[WebUI] 啟動飛書 Stream 客戶端失敗: {e}")


def main() -> int:
    """
    主入口函數
    
    支持環境變數配置:
        WEBUI_HOST: 監聽地址 (默認 127.0.0.1)
        WEBUI_PORT: 監聽端口 (默認 8000)
    """
    host = os.getenv("WEBUI_HOST", "127.0.0.1")
    port = int(os.getenv("WEBUI_PORT", "8000"))
    
    print(f"WebUI running: http://{host}:{port}")
    print("API Endpoints:")
    print("  GET  /              - 配置頁面")
    print("  GET  /health        - 健康檢查")
    print("  GET  /analysis?code=xxx - 觸發分析")
    print("  GET  /tasks         - 任務列表")
    print("  GET  /task?id=xxx   - 任務狀態")
    print("  POST /update        - 更新配置")
    print()
    print("Bot Webhooks:")
    print("  POST /bot/feishu    - 飛書機器人")
    print("  POST /bot/dingtalk  - 釘釘機器人")
    print("  POST /bot/wecom     - 企業微信機器人")
    print("  POST /bot/telegram  - Telegram 機器人")
    print()
    
    # 啟動 Bot Stream 客戶端（如果配置了）
    _start_bot_stream_clients()
    
    try:
        run_server(host=host, port=port)
    except KeyboardInterrupt:
        pass
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
