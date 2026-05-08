# CLAUDE.md — SOP Deviation Review Assistant

This file governs how Claude Code should behave in this repository.
Read it before writing any code or making any changes.

---

## Project Name

**SOP Deviation Review Assistant**

---

## Goal

A web application that helps pharmaceutical QA and lab personnel review manufacturing
deviations. Given a plain-text deviation description, the assistant retrieves the most
relevant Standard Operating Procedure (SOP) guidance, uses Claude Haiku to produce a
structured deviation summary, assigns a risk level, and recommends whether QA review is
required. All interactions are logged for observability, scored against a golden eval set,
and surfaced in a simple analytics dashboard.

---

## Scope Rules

### In Scope (V1)
- Single-turn deviation review (one input → one structured response)
- SOP retrieval from local `.txt` files via TF-IDF keyword search
- Claude Haiku structured JSON output (6 fields, validated on every call)
- QA escalation flag with written rationale
- Per-review feedback capture (thumbs up / thumbs down + optional comment)
- SQLite trace logging (inputs, outputs, latency, token counts)
- Eval runner against a 15-case golden test set
- Dashboard with 7 metric panels

### Out of Scope (V1 — do not implement)
- User authentication or multi-user sessions
- PDF or file upload
- Integration with real SOP databases, LIMS, or JIRA
- Multi-turn conversation or chat history
- Fine-tuning, RLHF, or model training
- Embedding-based retrieval (TF-IDF only for V1)
- Email notifications or external alerting

---

## Coding Conventions

### General
- All code must be clean, readable, and demo-friendly — prioritize clarity over cleverness.
- Every module must have a one-line docstring describing its purpose.
- No unused imports, no commented-out dead code, no TODO placeholders in shipped files.
- Use explicit variable names. Abbreviations are only acceptable for well-known acronyms
  (e.g., `sop`, `qa`, `llm`).

### Python (Backend)
- Python 3.11+
- Framework: **FastAPI**
- Package manager: **pip** with `requirements.txt`
- Style: follow PEP 8; max line length 100 characters
- Type hints on all function signatures (parameters and return types)
- Use `pydantic` models for all request and response schemas
- Use `sqlite3` from the standard library for database access (no ORM)
- Environment variables loaded via `python-dotenv`; never hard-code secrets
- API key for Anthropic must be read from `ANTHROPIC_API_KEY` in `.env`
- All routes must return consistent JSON; errors use `{"error": "message"}` shape
- Retry logic: on LLM parse failure, retry once with a correction prompt;
  on second failure return a safe hard-coded fallback

### React (Frontend)
- Framework: **React 18 + Vite**
- Styling: **Tailwind CSS** (utility classes only, no custom CSS files unless unavoidable)
- No UI component library — keep dependencies minimal
- Use `fetch` for API calls; no axios or react-query in V1
- State management: React `useState` and `useEffect` only — no Redux or Zustand
- File naming: PascalCase for components (`DeviationForm.jsx`),
  camelCase for hooks and utilities (`useReviewApi.js`)
- All API calls go through a single `src/api/client.js` module

### SQLite
- Database file: `backend/db/sop_assistant.db`
- Three tables: `traces`, `feedback`, `eval_runs`
- Schema defined in `backend/db/schema.py`; initialized by `backend/db/init_db.py`
- No migrations framework — drop and recreate for V1 schema changes
- All queries use parameterized statements (never string interpolation)

---

## Agent Behavior Rules

These rules govern how the LLM prompt and output validation logic must behave.
They are non-negotiable and must be enforced in both the system prompt and in
post-response validation code.

1. **Grounded in SOP text only.**
   The assistant must cite only SOP sections that appear verbatim in the retrieved
   context passed to the model. It must never fabricate procedure steps, thresholds,
   or regulatory citations.

2. **Escalate when uncertain.**
   If the deviation description is ambiguous, partially described, or if no SOP section
   directly addresses the situation, the assistant must set `qa_review_required: true`
   and `confidence: "Low"`. It must never guess or speculate on regulatory compliance.

3. **Escalate for high-risk categories.**
   Any deviation involving patient safety, product sterility, potency, identity, or
   chain-of-custody must result in `risk_level: "High"` and `qa_review_required: true`,
   regardless of how clearly the SOP covers the situation.

4. **Safe fallback on failure.**
   If the LLM response cannot be parsed to a valid schema after one retry, the system
   must return a hard-coded safe response:
   `risk_level: "High"`, `qa_review_required: true`, `confidence: "Low"`,
   `deviation_summary: "Automated review could not be completed. Manual QA review required."`.

5. **No hallucinated SOP IDs.**
   If `sop_reference` cannot be filled with a real ID from the retrieved context,
   it must be set to `"No directly applicable SOP section found"` — never invented.

6. **Conservative by default.**
   A false-positive QA escalation is always preferable to a missed escalation.
   When the risk classification is borderline between Medium and High, choose High.

---

## Folder Structure

```
sop-deviation-review/
│
├── CLAUDE.md                         # This file
├── .env                              # API keys (never committed)
├── .gitignore
│
├── backend/
│   ├── main.py                       # FastAPI app entry point, CORS, route registration
│   ├── requirements.txt
│   │
│   ├── routes/
│   │   ├── review.py                 # POST /api/review
│   │   ├── feedback.py               # POST /api/feedback
│   │   ├── dashboard.py              # GET /api/dashboard/metrics
│   │   └── evals.py                  # POST /api/evals/run, GET /api/evals/results
│   │
│   ├── retrieval/
│   │   ├── sop_loader.py             # Reads SOP .txt files into memory at startup
│   │   └── search.py                 # TF-IDF search, returns top-k SOP chunks + IDs
│   │
│   ├── llm/
│   │   ├── client.py                 # Anthropic SDK wrapper, Haiku calls, retry logic
│   │   └── prompts.py                # System prompt, user turn template, output schema
│   │
│   ├── observability/
│   │   └── tracer.py                 # Writes trace records to SQLite on every request
│   │
│   ├── evals/
│   │   ├── runner.py                 # Loads golden set, runs pipeline, writes results
│   │   └── scorer.py                 # QA flag accuracy, risk match, key phrase presence
│   │
│   └── db/
│       ├── schema.py                 # CREATE TABLE statements for all three tables
│       └── init_db.py                # Runs schema.py to initialize the database
│
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   │
│   └── src/
│       ├── main.jsx                  # React entry point
│       ├── App.jsx                   # Top-level routing (Input / Results / Dashboard)
│       │
│       ├── api/
│       │   └── client.js             # All fetch calls to the backend API
│       │
│       ├── components/
│       │   ├── DeviationForm.jsx     # Textarea + category dropdown + submit button
│       │   ├── ReviewResult.jsx      # Structured output card + feedback row
│       │   ├── SourceContext.jsx     # Collapsible SOP excerpt panel
│       │   ├── FeedbackBar.jsx       # Thumbs up/down + optional comment
│       │   ├── Dashboard.jsx         # 7-panel metrics view
│       │   ├── EvalRunner.jsx        # Run eval button + results table
│       │   └── RiskBadge.jsx         # Colored badge: Low / Medium / High
│       │
│       └── hooks/
│           └── useReviewApi.js       # Shared fetch logic for review submission
│
└── data/
    ├── sops/
    │   ├── SOP-001-sample-management.txt
    │   ├── SOP-002-environmental-monitoring.txt
    │   ├── SOP-003-equipment-calibration.txt
    │   ├── SOP-004-raw-material-testing.txt
    │   └── SOP-005-batch-record-review.txt
    │
    └── cases/
        ├── synthetic_deviations.json     # 25 deviation descriptions for demo use
        └── eval_golden_set.json          # 15 labeled cases with expected outputs
```

---

## File List (Complete)

### Root
- `CLAUDE.md`
- `.env`
- `.gitignore`

### Backend
- `backend/main.py`
- `backend/requirements.txt`
- `backend/routes/review.py`
- `backend/routes/feedback.py`
- `backend/routes/dashboard.py`
- `backend/routes/evals.py`
- `backend/retrieval/sop_loader.py`
- `backend/retrieval/search.py`
- `backend/llm/client.py`
- `backend/llm/prompts.py`
- `backend/observability/tracer.py`
- `backend/evals/runner.py`
- `backend/evals/scorer.py`
- `backend/db/schema.py`
- `backend/db/init_db.py`
- `backend/db/sop_assistant.db`           *(generated at runtime, not committed)*

### Frontend
- `frontend/index.html`
- `frontend/package.json`
- `frontend/vite.config.js`
- `frontend/tailwind.config.js`
- `frontend/src/main.jsx`
- `frontend/src/App.jsx`
- `frontend/src/api/client.js`
- `frontend/src/components/DeviationForm.jsx`
- `frontend/src/components/ReviewResult.jsx`
- `frontend/src/components/SourceContext.jsx`
- `frontend/src/components/FeedbackBar.jsx`
- `frontend/src/components/Dashboard.jsx`
- `frontend/src/components/EvalRunner.jsx`
- `frontend/src/components/RiskBadge.jsx`
- `frontend/src/hooks/useReviewApi.js`

### Data
- `data/sops/SOP-001-sample-management.txt`
- `data/sops/SOP-002-environmental-monitoring.txt`
- `data/sops/SOP-003-equipment-calibration.txt`
- `data/sops/SOP-004-raw-material-testing.txt`
- `data/sops/SOP-005-batch-record-review.txt`
- `data/cases/synthetic_deviations.json`
- `data/cases/eval_golden_set.json`

---

## Key Constraints for Claude Code

- **Never write code that is not listed in the file list above** without first updating
  this CLAUDE.md and confirming with the user.
- **Never hard-code the Anthropic API key.** Always read from `os.environ["ANTHROPIC_API_KEY"]`.
- **Always validate LLM output** against the 6-field schema before returning it to the frontend.
- **Always write trace records** before returning a response from `/api/review`.
- **Use prompt caching** (`cache_control` breakpoints) on the system prompt in `llm/client.py`
  to reduce token costs on repeated calls.
- **Do not install additional npm or pip packages** beyond those needed for the listed modules
  without a clear justification noted in a code comment.
- Build in the order defined in the implementation plan:
  Phase 1 (data + DB) → Phase 2 (pipeline) → Phase 3 (frontend) →
  Phase 4 (observability + evals) → Phase 5 (polish).
