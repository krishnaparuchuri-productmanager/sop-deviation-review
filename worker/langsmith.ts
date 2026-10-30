/**
 * langsmith.ts — Best-effort run logging to LangSmith (replaces the Python
 * langsmith client call in routes/review.py). Skipped when LANGSMITH_API_KEY is unset.
 */

import { Env, Row } from "./util";

export async function pushLangSmithRun(env: Env, run: {
  inputs: Row; outputs: Row; start: Date; end: Date; metadata: Row;
}): Promise<void> {
  const key = env.LANGSMITH_API_KEY;
  if (!key) return;
  const endpoint = (env.LANGSMITH_ENDPOINT || "https://api.smith.langchain.com").replace(/\/+$/, "");
  const project = env.LANGSMITH_PROJECT || env.LANGCHAIN_PROJECT || "default";
  try {
    const res = await fetch(`${endpoint}/runs`, {
      method: "POST",
      headers: { "x-api-key": key, "Content-Type": "application/json" },
      body: JSON.stringify({
        id: crypto.randomUUID(),
        name: "gmp-deviation-review",
        run_type: "chain",
        session_name: project,
        inputs: run.inputs,
        outputs: run.outputs,
        start_time: run.start.toISOString(),
        end_time: run.end.toISOString(),
        tags: ["pharma", "gmp", "deviation"],
        extra: { metadata: run.metadata },
      }),
    });
    if (!res.ok) console.warn(`[langsmith] push failed: HTTP ${res.status}`);
  } catch (e) {
    console.warn(`[langsmith] push failed: ${e}`);
  }
}
