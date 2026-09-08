"""登录/注册防爆破限流（进程内滑动窗口计数器）。

登录按「IP+邮箱」限制单账号爆破、按「IP」限制单机扫号（仅失败计数，
成功清零）；注册按 IP 对所有尝试计数（成功也算，防批量建号）。
多 worker 部署时各进程独立计数（以内存换部署简单），多副本生产环境
建议在网关层（nginx limit_req）统一限流。
"""
import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """线程安全滑动窗口计数器。

    - is_blocked(key)：窗口内计数已达上限则拒绝，返回 (是否超限, 建议等待秒数)
    - record(key)：计数一次（登录失败、注册尝试等）
    - reset(key)：成功登录等场景下清零该 key
    """

    def __init__(self, max_failures: int, window_seconds: float) -> None:
        if max_failures < 1 or window_seconds <= 0:
            raise ValueError("max_failures>=1 且 window_seconds>0")
        self._max = max_failures
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @staticmethod
    def _prune(hits: deque[float], now: float, window: float) -> None:
        while hits and now - hits[0] >= window:
            hits.popleft()

    def is_blocked(self, key: str) -> tuple[bool, int]:
        """返回 (是否已超限, 建议等待秒数)。"""
        now = time.monotonic()
        with self._lock:
            hits = self._hits.get(key)
            if not hits:
                return False, 0
            self._prune(hits, now, self._window)
            if len(hits) < self._max:
                return False, 0
            retry_after = int(self._window - (now - hits[0])) + 1
            return True, max(retry_after, 1)

    def record(self, key: str) -> None:
        """计数一次。"""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            self._prune(hits, now, self._window)
            hits.append(now)

    def reset(self, key: str) -> None:
        """清零该 key 的计数（登录成功等场景）。"""
        with self._lock:
            self._hits.pop(key, None)

    def clear(self) -> None:
        """清空全部状态（测试隔离/运维复位用）。"""
        with self._lock:
            self._hits.clear()
