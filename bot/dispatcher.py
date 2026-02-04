# -*- coding: utf-8 -*-
"""
===================================
命令分發器
===================================

負責解析命令、匹配處理器、分發執行。
"""

import logging
import time
from collections import defaultdict
from typing import Dict, List, Optional, Type, Callable

from bot.models import BotMessage, BotResponse
from bot.commands.base import BotCommand

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    簡單的頻率限制器
    
    基於滑動窗口算法，限制每個用戶的請求頻率。
    """
    
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        """
        Args:
            max_requests: 窗口內最大請求數
            window_seconds: 窗口時間（秒）
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, List[float]] = defaultdict(list)
    
    def is_allowed(self, user_id: str) -> bool:
        """
        檢查用戶是否允許請求
        
        Args:
            user_id: 用戶標識
            
        Returns:
            是否允許
        """
        now = time.time()
        window_start = now - self.window_seconds
        
        # 清理過期記錄
        self._requests[user_id] = [
            t for t in self._requests[user_id] 
            if t > window_start
        ]
        
        # 檢查是否超限
        if len(self._requests[user_id]) >= self.max_requests:
            return False
        
        # 記錄本次請求
        self._requests[user_id].append(now)
        return True
    
    def get_remaining(self, user_id: str) -> int:
        """獲取剩餘可用請求數"""
        now = time.time()
        window_start = now - self.window_seconds
        
        # 清理過期記錄
        self._requests[user_id] = [
            t for t in self._requests[user_id] 
            if t > window_start
        ]
        
        return max(0, self.max_requests - len(self._requests[user_id]))


class CommandDispatcher:
    """
    命令分發器
    
    職責：
    1. 註冊和管理命令處理器
    2. 解析消息中的命令和參數
    3. 分發命令到對應處理器
    4. 處理未知命令和錯誤
    
    使用示例：
        dispatcher = CommandDispatcher()
        dispatcher.register(AnalyzeCommand())
        dispatcher.register(HelpCommand())
        
        response = dispatcher.dispatch(message)
    """
    
    def __init__(
        self, 
        command_prefix: str = "/",
        rate_limit_requests: int = 10,
        rate_limit_window: int = 60,
        admin_users: Optional[List[str]] = None
    ):
        """
        Args:
            command_prefix: 命令前綴，默認 "/"
            rate_limit_requests: 頻率限制：窗口內最大請求數
            rate_limit_window: 頻率限制：窗口時間（秒）
            admin_users: 管理員用戶 ID 列表
        """
        self.command_prefix = command_prefix
        self.admin_users = set(admin_users or [])
        
        self._commands: Dict[str, BotCommand] = {}
        self._aliases: Dict[str, str] = {}
        self._rate_limiter = RateLimiter(rate_limit_requests, rate_limit_window)
        
        # 回呼函數：獲取幫助命令的命令列表
        self._help_command_getter: Optional[Callable] = None
    
    def register(self, command: BotCommand) -> None:
        """
        註冊命令
        
        Args:
            command: 命令實例
        """
        name = command.name.lower()
        
        if name in self._commands:
            logger.warning(f"[Dispatcher] 命令 '{name}' 已存在，將被覆蓋")
        
        self._commands[name] = command
        logger.debug(f"[Dispatcher] 註冊命令: {name}")
        
        # 註冊別名
        for alias in command.aliases:
            alias_lower = alias.lower()
            if alias_lower in self._aliases:
                logger.warning(f"[Dispatcher] 別名 '{alias_lower}' 已存在，將被覆蓋")
            self._aliases[alias_lower] = name
            logger.debug(f"[Dispatcher] 註冊別名: {alias_lower} -> {name}")
    
    def register_class(self, command_class: Type[BotCommand]) -> None:
        """
        註冊命令類（自動實例化）
        
        Args:
            command_class: 命令類
        """
        self.register(command_class())
    
    def unregister(self, name: str) -> bool:
        """
        註銷命令
        
        Args:
            name: 命令名稱
            
        Returns:
            是否成功註銷
        """
        name = name.lower()
        
        if name not in self._commands:
            return False
        
        command = self._commands.pop(name)
        
        # 移除別名
        for alias in command.aliases:
            self._aliases.pop(alias.lower(), None)
        
        logger.debug(f"[Dispatcher] 註銷命令: {name}")
        return True
    
    def get_command(self, name: str) -> Optional[BotCommand]:
        """
        獲取命令
        
        支援命令名和別名查詢。
        
        Args:
            name: 命令名或別名
            
        Returns:
            命令實例，或 None
        """
        name = name.lower()
        
        # 先查命令名
        if name in self._commands:
            return self._commands[name]
        
        # 再查別名
        if name in self._aliases:
            return self._commands.get(self._aliases[name])
        
        return None
    
    def list_commands(self, include_hidden: bool = False) -> List[BotCommand]:
        """
        列出所有命令
        
        Args:
            include_hidden: 是否包含隱藏命令
            
        Returns:
            命令列表
        """
        commands = list(self._commands.values())
        
        if not include_hidden:
            commands = [c for c in commands if not c.hidden]
        
        return sorted(commands, key=lambda c: c.name)
    
    def is_admin(self, user_id: str) -> bool:
        """檢查用戶是否是管理員"""
        return user_id in self.admin_users
    
    def add_admin(self, user_id: str) -> None:
        """添加管理員"""
        self.admin_users.add(user_id)
    
    def remove_admin(self, user_id: str) -> None:
        """移除管理員"""
        self.admin_users.discard(user_id)
    
    def dispatch(self, message: BotMessage) -> BotResponse:
        """
        分發消息到對應命令
        
        Args:
            message: 消息物件
            
        Returns:
            響應物件
        """
        # 1. 檢查頻率限制
        if not self._rate_limiter.is_allowed(message.user_id):
            remaining_time = self._rate_limiter.window_seconds
            return BotResponse.error_response(
                f"請求過於頻繁，請 {remaining_time} 秒後再試"
            )
        
        # 2. 解析命令和參數
        cmd_name, args = message.get_command_and_args(self.command_prefix)
        
        if cmd_name is None:
            # 不是命令，檢查是否 @了機器人
            if message.mentioned:
                return BotResponse.text_response(
                    "你好！我是股票分析助手。\n"
                    f"發送 `{self.command_prefix}help` 查看可用命令。"
                )
            # 非命令消息，不處理
            return BotResponse.text_response("")
        
        logger.info(f"[Dispatcher] 收到命令: {cmd_name}, 參數: {args}, 用戶: {message.user_name}")
        
        # 3. 查找命令處理器
        command = self.get_command(cmd_name)
        
        if command is None:
            return BotResponse.error_response(
                f"未知命令: {cmd_name}\n"
                f"發送 `{self.command_prefix}help` 查看可用命令。"
            )
        
        # 4. 檢查權限
        if command.admin_only and not self.is_admin(message.user_id):
            return BotResponse.error_response("此命令需要管理員權限")
        
        # 5. 驗證參數
        error_msg = command.validate_args(args)
        if error_msg:
            return BotResponse.error_response(
                f"{error_msg}\n用法: `{command.usage}`"
            )
        
        # 6. 執行命令
        try:
            response = command.execute(message, args)
            logger.info(f"[Dispatcher] 命令 {cmd_name} 執行成功")
            return response
        except Exception as e:
            logger.error(f"[Dispatcher] 命令 {cmd_name} 執行失敗: {e}")
            logger.exception(e)
            return BotResponse.error_response(f"命令執行失敗: {str(e)[:100]}")
    
    def set_help_command_getter(self, getter: Callable) -> None:
        """
        設置幫助命令的命令列表獲取器
        
        用於讓 HelpCommand 獲取命令列表。
        
        Args:
            getter: 回呼函數，返回命令列表
        """
        self._help_command_getter = getter


# 全局分發器實例
_dispatcher: Optional[CommandDispatcher] = None


def get_dispatcher() -> CommandDispatcher:
    """
    獲取全局分發器實例
    
    使用單例模式，首次調用時自動初始化並註冊所有命令。
    """
    global _dispatcher
    
    if _dispatcher is None:
        from src.config import get_config
        
        config = get_config()
        
        # 建立分發器
        _dispatcher = CommandDispatcher(
            command_prefix=getattr(config, 'bot_command_prefix', '/'),
            rate_limit_requests=getattr(config, 'bot_rate_limit_requests', 10),
            rate_limit_window=getattr(config, 'bot_rate_limit_window', 60),
            admin_users=getattr(config, 'bot_admin_users', []),
        )
        
        # 自動註冊所有命令
        from bot.commands import ALL_COMMANDS
        for command_class in ALL_COMMANDS:
            _dispatcher.register_class(command_class)
        
        logger.info(f"[Dispatcher] 初始化完成，已註冊 {len(_dispatcher._commands)} 個命令")
    
    return _dispatcher


def reset_dispatcher() -> None:
    """重置全局分發器（主要用於測試）"""
    global _dispatcher
    _dispatcher = None
