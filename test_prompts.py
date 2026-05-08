"""
test_prompts.py — Tests for backend/prompts.py.

Suite 1 — Static / structural tests (no API key needed):
    Verify module imports, SYSTEM_PROMPT content, DEVIATION_ASSESSMENT_TOOL schema,
    build_user_prompt formatting, validate_output logic, and SAFE_FALLBACK values.

Suite 2 — Live integration tests (require ANTHROPIC_API_KEY in environment or .env):
    Call assess_deviation() end-to-end and check that the structured response is valid
    and conservative-escalation rules are followed.

Run:
    python test_prompts.py
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
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Load .env — override=True ensures the .env file always wins over stale env vars
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

_HAS_API_KEY = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
print(f"[setup] ANTHROPIC_API_KEY loaded: {_HAS_API_KEY} "
      f"(length={len(os.environ.get('ANTHROPIC_API_KEY', ''))})")


# ===========================================================================
# Suite 1 — Static / structural tests (always run, no network needed)
# ===========================================================================
class TestModuleStructure(unittest.TestCase):

    def test_imports_cleanly(self) -> None:
        """prompts module must import without raising."""
        import backend.prompts  # noqa: F401

    def test_system_prompt_is_nonempty_string(self) -> None:
        """SYSTEM_PROMPT must be a non-empty string."""
        from backend.prompts import SYSTEM_PROMPT
        self.assertIsInstance(SYSTEM_PROMPT, str)
        self.assertGreater(len(SYSTEM_PROMPT.strip()), 100)

    def test_system_prompt_contains_escalation_instruction(self) -> None:
        """SYSTEM_PROMPT must mention QA escalation / conservative policy."""
        from backend.prompts import SYSTEM_PROMPT
        lower = SYSTEM_PROMPT.lower()
        self.assertTrue(
            "escalat" in lower or "qa" in lower,
            "SYSTEM_PROMPT must mention escalation or QA review"
        )

    def test_system_prompt_restricts_to_supplied_sop(self) -> None:
        """SYSTEM_PROMPT must instruct the agent to use ONLY supplied SOP context."""
        from backend.prompts import SYSTEM_PROMPT
        lower = SYSTEM_PROMPT.lower()
        self.assertTrue(
            "only" in lower or "supplied" in lower or "provided" in lower,
            "SYSTEM_PROMPT must restrict citations to supplied SOP context"
        )

    def test_deviation_assessment_tool_shape(self) -> None:
        """DEVIATION_ASSESSMENT_TOOL must have name, description, input_schema."""
        from backend.prompts import DEVIATION_ASSESSMENT_TOOL
        self.assertEqual(DEVIATION_ASSESSMENT_TOOL["name"], "submit_deviation_assessment")
        self.assertIn("description", DEVIATION_ASSESSMENT_TOOL)
        schema = DEVIATION_ASSESSMENT_TOOL["input_schema"]
        self.assertEqual(schema["type"], "object")
        required = set(schema["required"])
        self.assertEqual(
            required,
            {"classification", "severity", "impact", "immediate_action",
             "qa_escalation", "missing_info", "draft_summary"},
        )

    def test_deviation_assessment_tool_enums(self) -> None:
        """classification and severity must be constrained to allowed enums."""
        from backend.prompts import DEVIATION_ASSESSMENT_TOOL
        props = DEVIATION_ASSESSMENT_TOOL["input_schema"]["properties"]
        self.assertIn("Unknown", props["classification"]["enum"])
        self.assertEqual(
            set(props["severity"]["enum"]),
            {"High", "Medium", "Low"},
        )
        self.assertEqual(props["qa_escalation"]["type"], "boolean")

    def test_safe_fallback_has_all_required_fields(self) -> None:
        """SAFE_FALLBACK must have all 7 assessment fields plus shadow fields."""
        from backend.prompts import SAFE_FALLBACK
        for key in ("classification", "severity", "impact", "immediate_action",
                    "qa_escalation", "missing_info", "draft_summary"):
            self.assertIn(key, SAFE_FALLBACK, f"Missing key: {key}")
        # Shadow fields for cross-module consumers
        self.assertIn("risk_level",         SAFE_FALLBACK)
        self.assertIn("qa_review_required", SAFE_FALLBACK)
        self.assertIn("confidence",         SAFE_FALLBACK)

    def test_safe_fallback_is_conservative(self) -> None:
        """SAFE_FALLBACK must always escalate with High severity and Low confidence."""
        from backend.prompts import SAFE_FALLBACK
        self.assertEqual(SAFE_FALLBACK["severity"],         "High")
        self.assertTrue(SAFE_FALLBACK["qa_escalation"])
        self.assertEqual(SAFE_FALLBACK["confidence"],       "Low")
        self.assertEqual(SAFE_FALLBACK["risk_level"],       "High")
        self.assertTrue(SAFE_FALLBACK["qa_review_required"])

    # -----------------------------------------------------------------------
    # build_user_prompt tests
    # -----------------------------------------------------------------------

    def test_build_user_prompt_contains_deviation_text(self) -> None:
        """User prompt must include the deviation description verbatim."""
        from backend.prompts import build_user_prompt
        result = build_user_prompt("Temperature excursion in cold room 3.", [])
        self.assertIn("Temperature excursion in cold room 3.", result)

    def test_build_user_prompt_with_chunks_includes_chunk_text(self) -> None:
        """User prompt must include chunk text when chunks are supplied."""
        from backend.prompts import build_user_prompt
        chunks = [
            {
                "text": "Section 4.2: All temperature excursions must be reported.",
                "section_title": "Excursion Reporting",
                "source_file": "environmental_monitoring.md",
                "chunk_id": "SOP-EM-002__4",
                "score": 0.87,
            }
        ]
        result = build_user_prompt("Temperature excursion in cold room.", chunks)
        self.assertIn("Section 4.2", result)
        self.assertIn("Excursion Reporting", result)
        self.assertIn("environmental_monitoring.md", result)

    def test_build_user_prompt_no_chunks_warns_about_missing_context(self) -> None:
        """User prompt must mention missing SOP context when chunks list is empty."""
        from backend.prompts import build_user_prompt
        result = build_user_prompt("Unknown deviation type.", [])
        lower = result.lower()
        self.assertTrue(
            "no sop" in lower or "no sections" in lower or "not retrieved" in lower
            or "escalate" in lower,
            "Prompt must warn about missing SOP context when no chunks provided"
        )

    def test_build_user_prompt_returns_string(self) -> None:
        """build_user_prompt must always return a string."""
        from backend.prompts import build_user_prompt
        result = build_user_prompt("Some deviation.", [])
        self.assertIsInstance(result, str)

    # -----------------------------------------------------------------------
    # validate_output tests
    # -----------------------------------------------------------------------

    def _valid_payload(self) -> dict:
        return {
            "classification":   "Equipment",
            "severity":         "High",
            "impact":           "The balance produced unreliable readings.",
            "immediate_action": "Quarantine all results from the affected balance.",
            "qa_escalation":    True,
            "missing_info":     "None",
            "draft_summary":    "An expired calibration sticker was found on the balance.",
        }

    def test_validate_output_accepts_valid_json(self) -> None:
        """validate_output must return a dict for a fully valid payload."""
        from backend.prompts import validate_output
        result = validate_output(json.dumps(self._valid_payload()))
        self.assertIsInstance(result, dict)
        self.assertEqual(result["classification"], "Equipment")

    def test_validate_output_rejects_invalid_json(self) -> None:
        """validate_output must raise ValidationError on unparseable input."""
        from backend.prompts import validate_output, ValidationError
        with self.assertRaises(ValidationError):
            validate_output("not json }{")

    def test_validate_output_rejects_missing_field(self) -> None:
        """validate_output must raise ValidationError when a required field is absent."""
        from backend.prompts import validate_output, ValidationError
        payload = self._valid_payload()
        del payload["qa_escalation"]
        with self.assertRaises(ValidationError) as ctx:
            validate_output(json.dumps(payload))
        self.assertIn("qa_escalation", str(ctx.exception))

    def test_validate_output_rejects_invalid_classification(self) -> None:
        """validate_output must reject classification values not in the enum."""
        from backend.prompts import validate_output, ValidationError
        payload = self._valid_payload()
        payload["classification"] = "Biological"
        with self.assertRaises(ValidationError):
            validate_output(json.dumps(payload))

    def test_validate_output_rejects_invalid_severity(self) -> None:
        """validate_output must reject severity values not in High/Medium/Low."""
        from backend.prompts import validate_output, ValidationError
        payload = self._valid_payload()
        payload["severity"] = "Critical"
        with self.assertRaises(ValidationError):
            validate_output(json.dumps(payload))

    def test_validate_output_rejects_non_boolean_qa_escalation(self) -> None:
        """validate_output must reject qa_escalation that is not a boolean."""
        from backend.prompts import validate_output, ValidationError
        payload = self._valid_payload()
        payload["qa_escalation"] = "yes"
        with self.assertRaises(ValidationError):
            validate_output(json.dumps(payload))

    def test_validate_output_rejects_empty_string_field(self) -> None:
        """validate_output must reject empty-string values for text fields."""
        from backend.prompts import validate_output, ValidationError
        payload = self._valid_payload()
        payload["draft_summary"] = "   "
        with self.assertRaises(ValidationError):
            validate_output(json.dumps(payload))

    def test_validate_output_accepts_unknown_classification(self) -> None:
        """'Unknown' must be an accepted classification value."""
        from backend.prompts import validate_output
        payload = self._valid_payload()
        payload["classification"] = "Unknown"
        result = validate_output(json.dumps(payload))
        self.assertEqual(result["classification"], "Unknown")


# ===========================================================================
# Suite 2 — Live integration tests (skipped without ANTHROPIC_API_KEY)
# ===========================================================================
@unittest.skipUnless(_HAS_API_KEY, "ANTHROPIC_API_KEY not set — skipping live API tests")
class TestLiveAssessDeviation(unittest.TestCase):

    def test_assess_returns_valid_dict(self) -> None:
        """assess_deviation must return a dict with all 7 required fields."""
        from backend.prompts import assess_deviation, DEVIATION_ASSESSMENT_TOOL

        required_keys = set(DEVIATION_ASSESSMENT_TOOL["input_schema"]["required"])
        result = assess_deviation(
            user_text="A cold storage unit was found reading +8°C against a limit of +5°C.",
            sop_chunks=[],
        )

        print(f"\n  [live] result keys: {list(result.keys())}")
        print(f"  [live] severity={result.get('severity')}  "
              f"qa_escalation={result.get('qa_escalation')}  "
              f"classification={result.get('classification')}")

        self.assertIsInstance(result, dict)
        for key in required_keys:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_assess_high_risk_triggers_escalation(self) -> None:
        """A clearly critical deviation must produce qa_escalation=True and severity=High."""
        from backend.prompts import assess_deviation

        result = assess_deviation(
            user_text=(
                "The wrong active pharmaceutical ingredient was dispensed into Batch BLN-0071. "
                "Product A's API was replaced with Product B's API by mistake. "
                "Blending is complete and tableting has already run."
            ),
            sop_chunks=[],
        )

        print(f"\n  [live-high] severity={result.get('severity')}  "
              f"qa_escalation={result.get('qa_escalation')}")

        self.assertEqual(
            result.get("severity"), "High",
            f"Expected severity='High' for wrong-API scenario, got {result.get('severity')}"
        )
        self.assertTrue(
            result.get("qa_escalation"),
            "Expected qa_escalation=True for wrong-API scenario"
        )

    def test_assess_with_sop_chunks_returns_structured_output(self) -> None:
        """assess_deviation with supplied SOP chunks must return a valid assessment."""
        from backend.prompts import assess_deviation, validate_output
        import json

        chunks = [
            {
                "text": (
                    "## Immediate Containment\n"
                    "On discovery of an equipment calibration excursion, the operator "
                    "must immediately quarantine all outputs produced by the affected "
                    "instrument since its last verified calibration date."
                ),
                "section_title": "Immediate Containment",
                "source_file":   "immediate_containment.md",
                "chunk_id":      "SOP-IC-002__2",
                "score":         0.91,
            }
        ]

        result = assess_deviation(
            user_text=(
                "A weighing balance in QC lab 3 was found with an expired calibration "
                "label. It was last used 3 days ago for a batch release test."
            ),
            sop_chunks=chunks,
        )

        print(f"\n  [live-chunks] classification={result.get('classification')}  "
              f"severity={result.get('severity')}  "
              f"qa_escalation={result.get('qa_escalation')}")
        print(f"  [live-chunks] immediate_action: {result.get('immediate_action','')[:120]}")

        self.assertIsInstance(result, dict)
        self.assertIn(result.get("classification"),
                      {"Equipment", "Documentation", "Environmental",
                       "Process", "Material", "Personnel", "Unknown"})
        self.assertIn(result.get("severity"), {"High", "Medium", "Low"})
        self.assertIsInstance(result.get("qa_escalation"), bool)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    api_status = (
        "API key found - live tests will run"
        if _HAS_API_KEY
        else "No API key - live tests skipped"
    )
    print("=" * 60)
    print("  Prompts Module Test Suite")
    print(f"  {api_status}")
    print("=" * 60)
    unittest.main(verbosity=2)
