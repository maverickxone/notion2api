import time
import threading
from typing import Dict, List

from app.logger import logger
from app.notion_client import NotionOpusAPI

class AccountPool:
    def __init__(self, accounts: List[dict]):
        """
        从配置列表初始化，每个 dict 对应一组凭据。
        同时初始化客户端实例和它们的状态。
        """
        if not accounts:
            raise ValueError("账号池初始化失败：未提供任何账号配置。")
            
        self.clients = [NotionOpusAPI(acc) for acc in accounts]
        # 记录每个客户端的冷却释放时间戳（0 表示可用）
        self.cooldown_until = [0.0 for _ in self.clients]
        
        # 轮询索引
        self._current_index = 0
        self._lock = threading.Lock()
        
    def get_client(self) -> NotionOpusAPI:
        """
        轮询（Round-Robin）返回下一个可用客户端。
        过滤掉正处于冷却期中的客户端。
        若所有客户端均不可用，将抛出异常。
        """
        now = time.time()
        with self._lock:
            start_index = self._current_index
            
            while True:
                idx = self._current_index
                # 如果过了冷却时间，视为可用
                if self.cooldown_until[idx] <= now:
                    # 轮询步进
                    self._current_index = (self._current_index + 1) % len(self.clients)
                    return self.clients[idx]
                    
                # 不可用则顺延
                self._current_index = (self._current_index + 1) % len(self.clients)
                
                # 如果转了一圈都没找到可用的
                if self._current_index == start_index:
                    next_available = min(self.cooldown_until)
                    wait_seconds = max(1, int(next_available - now))
                    raise RuntimeError(
                        f"Notion 账号限流中（触发官方公平使用政策），请在 {wait_seconds} 秒后重试。"
                    )

    def get_status_summary(self) -> Dict[str, int]:
        """返回账号池简要状态，供健康检查和日志使用。"""
        now = time.time()
        with self._lock:
            active = sum(1 for ts in self.cooldown_until if ts <= now)
            cooling = len(self.cooldown_until) - active
            return {
                "total": len(self.clients),
                "active": active,
                "cooling": cooling,
            }
                    
    def mark_failed(self, client: NotionOpusAPI, cooldown_seconds: int = 10):
        """
        标记某个客户端为临时不可用（默认冷却 60 秒后恢复）
        """
        with self._lock:
            try:
                idx = self.clients.index(client)
                # 记录未来的冷却解封时间
                self.cooldown_until[idx] = time.time() + cooldown_seconds
                logger.warning(
                    "Account marked as failed",
                    extra={
                        "request_info": {
                            "event": "account_failed",
                            "account": client.account_key,
                            "space_id": client.space_id,
                            "cooldown_seconds": cooldown_seconds,
                        }
                    },
                )
            except ValueError:
                logger.warning(
                    "Attempted to mark unknown account as failed",
                    extra={"request_info": {"event": "account_failed_unknown"}},
                )
