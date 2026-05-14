"""
crop_screenshots.py — Produce clean zoomed-in screenshots for docs/demo/.

Changes:
  04-evals.png    → crop to top ~620px (summary cards + first table rows)
  05-feedback.png → crop to top ~680px (stats bar + first 3 cards)
  02-results.png  → REMOVED (Deviation Review — not needed in demo)

Remaining ordered set after this script:
  01-chat.png       (unchanged)
  02-dashboard.png  (renamed from 03-dashboard.png)
  03-evals.png      (cropped from 04-evals.png)
  04-feedback.png   (cropped from 05-feedback.png)
"""

from PIL import Image
import shutil
import os

DEMO = r"C:\Users\ADMIN\Desktop\sop-deviation-review\docs\demo"

def crop_and_save(src_name, dst_name, top, bottom, src_dir=DEMO, dst_dir=DEMO):
    src = os.path.join(src_dir, src_name)
    dst = os.path.join(dst_dir, dst_name)
    img = Image.open(src)
    w, h = img.size
    print(f"  {src_name}: {w}x{h}  crop y={top}..{bottom}  -> {dst_name}")
    cropped = img.crop((0, top, w, min(bottom, h)))
    cropped.save(dst, "PNG", optimize=True)
    kb = os.path.getsize(dst) // 1024
    print(f"    saved {dst_name}  ({kb} KB)")

def copy_unchanged(src_name, dst_name, d=DEMO):
    src = os.path.join(d, src_name)
    dst = os.path.join(d, dst_name)
    if src != dst:
        shutil.copy2(src, dst)
    img = Image.open(dst)
    kb = os.path.getsize(dst) // 1024
    print(f"  {src_name} -> {dst_name}  ({img.width}x{img.height}, {kb} KB)  [unchanged]")

print("=== Screenshot cleanup ===\n")

# 1. Chat — keep as-is, just rename to 01
copy_unchanged("01-chat.png", "01-chat.png")

# 2. Remove deviation review (02-results.png)
results_path = os.path.join(DEMO, "02-results.png")
if os.path.exists(results_path):
    os.remove(results_path)
    print(f"  02-results.png  DELETED  (Deviation Review — removed per spec)")

# 3. Dashboard — rename 03 → 02
copy_unchanged("03-dashboard.png", "02-dashboard.png")

# 4. Evals — crop to summary panel + first batch of table rows
#    Full height is ~3600px; the meaningful top section ends around y=700
crop_and_save("04-evals.png", "03-evals.png", top=0, bottom=700)

# 5. Feedback — crop to stats bar + first 3 cards
#    Full height is ~9000px; readable content in first ~650px
crop_and_save("05-feedback.png", "04-feedback.png", top=0, bottom=650)

# 6. Remove old numbered originals that have been superseded
for old in ["03-dashboard.png", "04-evals.png", "05-feedback.png"]:
    p = os.path.join(DEMO, old)
    if os.path.exists(p):
        os.remove(p)
        print(f"  {old}  removed (superseded by renamed/cropped version)")

print("\n=== Final docs/demo/ contents ===")
for f in sorted(os.listdir(DEMO)):
    p = os.path.join(DEMO, f)
    kb = os.path.getsize(p) // 1024
    if f.endswith(".png"):
        img = Image.open(p)
        print(f"  {f}  {img.width}x{img.height}  {kb} KB")
    else:
        print(f"  {f}  {kb} KB")
