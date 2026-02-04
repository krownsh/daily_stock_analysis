# -*- coding: utf-8 -*-
"""
===================================
定時調度模組
===================================

職責：
1. 支援每日定時執行股票分析
2. 支援定時執行大盤複盤
3. 優雅處理信號，確保可靠退出

依賴：
- schedule: 輕量級定時任務庫
"""

import logging
import signal
import sys
import time
import threading
from datetime import datetime
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class GracefulShutdown:
    """
    優雅退出處理器
    
    捕獲 SIGTERM/SIGINT 信號，確保任務完成後再退出
    """
    
    def __init__(self):
        self.shutdown_requested = False
        self._lock = threading.Lock()
        
        # 註冊信號處理器
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """信號處理函數"""
        with self._lock:
            if not self.shutdown_requested:
                logger.info(f"收到退出信號 ({signum})，等待當前任務完成...")
                self.shutdown_requested = True
    
    @property
    def should_shutdown(self) -> bool:
        """檢查是否應該退出"""
        with self._lock:
            return self.shutdown_requested


class Scheduler:
    """
    定時任務調度器
    
    基於 schedule 庫實現，支援：
    - 每日定時執行
    - 啟動時立即執行
    - 優雅退出
    """
    
    def __init__(self, schedule_time: str = "18:00"):
        """
        初始化調度器
        
        Args:
            schedule_time: 每日執行時間，格式 "HH:MM"
        """
        try:
            import schedule
            self.schedule = schedule
        except ImportError:
            logger.error("schedule 庫未安裝，請執行: pip install schedule")
            raise ImportError("請安裝 schedule 庫: pip install schedule")
        
        self.schedule_time = schedule_time
        self.shutdown_handler = GracefulShutdown()
        self._task_callback: Optional[Callable] = None
        self._running = False
        
    def set_daily_task(self, task: Callable, run_immediately: bool = True):
        """
        設置每日定時任務
        
        Args:
            task: 要執行的任務函數（無參數）
            run_immediately: 是否在設置後立即執行一次
        """
        self._task_callback = task
        
        # 設置每日定時任務
        self.schedule.every().day.at(self.schedule_time).do(self._safe_run_task)
        logger.info(f"已設置每日定時任務，執行時間: {self.schedule_time}")
        
        if run_immediately:
            logger.info("立即執行一次任務...")
            self._safe_run_task()
    
    def _safe_run_task(self):
        """安全執行任務（帶異常捕獲）"""
        if self._task_callback is None:
            return
        
        try:
            logger.info("=" * 50)
            logger.info(f"定時任務開始執行 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 50)
            
            self._task_callback()
            
            logger.info(f"定時任務執行完成 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
        except Exception as e:
            logger.exception(f"定時任務執行失敗: {e}")
    
    def run(self):
        """
        運行調度器主迴圈
        
        阻塞運行，直到收到退出信號
        """
        self._running = True
        logger.info("調度器開始運行...")
        logger.info(f"下次執行時間: {self._get_next_run_time()}")
        
        while self._running and not self.shutdown_handler.should_shutdown:
            self.schedule.run_pending()
            time.sleep(30)  # 每30秒檢查一次
            
            # 每小時打印一次心跳
            if datetime.now().minute == 0 and datetime.now().second < 30:
                logger.info(f"調度器運行中... 下次執行: {self._get_next_run_time()}")
        
        logger.info("調度器已停止")
    
    def _get_next_run_time(self) -> str:
        """獲取下次執行時間"""
        jobs = self.schedule.get_jobs()
        if jobs:
            next_run = min(job.next_run for job in jobs)
            return next_run.strftime('%Y-%m-%d %H:%M:%S')
        return "未設置"
    
    def stop(self):
        """停止調度器"""
        self._running = False


def run_with_schedule(
    task: Callable,
    schedule_time: str = "18:00",
    run_immediately: bool = True
):
    """
    便捷函數：使用定時調度運行任務
    
    Args:
        task: 要執行的任務函數
        schedule_time: 每日執行時間
        run_immediately: 是否立即執行一次
    """
    scheduler = Scheduler(schedule_time=schedule_time)
    scheduler.set_daily_task(task, run_immediately=run_immediately)
    scheduler.run()


if __name__ == "__main__":
    # 測試定時調度
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
    )
    
    def test_task():
        print(f"任務執行中... {datetime.now()}")
        time.sleep(2)
        print("任務完成!")
    
    print("啟動測試調度器（按 Ctrl+C 退出）")
    run_with_schedule(test_task, schedule_time="23:59", run_immediately=True)
