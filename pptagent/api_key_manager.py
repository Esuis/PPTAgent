"""
API Key Manager - 动态刷新 API Key 管理器

通过定时刷新机制，自动获取并更新 API Key，无需重启容器。
"""

import json
import os
import threading
import time
from typing import Optional

import httpx

from pptagent.utils import get_logger

logger = get_logger(__name__)


class ApiKeyManager:
    """
    API Key 管理器，负责定时刷新 API Key

    配置项（优先级从高到低）：
    1. 构造参数
    2. 环境变量
    3. 默认值

    环境变量：
    - API_KEY_URL: 获取 API Key 的 URL
    - API_KEY_SCENE_CODE: 场景代码
    - API_KEY_REFRESH_INTERVAL: 刷新间隔（秒），默认 1500（25分钟）
    - API_KEY_REFRESH_BUFFER: 提前刷新时间（秒），默认 300（5分钟）
    - API_KEY_INITIAL_KEY: 初始 API Key（可选，用于启动时）
    """

    _instance: Optional["ApiKeyManager"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        key_url: str | None = None,
        scene_code: str | None = None,
        refresh_interval: int | None = None,
        refresh_buffer: int | None = None,
        initial_key: str | None = None,
    ):
        if self._initialized:
            return

        self._initialized = True

        # 配置参数（优先级：构造参数 > 环境变量 > 默认值）
        self._key_url = key_url or os.environ.get(
            "API_KEY_URL",
            "http://eaip-ellm-1.bocomm.com/ELLM.ELLM-OMSERVICE.V-1.0/createSceneApiKey.do",
        )
        self._scene_code = scene_code or os.environ.get("API_KEY_SCENE_CODE", "P2024146")
        self._refresh_interval = refresh_interval or int(
            os.environ.get("API_KEY_REFRESH_INTERVAL", "1500")
        )  # 25分钟
        self._refresh_buffer = refresh_buffer or int(
            os.environ.get("API_KEY_REFRESH_BUFFER", "300")
        )  # 提前5分钟刷新

        # 状态
        self._current_key: str | None = initial_key or os.environ.get("API_KEY_INITIAL_KEY")
        self._expires_at: int | None = None
        self._last_refresh_time: float | None = None
        self._refresh_count: int = 0

        # 线程安全
        self._state_lock = threading.RLock()

        # 启动定时刷新
        self._timer: threading.Timer | None = None
        self._start_timer()

        logger.info(
            f"ApiKeyManager initialized: url={self._key_url}, scene_code={self._scene_code}, "
            f"refresh_interval={self._refresh_interval}s, buffer={self._refresh_buffer}s"
        )

    @classmethod
    def from_config(cls, config: "ApiKeyManagerConfig | None") -> "ApiKeyManager":
        """
        从配置对象创建 ApiKeyManager

        Args:
            config: ApiKeyManagerConfig 配置对象

        Returns:
            ApiKeyManager 实例
        """
        if config is None:
            return cls()

        if not config.enabled:
            # 禁用时返回一个不工作的空实例
            logger.warning("ApiKeyManager is disabled in config")
            return cls()

        return cls(
            key_url=config.key_url,
            scene_code=config.scene_code,
            refresh_interval=config.refresh_interval,
            refresh_buffer=config.refresh_buffer,
        )

    def _build_request_payload(self) -> dict:
        """构建请求 payload"""
        return {
            "REQ_HEAD": {"TRAN_PROCESS": "", "TRAN_ID": ""},
            "REQ_BODY": {"param": {"sceneCode": self._scene_code}},
        }

    def _refresh_key(self) -> bool:
        """
        刷新 API Key

        Returns:
            bool: 刷新是否成功
        """
        with self._state_lock:
            start_time = time.time()
            logger.info("Refreshing API Key...")

            try:
                payload = self._build_request_payload()

                # 使用 httpx 发送请求
                with httpx.Client(timeout=30.0) as client:
                    response = client.post(
                        self._key_url,
                        data={"REQ_MESSAGE": json.dumps(payload)},
                    )
                    response.raise_for_status()

                result = response.json()
                rsp_body = result.get("RSP_BODY", {})
                result_data = rsp_body.get("result", {})

                api_key = result_data.get("apiKey")
                time_to_live = result_data.get("timeToLive")

                if not api_key:
                    logger.error(f"API Key refresh failed: no apiKey in response: {result}")
                    return False

                old_key = self._current_key
                self._current_key = api_key
                self._expires_at = time_to_live
                self._last_refresh_time = start_time
                self._refresh_count += 1

                # 计算距离过期时间的毫秒数
                ttl_ms = time_to_live - int(time.time() * 1000)
                ttl_min = ttl_ms / 60000 if ttl_ms > 0 else 0

                logger.info(
                    f"API Key refreshed successfully: count={self._refresh_count}, "
                    f"TTL={ttl_min:.1f}min, key_prefix={api_key[:8]}..."
                )

                if old_key:
                    logger.debug(f"Key changed: {old_key[:8]}... -> {api_key[:8]}...")

                return True

            except httpx.TimeoutException:
                logger.error("API Key refresh timeout")
                return False
            except httpx.HTTPStatusError as e:
                logger.error(f"API Key refresh HTTP error: {e.response.status_code}")
                return False
            except Exception as e:
                logger.error(f"API Key refresh failed: {e}")
                return False

    def _should_refresh(self) -> bool:
        """检查是否需要刷新 Key"""
        with self._state_lock:
            # 首次加载时需要刷新
            if self._current_key is None:
                return True

            # 如果距离过期时间少于 buffer 时间，提前刷新
            if self._expires_at is not None:
                now_ms = int(time.time() * 1000)
                time_until_expiry = self._expires_at - now_ms
                buffer_ms = self._refresh_buffer * 1000

                if time_until_expiry <= buffer_ms:
                    logger.info(
                        f"API Key expires in {time_until_expiry / 60000:.1f}min, "
                        f"refreshing (buffer={self._refresh_buffer}s)"
                    )
                    return True

            return False

    def _schedule_refresh(self):
        """调度下次刷新"""
        if self._timer is not None:
            self._timer.cancel()

        # 优先使用 TTL 计算下次刷新时间
        if self._expires_at is not None:
            now_ms = int(time.time() * 1000)
            time_until_expiry = self._expires_at - now_ms
            # 提前 buffer 时间刷新，但不能超过 refresh_interval
            interval = max(1, min(time_until_expiry / 1000 - self._refresh_buffer, self._refresh_interval))
        else:
            interval = self._refresh_interval

        self._timer = threading.Timer(interval, self._timer_callback)
        self._timer.daemon = True
        self._timer.start()
        logger.debug(f"Next API Key refresh scheduled in {interval:.0f}s")

    def _timer_callback(self):
        """定时器回调"""
        try:
            if self._should_refresh():
                self._refresh_key()
        except Exception as e:
            logger.error(f"Error in API Key refresh timer: {e}")
        finally:
            self._schedule_refresh()

    def _start_timer(self):
        """启动定时刷新"""
        # 首次检查是否需要立即刷新
        if self._should_refresh():
            self._refresh_key()
        self._schedule_refresh()

    def get_key(self) -> str | None:
        """
        获取当前有效的 API Key

        如果 key 不存在或即将过期，会触发刷新。

        Returns:
            str | None: 当前 API Key，刷新失败时可能返回旧 key
        """
        with self._state_lock:
            if self._should_refresh():
                # 在单独线程中刷新，不阻塞获取
                threading.Thread(target=self._refresh_key, daemon=True).start()

            return self._current_key

    def get_key_sync(self) -> str | None:
        """
        同步获取 API Key（会阻塞直到获取成功或失败）

        Returns:
            str | None: 当前 API Key
        """
        with self._state_lock:
            if self._should_refresh():
                self._refresh_key()

            return self._current_key

    @property
    def refresh_count(self) -> int:
        """获取刷新次数"""
        return self._refresh_count

    @property
    def last_refresh_time(self) -> float | None:
        """获取上次刷新时间"""
        return self._last_refresh_time

    def stop(self):
        """停止定时刷新"""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        logger.info("ApiKeyManager stopped")

    def __del__(self):
        self.stop()


# 全局单例访问函数
def get_api_key_manager() -> ApiKeyManager:
    """获取 ApiKeyManager 单例"""
    return ApiKeyManager()