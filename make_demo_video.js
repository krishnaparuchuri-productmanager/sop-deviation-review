/**
 * make_demo_video.js — Build a 60-second annotated MP4 demo from screenshots.
 *
 * Each slide: 7.5 s hold + 0.5 s crossfade = 8 s × 8 slides = 64 s (trimmed to 60 s)
 *
 * Run: node make_demo_video.js
 * Output: docs/demo/app-demo.mp4
 */

const ffmpegPath = require('ffmpeg-static');
const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const ROOT   = __dirname;
const DEMO   = path.join(ROOT, 'docs', 'demo');
const OUTPUT = path.join(DEMO, 'app-demo.mp4');
const TMP    = path.join(ROOT, 'tmp_video');

fs.mkdirSync(TMP, { recursive: true });

// ── Slide definitions ────────────────────────────────────────────────────────
// Each slide: source image, duration (s), annotation text (shown at bottom)
const SLIDES = [
  {
    img:  path.join(DEMO, '01-chat.png'),
    dur:  7.5,
    line1: 'SOP Deviation Review Assistant',
    line2: 'AI-powered GMP compliance tool for pharmaceutical QA',
  },
  {
    img:  path.join(DEMO, '01-chat.png'),
    dur:  7.5,
    line1: 'Step 1 — Submit a Deviation',
    line2: 'Paste any free-text deviation scenario and click Review',
  },
  {
    img:  path.join(DEMO, '02-results.png'),
    dur:  7.5,
    line1: 'Step 2 — Structured Assessment in < 10 s',
    line2: 'Classification · Severity · Impact · Immediate Action · QA Escalation',
  },
  {
    img:  path.join(DEMO, '02-results.png'),
    dur:  7.5,
    line1: 'Step 3 — LLM-Powered Workflow',
    line2: 'Claude Haiku + TF-IDF SOP retrieval + forced tool-use output',
  },
  {
    img:  path.join(DEMO, '03-dashboard.png'),
    dur:  7.5,
    line1: 'Step 4 — Analytics Dashboard',
    line2: 'Total reviews · Escalation rate · Token cost · Severity breakdown',
  },
  {
    img:  path.join(DEMO, '04-evals.png'),
    dur:  7.5,
    line1: 'Step 5 — Evaluation Suite',
    line2: 'LLM-as-judge · 4 dimensions · 87 % pass rate vs 13 % baseline',
  },
  {
    img:  path.join(DEMO, '05-feedback.png'),
    dur:  7.5,
    line1: 'Step 6 — Feedback Queue',
    line2: 'Human reviewer corrections feed back into the improvement loop',
  },
  {
    img:  path.join(DEMO, '01-chat.png'),
    dur:  7.5,
    line1: 'Built with Claude Code  ·  FastAPI  ·  React 18  ·  SQLite',
    line2: 'github.com/krishnaparuchuri-productmanager/sop-deviation-review',
  },
];

const W = 1440;
const H = 900;
const FPS = 25;

// ── Helper: escape text for FFmpeg drawtext ──────────────────────────────────
function esc(s) {
  return s
    .replace(/\\/g, '\\\\')
    .replace(/'/g, "’")   // replace straight apostrophe with curly to avoid shell issues
    .replace(/:/g, '\\:')
    .replace(/,/g, '\\,');
}

// ── Build one padded/annotated clip per slide ────────────────────────────────
const clipPaths = [];

for (let i = 0; i < SLIDES.length; i++) {
  const slide   = SLIDES[i];
  const outClip = path.join(TMP, `clip_${String(i).padStart(2, '0')}.mp4`);
  clipPaths.push(outClip);

  const nFrames = Math.round(slide.dur * FPS);

  // drawtext filter — two lines at bottom with a semi-transparent bar
  const barH    = 90;
  const barY    = H - barH;
  const line1Y  = H - barH + 12;
  const line2Y  = H - barH + 52;

  const vf = [
    // Scale + pad to exact 1440×900 (letterbox with black)
    `scale=${W}:${H}:force_original_aspect_ratio=decrease`,
    `pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2:black`,
    // Semi-transparent dark bar at bottom
    `drawbox=x=0:y=${barY}:w=${W}:h=${barH}:color=black@0.65:t=fill`,
    // Line 1 — bold headline
    `drawtext=text='${esc(slide.line1)}':fontsize=32:fontcolor=white:x=(w-text_w)/2:y=${line1Y}:fontfile=/Windows/Fonts/arialbd.ttf`,
    // Line 2 — subtitle
    `drawtext=text='${esc(slide.line2)}':fontsize=22:fontcolor=#cccccc:x=(w-text_w)/2:y=${line2Y}:fontfile=/Windows/Fonts/arial.ttf`,
  ].join(',');

  const cmd = [
    `"${ffmpegPath}"`,
    `-y`,
    `-loop 1 -i "${slide.img}"`,
    `-vf "${vf}"`,
    `-t ${slide.dur}`,
    `-r ${FPS}`,
    `-c:v libx264 -preset fast -crf 22`,
    `-pix_fmt yuv420p`,
    `-an`,
    `"${outClip}"`,
  ].join(' ');

  console.log(`  Building clip ${i + 1}/${SLIDES.length}: ${path.basename(slide.img)} — "${slide.line1}"`);
  execSync(cmd, { stdio: 'inherit' });
}

// ── Crossfade-concat all clips using xfade ───────────────────────────────────
// xfade offset = cumulative duration of previous clips minus overlap (0.5 s each transition)
console.log('\n  Joining clips with crossfades...');

const XFADE_DUR = 0.5;

// Build complex filtergraph
let filterParts = [];
let inputArgs   = clipPaths.map(p => `-i "${p}"`).join(' ');
let prevLabel   = '[0:v]';

for (let i = 1; i < clipPaths.length; i++) {
  const offset  = SLIDES.slice(0, i).reduce((s, sl) => s + sl.dur, 0) - XFADE_DUR * i;
  const outLabel = i < clipPaths.length - 1 ? `[v${i}]` : '[vout]';
  filterParts.push(
    `${prevLabel}[${i}:v]xfade=transition=fade:duration=${XFADE_DUR}:offset=${offset.toFixed(3)}${outLabel}`
  );
  prevLabel = `[v${i}]`;
}

const filterComplex = filterParts.join('; ');

// Total duration = sum of all slide durations - (n-1) * xfade overlap, capped at 60 s
const rawDur  = SLIDES.reduce((s, sl) => s + sl.dur, 0) - XFADE_DUR * (SLIDES.length - 1);
const finalDur = Math.min(rawDur, 60);

const concatCmd = [
  `"${ffmpegPath}"`,
  `-y`,
  inputArgs,
  `-filter_complex "${filterComplex}"`,
  `-map "[vout]"`,
  `-t ${finalDur}`,
  `-c:v libx264 -preset fast -crf 20`,
  `-pix_fmt yuv420p`,
  `-movflags +faststart`,
  `"${OUTPUT}"`,
].join(' ');

execSync(concatCmd, { stdio: 'inherit' });

// ── Cleanup tmp ───────────────────────────────────────────────────────────────
fs.rmSync(TMP, { recursive: true, force: true });

const size = (fs.statSync(OUTPUT).size / (1024 * 1024)).toFixed(1);
console.log(`\n✅  Done!  →  docs/demo/app-demo.mp4  (${size} MB, ${finalDur}s)`);
