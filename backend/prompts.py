"""
prompts.py — Prompt construction, output validation, and deviation assessment
orchestration for the SOP Deviation Review Assistant.

Responsibilities:
  - SYSTEM_PROMPT: grounds the agent strictly in supplied SOP context.
  - DEVIATION_ASSESSMENT_TOOL: Anthropic tool schema for the 7-field assessment.
  - build_user_prompt(): formats deviation text + retrieved SOP chunks for the user turn.
  - validate_output(): parses and validates the JSON assessment dict.
  - assess_deviation(): end-to-end orchestration with up to 2 retries and a
    hard-coded conservative safe fallback on exhausted retries.

Public API:
    from backend.prompts import (
        SYSTEM_PROMPT,
        DEVIATION_ASSESSMENT_TOOL,
        build_user_prompt,
        validate_output,
        assess_deviation,
        assess_deviation_traced,
        AssessmentTrace,
        SAFE_FALLBACK,
        ValidationError,
    )
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

try:
    from llm_client import call_haiku, LLMResponse          # uvicorn from backend/
except ImportError:
    from backend.llm_client import call_haiku, LLMResponse  # pytest from project root

# ---------------------------------------------------------------------------
# Hard-coded conservative safe fallback
# Returned whenever the LLM cannot produce a valid assessment after retries.
# Every field required by the schema is populated. qa_escalation / qa_review_required
# and risk_level are always set to the most cautious values.
# ---------------------------------------------------------------------------
SAFE_FALLBACK: dict[str, Any] = {
    "classification":   "Unknown",
    "severity":         "High",
    "impact":           (
        "Could not be determined automatically. Manual review required."
    ),
    "immediate_action": (
        "Quarantine affected materials and escalate to QA immediately. "
        "Do not proceed until a qualified person has reviewed this deviation."
    ),
    "qa_escalation":    True,
    "missing_info":     (
        "Automated assessment failed. All information must be verified manually."
    ),
    "draft_summary":    (
        "Automated review could not be completed. Manual QA review is required "
        "before any disposition decision is made."
    ),
    # Shadow fields kept for cross-module consumers that use llm_client field names
    "risk_level":          "High",
    "qa_review_required":  True,
    "confidence":          "Low",
}

# ---------------------------------------------------------------------------
# SYSTEM_PROMPT
# The system turn is cached (cache_control applied in call_haiku) so it is
# paid for only once per cold-cache window.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a pharmaceutical GMP (Good Manufacturing Practice) compliance \
assistant embedded in a deviation review system.

## Role and Scope
- You may ONLY use the SOP sections supplied in the user message to support your assessment.
- Do NOT cite SOP document IDs, section numbers, or procedural requirements that are not \
explicitly present in the supplied context.
- If the supplied SOP context does not cover the deviation, say so explicitly in \
`missing_info` and set `qa_escalation` to true.

## Classification Categories
Classify the deviation as one of:
  - Equipment       — instrument, machine, or utility failure / misuse
  - Documentation   — record, entry, or logbook error
  - Environmental   — temperature, humidity, or cleanliness excursion
  - Process         — procedure step skipped, wrong order, or wrong method
  - Material        — wrong component, expired material, or labelling error
  - Personnel       — training gap, unauthorised action, or error by operator
  - Unknown         — cannot determine from the information provided

## Severity Levels
  - High    — direct or probable patient safety, product sterility, potency, or identity impact
  - Medium  — quality impact without immediate patient risk
  - Low     — procedural gap with no demonstrable quality or safety impact

## Conservative Escalation Policy
When in doubt, escalate. Specifically:
  - Set `qa_escalation` to true for ALL High-severity deviations.
  - Set `qa_escalation` to true whenever the deviation description is ambiguous or incomplete.
  - Set `qa_escalation` to true if no supplied SOP section directly addresses the situation.
  - Never recommend proceeding without QA review when confidence is low.

## Response Format
You MUST call the `submit_deviation_assessment` tool with all seven fields populated. \
Do not respond in plain text. Do not hallucinate SOP references."""

# ---------------------------------------------------------------------------
# Tool schema — enforces the 7-field deviation assessment output via tool_use.
# ---------------------------------------------------------------------------
DEVIATION_ASSESSMENT_TOOL: dict[str, Any] = {
    "name": "submit_deviation_assessment",
    "description": (
        "Submit a structured pharmaceutical deviation assessment. "
        "Call this tool exactly once with all seven required fields completed. "
        "Do not call any other tool."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "classification": {
                "type": "string",
                "enum": [
                    "Equipment", "Documentation", "Environmental",
                    "Process", "Material", "Personnel", "Unknown",
                ],
                "description": (
                    "The primary deviation category from the allowed list. "
                    "Choose 'Unknown' only if the type truly cannot be determined."
                ),
            },
            "severity": {
                "type": "string",
                "enum": ["High", "Medium", "Low"],
                "description": (
                    "Severity classification. High = patient safety, sterility, "
                    "potency, or identity risk. Medium = quality impact without "
                    "immediate patient risk. Low = procedural, no quality impact."
                ),
            },
            "impact": {
                "type": "string",
                "description": (
                    "1–3 sentences describing the actual or potential impact on "
                    "product quality, patient safety, or regulatory compliance."
                ),
            },
            "immediate_action": {
                "type": "string",
                "description": (
                    "Concrete first steps that must be taken right now (e.g., "
                    "quarantine, cease operations, notify supervisor). "
                    "Cite the SOP section that mandates this action if one was supplied."
                ),
            },
            "qa_escalation": {
                "type": "boolean",
                "description": (
                    "True if QA review is required before the batch or process "
                    "can proceed. Must be true for all High-severity deviations "
                    "and any situation where the assessment confidence is Low."
                ),
            },
            "missing_info": {
                "type": "string",
                "description": (
                    "Any information that would be needed to complete a more "
                    "definitive assessment but was not provided in the deviation "
                    "description. Write 'None' if the description is sufficient."
                ),
            },
            "draft_summary": {
                "type": "string",
                "description": (
                    "A 2–4 sentence factual summary of the deviation suitable "
                    "for inclusion in the deviation record: what happened, when, "
                    "what procedure was departed from, and the recommended action."
                ),
            },
        },
        "required": [
            "classification",
            "severity",
            "impact",
            "immediate_action",
            "qa_escalation",
            "missing_info",
            "draft_summary",
        ],
    },
}

# ---------------------------------------------------------------------------
# Allowed enum sets — used by validate_output
# ---------------------------------------------------------------------------
_VALID_CLASSIFICATIONS = {
    "Equipment", "Documentation", "Environmental",
    "Process", "Material", "Personnel", "Unknown",
}
_VALID_SEVERITIES = {"High", "Medium", "Low"}

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class ValidationError(ValueError):
    """Raised by validate_output when the LLM response fails schema validation."""


# ---------------------------------------------------------------------------
# build_user_prompt
# ---------------------------------------------------------------------------

def build_user_prompt(user_text: str, sop_chunks: list[dict]) -> str:
    """
    Combine the operator's deviation description with retrieved SOP chunks
    into a single user-turn message.

    Args:
        user_text:  Free-text deviation description from the operator.
        sop_chunks: List of chunk dicts returned by retrieval.search_sop().
                    Each dict must have at minimum: 'text' (str).
                    Optional keys used for context headers: 'section_title' (str),
                    'source_file' (str), 'chunk_id' (str), 'score' (float).

    Returns:
        A formatted string ready to pass as the `user_message` to call_haiku().
    """
    lines: list[str] = []

    # ---- Deviation description -----------------------------------------
    lines.append("## Deviation Description")
    lines.append(user_text.strip())
    lines.append("")

    # ---- Retrieved SOP context -----------------------------------------
    if sop_chunks:
        lines.append("## Relevant SOP Context")
        lines.append(
            "The following SOP sections were retrieved as most relevant. "
            "Use ONLY these sections to support your assessment."
        )
        lines.append("")

        for i, chunk in enumerate(sop_chunks, start=1):
            # Build a human-readable header from available metadata
            title      = chunk.get("section_title", "").strip()
            source     = chunk.get("source_file",   "").strip()
            chunk_id   = chunk.get("chunk_id",       "").strip()
            score      = chunk.get("score")

            header_parts: list[str] = []
            if title:
                header_parts.append(title)
            if source:
                header_parts.append(f"source: {source}")
            if chunk_id:
                header_parts.append(f"id: {chunk_id}")
            if score is not None:
                header_parts.append(f"relevance: {score:.3f}")

            header = " | ".join(header_parts) if header_parts else f"Chunk {i}"
            lines.append(f"### [{i}] {header}")
            lines.append(chunk.get("text", "").strip())
            lines.append("")
    else:
        lines.append("## Relevant SOP Context")
        lines.append(
            "No SOP sections were retrieved for this query. "
            "Assess based on general GMP principles and escalate to QA."
        )
        lines.append("")

    # ---- Instruction reminder ------------------------------------------
    lines.append(
        "Using only the SOP context above, call `submit_deviation_assessment` "
        "with all seven required fields."
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# validate_output
# ---------------------------------------------------------------------------

def validate_output(response_text: str) -> dict[str, Any]:
    """
    Parse and validate a JSON string produced by the LLM tool-use call.

    Validation rules:
      - Must be valid JSON.
      - Must contain all seven required fields.
      - `classification` must be one of the allowed enum values.
      - `severity` must be one of: High, Medium, Low.
      - `qa_escalation` must be a boolean.
      - String fields (impact, immediate_action, missing_info, draft_summary)
        must be non-empty strings.

    Args:
        response_text: The `.text` attribute of an LLMResponse — expected to be
                       a JSON-serialised dict from the tool_use block.

    Returns:
        The validated dict.

    Raises:
        ValidationError: If parsing fails or any field is missing / invalid.
    """
    # 1. Parse JSON
    try:
        data = json.loads(response_text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValidationError(f"Response is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValidationError(f"Expected a JSON object, got {type(data).__name__}")

    required_keys = [
        "classification", "severity", "impact",
        "immediate_action", "qa_escalation",
        "missing_info", "draft_summary",
    ]

    # 2. Check all required keys present
    missing = [k for k in required_keys if k not in data]
    if missing:
        raise ValidationError(f"Missing required fields: {missing}")

    # 3. Validate enum fields
    if data["classification"] not in _VALID_CLASSIFICATIONS:
        raise ValidationError(
            f"Invalid classification {data['classification']!r}. "
            f"Must be one of: {sorted(_VALID_CLASSIFICATIONS)}"
        )

    if data["severity"] not in _VALID_SEVERITIES:
        raise ValidationError(
            f"Invalid severity {data['severity']!r}. "
            f"Must be one of: {sorted(_VALID_SEVERITIES)}"
        )

    # 4. Validate boolean
    if not isinstance(data["qa_escalation"], bool):
        raise ValidationError(
            f"qa_escalation must be a boolean, got {type(data['qa_escalation']).__name__}"
        )

    # 5. Validate non-empty strings
    for key in ("impact", "immediate_action", "missing_info", "draft_summary"):
        if not isinstance(data[key], str) or not data[key].strip():
            raise ValidationError(f"Field '{key}' must be a non-empty string")

    return data


# ---------------------------------------------------------------------------
# assess_deviation — end-to-end orchestration with retry + safe fallback
# ---------------------------------------------------------------------------

def assess_deviation(
    user_text:  str,
    sop_chunks: list[dict],
    max_tokens: int = 1024,
) -> dict[str, Any]:
    """
    Assess a pharmaceutical deviation using Claude Haiku with structured output.

    Orchestration flow:
      1. Build the user prompt (deviation + SOP context).
      2. Call call_haiku() with DEVIATION_ASSESSMENT_TOOL, forcing tool_use.
      3. Validate the response with validate_output().
      4. On LLM error or ValidationError, retry with a correction prompt
         (up to 2 additional attempts, 3 total).
      5. If all attempts are exhausted, return SAFE_FALLBACK.

    Args:
        user_text:  Operator's free-text deviation description.
        sop_chunks: Retrieved SOP chunks from retrieval.search_sop().
        max_tokens: Max completion tokens passed to the LLM. Defaults to 1024.

    Returns:
        A validated assessment dict (7 required fields), or SAFE_FALLBACK on failure.
        The returned dict always contains 'qa_escalation' (bool) and 'severity' (str).
    """
    MAX_ATTEMPTS = 3

    base_user_message = build_user_prompt(user_text, sop_chunks)
    current_message   = base_user_message
    last_error:  str | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        response: LLMResponse = call_haiku(
            system_prompt=SYSTEM_PROMPT,
            user_message=current_message,
            max_tokens=max_tokens,
            tools=[DEVIATION_ASSESSMENT_TOOL],
            tool_choice={"type": "tool", "name": "submit_deviation_assessment"},
        )

        # --- LLM-level error (network, auth, rate-limit, etc.) -----------
        if not response.success:
            last_error = response.error or "Unknown LLM error"
            if attempt < MAX_ATTEMPTS:
                # Retry with a brief correction hint appended
                current_message = (
                    base_user_message
                    + f"\n\n[System note: previous attempt failed ({last_error}). "
                    "Please try again and call submit_deviation_assessment.]"
                )
            continue

        # --- Validation --------------------------------------------------
        try:
            validated = validate_output(response.text)
            return validated
        except ValidationError as exc:
            last_error = str(exc)
            if attempt < MAX_ATTEMPTS:
                current_message = (
                    base_user_message
                    + f"\n\n[System note: your previous response failed validation "
                    f"({exc}). Retry — call submit_deviation_assessment with all "
                    "seven required fields correctly populated.]"
                )
            continue

    # All attempts exhausted — return the conservative safe fallback
    return dict(SAFE_FALLBACK)


# ---------------------------------------------------------------------------
# AssessmentTrace — carries LLM metadata for trace logging
# ---------------------------------------------------------------------------

@dataclass
class AssessmentTrace:
    """
    Lightweight container returned by assess_deviation_traced().

    Carries the raw LLM response metadata needed to write a trace record.
    All fields default to safe zero/None values so the route never needs to
    guard against AttributeError.
    """
    input_tokens:     int       = 0
    output_tokens:    int       = 0
    model_output_raw: str       = ""   # JSON string from the tool_use block
    error:            str | None = None
    is_fallback:      bool      = False


# ---------------------------------------------------------------------------
# assess_deviation_traced — same as assess_deviation but also returns trace info
# ---------------------------------------------------------------------------

def assess_deviation_traced(
    user_text:  str,
    sop_chunks: list[dict],
    max_tokens: int = 1024,
) -> tuple[dict[str, Any], AssessmentTrace]:
    """
    Identical to assess_deviation() but also returns an AssessmentTrace so the
    caller can write a full trace record without re-running the pipeline.

    Args:
        user_text:  Operator's free-text deviation description.
        sop_chunks: Retrieved SOP chunks from retrieval.search_sop().
        max_tokens: Max completion tokens. Defaults to 1024.

    Returns:
        (assessment_dict, AssessmentTrace)
        - assessment_dict  — validated 7-field dict, or SAFE_FALLBACK on failure
        - AssessmentTrace  — token counts, raw model output, and error from the
                             last LLM call attempted
    """
    MAX_ATTEMPTS = 3

    base_user_message = build_user_prompt(user_text, sop_chunks)
    current_message   = base_user_message
    last_error:    str | None      = None
    last_response: LLMResponse | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        response: LLMResponse = call_haiku(
            system_prompt=SYSTEM_PROMPT,
            user_message=current_message,
            max_tokens=max_tokens,
            tools=[DEVIATION_ASSESSMENT_TOOL],
            tool_choice={"type": "tool", "name": "submit_deviation_assessment"},
        )
        last_response = response

        # --- LLM-level error (network, auth, rate-limit, etc.) -----------
        if not response.success:
            last_error = response.error or "Unknown LLM error"
            if attempt < MAX_ATTEMPTS:
                current_message = (
                    base_user_message
                    + f"\n\n[System note: previous attempt failed ({last_error}). "
                    "Please try again and call submit_deviation_assessment.]"
                )
            continue

        # --- Validation --------------------------------------------------
        try:
            validated = validate_output(response.text)
            trace = AssessmentTrace(
                input_tokens     = response.input_tokens,
                output_tokens    = response.output_tokens,
                model_output_raw = response.text,
                error            = None,
                is_fallback      = False,
            )
            return validated, trace
        except ValidationError as exc:
            last_error = str(exc)
            if attempt < MAX_ATTEMPTS:
                current_message = (
                    base_user_message
                    + f"\n\n[System note: your previous response failed validation "
                    f"({exc}). Retry — call submit_deviation_assessment with all "
                    "seven required fields correctly populated.]"
                )
            continue

    # All attempts exhausted — return the safe fallback + trace with error
    trace = AssessmentTrace(
        input_tokens     = last_response.input_tokens  if last_response else 0,
        output_tokens    = last_response.output_tokens if last_response else 0,
        model_output_raw = last_response.text          if last_response else "",
        error            = last_error,
        is_fallback      = True,
    )
    return dict(SAFE_FALLBACK), trace
