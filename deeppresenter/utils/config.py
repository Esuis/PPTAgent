import asyncio
import json
import random
from itertools import cycle, product
from math import ceil, gcd, lcm
from pathlib import Path
from typing import Any

import httpx
import json_repair
import yaml
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion
from openai.types.images_response import ImagesResponse
from pydantic import BaseModel, Field, PrivateAttr, ValidationError

from deeppresenter.utils.constants import (
    CONTEXT_LENGTH_LIMIT,
    MCP_CALL_TIMEOUT,
    PACKAGE_DIR,
    PIXEL_MULTIPLE,
    RETRY_TIMES,
)
from deeppresenter.utils.log import debug, info, logging_openai_exceptions


def get_json_from_response(response: str) -> dict | list:
    """
    Extract JSON from a text response.

    Args:
        response (str): The response text.

    Returns:
        Dict|List: The extracted JSON.

    Raises:
        Exception: If JSON cannot be extracted from the response.
    """

    assert isinstance(response, str) and len(response) > 0, (
        "response must be a non-empty string"
    )
    response = response.strip()
    try:
        return json.loads(response)
    except Exception:
        pass

    # Try to find JSON by looking for matching braces
    open_braces = []
    close_braces = []

    for i, char in enumerate(response):
        if char == "{" or char == "[":
            open_braces.append(i)
        elif char == "}" or char == "]":
            close_braces.append(i)

    for i, j in product(open_braces, reversed(close_braces)):
        if i > j:
            continue
        try:
            json_obj = json.loads(response[i : j + 1])
            if isinstance(json_obj, (dict, list)):
                return max(
                    json_obj, json_repair.loads(response), key=lambda x: len(str(x))
                )
        except Exception:
            pass

    return json_repair.loads(response)


class Endpoint(BaseModel):
    """LLM Endpoint Configuration"""

    base_url: str = Field(description="API base URL")
    model: str = Field(description="Model name")
    api_key: str = Field(description="API key")
    client_kwargs: dict[str, Any] = Field(
        default_factory=dict, description="Client parameters"
    )
    sampling_parameters: dict[str, Any] = Field(
        default_factory=dict, description="Sampling parameters"
    )
    _client: AsyncOpenAI = PrivateAttr()

    def model_post_init(self, _) -> None:
        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            **self.client_kwargs,
        )

    async def call(
        self,
        messages: list[dict[str, Any]],
        soft_response_parsing: bool,
        response_format: type[BaseModel] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatCompletion:
        """Execute a chat or tool call using the endpoint client"""
        # 日志：打印模型输入
        debug(f"[Model Input] model={self.model}, base_url={self.base_url}")
        debug(f"[Model Input] messages count={len(messages)}")
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            # 如果 content 是列表（多模态消息），简化打印
            if isinstance(content, list):
                content_summary = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            content_summary.append(f"text: {item.get('text', '')[:100]}..." if len(str(item.get('text', ''))) > 100 else f"text: {item.get('text', '')}")
                        elif item.get("type") == "image_url":
                            content_summary.append("image_url: <base64_image>")
                        else:
                            content_summary.append(f"{item.get('type')}: <content>")
                    else:
                        content_summary.append(str(item)[:100])
                debug(f"[Model Input] message[{i}] role={role}, content={content_summary}")
            else:
                # 文本消息，截断长内容
                content_str = str(content)
                if len(content_str) > 500:
                    debug(f"[Model Input] message[{i}] role={role}, content={content_str[:500]}... (truncated, total {len(content_str)} chars)")
                else:
                    debug(f"[Model Input] message[{i}] role={role}, content={content_str}")
            # 打印 tool_calls
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    debug(f"[Model Input] message[{i}] tool_call: {tc.get('function', {}).get('name', 'unknown')}")
        if tools:
            debug(f"[Model Input] tools count={len(tools)}, tool_names={[t.get('function', {}).get('name', 'unknown') for t in tools]}")
        if response_format:
            debug(f"[Model Input] response_format={response_format}")

        if tools is not None:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                **self.sampling_parameters,
            )
        elif not soft_response_parsing and response_format is not None:
            response: ChatCompletion = await self._client.chat.completions.parse(
                model=self.model,
                messages=messages,
                response_format=response_format,
                **self.sampling_parameters,
            )
        else:
            response: ChatCompletion = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                **self.sampling_parameters,
            )
        assert response.choices is not None and len(response.choices) > 0, (
            f"No choices returned from the model, got {response}"
        )
        message = response.choices[0].message

        # 日志：打印模型输出
        debug(f"[Model Output] model={self.model}")
        debug(f"[Model Output] usage: prompt_tokens={response.usage.prompt_tokens if response.usage else 'N/A'}, completion_tokens={response.usage.completion_tokens if response.usage else 'N/A'}, total_tokens={response.usage.total_tokens if response.usage else 'N/A'}")
        if message.content:
            content_str = str(message.content)
            if len(content_str) > 500:
                debug(f"[Model Output] content={content_str[:500]}... (truncated, total {len(content_str)} chars)")
            else:
                debug(f"[Model Output] content={content_str}")
        if message.tool_calls:
            for tc in message.tool_calls:
                debug(f"[Model Output] tool_call: {tc.function.name}, arguments={tc.function.arguments[:200] if tc.function.arguments and len(tc.function.arguments) > 200 else tc.function.arguments}")
        if hasattr(message, 'reasoning') and message.reasoning:
            reasoning_str = str(message.reasoning)
            if len(reasoning_str) > 200:
                debug(f"[Model Output] reasoning={reasoning_str[:200]}... (truncated)")
            else:
                debug(f"[Model Output] reasoning={reasoning_str}")

        debug(f"Response from {self.model}: {message}")
        if response_format is not None:
            message.content = response_format(
                **get_json_from_response(message.content)
            ).model_dump_json(indent=2)
        assert tools is None or len(message.tool_calls or []), (
            f"No tool call returned from the model, got {message}"
        )
        assert message.tool_calls or message.content, (
            "Empty content returned from the model"
        )
        return response


class LLM(BaseModel):
    """LLM Client Manager"""

    base_url: str | None = Field(default=None, description="API base URL")
    model: str | None = Field(default=None, description="Model name")
    api_key: str | None = Field(default=None, description="API key")
    identifier: str | None = Field(
        default=None,
        description="Optional identifier for the model instance, this will override property `model_name`",
    )
    is_multimodal: bool | None = Field(
        default=None, description="Whether the model is multimodal"
    )
    max_concurrent: int | None = Field(
        default=None, description="Maximum concurrency limit"
    )
    client_kwargs: dict[str, Any] = Field(
        default_factory=dict, description="Client parameters"
    )
    sampling_parameters: dict[str, Any] = Field(
        default_factory=dict, description="Sampling parameters"
    )
    endpoints: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Additional endpoints for alternating retries",
    )
    soft_response_parsing: bool = Field(
        default=False,
        description="Enable soft parsing: parse response content as JSON directly instead of using completion.parse",
    )
    min_image_size: int | None = Field(
        default=None,
        description="Minimum image size (width * height) for generation, smaller images will be resized proportionally",
    )
    secret_logging: bool = Field(
        default=False, description="Logging detailed endpoint (API key included)"
    )
    is_qwen_image_api: bool = Field(
        default=False,
        description="Whether to use Qwen Image Generation API (Dashscope native format)",
    )
    size: str | None = Field(
        default=None,
        description="Image size for Qwen Image API (e.g., '2048*2048')",
    )
    negative_prompt: str | None = Field(
        default=None,
        description="Negative prompt for Qwen Image API",
    )
    prompt_extend: bool | None = Field(
        default=None,
        description="Enable prompt extension for Qwen Image API",
    )
    watermark: bool | None = Field(
        default=None,
        description="Enable watermark for Qwen Image API",
    )

    _semaphore: asyncio.Semaphore = PrivateAttr()
    _endpoints: list[Endpoint] = PrivateAttr(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}

    @property
    def model_name(self) -> str:
        return self.identifier or self._endpoints[0].model.split("/")[-1].split(":")[0]

    def model_post_init(self, context) -> None:
        """Initialize semaphore and endpoints"""
        self._semaphore = asyncio.Semaphore(self.max_concurrent or 10000)
        if self.model:
            self._endpoints.insert(
                0,
                Endpoint(
                    base_url=self.base_url,
                    model=self.model,
                    api_key=self.api_key,
                    client_kwargs=self.client_kwargs,
                    sampling_parameters=self.sampling_parameters,
                ),
            )
        for endpoint in self.endpoints:
            self._endpoints.append(Endpoint(**endpoint))
        assert len(self._endpoints) >= 1, "At least one endpoint must be configured"

        model_lower = self._endpoints[0].model.lower()
        if self.is_multimodal is None:
            if any(word in model_lower for word in ("gpt", "claude", "gemini", "vl")):
                self.is_multimodal = True
                debug(
                    f"Model {self._endpoints[0].model} is detected as multimodal model, setting `is_multimodal` to True"
                )
            else:
                self.is_multimodal = False

        return super().model_post_init(context)

    async def run(
        self,
        messages: list[dict[str, Any]] | str,
        response_format: type[BaseModel] | None = None,
        tools: list[dict[str, Any]] | None = None,
        retry_times: int = RETRY_TIMES,
    ) -> ChatCompletion:
        """Unified interface for chat and tool calls with alternating retry"""
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        errors = []
        iter_endpoints = cycle(self._endpoints)
        async with self._semaphore:
            for _ in range(retry_times):
                endpoint = next(iter_endpoints)
                try:
                    return await endpoint.call(
                        messages,
                        self.soft_response_parsing,
                        response_format,
                        tools,
                    )
                except (AssertionError, ValidationError) as e:
                    errors.append(f"[{endpoint.model}] {e}")
                except Exception as e:
                    errors.append(f"[{endpoint.model}] {e}")
                    if self.secret_logging:
                        identifider = endpoint
                    else:
                        identifider = endpoint.model
                    logging_openai_exceptions(identifider, e)
        raise ValueError(f"All models failed after {retry_times} retries:\n{errors}")

    async def generate_image(
        self,
        prompt: str,
        width: int,
        height: int,
        retry_times: int = RETRY_TIMES,
        pixel_multiple: int = PIXEL_MULTIPLE,
    ) -> ImagesResponse:
        """Unified interface for image generation"""
        # Use Qwen Image API if enabled
        if self.is_qwen_image_api:
            return await self._generate_image_qwen(prompt, width, height, retry_times)

        # Original OpenAI-compatible API
        if self.min_image_size is not None and (width * height) < int(
            self.min_image_size
        ):
            ratio = (int(self.min_image_size) / (width * height)) ** 0.5
            width = int(width * ratio)
            height = int(height * ratio)
        assert (width % PIXEL_MULTIPLE == 0) and (height % PIXEL_MULTIPLE == 0), (
            f"Image width and height must be a multiple of {pixel_multiple}"
        )
        async with self._semaphore:
            errors = []
            random.shuffle(self._endpoints)
            for retry_idx in range(retry_times):
                # t2i is stateless
                endpoint = self._endpoints[retry_idx % len(self._endpoints)]
                try:
                    response = await endpoint._client.images.generate(
                        prompt=prompt,
                        model=endpoint.model,
                        size=f"{width}x{height}",
                        timeout=MCP_CALL_TIMEOUT // 5,
                        **endpoint.sampling_parameters,
                    )
                    assert len(response.data) >= 1, (
                        f"Expected at least an image response, got {response}"
                    )
                    return response

                except (AssertionError, ValidationError) as e:
                    errors.append(f"[{endpoint.model}] {e}")
                except Exception as e:
                    errors.append(f"[{endpoint.model}] {e}")
                    if self.secret_logging:
                        identifider = endpoint
                    else:
                        identifider = endpoint.model
                    logging_openai_exceptions(identifider, e)
            raise ValueError(f"All models failed after {retry_times} retries: {errors}")

    async def _generate_image_qwen(
        self,
        prompt: str,
        width: int,
        height: int,
        retry_times: int = RETRY_TIMES,
    ) -> ImagesResponse:
        """Generate image using Qwen Image Generation API (Dashscope native format)"""
        async with self._semaphore:
            errors = []
            for retry_idx in range(retry_times):
                endpoint = self._endpoints[retry_idx % len(self._endpoints)]
                try:
                    # Prepare the request payload
                    payload = {
                        "model": endpoint.model,
                        "input": {
                            "messages": [
                                {
                                    "role": "user",
                                    "content": [{"text": prompt}]
                                }
                            ]
                        },
                        "parameters": {
                            "size": self.size or f"{width}*{height}",
                            "watermark": self.watermark if self.watermark is not None else False,
                        }
                    }

                    # Add optional parameters
                    if self.negative_prompt:
                        payload["parameters"]["negative_prompt"] = self.negative_prompt
                    if self.prompt_extend is not None:
                        payload["parameters"]["prompt_extend"] = self.prompt_extend

                    # Make the HTTP request
                    async with httpx.AsyncClient(timeout=MCP_CALL_TIMEOUT // 5) as client:
                        response = await client.post(
                            endpoint.base_url,
                            headers={
                                "Content-Type": "application/json",
                                "Authorization": f"Bearer {endpoint.api_key}"
                            },
                            json=payload
                        )
                        response.raise_for_status()
                        result = response.json()

                    # Parse the response
                    if "output" not in result or "choices" not in result["output"]:
                        raise ValueError(f"Invalid response format: {result}")

                    image_url = result["output"]["choices"][0]["message"]["content"][0]["image"]

                    # Convert to OpenAI ImagesResponse format
                    from openai.types.images_response import Image
                    images_response = ImagesResponse(
                        created=int(result.get("usage", {}).get("timestamp", 0)),
                        data=[Image(url=image_url, b64_json=None, revised_prompt=None)]
                    )

                    return images_response

                except (AssertionError, ValidationError) as e:
                    errors.append(f"[{endpoint.model}] {e}")
                except Exception as e:
                    errors.append(f"[{endpoint.model}] {e}")
                    if self.secret_logging:
                        identifider = endpoint
                    else:
                        identifider = endpoint.model
                    logging_openai_exceptions(identifider, e)
            raise ValueError(f"All models failed after {retry_times} retries: {errors}")

    async def validate(self):
        endpoint = self._endpoints[0]
        models = await endpoint._client.models.list()
        # ? This for compatibility with google generative ai
        if not any(model.id.endswith(endpoint.model) for model in models.data):
            raise Exception(
                f"Model {endpoint.model} is not available at {endpoint.base_url}, please check your apikey or {PACKAGE_DIR / 'config.yaml'}\n"
            )


class QueueConfig(BaseModel):
    """Queue Configuration"""

    max_concurrent_tasks: int = Field(
        default=2, description="Maximum concurrent tasks for queue"
    )


class DeepPresenterConfig(BaseModel):
    """DeepPresenter Global Configuration"""

    # config
    offline_mode: bool = Field(
        default=False, description="Enable offline mode, disable all network requests"
    )
    file_path: str = Field(description="Configuration file path")
    mcp_config_file: str = Field(
        description="MCP configuration file", default=PACKAGE_DIR / "mcp.json"
    )
    context_folding: bool = Field(
        default=True, description="Enable context management and auto summarization"
    )
    context_window: int | None = Field(
        default=None,
        description="Context window for context management, if not set, use the default value",
    )
    max_context_folds: int = Field(
        default=5, description="Maximum number of folds for context management"
    )
    heavy_reflect: bool = Field(
        default=False,
        description="Enable heavy reflection, use rendered slide image for reflective design",
    )
    queue: QueueConfig = Field(
        default_factory=QueueConfig, description="Queue configuration"
    )

    # llms
    research_agent: LLM = Field(description="Research agent model configuration")
    design_agent: LLM = Field(description="Design agent model configuration")
    long_context_model: LLM = Field(description="Long context model configuration")
    vision_model: LLM | None = Field(
        default=None, description="Vision model configuration"
    )
    t2i_model: LLM | None = Field(
        default=None, description="Text-to-image model configuration"
    )

    def model_post_init(self, context):
        if self.context_window is None:
            if self.context_folding:
                self.context_window = CONTEXT_LENGTH_LIMIT // self.max_context_folds
            else:
                self.context_window = CONTEXT_LENGTH_LIMIT

        if self.context_folding:
            debug(
                f"Context folding is enabled, context window: {self.context_window}, max folds: {self.max_context_folds}"
            )
        else:
            debug(f"Context folding is disabled, context window: {self.context_window}")

        return super().model_post_init(context)

    @classmethod
    def load_from_file(cls, config_path: str | None = None) -> "DeepPresenterConfig":
        """Load configuration from file"""
        if config_path:
            config_file = Path(config_path)
        else:
            config_file = PACKAGE_DIR / "config.yaml"

        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file {config_file} does not exist")
        config_data = {}
        with open(config_file, encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}

        config_data["file_path"] = str(config_file.resolve())
        return cls(**config_data)

    async def validate_llms(self):
        # ? t2i endpoints might not support this api
        tasks = [
            self.research_agent.validate(),
            self.design_agent.validate(),
            self.long_context_model.validate(),
        ]
        if self.vision_model is not None:
            tasks.append(self.vision_model.validate())
        await asyncio.gather(*tasks)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)
