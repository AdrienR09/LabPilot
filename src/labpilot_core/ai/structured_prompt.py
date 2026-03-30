"""Structured prompt generation and parsing for LabPilot AI."""

from __future__ import annotations

import json
import re
from typing import Any

__all__ = ["StructuredPrompt", "extract_structured_prompt"]


class StructuredPrompt:
    """Represents a structured prompt for user input."""

    def __init__(
        self,
        message: str,
        inputs: list[dict[str, Any]],
        submit_label: str = "Submit"
    ):
        """Initialize structured prompt.

        Args:
            message: Question or instruction for the user
            inputs: List of input field definitions
            submit_label: Text for submit button
        """
        self.message = message
        self.inputs = inputs
        self.submit_label = submit_label

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict format for API response."""
        return {
            "message": self.message,
            "inputs": self.inputs,
            "submitLabel": self.submit_label
        }


def extract_structured_prompt(ai_response: str) -> StructuredPrompt | None:
    """Extract structured prompt from AI response.

    The AI can include a structured prompt by adding a JSON code block
    with the key `__structured_prompt__` at the end of its response.

    Example:
        "I can help you connect a camera. Please provide these details:

        ```json
        {
          "__structured_prompt__": {
            "message": "Which camera would you like to connect?",
            "inputs": [
              {
                "type": "select",
                "id": "camera_type",
                "label": "Camera Type",
                "required": true,
                "options": [
                  {"label": "Andor EMCCD", "value": "andor_sdk2"},
                  {"label": "Basler", "value": "basler"}
                ]
              }
            ]
          }
        }
        ```"

    Args:
        ai_response: Full AI response text

    Returns:
        StructuredPrompt if found, None otherwise
    """
    # First try: Look for JSON code blocks containing __structured_prompt__
    json_pattern = r'```json\s*(.*?)\s*```'
    matches = re.findall(json_pattern, ai_response, re.DOTALL)

    for match in matches:
        try:
            data = json.loads(match)

            if "__structured_prompt__" in data:
                prompt_data = data["__structured_prompt__"]
                return StructuredPrompt(
                    message=prompt_data.get("message"),
                    inputs=prompt_data.get("inputs", []),
                    submit_label=prompt_data.get("submitLabel", "Submit")
                )
        except json.JSONDecodeError:
            # Try lenient extraction if JSON is malformed
            result = _extract_from_malformed_json(match)
            if result:
                return result

    # Second try: Look for raw JSON containing __structured_prompt__ (not in code blocks)
    # Try to find and parse JSON objects that contain the __structured_prompt__ marker
    if "__structured_prompt__" in ai_response:
        # Find the start of JSON (first { after some text or at start)
        json_start = ai_response.find('{')
        if json_start >= 0:
            # Try to extract and parse JSON starting from this position
            for end_pos in range(len(ai_response), json_start, -1):
                try:
                    json_str = ai_response[json_start:end_pos]

                    # Try direct parse first
                    try:
                        data = json.loads(json_str)
                    except json.JSONDecodeError:
                        # If it fails, try fixing common issues
                        # Fix single quotes to double quotes in JSON strings
                        # This is a bit aggressive but necessary for malformed JSON
                        json_str = _fix_malformed_json(json_str)
                        data = json.loads(json_str)

                    if "__structured_prompt__" in data:
                        prompt_data = data["__structured_prompt__"]
                        return StructuredPrompt(
                            message=prompt_data.get("message"),
                            inputs=prompt_data.get("inputs", []),
                            submit_label=prompt_data.get("submitLabel", "Submit")
                        )
                except (json.JSONDecodeError, ValueError):
                    continue

    return None


def _fix_malformed_json(json_str: str) -> str:
    """Attempt to fix common JSON formatting issues."""
    # Replace single quotes with double quotes in JSON values
    # This is a simplified fix - only handles the most common case
    try:
        # Simple fix: replace 'value': \'...\' with "value": "..."
        # But only in value positions, not in keys
        result = json_str

        # Replace single-quoted values: '{"..."}' -> "{\\"...\\\"}"
        result = re.sub(r": '({[^}]*})'", r': "\1"', result)
        result = re.sub(r": '([^']*)'", r': "\1"', result)

        return result
    except Exception:
        return json_str


def _extract_from_malformed_json(text: str) -> StructuredPrompt | None:
    """Attempt to extract structured prompt from malformed JSON.

    Looks for key patterns even if JSON syntax is broken (e.g., comments, incomplete sections).
    """
    try:
        # Look for message field
        message_match = re.search(r'"message"\s*:\s*"([^"]*)"', text)
        message = message_match.group(1) if message_match else "Please provide the required information"

        # Look for inputs array
        inputs = []
        input_pattern = r'"type"\s*:\s*"([^"]*)"[^}]*"id"\s*:\s*"([^"]*)"[^}]*"label"\s*:\s*"([^"]*)"'
        for inp_match in re.finditer(input_pattern, text):
            inp_type, inp_id, inp_label = inp_match.groups()
            inputs.append({
                "type": inp_type,
                "id": inp_id,
                "label": inp_label,
                "required": True
            })

        if inputs:  # Only return if we extracted at least one input
            return StructuredPrompt(
                message=message,
                inputs=inputs,
                submit_label="Submit"
            )
    except Exception:
        pass

    return None


def clean_response_text(ai_response: str) -> str:
    """Remove structured prompt JSON from response text.

    Args:
        ai_response: AI response that may contain structured prompt

    Returns:
        Clean response text without the structured prompt JSON block
    """
    # Try to remove any JSON code blocks that look like structured prompts

    # First approach: Look for markdown code blocks with __structured_prompt__
    json_pattern = r'```json\s*\{[^}]*"__structured_prompt__"[^}]*\}\s*```'
    ai_response = re.sub(json_pattern, '', ai_response, flags=re.DOTALL | re.IGNORECASE)

    # Second approach: Look for raw JSON responses that are just __structured_prompt__
    # If the response STARTS with { and contains __structured_prompt__, it's likely just JSON
    if ai_response.strip().startswith('{') and '"__structured_prompt__"' in ai_response:
        try:
            # Try to find where JSON ends (balanced braces)
            brace_count = 0
            json_end = 0
            for i, char in enumerate(ai_response):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = i + 1
                        break

            # Extract and validate JSON
            potential_json = ai_response[:json_end]
            parsed = json.loads(potential_json)  # If this works, it's valid JSON

            # Verify it has __structured_prompt__ key
            if "__structured_prompt__" in parsed:
                # Remove JSON, keep any remaining text
                remaining = ai_response[json_end:].strip()
                ai_response = remaining
        except (json.JSONDecodeError, ValueError):
            pass  # Not valid JSON, keep original

    # Third approach: More aggressive - remove entire ```json``` blocks if they contain __structured_prompt__
    json_pattern2 = r'```json[\s\S]*?__structured_prompt__[\s\S]*?```'
    ai_response = re.sub(json_pattern2, '', ai_response, flags=re.DOTALL | re.IGNORECASE)

    return ai_response.strip()
