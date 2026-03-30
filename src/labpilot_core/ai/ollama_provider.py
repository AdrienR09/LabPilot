"""Ollama AI provider implementation.

Local AI provider using Ollama for workflow generation and assistance.
Supports streaming responses and tool calling with fallback to structured output.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from labpilot_core.ai.provider import (
    AIMessage,
    AIProviderError,
    AIResponse,
    AITool,
    AIToolCall,
)

__all__ = ["OllamaProvider"]


class OllamaProvider:
    """Ollama AI provider for local LLM inference.

    Features:
    - Async HTTP client for Ollama API
    - Streaming and non-streaming completion
    - Tool calling with native support + XML fallback
    - Health checking and model management
    - Configurable host/port/model

    Recommended models for LabPilot:
    - mistral:7b - Default, better reasoning for function calling
    - qwen2.5-coder:7b - Best for code generation
    - llama3.1:8b - Alternative for conversation
    """

    def __init__(
        self,
        host: str = "http://localhost:11434",
        default_model: str = "mistral",
        timeout: float = 120.0,
    ):
        """Initialize Ollama provider.

        Args:
            host: Ollama server URL.
            default_model: Default model name.
            timeout: Request timeout in seconds.
        """
        self.host = host.rstrip("/")
        self.default_model = default_model
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        """Provider name."""
        return "ollama"

    @property
    def supports_tools(self) -> bool:
        """Ollama supports tool calling in newer versions."""
        return True

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            )
        return self._client

    async def complete(
        self,
        messages: list[AIMessage],
        tools: list[AITool] | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AIResponse:
        """Generate completion using Ollama API."""
        client = await self._get_client()
        model = model or self.default_model

        # Use very low temperature for tool calling (more deterministic)
        if tools:
            temperature = 0.01  # Almost deterministic

        # Convert messages to Ollama format
        ollama_messages = self._convert_messages(messages)

        # Build request payload
        payload = {
            "model": model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        # Add max tokens if specified
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        # Add tools if supported
        if tools and self.supports_tools:
            payload["tools"] = self._convert_tools(tools)
            print(f"[DEBUG] Sending {len(tools)} tools to Ollama")
            # Log system message
            for msg in ollama_messages:
                if msg.get('role') == 'system':
                    print(f"[DEBUG] System prompt (first 300 chars): {msg.get('content', '')[:300]}")
                    break

        try:
            response = await client.post(f"{self.host}/api/chat", json=payload)
            response.raise_for_status()

            result = response.json()
            return self._parse_response(result, model)

        except httpx.HTTPStatusError as e:
            raise AIProviderError(
                f"Ollama API error: {e.response.status_code} {e.response.text}",
                provider="ollama",
                model=model,
            )
        except Exception as e:
            raise AIProviderError(f"Ollama request failed: {e}", provider="ollama", model=model)

    async def stream_complete(
        self,
        messages: list[AIMessage],
        tools: list[AITool] | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream completion tokens from Ollama."""
        client = await self._get_client()
        model = model or self.default_model

        # Convert messages
        ollama_messages = self._convert_messages(messages)

        # Build streaming request
        payload = {
            "model": model,
            "messages": ollama_messages,
            "stream": True,
            "options": {
                "temperature": temperature,
            },
        }

        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        if tools and self.supports_tools:
            payload["tools"] = self._convert_tools(tools)

        try:
            async with client.stream("POST", f"{self.host}/api/chat", json=payload) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if line.strip():
                        try:
                            chunk = json.loads(line)
                            if "message" in chunk and "content" in chunk["message"]:
                                content = chunk["message"]["content"]
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue

        except httpx.HTTPStatusError as e:
            raise AIProviderError(
                f"Ollama streaming error: {e.response.status_code}",
                provider="ollama",
                model=model,
            )
        except Exception as e:
            raise AIProviderError(f"Ollama streaming failed: {e}", provider="ollama", model=model)

    async def health_check(self) -> bool:
        """Check Ollama server health."""
        try:
            client = await self._get_client()
            response = await client.get(f"{self.host}/api/tags", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        """List available models on Ollama server.

        Returns:
            List of model names.
        """
        try:
            client = await self._get_client()
            response = await client.get(f"{self.host}/api/tags")
            response.raise_for_status()

            data = response.json()
            return [model["name"] for model in data.get("models", [])]
        except Exception as e:
            raise AIProviderError(f"Failed to list models: {e}", provider="ollama")

    async def pull_model(self, model: str) -> None:
        """Pull/download a model to Ollama.

        Args:
            model: Model name to pull (e.g., "llama3.1:8b").
        """
        try:
            client = await self._get_client()

            # Start model pull
            payload = {"name": model}
            response = await client.post(f"{self.host}/api/pull", json=payload)
            response.raise_for_status()

        except httpx.HTTPStatusError as e:
            raise AIProviderError(
                f"Failed to pull model {model}: {e.response.status_code}",
                provider="ollama",
            )
        except Exception as e:
            raise AIProviderError(f"Model pull failed: {e}", provider="ollama")

    def _convert_messages(self, messages: list[AIMessage]) -> list[dict[str, Any]]:
        """Convert AIMessage to Ollama message format."""
        ollama_messages = []

        for msg in messages:
            ollama_msg = {
                "role": msg.role,
                "content": msg.content,
            }

            # Add tool calls/results if present
            if msg.tool_calls:
                ollama_msg["tool_calls"] = msg.tool_calls
            if msg.tool_results:
                ollama_msg["tool_results"] = msg.tool_results

            ollama_messages.append(ollama_msg)

        return ollama_messages

    def _convert_tools(self, tools: list[AITool]) -> list[dict[str, Any]]:
        """Convert AITool to Ollama tool format."""
        ollama_tools = []

        for tool in tools:
            ollama_tool = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
            }
            ollama_tools.append(ollama_tool)

        return ollama_tools

    def _parse_response(self, result: dict[str, Any], model: str) -> AIResponse:
        """Parse Ollama API response to AIResponse."""
        message = result.get("message", {})
        content = message.get("content", "")

        print(f"[DEBUG] Raw response content: {content[:400]}...")
        print(f"[DEBUG] Parsing response - has tool_calls key: {'tool_calls' in message}")
        if 'tool_calls' in message:
            print(f"[DEBUG] Tool calls found: {len(message['tool_calls'])}")

        # Extract tool calls if present
        tool_calls = []

        # First try: Check if Ollama provided native tool_calls
        if "tool_calls" in message:
            for tc in message["tool_calls"]:
                if "function" in tc:
                    func = tc["function"]
                    tool_calls.append(AIToolCall(
                        id=tc.get("id", f"call_{int(time.time())}"),
                        name=func["name"],
                        parameters=func.get("arguments", {}),
                    ))

        # Second try: Parse tool calls from content if model generated JSON
        if not tool_calls and content:
            import json
            import re

            print("[DEBUG] === ATTEMPTING JSON EXTRACTION ===")
            print(f"[DEBUG] Content preview: {content[:150]}...")
            print(f"[DEBUG] Content starts with '[': {content.strip().startswith('[')}")
            print(f"[DEBUG] Content ends with ']': {content.strip().endswith(']')}")

            # Try 1: Look for JSON arrays/objects at the start of the content (most reliable for Mistral)
            if content.strip().startswith('[') or content.strip().startswith('{'):
                print("[DEBUG] Content starts with JSON marker")
                try:
                    # Find the first complete JSON structure
                    content_stripped = content.strip()

                    # Try to find JSON array first
                    if content_stripped.startswith('['):
                        print("[DEBUG] Parsing as JSON array")
                        # Find the closing bracket - properly handle nesting
                        bracket_count = 0
                        end_idx = 0
                        in_string = False
                        escape_next = False

                        for i, char in enumerate(content_stripped):
                            if escape_next:
                                escape_next = False
                                continue
                            if char == '\\':
                                escape_next = True
                                continue
                            if char == '"' and not escape_next:
                                in_string = not in_string
                                continue
                            if not in_string:
                                if char == '[':
                                    bracket_count += 1
                                elif char == ']':
                                    bracket_count -= 1
                                    if bracket_count == 0:
                                        end_idx = i + 1
                                        break

                        if end_idx > 0:
                            json_str = content_stripped[:end_idx]
                            print(f"[DEBUG] Extracted JSON array: {json_str[:100]}...")
                            tool_array = json.loads(json_str)

                            if isinstance(tool_array, list):
                                print(f"[DEBUG] Array has {len(tool_array)} items")
                                for tool_item in tool_array:
                                    if isinstance(tool_item, dict) and "name" in tool_item:
                                        print(f"[DEBUG] ✅ Found tool: {tool_item['name']}")
                                        tool_calls.append(AIToolCall(
                                            id=f"call_{int(time.time())}_{len(tool_calls)}",
                                            name=tool_item["name"],
                                            parameters=tool_item.get("arguments", tool_item.get("parameters", {})),
                                        ))
                                    else:
                                        print(f"[DEBUG] Item missing 'name': {tool_item}")

                    # Try as single JSON object if array parsing failed
                    elif content_stripped.startswith('{') and not tool_calls:
                        print("[DEBUG] Parsing as JSON object")
                        # Find the closing brace - properly handle nesting
                        brace_count = 0
                        end_idx = 0
                        in_string = False
                        escape_next = False

                        for i, char in enumerate(content_stripped):
                            if escape_next:
                                escape_next = False
                                continue
                            if char == '\\':
                                escape_next = True
                                continue
                            if char == '"' and not escape_next:
                                in_string = not in_string
                                continue
                            if not in_string:
                                if char == '{':
                                    brace_count += 1
                                elif char == '}':
                                    brace_count -= 1
                                    if brace_count == 0:
                                        end_idx = i + 1
                                        break

                        if end_idx > 0:
                            json_str = content_stripped[:end_idx]
                            print(f"[DEBUG] Extracted JSON object: {json_str[:100]}...")
                            tool_json = json.loads(json_str)

                            if "name" in tool_json:
                                print(f"[DEBUG] ✅ Found tool: {tool_json['name']}")
                                tool_calls.append(AIToolCall(
                                    id=f"call_{int(time.time())}_{len(tool_calls)}",
                                    name=tool_json["name"],
                                    parameters=tool_json.get("arguments", tool_json.get("parameters", {})),
                                ))
                            else:
                                print(f"[DEBUG] Object missing 'name' key: {tool_json}")

                except json.JSONDecodeError as e:
                    print(f"[DEBUG] ❌ JSON decode error: {e}")
                except Exception as e:
                    print(f"[DEBUG] ❌ Unexpected error: {e}")
                    import traceback
                    traceback.print_exc()

            # Try 2: Look for JSON in code blocks (markdown format)
            if not tool_calls:
                print("[DEBUG] Trying to extract JSON from code blocks")
                json_patterns = [
                    r'```json\s*(\[[\s\S]*?\])\s*```',  # JSON arrays in code blocks
                    r'```json\s*(\{[\s\S]*?\})\s*```',   # JSON objects in code blocks
                    r'```\s*(\[[\s\S]*?\])\s*```',        # Arrays without json tag
                    r'```\s*(\{[\s\S]*?\})\s*```',        # Objects without json tag
                ]

                for pattern in json_patterns:
                    matches = re.findall(pattern, content, re.DOTALL)
                    if matches:
                        print(f"[DEBUG] Found {len(matches)} matches with pattern")

                    for match in matches:
                        try:
                            parsed = json.loads(match.strip())

                            if isinstance(parsed, list):
                                for tool_item in parsed:
                                    if isinstance(tool_item, dict) and "name" in tool_item:
                                        print(f"[DEBUG] ✅ Extracted tool from code: {tool_item['name']}")
                                        tool_calls.append(AIToolCall(
                                            id=f"call_{int(time.time())}_{len(tool_calls)}",
                                            name=tool_item["name"],
                                            parameters=tool_item.get("arguments", tool_item.get("parameters", {})),
                                        ))
                            elif isinstance(parsed, dict) and "name" in parsed:
                                print(f"[DEBUG] ✅ Extracted tool from code: {parsed['name']}")
                                tool_calls.append(AIToolCall(
                                    id=f"call_{int(time.time())}_{len(tool_calls)}",
                                    name=parsed["name"],
                                    parameters=parsed.get("arguments", parsed.get("parameters", {})),
                                ))
                        except (json.JSONDecodeError, Exception) as e:
                            print(f"[DEBUG] Code block parse error: {e}")

                    if tool_calls:
                        print(f"[DEBUG] Successfully extracted {len(tool_calls)} tools from code blocks")
                        break

        # Extract usage stats if available
        usage = None
        if "usage" in result:
            usage = result["usage"]

        print("[DEBUG] === FINAL PARSING RESULT ===")
        print(f"[DEBUG] Tool calls extracted: {len(tool_calls)}")
        for i, tc in enumerate(tool_calls):
            print(f"[DEBUG]   {i}: {tc.name} with {tc.parameters}")
        print(f"[DEBUG] Response content (first 200 chars): {content[:200]}")

        return AIResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=result.get("done_reason", "stop"),
            usage=usage,
            model=model,
            provider="ollama",
        )

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
