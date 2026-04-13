"""
动态API Key管理器
定时刷新API Key，所有大模型调用共享同一个API Key
"""
import asyncio
import threading
import time
from typing import Optional

import httpx

from deeppresenter.utils.log import info, warning, error


def mask_api_key(api_key: str) -> str:
    """脱敏显示API Key，只显示前4位和后4位"""
    if len(api_key) <= 8:
        return api_key[:4] + "****"
    return api_key[:4] + "****" + api_key[-4:]


class ApiKeyManager:
    """
    动态API Key管理器 - 单例模式
    
    定时刷新API Key，提供当前有效的API Key供所有模块使用
    """
    
    _instance: Optional["ApiKeyManager"] = None
    _lock: threading.Lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                return cls._instance
            return cls._instance
    
    def __init__(
        self,
        key_url: str,
        scene_code: str,
        refresh_interval: int = 1500,
        refresh_buffer: int = 300,
    ):
        """
        初始化ApiKeyManager（只在首次创建时执行）
        
        Args:
            key_url: 获取API Key的服务URL
            scene_code: 场景代码
            refresh_interval: 刷新间隔（秒），默认1500秒（25分钟）
            refresh_buffer: 提前刷新时间（秒），默认300秒（5分钟）
        """
        # 只在首次创建时初始化，防止重复初始化
        if hasattr(self, "_initialized") and self._initialized:
            return
            
        self.key_url = key_url
        self.scene_code = scene_code
        self.refresh_interval = refresh_interval
        self.refresh_buffer = refresh_buffer
        
        self._current_api_key: str = ""
        self._last_refresh_time: float = 0
        self._refresh_lock = threading.Lock()
        self._refresh_task: Optional[asyncio.Task] = None
        self._initialized = True
        
        # 初始化时立即获取一次API Key
        asyncio.get_event_loop().run_until_complete(self.refresh_api_key())
        
        # 启动定时刷新任务
        self._start_periodic_refresh()
        info(f"ApiKeyManager initialized, refresh_interval={refresh_interval}s")
    
    @classmethod
    def get_instance(cls) -> "ApiKeyManager":
        """获取单例实例"""
        if cls._instance is None:
            raise RuntimeError("ApiKeyManager not initialized, call create_instance first")
        return cls._instance
    
    @classmethod
    def create_instance(
        cls,
        key_url: str,
        scene_code: str,
        refresh_interval: int = 1500,
        refresh_buffer: int = 300,
    ) -> "ApiKeyManager":
        """创建或获取单例实例"""
        if cls._instance is None:
            cls._instance = cls(key_url, scene_code, refresh_interval, refresh_buffer)
        return cls._instance
    
    @classmethod
    def reset_instance(cls):
        """重置单例实例（主要用于测试）"""
        with cls._lock:
            if cls._instance is not None and hasattr(cls._instance, "_refresh_task"):
                if cls._instance._refresh_task:
                    cls._instance._refresh_task.cancel()
            cls._instance = None
    
    def get_current_api_key(self) -> str:
        """获取当前有效的API Key（线程安全）"""
        with self._refresh_lock:
            return self._current_api_key
    
    async def refresh_api_key(self) -> str:
        """
        刷新API Key
        
        Returns:
            str: 刷新后的API Key
        """
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # 构造请求体
                req_message = {
                    "REQ_HEAD": {"TRAN_PROCESS": "", "TRAN_ID": ""},
                    "REQ_BODY": {
                        "param": {"sceneCode": self.scene_code}
                    }
                }
                
                # multipart/form-data 格式，files参数让httpx自动处理Content-Type
                response = await client.post(
                    self.key_url,
                    data={
                        "REQ_MESSAGE": ("", str(req_message), "application/json")
                    }
                )
                response.raise_for_status()
                
                result = response.json()
                
                # 解析API Key
                api_key = result.get("RSP_BODY", {}).get("result", {}).get("apiKey", "")
                if not api_key:
                    raise ValueError(f"Invalid response: missing apiKey, result={result}")
                
                # 更新API Key（线程安全）
                with self._refresh_lock:
                    old_key = self._current_api_key
                    self._current_api_key = api_key
                    self._last_refresh_time = time.time()
                
                info(
                    f"API Key refreshed successfully, "
                    f"old_key={mask_api_key(old_key) if old_key else 'N/A'}, "
                    f"new_key={mask_api_key(api_key)}"
                )
                
                return api_key
                
        except Exception as e:
            error(f"Failed to refresh API Key: {e}")
            # 如果刷新失败但有旧Key，继续使用旧Key
            with self._refresh_lock:
                if self._current_api_key:
                    warning(f"Using existing API Key after refresh failure")
                    return self._current_api_key
            raise
    
    async def _periodic_refresh_task(self):
        """定时刷新任务"""
        while True:
            try:
                # 计算下次刷新时间
                with self._refresh_lock:
                    time_since_last = time.time() - self._last_refresh_time
                    remaining = self.refresh_interval - time_since_last
                
                # 提前refresh_buffer秒触发刷新
                wait_time = max(remaining - self.refresh_buffer, 60)  # 至少等60秒
                
                await asyncio.sleep(wait_time)
                await self.refresh_api_key()
                
            except asyncio.CancelledError:
                info("Periodic refresh task cancelled")
                break
            except Exception as e:
                error(f"Error in periodic refresh task: {e}")
                # 出错后等待一段时间再重试
                await asyncio.sleep(60)
    
    def _start_periodic_refresh(self):
        """启动定时刷新任务"""
        loop = asyncio.get_event_loop()
        self._refresh_task = loop.create_task(self._periodic_refresh_task())
    
    def trigger_refresh(self):
        """手动触发一次刷新"""
        asyncio.get_event_loop().run_until_complete(self.refresh_api_key())