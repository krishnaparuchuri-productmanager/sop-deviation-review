"""
rebuild_demo.py -- Rebuild all docs/demo/ screenshots for the user-journey demo.

Journey narrative:
  1. User opens the deviation workflow and enters details
  2. User submits -- system processes the input
  3. System-generated review decision (HIGH / QA escalation flag / impact / action)
  4. System explains the decision: draft CAPA summary + retrieved SOP grounding
  5. Analytics dashboard -- all cases tracked over time
  6. Feedback queue -- reviewer corrections feed back into the loop

Output files in docs/demo/:
  01-deviation-form.png      Chat page with deviation filled in
  02-review-decision.png     Results top: severity badge + QA flag + impact + action
  03-review-reasoning.png    Results mid: draft summary + retrieved SOP sections
  04-dashboard.png           Aggregate analytics
  05-feedback-queue.png      Reviewer feedback cards

Deletes all previous numbered PNGs before writing the new set.
"""

import sys
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(r"C:\Users\ADMIN\Desktop\sop-deviation-review")
SRC  = ROOT / "screenshots"     # original full-page captures
DEMO = ROOT / "docs" / "demo"
DEMO.mkdir(parents=True, exist_ok=True)

# ── Helpers ───────────────────────────────────────────────────────────────────

def dims(path):
    img = Image.open(path)
    return img.width, img.height

def crop_save(src, dst, top, bottom, label=""):
    img = Image.open(src)
    w, h = img.size
    bot = min(bottom, h)
    cropped = img.crop((0, top, w, bot))
    cropped.save(dst, "PNG", optimize=True)
    kb = dst.stat().st_size // 1024
    print(f"  {dst.name}  {cropped.width}x{cropped.height}  {kb} KB  {label}")

def copy_as(src, dst, label=""):
    img = Image.open(src)
    img.save(dst, "PNG", optimize=True)
    kb = dst.stat().st_size // 1024
    print(f"  {dst.name}  {img.width}x{img.height}  {kb} KB  {label}")

# ── Remove old numbered PNGs ──────────────────────────────────────────────────
removed = []
for f in DEMO.glob("0*.png"):
    f.unlink()
    removed.append(f.name)
if removed:
    print(f"Removed old PNGs: {', '.join(sorted(removed))}\n")

# ── Print source dimensions for planning ─────────────────────────────────────
print("Source dimensions:")
for name in ["1-chat.png", "2-results.png", "3-dashboard.png",
             "4-evals.png", "5-feedback.png"]:
    p = SRC / name
    if p.exists():
        w, h = dims(p)
        print(f"  {name}  {w}x{h}")
print()

# ── 01  Deviation form (chat, filled textarea, Review Deviation button) ───────
# Full page is 1440x900 -- copy as-is, it is already clean
copy_as(SRC / "1-chat.png", DEMO / "01-deviation-form.png",
        label="[chat form filled, no crop needed]")

# ── 02  Review decision header ────────────────────────────────────────────────
# Results page: crop to top ~640px
# Contains: QA Review Required banner, HIGH severity badge,
#           Impact Assessment paragraph, Recommended Immediate Action heading
crop_save(SRC / "2-results.png", DEMO / "02-review-decision.png",
          top=0, bottom=640,
          label="[severity badge + QA flag + impact + immediate action]")

# ── 03  Review reasoning & SOP grounding ─────────────────────────────────────
# Results page: crop y=570 to y=1120
# Contains: Draft Summary, Additional Information Needed,
#           Retrieved SOP Sections (3 source chunks)
crop_save(SRC / "2-results.png", DEMO / "03-review-reasoning.png",
          top=570, bottom=1120,
          label="[draft summary + SOP retrieval sources]")

# ── 04  Dashboard ─────────────────────────────────────────────────────────────
copy_as(SRC / "3-dashboard.png", DEMO / "04-dashboard.png",
        label="[aggregate analytics -- no crop]")

# ── 05  Feedback queue (top crop) ─────────────────────────────────────────────
crop_save(SRC / "5-feedback.png", DEMO / "05-feedback-queue.png",
          top=0, bottom=650,
          label="[stats bar + first card]")

print("\nFinal docs/demo/ contents:")
for f in sorted(DEMO.iterdir()):
    kb = f.stat().st_size // 1024
    if f.suffix == ".png":
        img = Image.open(f)
        print(f"  {f.name}  {img.width}x{img.height}  {kb} KB")
    else:
        print(f"  {f.name}  {kb} KB")
