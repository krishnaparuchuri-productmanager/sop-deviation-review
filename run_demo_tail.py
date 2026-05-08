"""
run_demo_tail.py — Show dashboard metrics and run eval suite.
All 25 reviews already submitted via run_demo.py.
"""
import json, sys, time, urllib.request, urllib.error
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8001"

def post_json(path, body, timeout=600):
    data = json.dumps(body).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=data,
                                  headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def get_json(path, timeout=30):
    with urllib.request.urlopen(f"{BASE}{path}", timeout=timeout) as r:
        return json.loads(r.read())

# ── Dashboard metrics ──────────────────────────────────────────────────────────
print("=" * 60)
print("  Dashboard Metrics")
print("=" * 60)
m = get_json("/api/dashboard/metrics")
print(f"  total_chats       : {m['total_chats']}")
print(f"  escalation_rate   : {m['escalation_rate']}%")
print(f"  avg_latency_ms    : {m['avg_latency_ms']:.0f} ms")
print(f"  total_tokens_used : {m['total_tokens_used']:,}")
print(f"  estimated_cost    : ${m['estimated_cost_usd']:.4f}")
print(f"  downvote_rate     : {m['downvote_rate']}%")
for s in m.get("top_severity_breakdown", []):
    print(f"  severity {s['severity']:6}  : {s['count']} reviews")

# ── Feedback ───────────────────────────────────────────────────────────────────
print()
fb = get_json("/api/feedback?limit=100")
up   = sum(1 for f in fb["feedback"] if f["rating"] ==  1)
down = sum(1 for f in fb["feedback"] if f["rating"] == -1)
print(f"  feedback records  : {fb['count']}  (thumbs-up: {up}, thumbs-down: {down})")

# ── Eval run ───────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("  Running Eval Suite (3-6 min)...")
print("=" * 60)
t0 = time.time()
resp = post_json("/api/evals/run", {}, timeout=600)
dur = time.time() - t0
a, b = resp["actual"], resp["baseline"]

print(f"  Completed in {dur:.0f}s  |  run_id: {resp['run_id'][:16]}...")
print(f"  Total rows saved : {resp['total_rows']}")
print()
print(f"  {'Dimension':<22} {'Agent':>7}  {'Baseline':>9}")
print("  " + "-" * 42)
for label, key in [
    ("Groundedness",   "avg_groundedness"),
    ("Classification", "avg_classification"),
    ("Escalation",     "avg_escalation"),
    ("Clarity",        "avg_clarity"),
    ("Total /8",       "avg_total_score"),
]:
    print(f"  {label:<22} {a[key]:>7.2f}   {b[key]:>9.2f}")
print()
print(f"  Agent pass rate    : {a['pass_rate_pct']:.0f}%  ({a['pass_count']}/{a['cases']} cases)")
print(f"  Baseline pass rate : {b['pass_rate_pct']:.0f}%  ({b['pass_count']}/{b['cases']} cases)")
print()
print("All done. Open http://localhost:5173 to view all screens.")
