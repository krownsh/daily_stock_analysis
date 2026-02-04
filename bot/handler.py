# -*- coding: utf-8 -*-
"""
===================================
Bot Webhook 處理器
===================================

處理各平台的 Webhook 回呼，分發到命令處理器。
"""

import json
import logging
from typing import Dict, Any, Optional, TYPE_CHECKING

from bot.models import WebhookResponse
from bot.dispatcher import get_dispatcher
from bot.platforms import ALL_PLATFORMS

if TYPE_CHECKING:
    from bot.platforms.base import BotPlatform

logger = logging.getLogger(__name__)

# 平台實例快取
_platform_instances: Dict[str, 'BotPlatform'] = {}


def get_platform(platform_name: str) -> Optional['BotPlatform']:
    """
    獲取平台適配器實例
    
    使用快取避免重複建立。
    
    Args:
        platform_name: 平台名稱
        
    Returns:
        平台適配器實例，或 None
    """
    if platform_name not in _platform_instances:
        platform_class = ALL_PLATFORMS.get(platform_name)
        if platform_class:
            _platform_instances[platform_name] = platform_class()
        else:
            logger.warning(f"[BotHandler] 未知平台: {platform_name}")
            return None
    
    return _platform_instances[platform_name]


def handle_webhook(
    platform_name: str,
    headers: Dict[str, str],
    body: bytes,
    query_params: Optional[Dict[str, list]] = None
) -> WebhookResponse:
    """
    處理 Webhook 請求
    
    這是所有平台 Webhook 的統一入口。
    
    Args:
        platform_name: 平台名稱 (feishu, dingtalk, wecom, telegram)
        headers: HTTP 請求頭
        body: 請求體原始位元組
        query_params: URL 查詢參數（用於某些平台的驗證）
        
    Returns:
        WebhookResponse 響應物件
    """
    logger.info(f"[BotHandler] 收到 {platform_name} Webhook 請求")
    
    # 檢查機器人功能是否啟用
    from src.config import get_config
    config = get_config()
    
    if not getattr(config, 'bot_enabled', True):
        logger.info("[BotHandler] 機器人功能未啟用")
        return WebhookResponse.success()
    
    # 獲取平台適配器
    platform = get_platform(platform_name)
    if not platform:
        return WebhookResponse.error(f"Unknown platform: {platform_name}", 400)
    
    # 解析 JSON 數據
    try:
        data = json.loads(body.decode('utf-8')) if body else {}
    except json.JSONDecodeError as e:
        logger.error(f"[BotHandler] JSON 解析失敗: {e}")
        return WebhookResponse.error("Invalid JSON", 400)
    
    logger.debug(f"[BotHandler] 請求數據: {json.dumps(data, ensure_ascii=False)[:500]}")
    
    # 處理 Webhook
    message, challenge_response = platform.handle_webhook(headers, body, data)
    
    # 如果是驗證請求，直接返回驗證響應
    if challenge_response:
        logger.info(f"[BotHandler] 返回驗證響應")
        return challenge_response
    
    # 如果沒有消息需要處理，返回空響應
    if not message:
        logger.debug("[BotHandler] 無需處理的消息")
        return WebhookResponse.success()
    
    logger.info(f"[BotHandler] 解析到消息: user={message.user_name}, content={message.content[:50]}")
    
    # 分發到命令處理器
    dispatcher = get_dispatcher()
    response = dispatcher.dispatch(message)
    
    # 格式化響應
    if response.text:
        webhook_response = platform.format_response(response, message)
        return webhook_response
    
    return WebhookResponse.success()


def handle_feishu_webhook(headers: Dict[str, str], body: bytes) -> WebhookResponse:
    """處理飛書 Webhook"""
    return handle_webhook('feishu', headers, body)


def handle_dingtalk_webhook(headers: Dict[str, str], body: bytes) -> WebhookResponse:
    """處理釘釘 Webhook"""
    return handle_webhook('dingtalk', headers, body)


def handle_wecom_webhook(headers: Dict[str, str], body: bytes) -> WebhookResponse:
    """處理企業微信 Webhook"""
    return handle_webhook('wecom', headers, body)


def handle_telegram_webhook(headers: Dict[str, str], body: bytes) -> WebhookResponse:
    """處理 Telegram Webhook"""
    return handle_webhook('telegram', headers, body)
