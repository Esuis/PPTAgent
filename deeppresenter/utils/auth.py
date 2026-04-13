"""
动态API Key认证类
实现httpx.Auth接口，在每次请求时从ApiKeyManager获取最新API Key
"""
from typing import Optional

import httpx


class DynamicApiKeyAuth(httpx.Auth):
    """
    动态API Key认证类
    
    实现httpx.Auth接口，每次请求时动态获取最新的API Key并设置为 api-key 请求头
    """
    
    def __init__(self, api_key_manager):
        """
        初始化认证类
        
        Args:
            api_key_manager: ApiKeyManager单例实例
        """
        super().__init__()
        self.api_key_manager = api_key_manager
    
    def auth_flow(self, request: httpx.Request) -> httpx.Response:
        """
        同步认证流程
        
        在请求头中添加 api-key 字段
        
        Args:
            request: httpx.Request请求对象
            
        Returns:
            httpx.Response: 响应对象
        """
        # 获取当前API Key并设置到请求头
        current_key = self.api_key_manager.get_current_api_key()
        request.headers["api-key"] = current_key
        yield request
    
    async def async_auth_flow(self, request: httpx.Request) -> httpx.Response:
        """
        异步认证流程
        
        在请求头中添加 api-key 字段
        
        Args:
            request: httpx.Request请求对象
            
        Returns:
            httpx.Response: 响应对象
        """
        # 获取当前API Key并设置到请求头
        current_key = self.api_key_manager.get_current_api_key()
        request.headers["api-key"] = current_key
        yield request