/**
 * prompts.ts — Prompt construction, output validation, and deviation assessment
 * orchestration (port of backend/prompts.py). Prompt text is kept byte-for-byte.
 */

import { callHaiku, LLMResponse, succeeded } from "./llm";
import { SopChunk } from "./retrieval";
import { Env, Row, pyRepr, pyTypeName } from "./util";

// Hard-coded conservative safe fallback, returned when no valid assessment is produced.
export const SAFE_FALLBACK: Row = {
  classification: "Unknown",
  severity: "High",
  impact: "Could not be determined automatically. Manual review required.",
  immediate_action:
    "Quarantine affected materials and escalate to QA immediately. " +
    "Do not proceed until a qualified person has reviewed this deviation.",
  qa_escalation: true,
  missing_info: "Automated assessment failed. All information must be verified manually.",
  draft_summary:
    "Automated review could not be completed. Manual QA review is required " +
    "before any disposition decision is made.",
  // Shadow fields kept for cross-module consumers that use llm_client field names
  risk_level: "High",
  qa_review_required: true,
  confidence: "Low",
};

export const SYSTEM_PROMPT = `You are a pharmaceutical GMP (Good Manufacturing Practice) compliance \
assistant embedded in a deviation review system.

## Role and Scope
- You may ONLY use the SOP sections supplied in the user message to support your assessment.
- Do NOT cite SOP document IDs, section numbers, or procedural requirements that are not \
explicitly present in the supplied context.
- If the supplied SOP context does not cover the deviation, say so explicitly in \
\`missing_info\` and set \`qa_escalation\` to true.

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
  - Set \`qa_escalation\` to true for ALL High-severity deviations.
  - Set \`qa_escalation\` to true whenever the deviation description is ambiguous or incomplete.
  - Set \`qa_escalation\` to true if no supplied SOP section directly addresses the situation.
  - Never recommend proceeding without QA review when confidence is low.

## Response Format
You MUST call the \`submit_deviation_assessment\` tool with all seven fields populated. \
Do not respond in plain text. Do not hallucinate SOP references.`;

export const DEVIATION_ASSESSMENT_TOOL: Row = {
  name: "submit_deviation_assessment",
  description:
    "Submit a structured pharmaceutical deviation assessment. " +
    "Call this tool exactly once with all seven required fields completed. " +
    "Do not call any other tool.",
  input_schema: {
    type: "object",
    properties: {
      classification: {
        type: "string",
        enum: ["Equipment", "Documentation", "Environmental", "Process", "Material", "Personnel", "Unknown"],
        description:
          "The primary deviation category from the allowed list. " +
          "Choose 'Unknown' only if the type truly cannot be determined.",
      },
      severity: {
        type: "string",
        enum: ["High", "Medium", "Low"],
        description:
          "Severity classification. High = patient safety, sterility, " +
          "potency, or identity risk. Medium = quality impact without " +
          "immediate patient risk. Low = procedural, no quality impact.",
      },
      impact: {
        type: "string",
        description:
          "1–3 sentences describing the actual or potential impact on " +
          "product quality, patient safety, or regulatory compliance.",
      },
      immediate_action: {
        type: "string",
        description:
          "Concrete first steps that must be taken right now (e.g., " +
          "quarantine, cease operations, notify supervisor). " +
          "Cite the SOP section that mandates this action if one was supplied.",
      },
      qa_escalation: {
        type: "boolean",
        description:
          "True if QA review is required before the batch or process " +
          "can proceed. Must be true for all High-severity deviations " +
          "and any situation where the assessment confidence is Low.",
      },
      missing_info: {
        type: "string",
        description:
          "Any information that would be needed to complete a more " +
          "definitive assessment but was not provided in the deviation " +
          "description. Write 'None' if the description is sufficient.",
      },
      draft_summary: {
        type: "string",
        description:
          "A 2–4 sentence factual summary of the deviation suitable " +
          "for inclusion in the deviation record: what happened, when, " +
          "what procedure was departed from, and the recommended action.",
      },
    },
    required: [
      "classification", "severity", "impact", "immediate_action",
      "qa_escalation", "missing_info", "draft_summary",
    ],
  },
};

const VALID_CLASSIFICATIONS = ["Documentation", "Environmental", "Equipment", "Material", "Personnel", "Process", "Unknown"];
const VALID_SEVERITIES = ["High", "Low", "Medium"];
const REQUIRED_KEYS = [
  "classification", "severity", "impact", "immediate_action", "qa_escalation", "missing_info", "draft_summary",
];

export class ValidationError extends Error {}

/** Combine the deviation description with retrieved SOP chunks into the user turn. */
export function buildUserPrompt(userText: string, sopChunks: Partial<SopChunk>[]): string {
  const lines: string[] = ["## Deviation Description", userText.trim(), ""];

  if (sopChunks.length) {
    lines.push(
      "## Relevant SOP Context",
      "The following SOP sections were retrieved as most relevant. " +
        "Use ONLY these sections to support your assessment.",
      "",
    );
    sopChunks.forEach((chunk, idx) => {
      const title = (chunk.section_title ?? "").trim();
      const source = (chunk.source_file ?? "").trim();
      const chunkId = (chunk.chunk_id ?? "").trim();
      const parts: string[] = [];
      if (title) parts.push(title);
      if (source) parts.push(`source: ${source}`);
      if (chunkId) parts.push(`id: ${chunkId}`);
      if (chunk.score !== undefined && chunk.score !== null) parts.push(`relevance: ${chunk.score.toFixed(3)}`);
      const header = parts.length ? parts.join(" | ") : `Chunk ${idx + 1}`;
      lines.push(`### [${idx + 1}] ${header}`, (chunk.text ?? "").trim(), "");
    });
  } else {
    lines.push(
      "## Relevant SOP Context",
      "No SOP sections were retrieved for this query. " +
        "Assess based on general GMP principles and escalate to QA.",
      "",
    );
  }

  lines.push(
    "Using only the SOP context above, call `submit_deviation_assessment` " +
      "with all seven required fields.",
  );
  return lines.join("\n");
}

/** Parse and validate the tool-use JSON; throws ValidationError like the Python version. */
export function validateOutput(responseText: string): Row {
  let data: unknown;
  try {
    data = JSON.parse(responseText);
  } catch (e) {
    throw new ValidationError(`Response is not valid JSON: ${e instanceof Error ? e.message : e}`);
  }
  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    throw new ValidationError(`Expected a JSON object, got ${pyTypeName(data)}`);
  }
  const d = data as Row;

  const missing = REQUIRED_KEYS.filter((k) => !(k in d));
  if (missing.length) throw new ValidationError(`Missing required fields: ${pyRepr(missing)}`);

  if (!VALID_CLASSIFICATIONS.includes(d.classification)) {
    throw new ValidationError(
      `Invalid classification ${pyRepr(d.classification)}. Must be one of: ${pyRepr(VALID_CLASSIFICATIONS)}`,
    );
  }
  if (!VALID_SEVERITIES.includes(d.severity)) {
    throw new ValidationError(`Invalid severity ${pyRepr(d.severity)}. Must be one of: ${pyRepr(VALID_SEVERITIES)}`);
  }
  if (typeof d.qa_escalation !== "boolean") {
    throw new ValidationError(`qa_escalation must be a boolean, got ${pyTypeName(d.qa_escalation)}`);
  }
  for (const key of ["impact", "immediate_action", "missing_info", "draft_summary"]) {
    if (typeof d[key] !== "string" || !d[key].trim()) {
      throw new ValidationError(`Field '${key}' must be a non-empty string`);
    }
  }
  return d;
}

export interface AssessmentTrace {
  input_tokens: number;
  output_tokens: number;
  model_output_raw: string;   // JSON string from the tool_use block
  error: string | null;
  is_fallback: boolean;
}

const MAX_ATTEMPTS = 3;

/**
 * Assess a deviation with up to 2 retries and the conservative safe fallback
 * (assess_deviation_traced). Returns the assessment and trace metadata.
 */
export async function assessDeviationTraced(
  env: Env,
  userText: string,
  sopChunks: Partial<SopChunk>[],
  maxTokens = 1024,
): Promise<[Row, AssessmentTrace]> {
  const baseUserMessage = buildUserPrompt(userText, sopChunks);
  let currentMessage = baseUserMessage;
  let lastError: string | null = null;
  let lastResponse: LLMResponse | null = null;

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const response = await callHaiku(
      env, SYSTEM_PROMPT, currentMessage, maxTokens,
      [DEVIATION_ASSESSMENT_TOOL], { type: "tool", name: "submit_deviation_assessment" },
    );
    lastResponse = response;

    if (!succeeded(response)) {
      lastError = response.error || "Unknown LLM error";
      if (attempt < MAX_ATTEMPTS) {
        currentMessage =
          baseUserMessage +
          `\n\n[System note: previous attempt failed (${lastError}). ` +
          "Please try again and call submit_deviation_assessment.]";
      }
      continue;
    }

    try {
      const validated = validateOutput(response.text);
      return [validated, {
        input_tokens: response.input_tokens,
        output_tokens: response.output_tokens,
        model_output_raw: response.text,
        error: null,
        is_fallback: false,
      }];
    } catch (e) {
      if (!(e instanceof ValidationError)) throw e;
      lastError = e.message;
      if (attempt < MAX_ATTEMPTS) {
        currentMessage =
          baseUserMessage +
          `\n\n[System note: your previous response failed validation ` +
          `(${e.message}). Retry — call submit_deviation_assessment with all ` +
          "seven required fields correctly populated.]";
      }
    }
  }

  return [{ ...SAFE_FALLBACK }, {
    input_tokens: lastResponse?.input_tokens ?? 0,
    output_tokens: lastResponse?.output_tokens ?? 0,
    model_output_raw: lastResponse?.text ?? "",
    error: lastError,
    is_fallback: true,
  }];
}

/** assess_deviation: same pipeline, assessment only (used by the eval runner). */
export async function assessDeviation(env: Env, userText: string, sopChunks: Partial<SopChunk>[]): Promise<Row> {
  return (await assessDeviationTraced(env, userText, sopChunks))[0];
}
