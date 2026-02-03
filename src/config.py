# -*- coding: utf-8 -*-
"""
===================================
A股自選股智能分析系統 - 配置管理模組
===================================

職責：
1. 使用單例模式管理全域配置
2. 從 .env 文件載入敏感配置
3. 提供類型安全的配置訪問介面
"""

import os
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv, dotenv_values
from dataclasses import dataclass, field


def setup_env():
    """初始化環境變數（支持從 .env 載入）"""
    # src/config.py -> src/ -> root
    env_path = Path(__file__).parent.parent / '.env'
    load_dotenv(dotenv_path=env_path)


@dataclass
class Config:
    """
    系統配置類 - 單例模式
    
    設計說明：
    - 使用 dataclass 簡化配置屬性定義
    - 所有配置項從環境變數讀取，支持默認值
    - 類方法 get_instance() 實現單例訪問
    """
    
    # === 自選股配置 ===
    stock_list: List[str] = field(default_factory=list)

    # === 飛書雲文檔配置 ===
    feishu_app_id: Optional[str] = None
    feishu_app_secret: Optional[str] = None
    feishu_folder_token: Optional[str] = None  # 目標文件夾 Token

    # === 數據源 API Token ===
    tushare_token: Optional[str] = None
    
    # === AI 分析配置 ===
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-3-flash-preview"  # 主模型
    gemini_model_fallback: str = "gemini-2.5-flash"  # 備選模型
    gemini_temperature: float = 0.7  # 溫度參數（0.0-2.0，控制輸出隨機性，默認0.7）

    # Gemini API 請求配置（防止 429 限流）
    gemini_request_delay: float = 2.0  # 請求間隔（秒）
    gemini_max_retries: int = 5  # 最大重試次數
    gemini_retry_delay: float = 5.0  # 重試基礎延時（秒）

    # OpenAI 兼容 API（備選，當 Gemini 不可用時使用）
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None  # 如: https://api.openai.com/v1
    openai_model: str = "gpt-4o-mini"  # OpenAI 兼容模型名稱
    openai_temperature: float = 0.7  # OpenAI 溫度參數（0.0-2.0，默認0.7）
    
    # === 搜尋引擎配置（支持多 Key 負載均衡）===
    bocha_api_keys: List[str] = field(default_factory=list)  # Bocha API Keys
    tavily_api_keys: List[str] = field(default_factory=list)  # Tavily API Keys
    serpapi_keys: List[str] = field(default_factory=list)  # SerpAPI Keys
    
    # === 通知配置（可同時配置多個，全部推送）===
    
    # 企業微信 Webhook
    wechat_webhook_url: Optional[str] = None
    
    # 飛書 Webhook
    feishu_webhook_url: Optional[str] = None
    
    # Telegram 配置（需要同時配置 Bot Token 和 Chat ID）
    telegram_bot_token: Optional[str] = None  # Bot Token（@BotFather 獲取）
    telegram_chat_id: Optional[str] = None  # Chat ID
    
    # 郵件配置（只需郵箱和授權碼，SMTP 自動識別）
    email_sender: Optional[str] = None  # 發件人郵箱
    email_password: Optional[str] = None  # 郵箱密碼/授權碼
    email_receivers: List[str] = field(default_factory=list)  # 收件人列表（留空則發給自己）
    
    # Pushover 配置（手機/桌面推送通知）
    pushover_user_key: Optional[str] = None  # 用戶 Key（https://pushover.net 獲取）
    pushover_api_token: Optional[str] = None  # 應用 API Token
    
    # 自定義 Webhook（支持多個，逗號分隔）
    # 適用於：釘釘、Discord、Slack、Bark、自建服務等任意支持 POST JSON 的 Webhook
    custom_webhook_urls: List[str] = field(default_factory=list)
    custom_webhook_bearer_token: Optional[str] = None  # Bearer Token（用於需要認證的 Webhook）
    
    # Discord 通知配置
    discord_bot_token: Optional[str] = None  # Discord Bot Token
    discord_main_channel_id: Optional[str] = None  # Discord 主頻道 ID
    discord_webhook_url: Optional[str] = None  # Discord Webhook URL

    # AstrBot 通知配置
    astrbot_token: Optional[str] = None
    astrbot_url: Optional[str] = None

    # LINE 通知配置
    line_channel_access_token: Optional[str] = None  # LINE Messaging API Token
    line_user_id: Optional[str] = None              # LINE 用戶/群組 ID
    line_notify_token: Optional[str] = None         # LINE Notify Token (簡單通知用)

    # 單股推送模式：每分析完一隻股票立即推送，而不是匯總後推送
    single_stock_notify: bool = False

    # 報告類型：simple(精簡) 或 full(完整)
    report_type: str = "simple"

    # PushPlus 推送配置
    pushplus_token: Optional[str] = None  # PushPlus Token

    # 分析間隔時間（秒）- 用於避免 API 限流
    analysis_delay: float = 0.0  # 個股分析與大盤分析之間的延遲

    # 消息長度限制（字節）- 超長自動分批發送
    feishu_max_bytes: int = 20000  # 飛書限制約 20KB，默認 20000 字節
    wechat_max_bytes: int = 4000   # 企業微信限制 4096 字節，默認 4000 字節
    wechat_msg_type: str = "markdown"  # 企業微信消息類型，默認 markdown 類型
    
    # === 數據庫配置 ===
    database_path: str = "./data/stock_analysis.db"

    # 是否保存分析上下文快照（用於歷史回溯）
    save_context_snapshot: bool = True
    
    # === 日誌配置 ===
    log_dir: str = "./logs"  # 日誌文件目錄
    log_level: str = "INFO"  # 日誌級別
    
    # === 系統配置 ===
    max_workers: int = 3  # 低併發防封禁
    debug: bool = False
    http_proxy: Optional[str] = None  # HTTP 代理 (例如: http://127.0.0.1:10809)
    https_proxy: Optional[str] = None # HTTPS 代理
    
    # === 定時任務配置 ===
    schedule_enabled: bool = False            # 是否啟用定時任務
    schedule_time: str = "18:00"              # 每日推送時間（HH:MM 格式）
    market_review_enabled: bool = True        # 是否啟用大盤複盤
    
    # === 即時行情增強數據配置 ===
    # 即時行情開關（關閉後使用歷史收盤價進行分析）
    enable_realtime_quote: bool = True
    # 籌碼分佈開關（該介面不穩定，雲端部署建議關閉）
    enable_chip_distribution: bool = True
    # 即時行情數據源優先級（逗號分隔）
    # 推薦順序：tencent > akshare_sina > efinance > akshare_em > tushare
    # - tencent: 騰訊財經，有量比/換手率/市盈率等，單股查詢穩定（推薦）
    # - akshare_sina: 新浪財經，基本行情穩定，但無量比
    # - efinance/akshare_em: 東財全量介面，數據最全但容易被封
    # - tushare: Tushare Pro，需要 2000 積分，數據全面（付費用戶可優先使用）
    realtime_source_priority: str = "tencent,akshare_sina,efinance,akshare_em"
    # 即時行情快取時間（秒）
    realtime_cache_ttl: int = 600
    # 熔斷器冷卻時間（秒）
    circuit_breaker_cooldown: int = 300

    # Discord 機器人狀態
    discord_bot_status: str = "A股智能分析 | /help"

    # === 流控配置（防封禁關鍵參數）===
    # Akshare 請求間隔範圍（秒）
    akshare_sleep_min: float = 2.0
    akshare_sleep_max: float = 5.0
    
    # Tushare 每分鐘最大請求數（免費配額）
    tushare_rate_limit_per_minute: int = 80
    
    # 重試配置
    max_retries: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 30.0
    
    # === WebUI 配置 ===
    webui_enabled: bool = False
    webui_host: str = "127.0.0.1"
    webui_port: int = 8000
    
    # === 機器人配置 ===
    bot_enabled: bool = True              # 是否啟用機器人功能
    bot_command_prefix: str = "/"         # 命令前綴
    bot_rate_limit_requests: int = 10     # 頻率限制：視窗內最大請求數
    bot_rate_limit_window: int = 60       # 頻率限制：視窗時間（秒）
    bot_admin_users: List[str] = field(default_factory=list)  # 管理員用戶 ID 列表
    
    # 飛書機器人（事件訂閱）- 已有 feishu_app_id, feishu_app_secret
    feishu_verification_token: Optional[str] = None  # 事件訂閱驗證 Token
    feishu_encrypt_key: Optional[str] = None         # 消息加密金鑰（可選）
    feishu_stream_enabled: bool = False              # 是否啟用 Stream 長連接模式（無需公網 IP）
    
    # 釘釘機器人
    dingtalk_app_key: Optional[str] = None      # 應用 AppKey
    dingtalk_app_secret: Optional[str] = None   # 應用 AppSecret
    dingtalk_stream_enabled: bool = False       # 是否啟用 Stream 模式（無需公網 IP）
    
    # 企業微信機器人（回調模式）
    wecom_corpid: Optional[str] = None              # 企業 ID
    wecom_token: Optional[str] = None               # 回調 Token
    wecom_encoding_aes_key: Optional[str] = None    # 消息加解密金鑰
    wecom_agent_id: Optional[str] = None            # 應用 AgentId
    
    # Telegram 機器人 - 已有 telegram_bot_token, telegram_chat_id
    telegram_webhook_secret: Optional[str] = None   # Webhook 金鑰
    
    # Discord 機器人擴充配置
    # (重複定義，已刪除)
    
    # 單例實例存儲
    _instance: Optional['Config'] = None
    
    @classmethod
    def get_instance(cls) -> 'Config':
        """
        獲取配置單例實例
        
        單例模式確保：
        1. 全域只有一個配置實例
        2. 配置只從環境變數載入一次
        3. 所有模組共享相同配置
        """
        if cls._instance is None:
            cls._instance = cls._load_from_env()
        return cls._instance
    
    @classmethod
    def _load_from_env(cls) -> 'Config':
        """
        從 .env 文件載入配置
        
        載入優先級：
        1. 系統環境變數
        2. .env 文件
        3. 程式碼中的默認值
        """
        # 確保環境變數已載入
        setup_env()

        # === 智能代理配置 (關鍵修復) ===
        # 如果配置了代理，自動設置 NO_PROXY 以排除國內數據源，避免行情獲取失敗
        http_proxy = os.getenv('HTTP_PROXY') or os.getenv('http_proxy')
        if http_proxy:
            # 國內金融數據源域名列表
            domestic_domains = [
                'eastmoney.com',   # 東方財富 (Efinance/Akshare)
                'sina.com.cn',     # 新浪財經 (Akshare)
                '163.com',         # 網易財經 (Akshare)
                'tushare.pro',     # Tushare
                'baostock.com',    # Baostock
                'sse.com.cn',      # 上交所
                'szse.cn',         # 深交所
                'csindex.com.cn',  # 中證指數
                'cninfo.com.cn',   # 巨潮資訊
                'localhost',
                '127.0.0.1'
            ]

            # 獲取現有的 no_proxy
            current_no_proxy = os.getenv('NO_PROXY') or os.getenv('no_proxy') or ''
            existing_domains = current_no_proxy.split(',') if current_no_proxy else []

            # 合併去重
            final_domains = list(set(existing_domains + domestic_domains))
            final_no_proxy = ','.join(filter(None, final_domains))

            # 設置環境變數 (requests/urllib3/aiohttp 都會遵守此設置)
            os.environ['NO_PROXY'] = final_no_proxy
            os.environ['no_proxy'] = final_no_proxy

            # 確保 HTTP_PROXY 也被正確設置（以防僅在 .env 中定義但未匯出）
            os.environ['HTTP_PROXY'] = http_proxy
            os.environ['http_proxy'] = http_proxy

            # HTTPS_PROXY 同理
            https_proxy = os.getenv('HTTPS_PROXY') or os.getenv('https_proxy')
            if https_proxy:
                os.environ['HTTPS_PROXY'] = https_proxy
                os.environ['https_proxy'] = https_proxy

        
        # 解析自選股列表（逗號分隔）
        stock_list_str = os.getenv('STOCK_LIST', '')
        stock_list = [
            code.strip() 
            for code in stock_list_str.split(',') 
            if code.strip()
        ]
        
        # 如果沒有配置，使用默認的示例股票
        if not stock_list:
            stock_list = ['600519', '000001', '300750']
        
        # 解析搜尋引擎 API Keys（支持多個 key，逗號分隔）
        bocha_keys_str = os.getenv('BOCHA_API_KEYS', '')
        bocha_api_keys = [k.strip() for k in bocha_keys_str.split(',') if k.strip()]
        
        tavily_keys_str = os.getenv('TAVILY_API_KEYS', '')
        tavily_api_keys = [k.strip() for k in tavily_keys_str.split(',') if k.strip()]
        
        serpapi_keys_str = os.getenv('SERPAPI_API_KEYS', '')
        serpapi_keys = [k.strip() for k in serpapi_keys_str.split(',') if k.strip()]

        # 企微消息類型與最大字節數邏輯
        wechat_msg_type = os.getenv('WECHAT_MSG_TYPE', 'markdown')
        wechat_msg_type_lower = wechat_msg_type.lower()
        wechat_max_bytes_env = os.getenv('WECHAT_MAX_BYTES')
        if wechat_max_bytes_env not in (None, ''):
            wechat_max_bytes = int(wechat_max_bytes_env)
        else:
            # 未顯式配置時，根據消息類型選擇默認字節數
            wechat_max_bytes = 2048 if wechat_msg_type_lower == 'text' else 4000
        
        return cls(
            stock_list=stock_list,
            feishu_app_id=os.getenv('FEISHU_APP_ID'),
            feishu_app_secret=os.getenv('FEISHU_APP_SECRET'),
            feishu_folder_token=os.getenv('FEISHU_FOLDER_TOKEN'),
            tushare_token=os.getenv('TUSHARE_TOKEN'),
            gemini_api_key=os.getenv('GEMINI_API_KEY'),
            gemini_model=os.getenv('GEMINI_MODEL', 'gemini-3-flash-preview'),
            gemini_model_fallback=os.getenv('GEMINI_MODEL_FALLBACK', 'gemini-2.5-flash'),
            gemini_temperature=float(os.getenv('GEMINI_TEMPERATURE', '0.7')),
            gemini_request_delay=float(os.getenv('GEMINI_REQUEST_DELAY', '2.0')),
            gemini_max_retries=int(os.getenv('GEMINI_MAX_RETRIES', '5')),
            gemini_retry_delay=float(os.getenv('GEMINI_RETRY_DELAY', '5.0')),
            openai_api_key=os.getenv('OPENAI_API_KEY'),
            openai_base_url=os.getenv('OPENAI_BASE_URL'),
            openai_model=os.getenv('OPENAI_MODEL', 'gpt-4o-mini'),
            openai_temperature=float(os.getenv('OPENAI_TEMPERATURE', '0.7')),
            bocha_api_keys=bocha_api_keys,
            tavily_api_keys=tavily_api_keys,
            serpapi_keys=serpapi_keys,
            wechat_webhook_url=os.getenv('WECHAT_WEBHOOK_URL'),
            feishu_webhook_url=os.getenv('FEISHU_WEBHOOK_URL'),
            telegram_bot_token=os.getenv('TELEGRAM_BOT_TOKEN'),
            telegram_chat_id=os.getenv('TELEGRAM_CHAT_ID'),
            email_sender=os.getenv('EMAIL_SENDER'),
            email_password=os.getenv('EMAIL_PASSWORD'),
            email_receivers=[r.strip() for r in os.getenv('EMAIL_RECEIVERS', '').split(',') if r.strip()],
            pushover_user_key=os.getenv('PUSHOVER_USER_KEY'),
            pushover_api_token=os.getenv('PUSHOVER_API_TOKEN'),
            pushplus_token=os.getenv('PUSHPLUS_TOKEN'),
            custom_webhook_urls=[u.strip() for u in os.getenv('CUSTOM_WEBHOOK_URLS', '').split(',') if u.strip()],
            custom_webhook_bearer_token=os.getenv('CUSTOM_WEBHOOK_BEARER_TOKEN'),
            discord_bot_token=os.getenv('DISCORD_BOT_TOKEN'),
            discord_main_channel_id=os.getenv('DISCORD_MAIN_CHANNEL_ID'),
            astrbot_url=os.getenv('ASTRBOT_URL'),
            astrbot_token=os.getenv('ASTRBOT_TOKEN'),
            line_channel_access_token=os.getenv('LINE_CHANNEL_ACCESS_TOKEN'),
            line_user_id=os.getenv('LINE_USER_ID'),
            line_notify_token=os.getenv('LINE_NOTIFY_TOKEN'),
            single_stock_notify=os.getenv('SINGLE_STOCK_NOTIFY', 'false').lower() == 'true',
            report_type=os.getenv('REPORT_TYPE', 'simple').lower(),
            analysis_delay=float(os.getenv('ANALYSIS_DELAY', '0')),
            feishu_max_bytes=int(os.getenv('FEISHU_MAX_BYTES', '20000')),
            wechat_max_bytes=wechat_max_bytes,
            wechat_msg_type=wechat_msg_type_lower,
            database_path=os.getenv('DATABASE_PATH', './data/stock_analysis.db'),
            save_context_snapshot=os.getenv('SAVE_CONTEXT_SNAPSHOT', 'true').lower() == 'true',
            log_dir=os.getenv('LOG_DIR', './logs'),
            log_level=os.getenv('LOG_LEVEL', 'INFO'),
            max_workers=int(os.getenv('MAX_WORKERS', '3')),
            debug=os.getenv('DEBUG', 'false').lower() == 'true',
            http_proxy=os.getenv('HTTP_PROXY'),
            https_proxy=os.getenv('HTTPS_PROXY'),
            schedule_enabled=os.getenv('SCHEDULE_ENABLED', 'false').lower() == 'true',
            schedule_time=os.getenv('SCHEDULE_TIME', '18:00'),
            market_review_enabled=os.getenv('MARKET_REVIEW_ENABLED', 'true').lower() == 'true',
            webui_enabled=os.getenv('WEBUI_ENABLED', 'false').lower() == 'true',
            webui_host=os.getenv('WEBUI_HOST', '127.0.0.1'),
            webui_port=int(os.getenv('WEBUI_PORT', '8000')),
            # 機器人配置
            bot_enabled=os.getenv('BOT_ENABLED', 'true').lower() == 'true',
            bot_command_prefix=os.getenv('BOT_COMMAND_PREFIX', '/'),
            bot_rate_limit_requests=int(os.getenv('BOT_RATE_LIMIT_REQUESTS', '10')),
            bot_rate_limit_window=int(os.getenv('BOT_RATE_LIMIT_WINDOW', '60')),
            bot_admin_users=[u.strip() for u in os.getenv('BOT_ADMIN_USERS', '').split(',') if u.strip()],
            # 飛書機器人
            feishu_verification_token=os.getenv('FEISHU_VERIFICATION_TOKEN'),
            feishu_encrypt_key=os.getenv('FEISHU_ENCRYPT_KEY'),
            feishu_stream_enabled=os.getenv('FEISHU_STREAM_ENABLED', 'false').lower() == 'true',
            # 釘釘機器人
            dingtalk_app_key=os.getenv('DINGTALK_APP_KEY'),
            dingtalk_app_secret=os.getenv('DINGTALK_APP_SECRET'),
            dingtalk_stream_enabled=os.getenv('DINGTALK_STREAM_ENABLED', 'false').lower() == 'true',
            # 企業微信機器人
            wecom_corpid=os.getenv('WECOM_CORPID'),
            wecom_token=os.getenv('WECOM_TOKEN'),
            wecom_encoding_aes_key=os.getenv('WECOM_ENCODING_AES_KEY'),
            wecom_agent_id=os.getenv('WECOM_AGENT_ID'),
            # Telegram
            telegram_webhook_secret=os.getenv('TELEGRAM_WEBHOOK_SECRET'),
            # Discord 機器人擴充配置
            discord_bot_status=os.getenv('DISCORD_BOT_STATUS', 'A股智能分析 | /help'),
            # 即時行情增強數據配置
            enable_realtime_quote=os.getenv('ENABLE_REALTIME_QUOTE', 'true').lower() == 'true',
            enable_chip_distribution=os.getenv('ENABLE_CHIP_DISTRIBUTION', 'true').lower() == 'true',
            # 即時行情數據源優先級：
            # - tencent: 騰訊財經，有量比/換手率/PE/PB等，單股查詢穩定（推薦）
            # - akshare_sina: 新浪財經，基本行情穩定，但無量比
            # - efinance/akshare_em: 東財全量介面，數據最全但容易被封
            # - tushare: Tushare Pro，需要 2000 積分，數據全面
            realtime_source_priority=os.getenv('REALTIME_SOURCE_PRIORITY', 'tencent,akshare_sina,efinance,akshare_em'),
            realtime_cache_ttl=int(os.getenv('REALTIME_CACHE_TTL', '600')),
            circuit_breaker_cooldown=int(os.getenv('CIRCUIT_BREAKER_COOLDOWN', '300'))
        )
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置單例（主要用於測試）"""
        cls._instance = None

    def refresh_stock_list(self) -> None:
        """
        熱讀取 STOCK_LIST 環境變數並更新配置中的自選股列表
        
        支持兩種配置方式：
        1. .env 文件（本地開發、定時任務模式） - 修改後下次執行自動生效
        2. 系統環境變數（GitHub Actions、Docker） - 啟動時固定，運行中不變
        """
        # 優先從 .env 文件讀取最新配置，這樣即使在容器環境中修改了 .env 文件，
        # 也能獲取到最新的股票列表配置
        env_path = Path(__file__).parent.parent / '.env'
        stock_list_str = ''
        if env_path.exists():
            # 直接從 .env 文件讀取最新的配置
            env_values = dotenv_values(env_path)
            stock_list_str = (env_values.get('STOCK_LIST') or '').strip()

        # 如果 .env 文件不存在或未配置，才嘗試從系統環境變數讀取
        if not stock_list_str:
            stock_list_str = os.getenv('STOCK_LIST', '')

        stock_list = [
            code.strip()
            for code in stock_list_str.split(',')
            if code.strip()
        ]

        if not stock_list:        
            stock_list = ['000001']

        self.stock_list = stock_list
    
    def validate(self) -> List[str]:
        """
        驗證配置完整性
        
        Returns:
            缺失或無效配置項的警告列表
        """
        warnings = []
        
        if not self.stock_list:
            warnings.append("警告：未配置自選股列表 (STOCK_LIST)")
        
        if not self.tushare_token:
            warnings.append("提示：未配置 Tushare Token，將使用其他數據源")
        
        if not self.gemini_api_key and not self.openai_api_key:
            warnings.append("警告：未配置 Gemini 或 OpenAI API Key，AI 分析功能將不可用")
        elif not self.gemini_api_key:
            warnings.append("提示：未配置 Gemini API Key，將使用 OpenAI 兼容 API")
        
        if not self.bocha_api_keys and not self.tavily_api_keys and not self.serpapi_keys:
            warnings.append("提示：未配置搜尋引擎 API Key (Bocha/Tavily/SerpAPI)，新聞搜尋功能將不可用")
        
        # 檢查通知配置
        has_notification = (
            self.wechat_webhook_url or
            self.feishu_webhook_url or
            (self.telegram_bot_token and self.telegram_chat_id) or
            (self.email_sender and self.email_password) or
            (self.pushover_user_key and self.pushover_api_token) or
            self.pushplus_token or
            (self.custom_webhook_urls and self.custom_webhook_bearer_token) or
            (self.discord_bot_token and self.discord_main_channel_id) or
            self.discord_webhook_url or
            self.line_notify_token or
            (self.line_channel_access_token and self.line_user_id)
        )
        if not has_notification:
            warnings.append("提示：未配置通知渠道，將不發送推送通知")
        
        return warnings
    
    def get_db_url(self) -> str:
        """
        獲取 SQLAlchemy 數據庫連接 URL
        
        自動建立數據庫目錄（如果不存在）
        """
        db_path = Path(self.database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_path.absolute()}"


# === 便捷的配置訪問函數 ===
def get_config() -> Config:
    """獲取全域配置實例的快捷方式"""
    return Config.get_instance()


if __name__ == "__main__":
    # 測試配置載入
    config = get_config()
    print("=== 配置載入測試 ===")
    print(f"自選股列表: {config.stock_list}")
    print(f"數據庫路徑: {config.database_path}")
    print(f"最大併發數: {config.max_workers}")
    print(f"偵錯模式: {config.debug}")
    
    # 驗證配置
    warnings = config.validate()
    if warnings:
        print("\n配置驗證結果:")
        for w in warnings:
            print(f"  - {w}")
