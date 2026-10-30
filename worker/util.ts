/**
 * util.ts — small helpers that reproduce Python behaviour the backend relied on
 * (json.dumps formatting, repr(), round()) so stored data, error messages and
 * prompts come out identical to the FastAPI version.
 */

export type Row = Record<string, any>;

// Minimal D1 typings so the Worker needs no extra packages.
export interface D1Result<T = Row> { results: T[]; meta: { last_row_id: number; changes: number } }
export interface D1Stmt {
  bind(...values: unknown[]): D1Stmt;
  first<T = Row>(): Promise<T | null>;
  all<T = Row>(): Promise<D1Result<T>>;
  run(): Promise<D1Result>;
}
export interface D1Database { prepare(sql: string): D1Stmt; batch(stmts: D1Stmt[]): Promise<D1Result[]> }
export interface Fetcher { fetch(input: RequestInfo, init?: RequestInit): Promise<Response> }

export interface Env {
  DB: D1Database;
  ANTHROPIC_API_KEY?: string;
  ANTHROPIC_BASE_URL?: string;          // override for local testing
  EVAL_SECRET_TOKEN?: string;
  AGENTOPS?: Fetcher;                   // service binding to the AgentOps Worker
  AGENTOPS_API_URL?: string;            // used when no service binding is configured
  AGENTOPS_AGENT_ID?: string;
  LANGSMITH_API_KEY?: string;
  LANGSMITH_ENDPOINT?: string;
  LANGSMITH_PROJECT?: string;
  LANGCHAIN_PROJECT?: string;
}

export interface Ctx { waitUntil(p: Promise<unknown>): void }

export class HttpError extends Error {
  constructor(public status: number, public detail: unknown) { super(String(detail)); }
}

/** Python json.dumps: ", " / ": " separators; ensure_ascii escapes non-ASCII. */
export function dumps(v: unknown, ensureAscii = true): string {
  if (v === null || v === undefined) return "null";
  if (Array.isArray(v)) return `[${v.map((x) => dumps(x, ensureAscii)).join(", ")}]`;
  if (typeof v === "object") {
    return `{${Object.entries(v as Row).map(([k, x]) => `${dumps(k, ensureAscii)}: ${dumps(x, ensureAscii)}`).join(", ")}}`;
  }
  if (typeof v === "string") {
    const s = JSON.stringify(v);
    return ensureAscii
      ? s.replace(/[\u007f-￿]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, "0")}`)
      : s;
  }
  return JSON.stringify(v);
}

/** Python repr() for JSON-shaped values (str, int, float, bool, None, list, dict). */
export function pyRepr(v: unknown): string {
  if (v === null || v === undefined) return "None";
  if (v === true) return "True";
  if (v === false) return "False";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : String(v);
  if (typeof v === "string") {
    const q = v.includes("'") && !v.includes('"') ? '"' : "'";
    const body = v
      .replace(/\\/g, "\\\\")
      .replace(/\n/g, "\\n").replace(/\r/g, "\\r").replace(/\t/g, "\\t")
      .replace(new RegExp(q, "g"), `\\${q}`);
    return q + body + q;
  }
  if (Array.isArray(v)) return `[${v.map(pyRepr).join(", ")}]`;
  return `{${Object.entries(v as Row).map(([k, x]) => `${pyRepr(k)}: ${pyRepr(x)}`).join(", ")}}`;
}

/** Python type(x).__name__ for a value parsed from JSON. */
export function pyTypeName(v: unknown): string {
  if (v === null || v === undefined) return "NoneType";
  if (typeof v === "boolean") return "bool";
  if (typeof v === "number") return Number.isInteger(v) ? "int" : "float";
  if (typeof v === "string") return "str";
  return Array.isArray(v) ? "list" : "dict";
}

/** Python round(x, n) for display values. */
export function pyRound(x: number, n: number): number {
  return Number(x.toFixed(n));
}

/** UTC timestamp in the backend's "%Y-%m-%dT%H:%M:%SZ" format. */
export const utcStamp = (d = new Date()) => d.toISOString().slice(0, 19) + "Z";

/** Character count the way Python len() sees it (code points, not UTF-16 units). */
export const pyLen = (s: string) => [...s].length;
