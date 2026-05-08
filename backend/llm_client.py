"""
llm_client.py — Anthropic SDK wrapper for the SOP Deviation Review Assistant.

Responsibilities:
  - Load ANTHROPIC_API_KEY from environment (via .env or shell).
  - Expose call_haiku() — a generic, low-level wrapper around the Messages API.
  - Expose call_haiku_structured() — forces structured JSON output using tool_use,
    bypassing prompt-only JSON instructions which Haiku can hallucinate.
  - Apply prompt-cache breakpoints on the system prompt to minimise token costs
    on repeated calls that share the same system content.
  - Return a consistent LLMResponse object on both success and error — never raise
    to callers; errors are surfaced through LLMResponse.error.

Public API:
    from backend.llm_client import call_haiku, call_haiku_structured, LLMResponse, DEVIATION_REVIEW_TOOL
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load .env from project root (two levels up from backend/)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env", override=True)

# ---------------------------------------------------------------------------
# Model constant — single place to update when bumping Haiku versions
# ---------------------------------------------------------------------------
HAIKU_MODEL = "claude-haiku-4-5"

# ---------------------------------------------------------------------------
# Safe fallback response returned when the LLM cannot complete the review
# ---------------------------------------------------------------------------
_SAFE_FALLBACK: dict[str, Any] = {
    "deviation_summary": (
        "Automated review could not be completed due to a system error. "
        "Manual QA review is required before any disposition decision is made."
    ),
    "sop_reference": "No directly applicable SOP section found",
    "risk_level": "High",
    "qa_review_required": True,
    "rationale": (
        "The automated assistant encountered an error and could not produce a "
        "reliable assessment. All uncertain or failed reviews are treated as "
        "High risk per the conservative escalation policy."
    ),
    "confidence": "Low",
}


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------
@dataclass
class LLMResponse:
    """
    Unified return type for all call_haiku* functions.

    Fields are always present — on error, text/tool_input will be the safe
    fallback JSON string and error will describe what went wrong.
    """
    text:          str             # Raw text content OR JSON-serialised tool input
    input_tokens:  int             # Prompt tokens consumed (0 on hard failure)
    output_tokens: int             # Completion tokens produced (0 on hard failure)
    latency_ms:    int             # Wall-clock time from request start to return
    error:         str | None      # None on success; error message on failure
    stop_reason:   str | None      # "tool_use" | "end_turn" | "max_tokens" | None
    cached_tokens: int = 0         # Input tokens served from the prompt cache

    @property
    def success(self) -> bool:
        """True if the call completed without error."""
        return self.error is None

    def parsed(self) -> dict[str, Any]:
        """
        Parse self.text as JSON and return the dict.
        Returns the safe fallback dict if parsing fails.
        """
        try:
            return json.loads(self.text)
        except (json.JSONDecodeError, TypeError):
            return dict(_SAFE_FALLBACK)


# ---------------------------------------------------------------------------
# Tool schema — enforces the 6-field deviation review output via tool_use.
# Haiku MUST populate every required field; the SDK rejects incomplete inputs.
# ---------------------------------------------------------------------------
DEVIATION_REVIEW_TOOL: dict[str, Any] = {
    "name": "submit_deviation_review",
    "description": (
        "Submit a structured pharmaceutical deviation review assessment. "
        "Call this tool once with all six required fields completed. "
        "Do not call any other tool."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "deviation_summary": {
                "type": "string",
                "description": (
                    "A 2–3 sentence factual summary of what the deviation is, "
                    "when it occurred, and what procedure was departed from."
                ),
            },
            "sop_reference": {
                "type": "string",
                "description": (
                    "The specific SOP document ID and section number most relevant "
                    "to this deviation, exactly as it appears in the supplied SOP "
                    "context. Use 'No directly applicable SOP section found' if "
                    "none of the provided sections address this situation."
                ),
            },
            "risk_level": {
                "type": "string",
                "enum": ["Low", "Medium", "High"],
                "description": (
                    "Risk classification. High = patient safety, product sterility, "
                    "potency, or identity impact. Medium = quality impact without "
                    "immediate patient risk. Low = procedural with no quality impact."
                ),
            },
            "qa_review_required": {
                "type": "boolean",
                "description": (
                    "True if immediate QA review is required before the batch or "
                    "process can proceed. Must be true for all High risk deviations "
                    "and any situation where confidence is Low."
                ),
            },
            "rationale": {
                "type": "string",
                "description": (
                    "2–4 sentences explaining why this risk level was assigned and "
                    "whether QA review is required. Cite the SOP section that "
                    "supports the recommendation."
                ),
            },
            "confidence": {
                "type": "string",
                "enum": ["High", "Medium", "Low"],
                "description": (
                    "Confidence in this assessment. Low if the deviation description "
                    "is ambiguous, incomplete, or if no supplied SOP directly covers "
                    "the situation. Low confidence always requires qa_review_required=true."
                ),
            },
        },
        "required": [
            "deviation_summary",
            "sop_reference",
            "risk_level",
            "qa_review_required",
            "rationale",
            "confidence",
        ],
    },
}


# ---------------------------------------------------------------------------
# Internal — build the Anthropic client (cached after first call)
# ---------------------------------------------------------------------------
_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    """Return a cached Anthropic client. Raises clearly if API key is missing."""
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY is not set. "
                "Add it to your .env file or set it in the shell environment."
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# Internal — extract response content from a Messages API response object
# ---------------------------------------------------------------------------
def _extract_content(response: anthropic.types.Message) -> tuple[str, str | None]:
    """
    Extract the usable text from a Messages API response.

    For tool_use responses  : returns (json.dumps(tool_input), "tool_use")
    For plain text responses: returns (text_content,           stop_reason)

    Returns ("", stop_reason) if no extractable content exists.
    """
    for block in response.content:
        if block.type == "tool_use":
            return json.dumps(block.input, ensure_ascii=False), "tool_use"
        if block.type == "text":
            return block.text, response.stop_reason

    return "", response.stop_reason


# ---------------------------------------------------------------------------
# Core public function
# ---------------------------------------------------------------------------
def call_haiku(
    system_prompt: str,
    user_message:  str,
    max_tokens:    int = 1024,
    tools:         list[dict] | None = None,
    tool_choice:   dict | None = None,
) -> LLMResponse:
    """
    Call Claude Haiku via the Anthropic Messages API.

    Applies a prompt-cache breakpoint to the system prompt so repeated calls
    with the same system content hit the cache and reduce input token costs.

    Args:
        system_prompt: The system instruction block (SOP context goes here).
        user_message:  The user turn — deviation description + any retrieved chunks.
        max_tokens:    Maximum completion tokens. Defaults to 1024.
        tools:         Optional list of Anthropic tool definitions. When supplied,
                       the model may call one of these tools instead of replying
                       in plain text.
        tool_choice:   Optional tool_choice dict, e.g.
                       {"type": "tool", "name": "submit_deviation_review"} to
                       force a specific tool call every time.

    Returns:
        LLMResponse — always. Never raises to the caller.
    """
    t0 = time.monotonic()

    try:
        client = _get_client()

        # Build request kwargs
        kwargs: dict[str, Any] = {
            "model":      HAIKU_MODEL,
            "max_tokens": max_tokens,
            # Cache the system prompt — same prompt across all deviation reviews
            # means the first call pays full price; every subsequent call is ~90%
            # cheaper on the input side.
            "system": [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [
                {"role": "user", "content": user_message},
            ],
        }

        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        response = client.messages.create(**kwargs)

        latency_ms = int((time.monotonic() - t0) * 1000)
        text, stop_reason = _extract_content(response)

        # Cache usage is in response.usage if the API returned it
        cached = getattr(response.usage, "cache_read_input_tokens", 0) or 0

        return LLMResponse(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=latency_ms,
            error=None,
            stop_reason=stop_reason,
            cached_tokens=int(cached),
        )

    except EnvironmentError as exc:
        # Missing API key — configuration error, not a transient failure
        return LLMResponse(
            text=json.dumps(_SAFE_FALLBACK),
            input_tokens=0,
            output_tokens=0,
            latency_ms=int((time.monotonic() - t0) * 1000),
            error=f"Configuration error: {exc}",
            stop_reason=None,
        )

    except anthropic.AuthenticationError as exc:
        return LLMResponse(
            text=json.dumps(_SAFE_FALLBACK),
            input_tokens=0,
            output_tokens=0,
            latency_ms=int((time.monotonic() - t0) * 1000),
            error=f"Authentication error — check ANTHROPIC_API_KEY: {exc}",
            stop_reason=None,
        )

    except anthropic.RateLimitError as exc:
        return LLMResponse(
            text=json.dumps(_SAFE_FALLBACK),
            input_tokens=0,
            output_tokens=0,
            latency_ms=int((time.monotonic() - t0) * 1000),
            error=f"Rate limit exceeded — retry after a pause: {exc}",
            stop_reason=None,
        )

    except anthropic.APIConnectionError as exc:
        return LLMResponse(
            text=json.dumps(_SAFE_FALLBACK),
            input_tokens=0,
            output_tokens=0,
            latency_ms=int((time.monotonic() - t0) * 1000),
            error=f"Network error connecting to Anthropic API: {exc}",
            stop_reason=None,
        )

    except anthropic.APIStatusError as exc:
        return LLMResponse(
            text=json.dumps(_SAFE_FALLBACK),
            input_tokens=0,
            output_tokens=0,
            latency_ms=int((time.monotonic() - t0) * 1000),
            error=f"Anthropic API error {exc.status_code}: {exc.message}",
            stop_reason=None,
        )

    except Exception as exc:  # noqa: BLE001 — intentional broad catch for safety
        return LLMResponse(
            text=json.dumps(_SAFE_FALLBACK),
            input_tokens=0,
            output_tokens=0,
            latency_ms=int((time.monotonic() - t0) * 1000),
            error=f"Unexpected error: {type(exc).__name__}: {exc}",
            stop_reason=None,
        )


# ---------------------------------------------------------------------------
# Convenience wrapper — always forces the structured deviation review tool
# ---------------------------------------------------------------------------
def call_haiku_structured(
    system_prompt: str,
    user_message:  str,
    max_tokens:    int = 1024,
) -> LLMResponse:
    """
    Call Haiku and force it to return structured deviation review JSON via tool_use.

    This is the function used by routes/review.py. It always passes
    DEVIATION_REVIEW_TOOL and sets tool_choice to require that specific tool,
    so the model cannot respond in free text and must populate all 6 fields.

    Args:
        system_prompt: System instructions including retrieved SOP context.
        user_message:  Deviation description from the user.
        max_tokens:    Maximum tokens for the response. Defaults to 1024.

    Returns:
        LLMResponse where .text is always a JSON string.
        Call .parsed() to get the dict, which falls back to _SAFE_FALLBACK on error.
    """
    return call_haiku(
        system_prompt=system_prompt,
        user_message=user_message,
        max_tokens=max_tokens,
        tools=[DEVIATION_REVIEW_TOOL],
        tool_choice={"type": "tool", "name": "submit_deviation_review"},
    )
