# -*- coding: utf-8 -*-
"""
===================================
平台適配器基類
===================================

定義平台適配器的抽象基類，各平台必須繼承此類。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple

from bot.models import BotMessage, BotResponse, WebhookResponse


class BotPlatform(ABC):
    """
    平台適配器抽象基類
    
    負責：
    1. 驗證 Webhook 請求簽名
    2. 解析平台消息為統一格式
    3. 將響應轉換為平台格式
    
    使用示例：
        class MyPlatform(BotPlatform):
            @property
            def platform_name(self) -> str:
                return "myplatform"
            
            def verify_request(self, headers, body) -> bool:
                # 驗證簽名邏輯
                return True
            
            def parse_message(self, data) -> Optional[BotMessage]:
                # 解析消息邏輯
                return BotMessage(...)
            
            def format_response(self, response, message) -> WebhookResponse:
                # 格式化響應邏輯
                return WebhookResponse.success({"text": response.text})
    """
    
    @property
    @abstractmethod
    def platform_name(self) -> str:
        """
        平台標識名稱
        
        用於路由匹配和日誌標識，如 "feishu", "dingtalk"
        """
        pass
    
    @abstractmethod
    def verify_request(self, headers: Dict[str, str], body: bytes) -> bool:
        """
        驗證請求簽名
        
        各平台有不同的簽名驗證機制，需要單獨實作。
        
        Args:
            headers: HTTP 請求頭
            body: 請求體原始位元組
            
        Returns:
            簽名是否有效
        """
        pass
    
    @abstractmethod
    def parse_message(self, data: Dict[str, Any]) -> Optional[BotMessage]:
        """
        解析平台消息為統一格式
        
        將平台特定的消息格式轉換為 BotMessage。
        如果不是需要處理的消息類型（如事件回呼），返回 None。
        
        Args:
            data: 解析後的 JSON 數據
            
        Returns:
            BotMessage 對象，或 None（不需要處理）
        """
        pass
    
    @abstractmethod
    def format_response(
        self, 
        response: BotResponse, 
        message: BotMessage
    ) -> WebhookResponse:
        """
        將統一響應轉換為平台格式
        
        Args:
            response: 統一響應對象
            message: 原始消息對象（用於獲取回覆目標等資訊）
            
        Returns:
            WebhookResponse 對象
        """
        pass
    
    def handle_challenge(self, data: Dict[str, Any]) -> Optional[WebhookResponse]:
        """
        處理平台驗證請求
        
        部分平台在配置 Webhook 時會發送驗證請求，需要返回特定響應。
        子類可重寫此方法。
        
        Args:
            data: 請求數據
            
        Returns:
            驗證響應，或 None（不是驗證請求）
        """
        return None
    
    def handle_webhook(
        self, 
        headers: Dict[str, str], 
        body: bytes,
        data: Dict[str, Any]
    ) -> Tuple[Optional[BotMessage], Optional[WebhookResponse]]:
        """
        處理 Webhook 請求
        
        這是主入口方法，協調驗證、解析等流程。
        
        Args:
            headers: HTTP 請求頭
            body: 請求體原始位元組
            data: 解析後的 JSON 數據
            
        Returns:
            (BotMessage, WebhookResponse) 元組
            - 如果是驗證請求：(None, challenge_response)
            - 如果是普通消息：(message, None) - 響應將在命令處理後生成
            - 如果驗證失敗或無需處理：(None, error_response 或 None)
        """
        # 1. 檢查是否是驗證請求
        challenge_response = self.handle_challenge(data)
        if challenge_response:
            return None, challenge_response
        
        # 2. 驗證請求簽名
        if not self.verify_request(headers, body):
            return None, WebhookResponse.error("Invalid signature", 403)
        
        # 3. 解析消息
        message = self.parse_message(data)
        
        return message, None
