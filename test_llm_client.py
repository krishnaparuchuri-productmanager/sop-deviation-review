"""
test_llm_client.py — Tests for backend/llm_client.py.

Suite 1 — Static tests (no API key needed):
    Verify imports, LLMResponse structure, tool schema shape, and safe fallback.

Suite 2 — Live tests (require ANTHROPIC_API_KEY in environment or .env):
    Make real calls to Claude Haiku and assert that the response object
    carries text, token counts, and latency. Skipped automatically when
    the API key is not present.

Run:
    python test_llm_client.py
"""

import sys
import json
import os
import unittest
from pathlib import Path

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Make backend/ importable from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

# Load .env — override=True ensures the .env file always wins over any stale
# or empty value that may already exist in the Windows system environment.
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

_HAS_API_KEY = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
print(f"[setup] ANTHROPIC_API_KEY loaded: {_HAS_API_KEY} "
      f"(length={len(os.environ.get('ANTHROPIC_API_KEY',''))})")


# ===========================================================================
# Suite 1 — Static / structural tests (always run, no network needed)
# ===========================================================================
class TestModuleStructure(unittest.TestCase):

    def test_imports_cleanly(self) -> None:
        """llm_client must import without raising."""
        import llm_client  # noqa: F401

    def test_haiku_model_constant_is_string(self) -> None:
        """HAIKU_MODEL must be a non-empty string."""
        from llm_client import HAIKU_MODEL
        self.assertIsInstance(HAIKU_MODEL, str)
        self.assertTrue(HAIKU_MODEL.startswith("claude-"), HAIKU_MODEL)

    def test_llm_response_dataclass_fields(self) -> None:
        """LLMResponse must carry all required fields with correct types."""
        from llm_client import LLMResponse
        r = LLMResponse(
            text="hello",
            input_tokens=10,
            output_tokens=5,
            latency_ms=123,
            error=None,
            stop_reason="end_turn",
        )
        self.assertEqual(r.text, "hello")
        self.assertEqual(r.input_tokens, 10)
        self.assertEqual(r.output_tokens, 5)
        self.assertEqual(r.latency_ms, 123)
        self.assertIsNone(r.error)
        self.assertTrue(r.success)
        self.assertEqual(r.stop_reason, "end_turn")

    def test_llm_response_success_property(self) -> None:
        """success must be False when error is set."""
        from llm_client import LLMResponse
        ok  = LLMResponse("t", 1, 1, 50, None, "end_turn")
        err = LLMResponse("t", 0, 0, 10, "boom", None)
        self.assertTrue(ok.success)
        self.assertFalse(err.success)

    def test_llm_response_parsed_method_valid_json(self) -> None:
        """parsed() must return a dict when text is valid JSON."""
        from llm_client import LLMResponse
        payload = {"risk_level": "High", "qa_review_required": True}
        r = LLMResponse(json.dumps(payload), 10, 5, 100, None, "tool_use")
        result = r.parsed()
        self.assertEqual(result["risk_level"], "High")
        self.assertTrue(result["qa_review_required"])

    def test_llm_response_parsed_method_invalid_json_returns_fallback(self) -> None:
        """parsed() must return the safe fallback dict on bad JSON, not raise."""
        from llm_client import LLMResponse, _SAFE_FALLBACK
        r = LLMResponse("this is not json }{", 0, 0, 10, "some error", None)
        result = r.parsed()
        self.assertEqual(result["risk_level"], _SAFE_FALLBACK["risk_level"])
        self.assertTrue(result["qa_review_required"])
        self.assertEqual(result["confidence"], "Low")

    def test_deviation_review_tool_schema_shape(self) -> None:
        """DEVIATION_REVIEW_TOOL must have name, description, and input_schema."""
        from llm_client import DEVIATION_REVIEW_TOOL
        self.assertEqual(DEVIATION_REVIEW_TOOL["name"], "submit_deviation_review")
        self.assertIn("description", DEVIATION_REVIEW_TOOL)
        schema = DEVIATION_REVIEW_TOOL["input_schema"]
        self.assertEqual(schema["type"], "object")
        required = set(schema["required"])
        self.assertEqual(
            required,
            {"deviation_summary", "sop_reference", "risk_level",
             "qa_review_required", "rationale", "confidence"},
        )

    def test_deviation_review_tool_enum_values(self) -> None:
        """risk_level and confidence must be constrained to the correct enums."""
        from llm_client import DEVIATION_REVIEW_TOOL
        props = DEVIATION_REVIEW_TOOL["input_schema"]["properties"]
        self.assertEqual(set(props["risk_level"]["enum"]), {"Low", "Medium", "High"})
        self.assertEqual(set(props["confidence"]["enum"]), {"High", "Medium", "Low"})
        self.assertEqual(props["qa_review_required"]["type"], "boolean")

    def test_safe_fallback_is_valid_deviation_response(self) -> None:
        """_SAFE_FALLBACK must have all 6 required fields and correct values."""
        from llm_client import _SAFE_FALLBACK
        for key in ("deviation_summary", "sop_reference", "risk_level",
                    "qa_review_required", "rationale", "confidence"):
            self.assertIn(key, _SAFE_FALLBACK, f"Missing key: {key}")
        self.assertEqual(_SAFE_FALLBACK["risk_level"], "High")
        self.assertTrue(_SAFE_FALLBACK["qa_review_required"])
        self.assertEqual(_SAFE_FALLBACK["confidence"], "Low")

    def test_call_haiku_missing_api_key_returns_error_response(self) -> None:
        """call_haiku must return an error LLMResponse — not raise — when key is missing."""
        import llm_client as lc

        # Temporarily clear the key and reset the cached client
        original_key = os.environ.pop("ANTHROPIC_API_KEY", None)
        original_client = lc._client
        lc._client = None

        try:
            result = lc.call_haiku("system", "hello")
            self.assertIsInstance(result, lc.LLMResponse)
            self.assertFalse(result.success)
            self.assertIsNotNone(result.error)
            self.assertIn("ANTHROPIC_API_KEY", result.error)
        finally:
            # Always restore state
            if original_key:
                os.environ["ANTHROPIC_API_KEY"] = original_key
            lc._client = original_client


# ===========================================================================
# Suite 2 — Live API tests (skipped when ANTHROPIC_API_KEY is absent)
# ===========================================================================
@unittest.skipUnless(_HAS_API_KEY, "ANTHROPIC_API_KEY not set — skipping live API tests")
class TestLiveCallHaiku(unittest.TestCase):

    def test_plain_text_call_returns_response_object(self) -> None:
        """
        A simple plain-text call (no tools) must return an LLMResponse with:
          - non-empty text
          - input_tokens > 0
          - output_tokens > 0
          - latency_ms > 0
          - error is None
        """
        from llm_client import call_haiku

        result = call_haiku(
            system_prompt="You are a helpful assistant. Keep answers very brief.",
            user_message="Reply with exactly the word: PONG",
            max_tokens=16,
        )

        print(f"\n  [plain text] text={result.text!r}  "
              f"in={result.input_tokens}  out={result.output_tokens}  "
              f"latency={result.latency_ms}ms  cached={result.cached_tokens}")

        self.assertIsNone(result.error, f"Unexpected error: {result.error}")
        self.assertTrue(result.success)
        self.assertIsInstance(result.text, str)
        self.assertGreater(len(result.text.strip()), 0)
        self.assertGreater(result.input_tokens, 0)
        self.assertGreater(result.output_tokens, 0)
        self.assertGreater(result.latency_ms, 0)

    def test_structured_tool_call_returns_valid_json(self) -> None:
        """
        call_haiku_structured must return JSON with all 6 required fields
        populated by Haiku using the tool_use mechanism.
        """
        from llm_client import call_haiku_structured

        system = (
            "You are a GMP compliance assistant. "
            "Review the deviation and submit a structured assessment."
        )
        user = (
            "A balance used for API weighing was found to have an expired "
            "calibration sticker. The calibration due date was 2 weeks ago. "
            "The balance was used yesterday for a batch release test."
        )

        result = call_haiku_structured(system, user, max_tokens=512)

        print(f"\n  [structured] stop_reason={result.stop_reason}  "
              f"in={result.input_tokens}  out={result.output_tokens}  "
              f"latency={result.latency_ms}ms  error={result.error}")
        print(f"  text (first 200): {result.text[:200]}")

        self.assertIsNone(result.error, f"Unexpected error: {result.error}")
        self.assertEqual(result.stop_reason, "tool_use",
                         f"Expected stop_reason='tool_use', got {result.stop_reason!r}")

        parsed = result.parsed()
        required_keys = {
            "deviation_summary", "sop_reference", "risk_level",
            "qa_review_required", "rationale", "confidence",
        }
        for key in required_keys:
            self.assertIn(key, parsed, f"Missing key in parsed output: {key}")

        self.assertIn(parsed["risk_level"], ("Low", "Medium", "High"))
        self.assertIn(parsed["confidence"], ("Low", "Medium", "High"))
        self.assertIsInstance(parsed["qa_review_required"], bool)
        self.assertIsInstance(parsed["deviation_summary"], str)
        self.assertGreater(len(parsed["deviation_summary"]), 20)

    def test_token_counts_are_positive_integers(self) -> None:
        """Token counts must be positive integers on a successful call."""
        from llm_client import call_haiku

        result = call_haiku(
            system_prompt="Answer in one word.",
            user_message="What colour is the sky?",
            max_tokens=8,
        )

        self.assertIsNone(result.error)
        self.assertIsInstance(result.input_tokens, int)
        self.assertIsInstance(result.output_tokens, int)
        self.assertGreater(result.input_tokens, 0)
        self.assertGreater(result.output_tokens, 0)

    def test_latency_ms_is_reasonable(self) -> None:
        """Latency must be a positive integer under 30 seconds for a trivial call."""
        from llm_client import call_haiku

        result = call_haiku(
            system_prompt="Be brief.",
            user_message="Say yes.",
            max_tokens=8,
        )

        self.assertIsNone(result.error)
        self.assertGreater(result.latency_ms, 0)
        self.assertLess(result.latency_ms, 30_000,
                        f"Latency {result.latency_ms}ms exceeds 30s — possible timeout.")

    def test_high_risk_deviation_triggers_qa_flag(self) -> None:
        """
        A clearly critical deviation (wrong API in batch) must produce
        qa_review_required=True and risk_level='High'.
        """
        from llm_client import call_haiku_structured

        system = (
            "You are a GMP compliance assistant. "
            "A conservative escalation policy applies: when in doubt, escalate."
        )
        user = (
            "The wrong API was dispensed into Batch BLN-0041. "
            "The operator used Product B's API instead of Product A's. "
            "Blending is already complete and the batch has been tableted."
        )

        result = call_haiku_structured(system, user, max_tokens=512)
        self.assertIsNone(result.error)

        parsed = result.parsed()
        self.assertEqual(
            parsed.get("risk_level"), "High",
            f"Expected risk_level='High' for wrong-API scenario, got {parsed.get('risk_level')}",
        )
        self.assertTrue(
            parsed.get("qa_review_required"),
            "Expected qa_review_required=True for wrong-API scenario",
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    api_status = "API key found - live tests will run" if _HAS_API_KEY else "No API key - live tests skipped"
    print("=" * 60)
    print("  LLM Client Test Suite")
    print(f"  {api_status}")
    print("=" * 60)
    unittest.main(verbosity=2)
