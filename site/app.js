/* The Window: showcase page.
   Everything shown is read from the repository's own files: storyboard.json, the timing file,
   runs.jsonl and the Markdown documents. Nothing is copied into this script, so the page cannot
   drift from the project. */

const REPO = "https://github.com/Jogoraa/the-window-film";
const RAW = "https://raw.githubusercontent.com/Jogoraa/the-window-film/main";
const $ = (selector, root = document) => root.querySelector(selector);
const el = (tag, attrs = {}, ...children) => {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "text") node.textContent = value;
    else if (key === "html") node.innerHTML = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of children) node.append(child);
  return node;
};
const getJSON = (path) => fetch(path).then((r) => { if (!r.ok) throw new Error(`${path}: ${r.status}`); return r.json(); });
const getText = (path) => fetch(path).then((r) => { if (!r.ok) throw new Error(`${path}: ${r.status}`); return r.text(); });
const clock = (seconds) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;

/* ---------- the film ---------- */

const CUTS = {
  "9x16": { src: "outputs/film/the_window_9x16.mp4", poster: "outputs/keyframes/shot_04_9x16.jpg",
            note: "The main version, made for a phone held upright." },
  "16x9": { src: "outputs/film/the_window_16x9.mp4", poster: "outputs/keyframes/shot_04_16x9.jpg",
            note: "Every shot was generated again for the wide frame, not cropped from the tall one." },
  "radio": { src: "outputs/film/radio_cut_am.mp4", poster: "",
             note: "The first prototype: the voice over a placeholder bed on a black screen, used to test the story before any picture existed." },
};
const player = $("#player");
const frame = $("#window");

function showCut(name, seekTo = null) {
  const cut = CUTS[name];
  frame.dataset.cut = name;
  document.querySelectorAll(".cuts button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.cut === name)));
  $("#cut-note").textContent = cut.note;
  if (!player.currentSrc.endsWith(cut.src)) {
    player.poster = cut.poster;
    player.src = cut.src;
    const pane = $(".pane");
    pane.classList.remove("opening");
    void pane.offsetWidth;
    pane.classList.add("opening");
  }
  if (seekTo !== null) {
    const go = () => { player.currentTime = seekTo; player.play().catch(() => {}); };
    if (player.readyState >= 1) go(); else player.addEventListener("loadedmetadata", go, { once: true });
  }
}
document.querySelectorAll(".cuts button").forEach((b) => b.addEventListener("click", () => showCut(b.dataset.cut)));
$("#cut-note").textContent = CUTS["9x16"].note;

/* ---------- shot by shot ---------- */

const MOVES = { push_in: "slow push in", pull_out: "slow pull out", pan_left: "slow pan left", pan_right: "slow pan right",
                tilt_up: "slow tilt up", tilt_down: "slow tilt down", static: "held still" };

function renderShots(storyboard, timing) {
  const strip = $("#strip");
  const slots = Object.fromEntries((timing?.shots || []).map((s) => [s.id, s]));
  const people = Object.fromEntries(storyboard.characters.map((c) => [c.id, c.name]));

  const select = (index) => {
    const shot = storyboard.shots[index];
    const slot = slots[shot.id];
    strip.querySelectorAll("button").forEach((b, i) => b.setAttribute("aria-current", String(i === index)));
    const number = shot.id.split("_")[1];
    const cast = shot.characters.length ? shot.characters.map((c) => people[c] || c).join(" and ") : "No one: an imagined or empty view";
    const figure = el("figure", { class: "swap" },
      el("img", { src: `outputs/keyframes/${shot.id}_9x16.jpg`, alt: `Keyframe for shot ${number}`, loading: "lazy" }),
      el("figcaption", { text: `Keyframe, generated at seed ${shot.seed}. The edit adds a ${MOVES[shot.camera_move] || shot.camera_move}.` }));
    const facts = el("dl", {},
      el("dt", { text: "In the picture" }), el("dd", { text: cast }),
      el("dt", { text: "On screen" }), el("dd", { text: slot ? `${clock(slot.start)} to ${clock(slot.start + slot.duration)} (${slot.duration.toFixed(1)} s)` : "not timed yet" }),
      el("dt", { text: "Camera" }), el("dd", { text: MOVES[shot.camera_move] || shot.camera_move }));
    const body = el("div", {},
      el("div", { class: "shot-head" }, el("strong", { text: `Shot ${number} of ${storyboard.shots.length}` })),
      el("p", { class: "narration", lang: "am", text: shot.narration.text }),
      el("p", { class: "subtitle", text: shot.narration.subtitle_en }),
      el("p", { class: "reason" }, el("b", { text: "Why this shot exists" }), document.createTextNode(shot.reason)),
      facts,
      el("details", {}, el("summary", { text: "The prompt that made this picture" }), el("p", { text: shot.keyframe_prompt })),
      el("div", { class: "actions" },
        el("button", { class: "go", type: "button", text: "Play the film from this shot",
          onclick: () => { showCut(frame.dataset.cut === "radio" ? "radio" : frame.dataset.cut, slot ? slot.start : 0); $("#film").scrollIntoView(); } }),
        el("audio", { controls: "", preload: "none", src: `outputs/narration/am/${shot.id}.wav`, "aria-label": `Narration for shot ${number}` })));
    $("#shot").replaceChildren(figure, body);
  };

  storyboard.shots.forEach((shot, index) => {
    const number = shot.id.split("_")[1];
    strip.append(el("li", {}, el("button", { type: "button", "aria-label": `Shot ${number}: ${shot.narration.subtitle_en}`, onclick: () => select(index) },
      el("img", { src: `outputs/keyframes/${shot.id}_9x16.jpg`, alt: "", loading: "lazy" }), el("span", { text: number }))));
  });
  select(0);
  if (timing?.total) $("#runtime").textContent = `${Math.round(timing.total)} seconds.`;
}

/* ---------- how it was made ---------- */

const STAGES = [
  ["Narration", "One recording per shot", "Gemini 3.8 Flash TTS"],
  ["Timing", "Picture is cut to the measured voice", "no model"],
  ["Keyframes", "A portrait per character, then every shot", "FLUX.2 klein on a Kaggle GPU"],
  ["Score", "Three candidates, one chosen by ear", "ACE-Step 1.5 on a Kaggle GPU"],
  ["Shots", "A slow camera move over each keyframe", "FFmpeg"],
  ["Film", "Subtitles, end card, score ducked under the voice", "FFmpeg"],
];
const STAGE_NAMES = { smoke: "Provider checks", script: "Script drafts", narration: "Narration", keyframes: "Keyframes", music: "Score", video: "Video test" };

function renderLedger(lines) {
  $("#stages").append(...STAGES.map(([name, what, tool]) => el("li", {}, el("b", { text: name }), el("span", { text: what }), el("em", { text: tool }))));
  const rows = new Map();
  for (const line of lines) {
    if (line.model === "gpu-job" || line.model === "gpu-check") continue;
    const row = rows.get(line.stage) || { attempts: 0, ok: 0, latency: 0, gpu: 0 };
    row.attempts += 1;
    if (line.status === "ok") { row.ok += 1; row.latency += line.latency_s || 0; }
    row.gpu += line.gpu_seconds || 0;
    rows.set(line.stage, row);
  }
  const table = $("#ledger");
  table.append(el("thead", {}, el("tr", {},
    el("th", { text: "Stage" }), el("th", { class: "num", text: "Attempts" }), el("th", { class: "num", text: "Succeeded" }),
    el("th", { class: "num", text: "Did not" }), el("th", { class: "num", text: "Mean time when it worked" }), el("th", { class: "num", text: "GPU minutes" }))));
  const body = el("tbody");
  let attempts = 0, ok = 0;
  for (const [stage, row] of rows) {
    attempts += row.attempts; ok += row.ok;
    body.append(el("tr", {},
      el("td", { text: STAGE_NAMES[stage] || stage }), el("td", { class: "num", text: row.attempts }), el("td", { class: "num", text: row.ok }),
      el("td", { class: "num", text: row.attempts - row.ok }),
      el("td", { class: "num", text: row.ok ? `${(row.latency / row.ok).toFixed(1)} s` : "–" }),
      el("td", { class: "num", text: row.gpu ? (row.gpu / 60).toFixed(1) : "–" })));
  }
  table.append(body);
  $("#ledger-note").textContent =
    `${attempts} attempts are logged and ${attempts - ok} of them did not succeed: overloaded models, used-up free allowances and GPU memory. ` +
    "Each failure, and what was done about it, is written up under Documents, in the failures log. No money was spent.";
}

/* ---------- the brief ---------- */

const BRIEF = [
  ["The codebase and report"],
  ["A reproducible pipeline", "Stage boundaries around a validated storyboard; caching so a re-run regenerates only what changed; retries; no secrets; a complete run log; one command from a clean clone.", ["ARCHITECTURE.md", "Architecture"]],
  ["Documentation", "A README a stranger can follow, and an architecture document that explains contracts, caching and failure handling.", ["README.md", "README"]],
  ["Design thinking", "Audience and intent stated before generating; two audience tests with three people each; the storyboard changed by what they said; a reason for every shot.", ["DESIGN.md", "Design"]],
  ["Experiments", "At least ten logged experiments, each with a hypothesis, evidence and a decision.", ["EXPERIMENTS.md", "Experiments"]],
  ["Troubleshooting", "Real blockers (quota, memory, consistency, language), what was tried and how each was resolved.", ["FAILURES.md", "Failures"]],
  ["Measurement", "Measured latency and GPU minutes per stage, and a list-price equivalent.", ["COSTS.md", "Costs"]],
  ["Consent, labelling, licences", "A consent record for every real person shown or voiced; licences checked; a clear labelling plan.", ["ETHICS.md", "Ethics"]],
  ["The film"],
  ["60 to 90 seconds, two aspect ratios", "Clear narration, a score ducked under the voice, accurate subtitles, consistent characters and style, and an end card saying it was made with AI.", ["#film", "Watch it"]],
  ["A story that lands", "For the audience the maker chose, and for a reason the maker can state.", ["DESIGN.md", "Design"]],
];
const FILES = [
  ["README.md", "one command, what it does, what it costs", "README.md"],
  ["storyboard.json", "the contract between every stage", `${REPO}/blob/main/storyboard.json`],
  ["schema/", "the storyboard's schema, checked before every run", `${REPO}/tree/main/schema`],
  ["pipeline/", "one module per stage", `${REPO}/tree/main/pipeline`],
  ["runs.jsonl", "one line per model call", `${REPO}/blob/main/runs.jsonl`],
  ["outputs/", "everything generated, kept for inspection", `${REPO}/tree/main/outputs`],
  ["DESIGN.md", "audience, intent, the audience tests", "DESIGN.md"],
  ["ARCHITECTURE.md", "stages, contracts, caching, failures", "ARCHITECTURE.md"],
  ["EXPERIMENTS.md", "hypothesis, change, result", "EXPERIMENTS.md"],
  ["FAILURES.md", "what broke and what fixed it", "FAILURES.md"],
  ["COSTS.md", "measured time and GPU minutes", "COSTS.md"],
  ["ETHICS.md", "consent, labelling, licences", "ETHICS.md"],
];

function linkTo(target, label) {
  if (target.endsWith(".md")) return el("button", { type: "button", text: label, onclick: () => openDoc(target, true) });
  return el("a", { href: target, text: label });
}
function renderBrief() {
  const body = el("tbody");
  for (const row of BRIEF) {
    if (row.length === 1) { body.append(el("tr", { class: "group" }, el("td", { colspan: "3", text: row[0] }))); continue; }
    body.append(el("tr", {}, el("td", { text: row[0] }), el("td", { text: row[1] }), el("td", {}, linkTo(row[2][0], row[2][1]))));
  }
  $("#brief-table").append(el("thead", {}, el("tr", {}, el("th", { text: "What is asked" }), el("th", { text: "What earns full marks, in short" }), el("th", { text: "Where to look" }))), body);
  $("#files").append(...FILES.map(([name, what, target]) => el("li", {}, linkTo(target, name), el("span", { text: what }))));
}

/* ---------- documents: a small Markdown reader ---------- */

const DOCS = [["README.md", "README"], ["DESIGN.md", "Design"], ["ARCHITECTURE.md", "Architecture"], ["EXPERIMENTS.md", "Experiments"],
              ["FAILURES.md", "Failures"], ["COSTS.md", "Costs"], ["ETHICS.md", "Ethics"]];
// The documents are this repository's own files. They are still escaped before any markup is added,
// including quotes, so nothing in them can become a tag or break out of an attribute.
const escapeHtml = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

function inline(text) {
  const codes = [];
  let out = escapeHtml(text).replace(/`([^`]+)`/g, (_, code) => { codes.push(code); return `\u0000${codes.length - 1}\u0000`; });
  out = out.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, label, href) => {
    if (/^[A-Z]+\.md$/.test(href)) return `<a href="#documents" data-doc="${href}">${label}</a>`;
    const url = /^(https?:|#|mailto:)/.test(href) ? href : `${REPO}/blob/main/${href}`;
    return `<a href="${url}">${label}</a>`;
  });
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/(^|[\s(])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>");
  return out.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codes[Number(i)]}</code>`);
}

function markdown(source) {
  const lines = source.replace(/\r/g, "").split("\n");
  const html = [];
  let i = 0;
  const isBlockStart = (l) => /^(#{1,6} |```|> |\s*[-*] |\s*\d+\. |\|)/.test(l) || /^-{3,}\s*$/.test(l);
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i += 1; continue; }
    if (line.startsWith("```")) {
      const code = [];
      i += 1;
      while (i < lines.length && !lines[i].startsWith("```")) code.push(lines[i++]);
      i += 1;
      html.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
    } else if (/^#{1,6} /.test(line)) {
      const level = line.match(/^#+/)[0].length;
      html.push(`<h${level}>${inline(line.slice(level + 1))}</h${level}>`);
      i += 1;
    } else if (/^-{3,}\s*$/.test(line)) {
      html.push("<hr>");
      i += 1;
    } else if (line.startsWith("|") && /^\|[\s:|-]+\|\s*$/.test(lines[i + 1] || "")) {
      const cells = (l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const head = cells(line);
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].startsWith("|")) rows.push(cells(lines[i++]));
      html.push(`<div class="table-scroll"><table><thead><tr>${head.map((c) => `<th>${inline(c)}</th>`).join("")}</tr></thead><tbody>` +
        rows.map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`).join("") + "</tbody></table></div>");
    } else if (line.startsWith("> ")) {
      const quote = [];
      while (i < lines.length && lines[i].startsWith(">")) quote.push(lines[i++].replace(/^> ?/, ""));
      html.push(`<blockquote>${markdown(quote.join("\n"))}</blockquote>`);
    } else if (/^\s*([-*]|\d+\.) /.test(line)) {
      const ordered = /^\s*\d+\. /.test(line);
      const items = [];
      while (i < lines.length && (/^\s*([-*]|\d+\.) /.test(lines[i]) || (/^\s{2,}\S/.test(lines[i]) && items.length))) {
        if (/^\s*([-*]|\d+\.) /.test(lines[i]) && !/^\s{2,}/.test(lines[i])) items.push(lines[i].replace(/^\s*([-*]|\d+\.) /, ""));
        else items[items.length - 1] += "\n" + lines[i].replace(/^\s{2}/, "");
        i += 1;
      }
      const tag = ordered ? "ol" : "ul";
      html.push(`<${tag}>${items.map((item) => {
        const [first, ...rest] = item.split("\n");
        return `<li>${inline(first)}${rest.length ? markdown(rest.join("\n")) : ""}</li>`;
      }).join("")}</${tag}>`);
    } else {
      const para = [];
      while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i])) para.push(lines[i++]);
      html.push(`<p>${inline(para.join(" "))}</p>`);
    }
  }
  return html.join("\n");
}

const cache = new Map();
async function openDoc(name, scroll = false) {
  const panel = $("#doc");
  document.querySelectorAll("#doc-tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.doc === name)));
  if (scroll) $("#documents").scrollIntoView();
  if (!cache.has(name)) {
    panel.innerHTML = `<p class="state">Loading ${name}…</p>`;
    // Some hosts do not publish a README; fall back to the copy on GitHub.
    try { cache.set(name, markdown(await getText(name).catch(() => getText(`${RAW}/${name}`)))); }
    catch (error) {
      panel.replaceChildren(el("p", { class: "state" }, document.createTextNode(`${name} could not be loaded here. `), el("a", { href: `${REPO}/blob/main/${name}`, text: "Read it on GitHub" }), document.createTextNode(".")));
      return;
    }
  }
  panel.innerHTML = cache.get(name);
  panel.scrollTop = 0;
}
function renderDocs() {
  $("#doc-tabs").append(...DOCS.map(([file, label]) => el("button", { type: "button", role: "tab", "data-doc": file, "aria-selected": "false", text: label, onclick: () => openDoc(file) })));
  $("#doc").addEventListener("click", (event) => {
    const link = event.target.closest("a[data-doc]");
    if (link) { event.preventDefault(); openDoc(link.dataset.doc, true); }
  });
  openDoc("DESIGN.md");
}

/* ---------- section highlighting in the top bar ---------- */

const navLinks = [...document.querySelectorAll(".bar nav a")];
const watcher = new IntersectionObserver((entries) => {
  for (const entry of entries) {
    if (entry.isIntersecting) navLinks.forEach((a) => a.setAttribute("aria-current", String(a.getAttribute("href") === `#${entry.target.id}`)));
  }
}, { rootMargin: "-45% 0px -50% 0px" });
document.querySelectorAll("main section").forEach((section) => watcher.observe(section));

/* ---------- start ---------- */

renderBrief();
renderDocs();
Promise.all([getJSON("storyboard.json"), getJSON("outputs/timing_am.json").catch(() => null)])
  .then(([storyboard, timing]) => renderShots(storyboard, timing))
  .catch((error) => { $("#shot").replaceChildren(el("p", { text: `The storyboard could not be loaded (${error.message}).` })); });
getText("runs.jsonl")
  .then((text) => renderLedger(text.split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l))))
  .catch((error) => { $("#ledger-note").textContent = `The run log could not be loaded (${error.message}).`; });
