import base64
import re
from dataclasses import dataclass

from openai import AsyncOpenAI, OpenAI
from pydantic import BaseModel

from pptagent.utils import get_json_from_response, get_logger, tenacity_decorator

logger = get_logger(__name__)
MAX_CONTEXT_SIZE = 32768


@dataclass
class LLM:
    """
    A wrapper class to interact with a language model.
    """

    model: str
    base_url: str | None = None
    api_key: str | None = None
    timeout: int = 360

    def __post_init__(self):
        self.client = OpenAI(
            base_url=self.base_url, api_key=self.api_key, timeout=self.timeout
        )

    @tenacity_decorator
    def __call__(
        self,
        content: str,
        images: str | list[str] | None = None,
        system_message: str | None = None,
        history: list | None = None,
        return_json: bool = False,
        return_message: bool = False,
        response_format: BaseModel | None = None,
        **client_kwargs,
    ) -> str | dict | list | tuple:
        """
        Call the language model with a prompt and optional images.

        Args:
            content (str): The prompt content.
            images (str or list[str]): An image file path or list of image file paths.
            system_message (str): The system message.
            history (list): The conversation history.
            return_json (bool): Whether to return the response as JSON.
            return_message (bool): Whether to return the message.
            **client_kwargs: Additional keyword arguments to pass to the client.

        Returns:
            Union[str, Dict, List, Tuple]: The response from the model.
        """
        if history is None:
            history = []
        system, message = self.format_message(content, images, system_message)
        try:
            # 统一使用流式请求，收集完整响应后返回
            if response_format is not None:
                # 流式不支持 response_format，用流式请求获取后解析
                stream_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=system + history + message,
                    response_format=response_format,
                    stream=True,
                    **client_kwargs,
                )
            else:
                stream_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=system + history + message,
                    stream=True,
                    **client_kwargs,
                )
            # 收集流式响应
            response = self._collect_stream_response(stream_response, message)
            return self.__post_process__(response, message, return_json, return_message)

        except Exception as e:
            logger.warning("Error in LLM (%s) service: %s", self.model, e)
            raise e

    def _collect_stream_response(self, stream_response, message: list) -> str:
        """
        Collect streaming response and return complete content.
        
        Args:
            stream_response: The streaming response from the API.
            message (list): The message history.
            
        Returns:
            str: The complete response content.
        """
        full_response = []
        for chunk in stream_response:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_response.append(content)
        
        # 保存完整响应到消息历史
        response = "".join(full_response)
        message.append({"role": "assistant", "content": response})
        return response

    def __post_process__(
        self,
        response: str,
        message: list,
        return_json: bool = False,
        return_message: bool = False,
    ) -> str | dict | tuple:
        """
        Process the response based on return options.

        Args:
            response (str): The raw response from the model.
            message (List): The message history.
            return_json (bool): Whether to return the response as JSON.
            return_message (bool): Whether to return the message.

        Returns:
            Union[str, Dict, Tuple]: Processed response.
        """
        response = response.strip()
        if return_json:
            response = get_json_from_response(response)
        if return_message:
            response = (response, message)
        return response

    def __repr__(self) -> str:
        repr_str = f"{self.__class__.__name__}(model={self.model}"
        if self.base_url is not None:
            repr_str += f", base_url={self.base_url}"
        return repr_str + ")"

    def test_connection(self) -> bool:
        """
        Test the connection to the LLM.

        Returns:
            bool: True if connection is successful, False otherwise.
        """
        try:
            self.client.models.list()
            return True
        except Exception as e:
            logger.warning(
                "Connection test failed: %s\nLLM: %s: %s, %s",
                e,
                self.model,
                self.base_url,
                self.api_key,
            )
            return False

    def format_message(
        self,
        content: str,
        images: str | list[str] | None = None,
        system_message: str | None = None,
    ) -> tuple[list, list]:
        """
        Format messages for OpenAI server call.

        Args:
            content (str): The prompt content.
            images (str or list[str]): An image file path or list of image file paths.
            system_message (str): The system message.

        Returns:
            Tuple[List, List]: Formatted system and user messages.
        """
        if isinstance(images, str):
            images = [images]
        if len(content) > MAX_CONTEXT_SIZE:
            logger.info(f"Input sequence might be too long: {len(content)}")
        if system_message is None:
            if content.startswith("You are"):
                system_message, content = content.split("\n", 1)
            else:
                system_message = "You are a helpful assistant"
        system = [
            {
                "role": "system",
                "content": [{"type": "text", "text": system_message}],
            }
        ]
        message = [{"role": "user", "content": [{"type": "text", "text": content}]}]
        model_idf = self.model.lower()
        if "qwen3" in model_idf or "deepseek" in model_idf:
            system = []
            message[0]["content"][0]["text"] = (
                system_message + message[0]["content"][0]["text"]
            )
        if images is not None:
            for image in images:
                try:
                    with open(image, "rb") as f:
                        message[0]["content"].append(
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode('utf-8')}"
                                },
                            }
                        )
                except Exception as e:
                    logger.error("Failed to load image %s: %s", image, e)
        return system, message

    def gen_image(self, prompt: str, n: int = 1, **kwargs) -> str:
        """
        Generate an image from a prompt.
        """
        return (
            self.client.images.generate(model=self.model, prompt=prompt, n=n, **kwargs)
            .data[0]
            .b64_json
        )

    def to_async(self) -> "AsyncLLM":
        """
        Convert the LLM to an asynchronous LLM.
        """
        return AsyncLLM(
            model=self.model,
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
        )


@dataclass
class AsyncLLM(LLM):
    """
    Asynchronous wrapper class for language model interaction.
    """

    def __post_init__(self):
        """
        Initialize the AsyncLLM.

        Args:
            model (str): The model name.
            base_url (str): The base URL for the API.
            api_key (str): API key for authentication. Defaults to environment variable.
        """
        self.client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
        )

    @tenacity_decorator
    async def __call__(
        self,
        content: str,
        images: str | list[str] | None = None,
        system_message: str | None = None,
        history: list | None = None,
        return_json: bool = False,
        return_message: bool = False,
        response_format: BaseModel | None = None,
        **client_kwargs,
    ) -> str | dict | tuple:
        """
        Asynchronously call the language model with a prompt and optional images.
    
        Args:
            content (str): The prompt content.
            images (str or list[str]): An image file path or list of image file paths.
            system_message (str): The system message.
            history (list): The conversation history.
            return_json (bool): Whether to return the response as JSON.
            return_message (bool): Whether to return the message.
            response_format (BaseModel): The response format for structured output.
            **client_kwargs: Additional keyword arguments to pass to the client.
    
        Returns:
            Union[str, Dict, Tuple]: The response from the model.
        """
        if history is None:
            history = []
        system, message = self.format_message(content, images, system_message)
        try:
            # 统一使用流式请求，收集完整响应后返回
            if response_format is not None:
                stream_response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=system + history + message,
                    response_format=response_format,
                    stream=True,
                    **client_kwargs,
                )
            else:
                stream_response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=system + history + message,
                    stream=True,
                    **client_kwargs,
                )
            # 收集流式响应
            response = await self._async_collect_stream_response(stream_response, message)
            return self.__post_process__(response, message, return_json, return_message)
    
        except Exception as e:
            logger.error("Error in AsyncLLM call: %s", e)
            raise e

    async def _async_collect_stream_response(self, stream_response, message: list) -> str:
        """
        Collect async streaming response and return complete content.
        
        Args:
            stream_response: The async streaming response from the API.
            message (list): The message history.
            
        Returns:
            str: The complete response content.
        """
        full_response = []
        async for chunk in stream_response:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_response.append(content)
        
        # 保存完整响应到消息历史
        response = "".join(full_response)
        message.append({"role": "assistant", "content": response})
        return response

    def __getstate__(self):
        state = self.__dict__.copy()
        state["client"] = None
        return state

    def __setstate__(self, state: dict):
        self.__dict__.update(state)
        self.client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
        )

    async def test_connection(self) -> bool:
        """
        Test the connection to the LLM asynchronously.

        Returns:
            bool: True if connection is successful, False otherwise.
        """
        try:
            models = await self.client.models.list()
            return any(model.id == self.model for model in models.data)
        except Exception as e:
            logger.warning(
                "Async connection test failed: %s\nLLM: %s: %s, %s",
                e,
                self.model,
                self.base_url,
                self.api_key,
            )
            return False

    async def gen_image(self, prompt: str, n: int = 1, **kwargs) -> str:
        """
        Generate an image from a prompt asynchronously.

        Args:
            prompt (str): The text prompt to generate an image from.
            n (int): Number of images to generate.
            **kwargs: Additional keyword arguments for image generation.

        Returns:
            str: Base64-encoded image data.
        """
        response = await self.client.images.generate(
            model=self.model, prompt=prompt, n=n, response_format="b64_json", **kwargs
        )
        return response.data[0].b64_json

    def to_sync(self) -> LLM:
        """
        Convert the AsyncLLM to a synchronous LLM.
        """
        return LLM(model=self.model, base_url=self.base_url, api_key=self.api_key)


def get_model_abbr(llms: LLM | list[LLM]) -> str:
    """
    Get abbreviated model names from LLM instances.

    Args:
        llms: A single LLM instance or a list of LLM instances.

    Returns:
        str: Abbreviated model names joined with '+'.
    """
    # Convert single LLM to list for consistent handling
    if isinstance(llms, LLM):
        llms = [llms]

    try:
        # Attempt to extract model names before version numbers
        return "+".join(re.search(r"^(.*?)-\d{2}", llm.model).group(1) for llm in llms)
    except Exception:
        # Fallback: return full model names if pattern matching fails
        return "+".join(llm.model for llm in llms)
