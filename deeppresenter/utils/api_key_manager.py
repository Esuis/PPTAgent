"""Dynamic API Key Manager for periodic key refresh.

This module provides a singleton ApiKeyManager that periodically fetches
a new API key from an external service, and a DynamicApiKeyAuth that
injects the current key into every HTTP request as an `api-key` header
(replacing OpenAI SDK's default `Authorization: Bearer` header).
"""

import json
import threading

import httpx
import requests

from deeppresenter.utils.log import debug, error, info, warning

# Module-level reference to the active ApiKeyManager instance
_active_manager: "ApiKeyManager | None" = None


def set_active_manager(manager: "ApiKeyManager"):
    """Set the active ApiKeyManager instance (called during initialization)."""
    global _active_manager
    _active_manager = manager


def get_active_manager() -> "ApiKeyManager":
    """Get the active ApiKeyManager instance."""
    if _active_manager is None:
        raise RuntimeError(
            "ApiKeyManager has not been initialized. "
            "Ensure api_key_manager is configured in config.yaml with enabled=true."
        )
    return _active_manager


class ApiKeyManager:

    def __init__(
        self,
        key_url: str,
        scene_code: str,
        refresh_interval: int = 1500,
        refresh_buffer: int = 300,
    ):
        self._key_url = key_url
        self._scene_code = scene_code
        self._refresh_interval = refresh_interval
        self._refresh_buffer = refresh_buffer
        self._api_key: str | None = None
        self._key_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._refresh_thread: threading.Thread | None = None

    @classmethod
    def from_config(cls, config: "ApiKeyManagerConfig") -> "ApiKeyManager":  # noqa: F821
        """Create an ApiKeyManager instance from an ApiKeyManagerConfig."""
        return cls(
            key_url=config.key_url,
            scene_code=config.scene_code,
            refresh_interval=config.refresh_interval,
            refresh_buffer=config.refresh_buffer,
        )

    def start(self):
        """Start the manager: fetch key immediately, then start background refresh."""
        actual_interval = self._refresh_interval - self._refresh_buffer
        info(
            f"[ApiKeyManager] Starting, key_url={self._key_url}, "
            f"scene_code={self._scene_code}, "
            f"refresh_interval={self._refresh_interval}s, "
            f"refresh_buffer={self._refresh_buffer}s, "
            f"actual_refresh_cycle={actual_interval}s"
        )
        set_active_manager(self)
        self.refresh_key()
        self._refresh_thread = threading.Thread(
            target=self._background_refresh,
            args=(actual_interval,),
            daemon=True,
            name="ApiKeyRefreshThread",
        )
        self._refresh_thread.start()
        info(
            f"[ApiKeyManager] Background refresh thread started, "
            f"refresh every {actual_interval}s"
        )

    def stop(self):
        """Stop the background refresh thread."""
        self._stop_event.set()
        if self._refresh_thread and self._refresh_thread.is_alive():
            self._refresh_thread.join(timeout=5)
        info("[ApiKeyManager] Stopped")

    def get_api_key(self) -> str:
        """Thread-safe access to the current API key."""
        with self._key_lock:
            if self._api_key is None:
                error(
                    "[ApiKeyManager] API key is not available! "
                    "Attempted to get key before initial fetch succeeded."
                )
                raise RuntimeError("API key not available")
            return self._api_key

    def refresh_key(self):
        """Immediately refresh the API key from the server."""
        new_key = self._fetch_key_from_server()
        if new_key is not None:
            with self._key_lock:
                old_key = self._api_key
                self._api_key = new_key
            masked_new = (
                f"{new_key[:8]}...{new_key[-4:]}" if len(new_key) > 12 else "***"
            )
            masked_old = (
                f"{old_key[:8]}...{old_key[-4:]}"
                if old_key and len(old_key) > 12
                else "None"
            )
            info(
                f"[ApiKeyManager] API key refreshed successfully. "
                f"old_key={masked_old}, new_key={masked_new}"
            )
        else:
            warning(
                "[ApiKeyManager] Failed to refresh API key, "
                "keeping the existing key"
            )

    def _fetch_key_from_server(self) -> str | None:
        """Fetch a new API key from the configured server."""
        try:
            req_message = json.dumps(
                {
                    "REQ_HEAD": {"TRAN_PROCESS": "", "TRAN_ID": ""},
                    "REQ_BODY": {"param": {"sceneCode": self._scene_code}},
                }
            )
            debug(f"[ApiKeyManager] Fetching key from {self._key_url}")
            response = requests.post(
                self._key_url,
                # headers={"content-type": "multipart/form-data"},
                data={"REQ_MESSAGE": (None, req_message)},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            result = data.get("RSP_BODY", {}).get("result", {})
            api_key = result.get("apiKey")
            ttl = result.get("timeToLive")
            tran_success = data.get("RSP_HEAD", {}).get("TRAN_SUCCESS")

            if tran_success == "1" and api_key:
                info(
                    f"[ApiKeyManager] Key fetched from server, "
                    f"ttl={ttl}, sceneCode={self._scene_code}"
                )
                return api_key
            else:
                error(
                    f"[ApiKeyManager] Server returned unsuccessful response: "
                    f"TRAN_SUCCESS={tran_success}, data={json.dumps(data)[:200]}"
                )
                return None

        except requests.Timeout:
            error(f"[ApiKeyManager] Timeout fetching key from {self._key_url}")
            return None
        except requests.RequestException as e:
            error(f"[ApiKeyManager] HTTP error fetching key: {e}")
            return None
        except (KeyError, json.JSONDecodeError) as e:
            error(f"[ApiKeyManager] Failed to parse key response: {e}")
            return None

    def _background_refresh(self, interval: int):
        """Background loop that refreshes the key at regular intervals."""
        while not self._stop_event.wait(timeout=interval):
            debug("[ApiKeyManager] Scheduled refresh triggered")
            self.refresh_key()


class DynamicApiKeyAuth(httpx.Auth):
    """httpx Auth that dynamically injects the current API key from ApiKeyManager.

    On every HTTP request:
    1. Removes the `Authorization` header that OpenAI SDK adds by default.
    2. Adds the `api-key` header with the current value from ApiKeyManager.
    """

    def auth_flow(self, request: httpx.Request):
        # Remove OpenAI SDK's default Authorization header
        if "authorization" in request.headers:
            del request.headers["authorization"]
        # Inject custom api-key header from active manager
        api_key = get_active_manager().get_api_key()
        request.headers["api-key"] = api_key
        yield request


def create_openai_client(
    base_url: str,
    use_dynamic_key: bool = False,
    api_key: str | None = None,
    timeout: int = 360,
    is_async: bool = True,
    **client_kwargs,
):
    """Create an OpenAI client, optionally with dynamic API key injection.

    Args:
        base_url: API base URL.
        use_dynamic_key: If True, use DynamicApiKeyAuth for per-request key injection.
        api_key: Static API key (used when use_dynamic_key is False).
        timeout: Request timeout in seconds.
        is_async: Whether to create an async client.
        **client_kwargs: Additional keyword arguments for the OpenAI client.

    Returns:
        AsyncOpenAI or OpenAI client instance.
    """
    from openai import AsyncOpenAI, OpenAI

    if use_dynamic_key:
        if is_async:
            http_client = httpx.AsyncClient(auth=DynamicApiKeyAuth())
        else:
            http_client = httpx.Client(auth=DynamicApiKeyAuth())
        client_cls = AsyncOpenAI if is_async else OpenAI
        return client_cls(
            api_key="placeholder",  # Placeholder, actual key injected by DynamicApiKeyAuth
            base_url=base_url,
            timeout=timeout,
            http_client=http_client,
            **client_kwargs,
        )
    else:
        client_cls = AsyncOpenAI if is_async else OpenAI
        return client_cls(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            **client_kwargs,
        )
