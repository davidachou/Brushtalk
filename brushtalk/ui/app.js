"use strict";

const token = new URLSearchParams(location.search).get("token") || "";

const ICONS = {
  mic: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v4M8 22h8"/>',
  stop: '<rect x="5" y="5" width="14" height="14" rx="2" class="s"/>',
  pause: '<path d="M9 5v14M15 5v14"/>',
  play: '<path d="M7 4.5v15l12-7.5z" class="s"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.9 2.9l-.1-.1a1.7 1.7 0 0 0-2.9 1.2V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-2.9-1.2l-.1.1a2 2 0 1 1-2.9-2.9l.1-.1a1.7 1.7 0 0 0-1.2-2.9H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.2-2.9l-.1-.1a2 2 0 1 1 2.9-2.9l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 2.9 1.2l.1-.1a2 2 0 1 1 2.9 2.9l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/>',
  more: '<circle cx="5" cy="12" r="1.6" class="s"/><circle cx="12" cy="12" r="1.6" class="s"/><circle cx="19" cy="12" r="1.6" class="s"/>',
  check: '<path class="s" d="M3.6 12.6c1.8.3 4 1.8 5.6 4 2.4-4.6 6.4-9 11.4-12.2.4-.2.6.2.3.5C16.4 9 13 13.6 10.4 19.2c-.4.9-1.4 1-1.9.2-1.3-2.4-2.9-4.6-5-6.2-.3-.2-.2-.6.1-.6z"/>',
  alert: '<path d="M12 9v4M12 17h.01M10.3 3.9 2.4 17.5A2 2 0 0 0 4.1 20.5h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  edit: '<path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  trash: '<path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1L5 6"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5M21 12a9 9 0 0 1-15 6.7L3 16M3 21v-5h5"/>',
  sparkle: '<path d="M12 3 13.8 9.2 20 11l-6.2 1.8L12 19l-1.8-6.2L4 11l6.2-1.8z"/>',
  history: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  compare: '<path d="M4 7h16M4 12h10M4 17h13"/>',
  back: '<path d="M15 18l-6-6 6-6"/>',
  prompt: '<path d="M4 5h16v11H9l-5 4z"/><path d="M8 9h8M8 12h5"/>',
};

const S = {
  snap: null,
  version: -1,
  wasRecording: null,
  meetings: [],
  query: "",
  view: "home",
  selected: null,
  detail: null,
  detailKey: "",
  tab: "notes",
  editing: false,
  settings: null,
  devices: null,
  checks: null,
  menuOpen: false,
  transcriptFilter: "",
  meter: { mic: 0, system: 0 },
  testing: false,
  original: null,
  myNotesOpen: false,
  overview: null,
  onlyMine: false,
  engines: [],
  transcriptVersion: null,
  testId: null,
  test: null,
  sample: 0,
  discardingTest: false,
  promptId: null,
  prompt: null,
  typedDraft: "",
  discardingPrompt: false,
};

const $ = (selector, root = document) => root.querySelector(selector);

// Everything from outside the app goes in as text nodes, never as HTML: a transcript can contain anything.
function h(tag, props, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === "value") el.value = value;
    else if (key === "checked" || key === "disabled" || key === "selected") el[key] = Boolean(value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === undefined || child === null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

function icon(name, extra = "") {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", `icon ${extra}`.trim());
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = ICONS[name];
  svg.querySelectorAll(".s").forEach((node) => {
    node.setAttribute("fill", "currentColor");
    node.setAttribute("stroke", "none");
  });
  return svg;
}

// A page's title, with its brush character. It writes itself the first time you open that page, and just sits there after that.
const writtenTitles = new Set();

function pageTitle(ch, text) {
  const first = !writtenTitles.has(ch);
  writtenTitles.add(ch);
  return h("div", { class: "page-title" }, Ink.glyph(ch, "still", { size: 46, write: first, seconds: 0.7 }), h("h1", {}, text));
}

// An empty screen, with a pale brush character.
function emptyNote(ch, ...children) {
  return h("div", { class: "empty-tab" }, Ink.glyph(ch, "faint", { size: 76 }), ...children);
}

// The live screens: the wave across the top, your status as a brush character, the time, and the controls below.
function stageView({ ch, kind, glyphId, word, wordId, time, timeId, below }) {
  const canvas = h("canvas", { class: "wave" });
  const view = h(
    "div",
    { class: "stage-view" },
    h(
      "div",
      { class: "stage" },
      canvas,
      h(
        "div",
        { class: "stage-status" },
        Ink.glyph(ch, kind, { size: 96, write: true, id: glyphId }),
        h("div", {}, h("div", { class: "stage-word", id: wordId }, word), h("div", { class: "stage-time", id: timeId }, time)),
      ),
    ),
    h("div", { class: "stage-below" }, below),
  );
  return { view, canvas };
}

const STAGE_FADE = { fadeFrom: 250, fadeTo: 470 };

async function api(path, options = {}) {
  const init = { method: options.method || "GET", headers: { "X-Token": token } };
  if (options.body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Something went wrong.");
  return data;
}

function toast(message, kind = "") {
  const el = h("div", { class: `toast ${kind}` }, message);
  $("#toast-root").append(el);
  setTimeout(() => el.remove(), kind === "error" ? 6000 : 2400);
}

async function attempt(action) {
  try {
    return await action();
  } catch (error) {
    toast(error.message, "error");
    return undefined;
  }
}

// ---- saves in order: tests/test_prompt_saves.py runs this part by itself.
// For what saves as you type: one at a time, so the last thing you typed is what ends up saved, however long each one takes.
function inOrder() {
  let last = Promise.resolve();
  return (send) => {
    last = last.then(send);
    return last;
  };
}
// ---- end of saves in order

async function copyText(text, done = "Copied") {
  let copied = true;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const area = h("textarea", { value: text });
    document.body.append(area);
    area.select();
    copied = document.execCommand("copy");
    area.remove();
  }
  if (copied) toast(done);
  else toast("That didn't reach the clipboard, so what's there hasn't changed. Try again in a moment.", "error");
}

// ---------------------------------------------------------------- formatting

function clock(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = String(total % 60).padStart(2, "0");
  return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${secs}` : `${String(minutes).padStart(2, "0")}:${secs}`;
}

function parseClock(text) {
  const parts = text.split(":").map(Number);
  return parts.length === 3 ? parts[0] * 3600 + parts[1] * 60 + parts[2] : parts[0] * 60 + parts[1];
}

function lengthText(seconds) {
  if (!seconds) return "";
  if (seconds < 60) return `${Math.max(1, Math.round(seconds))} sec`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} hr ${minutes % 60} min`;
}

function dayLabel(date) {
  const start = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const days = Math.round((start(new Date()) - start(date)) / 86400000);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return date.toLocaleDateString(undefined, { weekday: "long" });
  const options = { month: "long", day: "numeric" };
  if (date.getFullYear() !== new Date().getFullYear()) options.year = "numeric";
  return date.toLocaleDateString(undefined, options);
}

const timeOf = (date) => date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });

// ---------------------------------------------------------------- record slot

// 錄 for a meeting, 記 for a solo note, and 停 while paused, in red only while it's actually recording.
const recordingGlyph = (recording) => (recording.paused ? ["停", "still"] : [recording.mode === "solo" ? "記" : "錄", "live"]);
const listeningGlyph = (listening) => (listening.paused ? ["停", "still"] : ["聽", "live"]);

// The things it does. They sit side by side everywhere you can start one, and none of them is the main one.
const MODES = [
  { key: "hotkey", ch: "錄", name: "Meeting", about: "Your mic and all computer audio, for a call. You get notes.", start: () => startRecording() },
  { key: "hotkey_solo", ch: "記", name: "Solo note", about: "Only your mic, for thinking out loud. You get notes.", start: () => startRecording("", "solo") },
  { key: "hotkey_prompt", ch: "言", name: "Prompt", about: "Talk and copy as you read. You get a clear prompt to paste.", start: () => startPromptAndShow() },
  { key: "hotkey_code", ch: "碼", name: "Code", about: "Talk and copy as you read. You get the code itself, and nothing else, to paste and run.", start: () => startPromptAndShow("code") },
  { key: "hotkey_proofread", ch: "改", name: "Proofread", about: "Copy some text, and say how you want it edited if you like. You get the edited text, and nothing else, to paste.", start: () => startProofreadTalking() },
];

function startButton(mode, big = false) {
  const shortcut = S.snap?.[mode.key] || S.settings?.[mode.key] || "";
  const refused = S.snap?.hotkey_errors?.[mode.key];
  return h(
    "button",
    { class: big ? "mode-start big" : "mode-start", onclick: mode.start, title: big ? undefined : `${mode.about} ${refused ? "This shortcut isn't available." : `Shortcut: ${shortcut}`}` },
    big ? h("span", { class: "mode-enso" }, Ink.glyph(mode.ch, "live", { size: 48 })) : Ink.glyph(mode.ch, "live", { size: 32 }),
    h("span", { class: "mode-name" }, mode.name),
    big && h("span", { class: "mode-about" }, mode.about),
    h("kbd", { class: refused ? "refused" : undefined }, shortcut),
  );
}

function liveCard(glyph, status, word, show, stop, stopWord, pause) {
  return h(
    "div",
    { class: "live-card" },
    h(
      "button",
      { class: "live-row", onclick: show, title: "Show the recording" },
      Ink.glyph(...glyph, { size: 40, write: true, id: "side-glyph" }),
      h("span", { class: "live-time", id: "side-time" }, clock(status.elapsed)),
      h("span", { class: "live-label", id: "side-label" }, status.paused ? "Paused" : word),
    ),
    h(
      "div",
      { class: "live-actions" },
      h("button", { class: "danger", onclick: stop }, icon("stop"), stopWord),
      h(
        "button",
        { class: "icon-only", id: "side-pause", onclick: pause, "aria-label": status.paused ? "Resume" : "Pause", title: status.paused ? "Resume" : "Pause" },
        icon(status.paused ? "play" : "pause"),
      ),
    ),
    h("div", { class: "side-health", id: "side-health" }),
  );
}

function renderRecordSlot() {
  const slot = $("#record-slot");
  const recording = S.snap?.recording;
  const listening = S.snap?.prompt?.recording;
  slot.replaceChildren();
  if (recording?.active) {
    slot.append(liveCard(recordingGlyph(recording), recording, "Recording", () => setView("recording"), () => stopRecording(), "Stop", togglePause));
  } else if (listening) {
    slot.append(liveCard(listeningGlyph(listening), listening, "Listening", () => setView("prompts"), finishPrompt, "Finish", togglePromptPause));
  } else {
    // For the few seconds a dictation you've cancelled can still come back.
    if (S.snap?.prompt?.stage === "cancelled") {
      slot.append(h("div", { class: "side-hint" }, "Cancelled. ", h("button", { class: "ghost", onclick: () => attempt(() => api("/api/prompts/undo-cancel", { method: "POST" })) }, "Undo")));
    }
    slot.append(h("div", { class: "side-start", role: "group", "aria-label": "Start" }, MODES.map((mode) => startButton(mode))));
    if (MODES.some((mode) => S.snap?.hotkey_errors?.[mode.key])) slot.append(h("div", { class: "side-hint warn" }, "A shortcut isn't available. Change it in Settings."));
  }
}

// The card in the sidebar, for whichever is going.
function updateLiveCard(status, glyph, word) {
  Ink.clock($("#side-time"), clock(status.elapsed));
  // Here too, so a problem shows whichever page is open.
  const sideHealth = $("#side-health");
  if (sideHealth) {
    const text = status.health && status.health.kind !== "note" ? status.health.text : "";
    if (sideHealth.textContent !== text) sideHealth.textContent = text;
    sideHealth.dataset.kind = status.health?.kind || "";
  }
  const sideGlyph = $("#side-glyph");
  if (sideGlyph) {
    Ink.setGlyph(sideGlyph, ...glyph);
    const label = $("#side-label");
    const text = status.paused ? "Paused" : word;
    if (label.textContent !== text) {
      label.textContent = text;
      const pause = $("#side-pause");
      pause.replaceChildren(icon(status.paused ? "play" : "pause"));
      pause.title = status.paused ? "Resume" : "Pause";
      pause.setAttribute("aria-label", pause.title);
    }
  }
}

async function startRecording(title = "", mode = "meeting") {
  await attempt(() => api("/api/recording/start", { method: "POST", body: { title, mode } }));
}

async function stopRecording(after) {
  await attempt(() => api("/api/recording/stop", { method: "POST", body: { after } }));
}

function confirmStopAndDelete() {
  dialog("Stop and delete this recording?", "Recording stops, nothing is transcribed or sent anywhere, and the audio goes to the Recycle Bin.", [
    ["Keep recording", ""],
    [
      "Stop and delete",
      "danger",
      () => stopRecording("delete"),
    ],
  ]);
}

async function togglePause() {
  const paused = S.snap?.recording?.paused;
  await attempt(() => api(`/api/recording/${paused ? "resume" : "pause"}`, { method: "POST" }));
}

// ---------------------------------------------------------------- list

function statusLine(meta) {
  const progress = S.snap?.jobs?.progress?.[meta.id];
  const start = new Date(meta.started_at);
  if (meta.status === "recording") return { text: "Recording now", kind: "live" };
  if (meta.status === "failed") return { text: meta.error === "Stopped." ? "Stopped" : "Needs attention", kind: "failed" };
  if (meta.status === "saving" || progress?.stage === "queued") return { text: "Saving the audio", kind: "busy", bar: 0.05 };
  if (meta.status === "transcribing") {
    const fraction = progress?.fraction || 0;
    return { text: `Transcribing ${Math.round(fraction * 100)}%`, kind: "busy", bar: Math.max(fraction, 0.05) };
  }
  if (meta.status === "notes") return { text: "Writing notes", kind: "busy", bar: 1 };
  return { text: [meta.mode === "solo" && "Solo", timeOf(start), lengthText(meta.duration), meta.status === "saved" && "No notes"].filter(Boolean).join(" · "), kind: "" };
}

function renderList() {
  const list = $("#meeting-list");
  const top = list.scrollTop;
  list.replaceChildren();
  if (!S.meetings.length) {
    list.append(h("div", { class: "list-empty" }, Ink.glyph(S.query ? "無" : "空", "faint", { size: 64 }), S.query ? "Nothing matches that search." : "Your meetings and notes will show up here."));
    return;
  }
  let group = null;
  for (const meta of S.meetings) {
    const label = dayLabel(new Date(meta.started_at));
    if (label !== group) {
      group = label;
      list.append(h("div", { class: "group-label" }, label));
    }
    const status = statusLine(meta);
    const row = h(
      "button",
      {
        class: `meeting-row ${S.view === "meeting" && S.selected === meta.id ? "selected" : ""}`,
        "data-id": meta.id,
        onclick: () => openMeeting(meta.id),
      },
      h("div", { class: "row-title" }, meta.title),
      h("div", { class: `row-sub ${status.kind}` }, status.text),
      status.bar !== undefined && h("div", { class: "row-bar" }, h("span")),
    );
    const bar = row.querySelector(".row-bar span");
    if (bar) bar.style.transform = `scaleX(${status.bar})`;
    list.append(row);
  }
  list.scrollTop = top;
}

function updateListProgress() {
  for (const meta of S.meetings) {
    const row = $(`.meeting-row[data-id="${meta.id}"]`);
    if (!row) continue;
    const status = statusLine(meta);
    const sub = row.querySelector(".row-sub");
    if (sub.textContent !== status.text) sub.textContent = status.text;
    const bar = row.querySelector(".row-bar span");
    if (bar && status.bar !== undefined) bar.style.transform = `scaleX(${status.bar})`;
  }
}

async function refreshMeetings() {
  const query = S.query ? `?q=${encodeURIComponent(S.query)}` : "";
  const meetings = await attempt(() => api(`/api/meetings${query}`));
  if (meetings) {
    S.meetings = meetings;
    renderList();
  }
}

// ---------------------------------------------------------------- views

function setView(view) {
  if (view !== "meeting") {
    Player.unload();
    S.selected = null;
    S.detail = null;
    S.detailKey = "";
    S.testId = null;
    S.test = null;
    S.promptId = null;
    S.prompt = null;
  }
  S.view = view;
  S.editing = false;
  S.menuOpen = false;
  markNav();
  renderMain();
  renderList();
}

function markNav() {
  $("#home-btn").classList.toggle("active", S.view === "home");
  $("#prompts-btn").classList.toggle("active", S.view === "prompts");
  $("#tests-btn").classList.toggle("active", S.view === "tests");
  $("#settings-btn").classList.toggle("active", S.view === "settings" || S.view === "instructions");
}

function renderMain() {
  const main = $("#main");
  if (S.view === "recording" && S.snap?.recording?.active) renderRecording(main);
  else if (S.view === "meeting" && S.detail) renderMeeting(main);
  else if (S.view === "settings") renderSettings(main);
  else if (S.view === "instructions") renderInstructions(main);
  else if (S.view === "tests") renderTests(main);
  else if (S.view === "prompts") renderPrompts(main);
  else renderHome(main);
}

async function renderHome(main) {
  const data = await attempt(() => api("/api/overview"));
  if (!data || S.view !== "home") return;
  S.overview = data;
  const { meetings, solo, prompts, code } = data.totals;
  if (!meetings && !solo && !prompts && !code) {
    renderReady(main);
    return;
  }
  if (!$("#dash")) main.replaceChildren(h("div", { class: "dash-view" }, h("div", { class: "dash", id: "dash" })));
  drawOverview();
}

const shortDate = (iso) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });

function meetingLink(item) {
  return h("button", { class: "link", onclick: () => openMeeting(item.meeting_id) }, item.meeting);
}

function panel(title, ...children) {
  return h("section", { class: "card" }, h("h2", {}, title), ...children);
}

function drawOverview() {
  const { totals, weeks, tasks, decisions, recent, prompts, attention } = S.overview;
  const root = $("#dash");
  if (!root) return;
  const tile = (label, value) => h("div", { class: "tile" }, h("div", { class: "tile-value" }, value), h("div", { class: "tile-label" }, label));
  root.replaceChildren(
    ...[
      pageTitle("覽", "Overview"),
      h(
        "div",
        { class: "tiles" },
        tile("Meetings", totals.meetings),
        tile("Solo notes", totals.solo),
        tile("Prompts", totals.prompts),
        tile("Code", totals.code),
        tile("Proofread", totals.proofread),
        tile("Open action items", totals.open_tasks),
        tile("Decisions", totals.decisions),
      ),
      attention.length > 0 && panel("Needs you", ...attention.map(renderAttention)),
      h(
        "div",
        { class: "dash-grid" },
        h(
          "div",
          {},
          renderTasksPanel(tasks),
          panel("Recent meetings and notes", recent.length ? recent.map(renderRecent) : h("div", { class: "help" }, "Meetings and solo notes will show up here.")),
        ),
        h(
          "div",
          {},
          panel("Recent prompts, code and edits", prompts.length ? prompts.map(renderPromptRow) : h("div", { class: "help" }, "Prompts and code you dictate, and text you proofread, will show up here.")),
          panel("Time recorded, last 8 weeks", totals.seconds > 0 && h("div", { class: "dash-meta chart-total" }, `${lengthText(totals.seconds)} in all`), renderWeeks(weeks)),
          panel("Recent decisions", decisions.length ? decisions.map(renderDecision) : h("div", { class: "help" }, "Decisions from your recordings will show up here.")),
        ),
      ),
    ].filter(Boolean),
  );
}

function renderAttention(item) {
  const what = {
    saved: "Saved without notes",
    failed: item.error === "Stopped." ? "Stopped before finishing" : "Needs attention",
    check: `${item.count === 1 ? "1 item" : `${item.count} items`} to check`,
  }[item.kind];
  return h(
    "div",
    { class: "dash-row spread" },
    h("div", {}, meetingLink(item), h("div", { class: "dash-meta" }, `${what} · ${shortDate(item.started_at)}`)),
    item.kind === "saved" && h("button", { onclick: () => process(item.meeting_id, "transcribe") }, icon("sparkle"), S.settings?.notes_engine === "none" ? "Transcribe" : "Make notes"),
  );
}

function renderTasksPanel(tasks) {
  const list = h("div");
  const draw = () => {
    const shown = S.onlyMine ? tasks.filter((task) => task.owner === "You") : tasks;
    list.replaceChildren(
      ...(shown.length
        ? shown.map(renderOpenTask)
        : [h("div", { class: "help" }, tasks.length ? "Nothing open is yours." : "Nothing open. Action items from your recordings will show up here.")]),
    );
  };
  draw();
  return h(
    "section",
    { class: "card" },
    h(
      "div",
      { class: "card-head" },
      h("h2", {}, "Open action items"),
      h(
        "label",
        { class: "only-mine" },
        h("input", {
          type: "checkbox",
          checked: S.onlyMine,
          onchange: (event) => {
            S.onlyMine = event.target.checked;
            draw();
          },
        }),
        "Only mine",
      ),
    ),
    list,
  );
}

function renderOpenTask(task) {
  return h(
    "div",
    { class: "dash-row" },
    h("input", {
      type: "checkbox",
      "aria-label": `Mark done: ${task.text}`,
      onchange: async (event) => {
        const box = event.target;
        const done = await attempt(() => api(`/api/meetings/${task.meeting_id}/task`, { method: "POST", body: { line: task.line, raw: task.raw, done: box.checked } }));
        if (!done) box.checked = !box.checked;
      },
    }),
    h(
      "div",
      {},
      h("div", {}, task.owner && h("strong", {}, `${task.owner}: `), task.text, task.unverified && h("span", { class: "flag", title: "This couldn't be found in the transcript" }, "Check this")),
      h("div", { class: "dash-meta" }, task.due && `Due ${task.due} · `, meetingLink(task), ` · ${shortDate(task.started_at)}`),
    ),
  );
}

function renderDecision(item) {
  return h("div", { class: "dash-row plain" }, h("div", {}, h("div", {}, item.text), h("div", { class: "dash-meta" }, meetingLink(item), ` · ${shortDate(item.started_at)}`)));
}

function renderRecent(item) {
  const facts = [shortDate(item.started_at), lengthText(item.duration), item.open_tasks && `${item.open_tasks} open`].filter(Boolean).join(" · ");
  return h(
    "div",
    { class: "dash-row plain" },
    h("div", {}, meetingLink(item), h("div", { class: "dash-meta" }, facts), item.summary && h("div", { class: "dash-summary" }, item.summary)),
  );
}

function renderWeeks(weeks) {
  const peak = Math.max(...weeks.map((week) => week.seconds), 60);
  const top = [5, 10, 15, 30, 60, 120, 180, 300, 600, 1200, 2400, 6000].find((minutes) => minutes * 60 >= peak) ?? Math.ceil(peak / 3600) * 60;
  const label = (minutes) => (minutes === 0 ? "0" : minutes < 60 ? `${minutes} min` : `${minutes / 60} hr`);
  const ticks = [top, ...(Number.isInteger(top / 2) ? [top / 2] : []), 0];
  const tip = h("div", { class: "chart-tip", hidden: true });
  const describe = (week) => `Week of ${shortDate(`${week.start}T12:00:00`)}: ${lengthText(week.seconds) || "nothing recorded"}${week.meetings ? `, ${week.meetings} ${week.meetings === 1 ? "recording" : "recordings"}` : ""}`;
  const columns = weeks.map((week) => {
    const bar = h("div", { class: "chart-bar" });
    bar.style.height = `${(week.seconds / (top * 60)) * 100}%`;
    const column = h("div", { class: "chart-col", tabindex: 0, "aria-label": describe(week) }, bar);
    const show = () => {
      tip.textContent = describe(week);
      tip.hidden = false;
      tip.style.left = `${column.offsetLeft + column.offsetWidth / 2}px`;
    };
    column.addEventListener("mouseenter", show);
    column.addEventListener("focus", show);
    column.addEventListener("mouseleave", () => { tip.hidden = true; });
    column.addEventListener("blur", () => { tip.hidden = true; });
    return column;
  });
  return h(
    "div",
    { class: "chart" },
    h(
      "div",
      { class: "chart-plot" },
      ticks.map((minutes) => {
        const line = h("div", { class: "chart-line" }, h("span", {}, label(minutes)));
        line.style.bottom = `${(minutes / top) * 100}%`;
        return line;
      }),
      h("div", { class: "chart-bars" }, columns, tip),
    ),
    h("div", { class: "chart-x" }, weeks.map((week, index) => h("span", {}, index % 2 === weeks.length % 2 ? "" : shortDate(`${week.start}T12:00:00`)))),
    h("table", { class: "sr-only" }, h("tbody", {}, weeks.map((week) => h("tr", {}, h("td", {}, describe(week)))))),
  );
}

async function renderReady(main) {
  const names = S.devicesSummary || {};
  main.replaceChildren(
    h(
      "div",
      { class: "home-view" },
      h(
        "div",
        { class: "home" },
        h("h1", {}, "Ready when you are"),
        h("p", {}, "Click one, or press its shortcut from anywhere, even with this window closed."),
        h("div", { class: "home-modes", role: "group", "aria-label": "Start" }, MODES.map((mode) => startButton(mode, true))),
        h(
          "div",
          { class: "device-lines" },
          h("div", { class: "device-line" }, h("span", { class: "pill you" }, "You"), h("span", { id: "home-mic" }, names.mic || "Your microphone")),
          h("div", { class: "device-line" }, h("span", { class: "pill them" }, "Them"), h("span", { id: "home-out" }, names.output || "All computer audio")),
        ),
      ),
    ),
  );
  if (!S.devicesSummary) {
    const devices = await attempt(() => api("/api/devices"));
    if (devices) {
      S.devicesSummary = {
        mic: devices.selected_mic === "default" ? devices.default_mic : devices.selected_mic,
        output: devices.selected_output === "all" ? "All computer audio" : devices.selected_output,
      };
      const mic = $("#home-mic");
      if (mic) mic.textContent = S.devicesSummary.mic || "No microphone found";
      const out = $("#home-out");
      if (out) out.textContent = S.devicesSummary.output;
    }
  }
}

// ---------------------------------------------------------------- recording view

function meterRow(kind, label) {
  return h(
    "div",
    {},
    h(
      "div",
      { class: "meter-head" },
      h("span", { class: `pill ${kind}` }, label),
      h("span", { class: "meter-name", id: `name-${kind}` }),
      h("span", { class: "meter-state", id: `state-${kind}` }),
    ),
    h("div", { class: `meter ${kind}` }, h("span", { id: `fill-${kind}` })),
  );
}

function renderRecording(main) {
  const recording = S.snap.recording;
  const solo = recording.mode === "solo";
  const meta = S.meetings.find((m) => m.id === recording.meeting_id);
  const defaultTitle = meta && meta.title_source !== "user" ? "" : meta?.title || "";
  const [ch, kind] = recordingGlyph(recording);
  const { view, canvas } = stageView({
    ch,
    kind,
    glyphId: "rec-glyph",
    word: "Recording",
    wordId: "rec-label",
    time: clock(recording.elapsed),
    timeId: "rec-time",
    below: h(
      "div",
      { class: "rec-view" },
      h("div", { class: "meters" }, meterRow("you", "You"), !solo && meterRow("them", "Them"), !solo && h("div", { class: "rec-outputs", id: "rec-outputs" })),
      h(
        "div",
        { class: "rec-actions" },
        h("button", { class: "danger", onclick: () => stopRecording("notes") }, icon("stop"), "Stop and make notes"),
        h("button", { class: "pause", id: "rec-pause", onclick: togglePause }),
      ),
      h(
        "div",
        { class: "rec-more" },
        h("button", { class: "ghost", title: "Saves the audio only. Nothing is transcribed or sent anywhere, and you can make notes later.", onclick: () => stopRecording("save") }, "Stop without notes"),
        h("button", { class: "ghost", title: "Stops and sends the audio to the Recycle Bin. Nothing is transcribed or sent anywhere.", onclick: confirmStopAndDelete }, icon("trash"), "Stop and delete"),
      ),
      h("div", { class: "banners", id: "rec-banners" }),
      h(
        "div",
        { class: "rec-name" },
        h("label", { class: "field-label", for: "rec-title" }, solo ? "Name this note " : "Name this meeting ", h("small", {}, "(optional)")),
        h("input", {
          type: "text",
          id: "rec-title",
          value: defaultTitle,
          placeholder: "Otherwise the notes will suggest a name",
          onchange: (event) => {
            const title = event.target.value.trim();
            if (title) attempt(() => api(`/api/meetings/${recording.meeting_id}`, { method: "PATCH", body: { title } }));
          },
        }),
      ),
      !solo && h(
        "div",
        { class: "consent" },
        h("span", {}, "Everyone on the call should agree to being recorded."),
        h("button", { class: "ghost", onclick: () => copyText(S.settings?.notice_text || "", "Notice copied. Paste it in the chat.") }, icon("copy"), "Copy a notice"),
      ),
    ),
  });
  main.replaceChildren(view);
  // On a meeting you're above the line and they're below it. On a solo note it's all you.
  S.wave = new Ink.Wave(canvas, { lanes: solo ? "mic" : "both", ...STAGE_FADE });
  updateRecording();
}

function silentMessage(track, seconds, elapsed) {
  if (elapsed < 45 || seconds < 45) return null;
  const length = clock(seconds);
  if (track === "system") return `No computer audio for ${length}. If people are talking, check which speaker your call is using.`;
  return `No sound from your microphone for ${length}. Check that it's on and not muted.`;
}

function setMeter(element, value, key) {
  S.meter[key] = Math.max(value, S.meter[key] * 0.82);
  if (element) element.style.transform = `scaleX(${S.meter[key]})`;
}

// A quiet room still gives a mic some level, measured on the Antlion at up to -45 dB, about as loud as soft speech. So "hearing" means clearly above
// the quietest this track has been in the last 8 seconds, and it stays on through the gaps between words.
const HEARING_ABOVE_ROOM = 0.15;
const HEARING_HOLD = 1200;
const recentLevels = {};
const lastHeard = {};

function isHearing(track, level) {
  const recent = (recentLevels[track] ??= []);
  // A level of exactly nothing is a pause or a gap in the recording, not the room.
  if (level > 0) recent.push(level);
  if (recent.length > 100) recent.shift();
  if (level > 0 && level > Math.min(...recent) + HEARING_ABOVE_ROOM) lastHeard[track] = Date.now();
  return Date.now() - (lastHeard[track] ?? 0) < HEARING_HOLD;
}

function setMeterState(id, recording, track, label) {
  const element = $(id);
  if (!element) return;
  const hearing = isHearing(track, recording.levels[track]);
  if (recording.paused) {
    element.textContent = "Paused";
    element.className = "meter-state";
  } else if (hearing) {
    element.textContent = label;
    element.className = "meter-state good";
  } else {
    element.textContent = "Quiet";
    element.className = "meter-state";
  }
}

// Every output the call's sound is recorded from, the ones with sound now marked. If the other side is missing, this shows why: the call
// may be playing somewhere that isn't on the list, or nowhere at all.
function updateOutputs(outputs) {
  const element = $("#rec-outputs");
  if (!element) return;
  const key = outputs.map((output) => `${output.name}:${output.sound}`).join("|");
  if (element.dataset.key === key) return;
  element.dataset.key = key;
  element.replaceChildren(
    h("span", {}, outputs.length ? `Recording what plays on ${outputs.length === 1 ? "" : `these ${outputs.length}: `}` : "No computer audio is being recorded."),
    ...outputs.map((output) => h("span", { class: `output${output.sound ? " sound" : ""}`, title: output.sound ? "Sound is playing here now" : "Nothing playing here just now" }, output.sound ? `♪ ${output.name}` : output.name)),
  );
}

function updateRecording() {
  const recording = S.snap?.recording;
  if (!recording?.active) return;
  const time = clock(recording.elapsed);
  updateLiveCard(recording, recordingGlyph(recording), "Recording");
  if (S.view !== "recording") return;
  const timeEl = $("#rec-time");
  if (!timeEl) return;
  Ink.clock(timeEl, time);
  Ink.setGlyph($("#rec-glyph"), ...recordingGlyph(recording));
  S.wave?.levels(recording.levels.mic, recording.levels.system, recording.paused);
  const pausedText = recording.paused ? "Paused: nothing is being recorded" : "Recording";
  const label = $("#rec-label");
  if (label.textContent !== pausedText) label.textContent = pausedText;
  const pause = $("#rec-pause");
  const pauseState = recording.paused ? "resume" : "pause";
  if (pause.dataset.state !== pauseState) {
    pause.dataset.state = pauseState;
    pause.replaceChildren(icon(recording.paused ? "play" : "pause"), recording.paused ? "Resume" : "Pause");
  }
  setMeter($("#fill-you"), recording.levels.mic, "mic");
  setMeter($("#fill-them"), recording.levels.system, "system");
  setMeterState("#state-you", recording, "mic", "Hearing you");
  setMeterState("#state-them", recording, "system", "Hearing them");
  const micName = recording.devices.mic[0] || "No microphone";
  const youName = $("#name-you");
  if (youName.textContent !== micName) youName.textContent = micName;
  const outputs = recording.devices.system.length;
  const outName = outputs > 1 ? "All computer audio" : recording.devices.system[0] || "No computer audio";
  const themName = $("#name-them");
  if (themName && themName.textContent !== outName) themName.textContent = outName;
  updateOutputs(recording.outputs || []);

  const messages = [];
  if (recording.error) messages.push({ text: recording.error, kind: "error" });
  for (const notice of recording.notices || []) messages.push({ text: notice });
  if (!recording.paused) {
    for (const track of recording.mode === "solo" ? ["mic"] : ["mic", "system"]) {
      const text = silentMessage(track, recording.silent_for[track], recording.elapsed);
      if (text) messages.push({ text });
    }
  }
  const banners = $("#rec-banners");
  const key = messages.map((m) => m.text.replace(/\d+:\d+/, "")).join("|");
  if (banners.dataset.key !== key) {
    banners.dataset.key = key;
    banners.replaceChildren(...messages.map((m) => banner(m.text, m.kind)));
  }
}

function banner(text, kind = "") {
  return h("div", { class: `banner ${kind}` }, icon("alert"), h("span", {}, text));
}

// ---------------------------------------------------------------- meeting view

async function openMeeting(id) {
  if (S.view === "meeting" && S.selected === id) return;
  if (S.snap?.recording?.active && S.snap.recording.meeting_id === id) {
    setView("recording");
    return;
  }
  Player.unload();
  S.selected = id;
  S.tab = "notes";
  S.editing = false;
  S.menuOpen = false;
  S.transcriptFilter = "";
  S.original = null;
  S.myNotesOpen = false;
  S.transcriptVersion = null;
  S.view = "meeting";
  markNav();
  S.detail = null;
  await loadDetail(true);
  renderList();
}

async function loadDetail(force = false) {
  const id = S.selected;
  if (!id) return;
  // Saves already on their way go first, so what comes back has them in it. What's still waiting to be saved goes on top of it,
  // so a refresh can't replace what you've just typed or ticked.
  await meetingQueue(id)(() => undefined);
  const detail = await attempt(() => api(`/api/meetings/${id}`));
  if (!detail) {
    setView("home");
    return;
  }
  if (S.selected !== id) return;
  withMeetingEdits(detail);
  const key = JSON.stringify(detail);
  if (!force && key === S.detailKey) return;
  // You were watching it work, and the notes just came in: that moment gets the seal.
  if (S.detail?.meta.id === id && BUSY.includes(S.detail.meta.status) && detail.meta.status === "done" && detail.notes) S.arrived = { id, fresh: true };
  S.detail = detail;
  S.detailKey = key;
  if (S.view !== "meeting") return;
  if (S.editing || document.activeElement?.id === "my-notes") return;
  renderMeeting($("#main"));
}

const BUSY = ["saving", "transcribing", "notes"];

function renderMeeting(main) {
  const { meta, notes, transcript, has_audio: hasAudio } = S.detail;
  const start = new Date(meta.started_at);
  const facts = [
    start.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }) + ", " + timeOf(start),
    lengthText(meta.duration),
    meta.transcribed_with && `Transcribed with ${meta.transcribed_with}`,
    meta.notes_engine && `Notes by ${[meta.notes_engine, meta.notes_model, meta.notes_effort].filter(Boolean).join(", ")}`,
    meta.notes_edited && "Edited",
  ].filter(Boolean);

  const focused = document.activeElement?.classList?.contains("title-input");
  const previous = focused ? document.activeElement.value : null;

  const body = h("div", { class: "meeting-body", id: "meeting-body" }, h("div", { class: "content", id: "meeting-content" }));
  let slot = $("#player-slot");
  if (slot && slot.dataset.id !== meta.id) slot = null;
  if (!slot) slot = h("div", { id: "player-slot", "data-id": meta.id });

  const oldBody = $("#meeting-body");
  const scroll = oldBody ? oldBody.scrollTop : 0;

  main.replaceChildren(
    h(
      "div",
      { class: "meeting-head" },
      h(
        "div",
        { class: "title-row" },
        Ink.glyph(meta.mode === "solo" ? "記" : "錄", "still", { size: 38 }),
        h("input", {
          class: "title-input",
          value: previous ?? meta.title,
          "aria-label": "Name",
          title: "Click to rename",
          onkeydown: (event) => {
            if (event.key === "Enter") event.target.blur();
            if (event.key === "Escape") {
              event.target.value = S.detail.meta.title;
              event.target.blur();
            }
          },
          onchange: async (event) => {
            const title = event.target.value.trim();
            if (!title) {
              event.target.value = S.detail.meta.title;
              return;
            }
            await attempt(() => api(`/api/meetings/${meta.id}`, { method: "PATCH", body: { title } }));
          },
        }),
        notes && S.tab === "notes" && !S.editing && !S.original && !BUSY.includes(meta.status) &&
          h("button", { onclick: () => { S.editing = true; renderMeeting($("#main")); } }, icon("edit"), "Edit"),
        (notes || S.detail.my_notes) && h("button", { onclick: () => copyText(notesToCopy(), "Notes copied") }, icon("copy"), "Copy notes"),
        renderMenu(meta, notes, transcript, hasAudio),
      ),
      h("div", { class: "meta-line" }, facts.join(" · ")),
      h(
        "div",
        { class: "tabs", role: "tablist" },
        tabButton("notes", "Notes"),
        tabButton("transcript", "Transcript", transcript.length ? String(transcript.length) : ""),
      ),
    ),
    body,
    slot,
  );
  if (focused) $(".title-input").focus();

  renderTab();
  $("#meeting-body").scrollTop = scroll;
  if (hasAudio) Player.load(meta.id, slot, meta.duration, meta.playback_gain);
  else {
    Player.unload();
    slot.replaceChildren();
  }
}

function tabButton(id, label, count) {
  return h(
    "button",
    {
      class: `tab ${S.tab === id ? "active" : ""}`,
      role: "tab",
      "aria-selected": String(S.tab === id),
      onclick: () => {
        if (S.tab === id) return;
        S.tab = id;
        S.editing = false;
        S.original = null;
        renderMeeting($("#main"));
      },
    },
    label,
    count ? h("small", {}, ` ${count}`) : null,
  );
}

function renderMenu(meta, notes, transcript, hasAudio) {
  const busy = BUSY.includes(meta.status);
  const wrap = h(
    "div",
    { class: "menu-wrap" },
    h(
      "button",
      {
        class: "icon-only",
        "aria-label": "More actions",
        title: "More",
        onclick: (event) => {
          event.stopPropagation();
          S.menuOpen = !S.menuOpen;
          renderMeeting($("#main"));
        },
      },
      icon("more"),
    ),
  );
  if (!S.menuOpen) return wrap;
  const item = (name, label, action, destructive = false, disabled = false) =>
    h(
      "button",
      {
        class: destructive ? "destructive" : "",
        disabled,
        onclick: () => {
          S.menuOpen = false;
          action();
          renderMeeting($("#main"));
        },
      },
      icon(name),
      label,
    );
  wrap.append(
    h(
      "div",
      { class: "menu", role: "menu" },
      item("sparkle", "Write notes again", () => confirmRegenerate(meta), false, busy || !transcript.length),
      meta.status !== "saved" && item("refresh", "Transcribe again", () => confirmRetranscribe(meta), false, busy || !hasAudio),
      S.engines.length > 1 && item("refresh", "Try another speech model", () => tryAnotherModel(meta), false, busy || !hasAudio),
      item("copy", "Copy transcript for another AI", async () => {
        const data = await attempt(() => api(`/api/meetings/${meta.id}/prompt`));
        if (data) copyText(data.prompt, "Copied, with the notes instructions. Paste it into any AI chat.");
      }, false, !transcript.length),
      S.detail.originals.length > 0 && item("history", "See the AI's original", () => openOriginal(S.detail.originals[0].name)),
      item("folder", "Open folder", () => attempt(() => api(`/api/meetings/${meta.id}/reveal`, { method: "POST" }))),
      h("hr"),
      item("trash", "Delete audio, keep notes", () => confirmDeleteAudio(meta), true, busy || !hasAudio),
      item("trash", meta.mode === "solo" ? "Delete note" : "Delete meeting", () => confirmDelete(meta), true, busy),
    ),
  );
  return wrap;
}

function renderTab() {
  const content = $("#meeting-content");
  if (!content || !S.detail) return;
  const { meta, notes, transcript } = S.detail;
  content.replaceChildren();
  for (const warning of meta.warnings || []) content.append(banner(warning));
  if (S.tab === "transcript") {
    renderTranscript(content, transcript, meta);
    return;
  }
  if (S.original) {
    content.append(renderOriginal());
    return;
  }
  if (!S.editing) content.append(renderMyNotes());
  if (BUSY.includes(meta.status)) {
    content.append(h("div", { id: "progress-slot" }));
    updateProgress();
    return;
  }
  if (meta.status === "failed") {
    content.append(renderFailure(meta));
    if (notes) {
      content.append(h("div", { class: "process-note" }, "These are the notes from before:"), renderNotes(notes));
    }
    return;
  }
  if (meta.status === "saved") {
    content.append(
      emptyNote(
        "錄",
        h("div", {}, "The audio is saved. Nothing has been transcribed or sent anywhere."),
        h(
          "div",
          { class: "row-actions" },
          h("button", { class: "primary", onclick: () => process(meta.id, "transcribe") }, icon("sparkle"), S.settings?.notes_engine === "none" ? "Transcribe" : "Make notes"),
          h("button", { onclick: () => confirmDelete(meta) }, icon("trash"), "Delete recording"),
        ),
      ),
    );
    return;
  }
  if (S.editing) {
    content.append(renderNotesEditor(notes || ""));
    return;
  }
  if (notes) {
    if (meta.notes_edited && S.detail.originals.length) {
      content.append(
        h(
          "div",
          { class: "process-note" },
          "You've edited these notes. The AI's version is kept safe. ",
          h("button", { class: "link", onclick: () => openOriginal(S.detail.originals[0].name) }, "See the original"),
        ),
      );
    }
    // You chose Just switch, so these were written from the transcript you had before. Older meetings didn't note it, and say nothing.
    if (meta.notes_from && meta.transcript_version && meta.notes_from !== meta.transcript_version) {
      content.append(h("div", { class: "process-note" }, "Written from an earlier transcript. ", h("button", { class: "link", onclick: () => confirmRegenerate(meta) }, "Write new notes")));
    }
    if (meta.unverified) {
      const count = meta.unverified;
      content.append(banner(`${count === 1 ? "1 item" : `${count} items`} couldn't be traced back to the transcript. Check ${count === 1 ? "it" : "them"} before relying on ${count === 1 ? "it" : "them"}.`));
    }
    const written = renderNotes(notes);
    if (S.arrived?.id === meta.id) {
      if (S.arrived.fresh) written.classList.add("arrive");
      const seal = Ink.seal({ size: 58, stamp: S.arrived.fresh });
      seal.classList.add("notes-seal");
      S.arrived.fresh = false;
      content.append(seal);
    }
    content.append(written);
    return;
  }
  if (!transcript.length) {
    content.append(emptyNote("無", "No speech was found in this recording, so there's nothing to take notes on."));
    return;
  }
  content.append(
    emptyNote(
      "空",
      h("div", {}, "No notes yet."),
      h("button", { class: "primary", onclick: () => process(meta.id, "notes") }, icon("sparkle"), "Write notes"),
    ),
  );
}

function notesToCopy() {
  const { notes, my_notes: myNotes } = S.detail;
  const mine = myNotes?.trim() ? `## My notes\n\n${myNotes.trim()}\n\n` : "";
  return mine + (notes || "").replaceAll("[unverified]", "(check this)");
}

// ---- meeting saves: tests/test_meeting_saves.py runs this part by itself.
// My notes as you type, and the notes as you tick tasks. What you've changed stays here, by meeting, until a save of it has worked, so a refresh
// or coming back to the meeting shows it rather than the saved copy. A save that didn't work is tried again, with your next change and every few
// seconds until then. A meeting's saves go one at a time, and each sends what's newest when its turn comes, so the last one has everything.
const meetingEdits = new Map();
const meetingQueues = new Map();
const MEETING_RETRY = 3000;

function meetingQueue(id) {
  if (!meetingQueues.has(id)) meetingQueues.set(id, inOrder());
  return meetingQueues.get(id);
}

// Once the first failure has said why, the note by the box says it isn't saved, rather than a message every few seconds.
async function quietly(action) {
  try {
    return await action();
  } catch {
    return undefined;
  }
}

function sendMeetingEdit(key) {
  const waiting = meetingEdits.get(key);
  if (!waiting) return Promise.resolve(true);
  clearTimeout(waiting.timer);
  waiting.timer = null;
  return meetingQueue(waiting.id)(async () => {
    const edit = meetingEdits.get(key);
    // Already sent by the save before this one, replaced by your edit of the notes, or gone with the meeting.
    if (!edit) return true;
    clearTimeout(edit.timer);
    edit.timer = null;
    // Ticking a task isn't editing the notes, so they still count as the AI's.
    const body = edit.field === "notes" ? { notes: edit.value, edited: false } : { my_notes: edit.value };
    const saved = await (edit.failed ? quietly : attempt)(() => api(`/api/meetings/${edit.id}`, { method: "PATCH", body }));
    const newest = meetingEdits.get(key);
    if (saved && newest === edit) meetingEdits.delete(key);
    else if (newest) {
      newest.failed = !saved;
      // A newer change is on its way already. Otherwise this one goes again in a moment.
      if (!saved && newest === edit) newest.timer = setTimeout(() => sendMeetingEdit(key), MEETING_RETRY);
    }
    showUnsaved(edit.id);
    return Boolean(saved);
  });
}

// wait gives your typing a moment before it's sent. Once a save has failed, the changes after it say so too, until one of them is saved.
function editMeeting(id, field, value, wait = 0) {
  const key = `${id} ${field}`;
  const before = meetingEdits.get(key);
  clearTimeout(before?.timer);
  meetingEdits.set(key, { id, field, value, failed: Boolean(before?.failed), timer: wait ? setTimeout(() => sendMeetingEdit(key), wait) : null });
  if (!wait) sendMeetingEdit(key);
}

// What's still waiting to be saved goes on top of what came back from the app.
function withMeetingEdits(detail) {
  for (const edit of meetingEdits.values()) {
    if (edit.id === detail.meta.id) detail[edit.field] = edit.value;
  }
  return detail;
}

// Only once a save of it has failed: until then it's on its way as usual.
function meetingUnsaved(id, field) {
  return Boolean(meetingEdits.get(`${id} ${field}`)?.failed);
}

function dropMeetingEdits(id, field) {
  for (const [key, edit] of meetingEdits) {
    if (edit.id === id && (field === undefined || edit.field === field)) {
      clearTimeout(edit.timer);
      meetingEdits.delete(key);
    }
  }
}

// For what replaces the whole of the notes, like saving your edit or going back to the AI's original. It goes after any ticks already on their
// way, and once it has worked, ticks still waiting go too, since sending them would undo it.
async function replaceMeetingNotes(id, send) {
  const done = await meetingQueue(id)(() => attempt(send));
  if (done) {
    dropMeetingEdits(id, "notes");
    showUnsaved(id);
  }
  return done;
}

function saveMyNotes(id, value, soon = false) {
  if (S.detail?.meta.id === id) S.detail.my_notes = value;
  editMeeting(id, "my_notes", value, soon ? 500 : 0);
}

// The tick stays on the screen whatever happens to its save.
function toggleTask(index, done) {
  const lines = S.detail.notes.split("\n");
  lines[index] = lines[index].replace(/\[( |x|X)\]/, done ? "[x]" : "[ ]");
  S.detail.notes = lines.join("\n");
  editMeeting(S.detail.meta.id, "notes", S.detail.notes);
  renderTab();
}
// ---- end of meeting saves

function renderMyNotes() {
  const { meta, my_notes: text } = S.detail;
  const unsaved = meetingUnsaved(meta.id, "my_notes");
  if (!text && !S.myNotesOpen && !unsaved) {
    return h(
      "button",
      {
        class: "ghost add-my-notes",
        onclick: () => {
          S.myNotesOpen = true;
          renderTab();
          $("#my-notes")?.focus();
        },
      },
      icon("edit"),
      "Add your own notes",
    );
  }
  return h(
    "section",
    { class: "my-notes" },
    h("label", { class: "field-label", for: "my-notes" }, "My notes"),
    h("textarea", {
      id: "my-notes",
      rows: Math.min(14, Math.max(3, (text || "").split("\n").length + 1)),
      placeholder: "Your own notes. The AI never reads or changes these.",
      value: text || "",
      oninput: (event) => saveMyNotes(meta.id, event.target.value, true),
      onchange: (event) => saveMyNotes(meta.id, event.target.value),
    }),
    h("div", { class: "help error", id: "my-notes-unsaved", hidden: !unsaved }, "Not saved yet. Trying again."),
  );
}

// The notes that say something isn't saved, kept up to date without drawing the page again under your typing.
function showUnsaved(id) {
  if (S.detail?.meta.id !== id) return;
  const mine = $("#my-notes-unsaved");
  if (mine) mine.hidden = !meetingUnsaved(id, "my_notes");
  for (const note of document.querySelectorAll(".ticks-unsaved")) note.hidden = !meetingUnsaved(id, "notes");
}

async function openOriginal(name) {
  const id = S.selected;
  const data = await attempt(() => api(`/api/meetings/${id}/originals/${name}`));
  if (!data || S.selected !== id) return;
  S.original = { name, text: data.text };
  S.tab = "notes";
  S.editing = false;
  renderMeeting($("#main"));
}

function describeOriginal(info) {
  const when = info?.written_at ? new Date(info.written_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "";
  return [[info?.engine, info?.model, info?.effort].filter(Boolean).join(", "), when].filter(Boolean).join(" · ");
}

function renderOriginal() {
  const { originals, meta } = S.detail;
  const current = originals.find((item) => item.name === S.original.name);
  return h(
    "div",
    {},
    h(
      "div",
      { class: "original-bar" },
      h(
        "div",
        { class: "original-what" },
        h("strong", {}, "The AI's original"),
        h("div", { class: "help" }, `${describeOriginal(current)}. This copy never changes.`),
      ),
      originals.length > 1 &&
        h(
          "select",
          { "aria-label": "Version", onchange: (event) => openOriginal(event.target.value) },
          originals.map((item) => h("option", { value: item.name, selected: item.name === S.original.name }, describeOriginal(item))),
        ),
      h("button", { onclick: () => confirmRestore(meta.id, S.original.name) }, icon("refresh"), "Use this version"),
      h("button", { class: "ghost", onclick: () => { S.original = null; renderMeeting($("#main")); } }, "Back to notes"),
    ),
    renderNotes(S.original.text, true),
  );
}

function confirmRestore(id, name) {
  dialog("Go back to this version?", "It replaces the notes you see. Your current version is kept as notes.previous.md in the same folder, and My notes aren't affected.", [
    ["Cancel", ""],
    [
      "Use this version",
      "primary",
      async () => {
        const done = await replaceMeetingNotes(id, () => api(`/api/meetings/${id}/originals/${name}/restore`, { method: "POST" }));
        if (done) {
          S.original = null;
          await loadDetail(true);
        }
      },
    ],
  ]);
}

function renderFailure(meta) {
  const stage = ["notes", "save"].includes(meta.failed_stage) ? meta.failed_stage : "transcribe";
  const stopped = meta.error === "Stopped.";
  const heading = { notes: "The notes couldn't be written", save: "The audio couldn't be saved", transcribe: "The transcript couldn't be made" }[stage];
  return h(
    "div",
    { class: "failure" },
    Ink.glyph(stopped ? "停" : "錯", stopped ? "still" : "problem", { size: 60, write: !stopped }),
    h("h3", {}, stopped ? "Stopped before finishing" : heading),
    h("p", {}, stopped ? "Your audio is safe. Pick up where this left off whenever you're ready." : `${meta.error} Your audio is safe.`),
    h(
      "div",
      { class: "process-actions" },
      h("button", { class: "primary", onclick: () => process(meta.id, stage) }, icon("refresh"), "Try again"),
      stage === "notes" && h("button", { onclick: () => setView("settings") }, "Open Settings"),
    ),
  );
}

async function process(id, from, engine) {
  await attempt(() => api(`/api/meetings/${id}/process`, { method: "POST", body: { from, engine } }));
}

function tryAnotherModel(meta) {
  const choice = h("select", { "aria-label": "Speech model" }, S.engines.map((engine) => h("option", { value: engine.id, selected: engine.id !== meta.transcript_engine && engine.id !== "whisper" }, engine.label)));
  dialog(
    "Try another speech model",
    "This keeps your current transcript and notes. The new transcript appears in the list on the Transcript tab, so you can compare them on the same recording.",
    [
      ["Cancel", ""],
      [
        "Start",
        "primary",
        () => {
          S.tab = "transcript";
          process(meta.id, "compare", choice.value);
        },
      ],
    ],
    choice,
  );
}

function stepItem(state, label, right) {
  return h(
    "div",
    { class: `step ${state}` },
    h("span", { class: "mark" }, state === "done" ? icon("check") : null),
    h("span", {}, label),
    right && h("span", { class: "right" }, right),
  );
}

function updateProgress() {
  const slot = $("#progress-slot");
  if (!slot || !S.detail) return;
  const { meta } = S.detail;
  if (meta.save_only) {
    if (!slot.firstChild) slot.append(h("div", { class: "steps" }, stepItem("active", "Saving the audio")));
    return;
  }
  const live = S.snap?.jobs?.progress?.[meta.id] || {};
  const stage = live.stage === "queued" ? "saving" : live.stage || meta.status;
  const order = ["saving", "loading", "transcribing", "notes"];
  const at = Math.max(order.indexOf(stage), 0);
  const fraction = stage === "transcribing" ? live.fraction || 0 : 0;

  const steps = [
    stepItem(at > 0 ? "done" : "active", "Saving the audio"),
    stepItem(
      at > 2 ? "done" : at >= 1 ? "active" : "",
      stage === "loading" ? "Loading the speech model" : "Transcribing",
      stage === "transcribing" ? `${Math.round(fraction * 100)}%${live.device ? ` on ${live.device}` : ""}` : "",
    ),
  ];
  if (stage === "transcribing") {
    const bar = h("div", { class: "step-bar" }, h("span"));
    bar.firstChild.style.transform = `scaleX(${Math.max(fraction, 0.02)})`;
    steps.push(bar);
  }
  const engine = { codex: "Codex", claude: "Claude Code" }[S.settings?.notes_engine] || "";
  const running = stage === "notes" && live.started ? clock(Date.now() / 1000 - live.started) : "";
  if (meta.compare_engine) steps.shift();
  else steps.push(stepItem(stage === "notes" ? "active" : "", engine ? `Writing notes with ${engine}` : "Writing notes", running));

  const queued = S.snap?.jobs?.queued?.includes(meta.id);
  const key = JSON.stringify([stage, Math.round(fraction * 100), running, queued, live.note, live.device]);
  if (slot.dataset.key === key) return;
  slot.dataset.key = key;
  slot.replaceChildren(
    ...[
      h("div", { class: "steps" }, steps),
      queued && h("div", { class: "process-note" }, "Waiting for another recording to finish first."),
      live.note && h("div", { class: "process-note" }, live.note),
      h(
        "div",
        { class: "process-actions" },
        h("button", { class: "ghost", onclick: () => attempt(() => api(`/api/meetings/${meta.id}/cancel`, { method: "POST" })) }, icon("x"), "Stop processing"),
      ),
    ].filter(Boolean),
  );
}

// ---------------------------------------------------------------- notes

// A small renderer for the Markdown the notes use. It builds DOM nodes, so text can't become HTML.
function inlineNodes(text) {
  const nodes = [];
  const pattern = /\*\*(.+?)\*\*|\[(\d{1,2}:\d{2}(?::\d{2})?)\]|\[unverified\]/g;
  let last = 0;
  let match;
  while ((match = pattern.exec(text))) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    if (match[1] !== undefined) nodes.push(h("strong", {}, match[1]));
    else if (match[2] !== undefined) nodes.push(timeChip(parseClock(match[2]), match[2]));
    else nodes.push(h("span", { class: "flag", title: "This couldn't be found in the transcript" }, "Check this"));
    last = pattern.lastIndex;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function timeChip(seconds, label) {
  const hasAudio = S.detail?.has_audio;
  return h(
    "button",
    {
      class: "chip",
      disabled: !hasAudio,
      title: hasAudio ? "Play from here" : "The audio was deleted",
      onclick: () => {
        Player.seek(seconds, true);
        highlightLine(seconds);
      },
    },
    label,
  );
}

function renderNotes(markdown, readOnly = false) {
  const root = h("div", { class: "notes" });
  const lines = markdown.split("\n");
  let list = null;
  let listKind = "";
  lines.forEach((line, index) => {
    const task = line.match(/^\s*[-*] \[( |x|X)\] (.*)$/);
    const bullet = line.match(/^\s*[-*] (.*)$/);
    if (task) {
      if (listKind !== "tasks") {
        list = h("ul", { class: "tasks" });
        listKind = "tasks";
        root.append(list);
        if (!readOnly) root.append(h("div", { class: "help error ticks-unsaved", hidden: !meetingUnsaved(S.detail.meta.id, "notes") }, "Your ticks aren't saved yet. Trying again."));
      }
      const done = task[1].toLowerCase() === "x";
      list.append(
        h(
          "li",
          { class: done ? "done" : "" },
          h("input", {
            type: "checkbox",
            checked: done,
            disabled: readOnly,
            "aria-label": "Mark done",
            onchange: (event) => toggleTask(index, event.target.checked),
          }),
          h("span", { class: "task-text" }, inlineNodes(task[2])),
        ),
      );
      return;
    }
    if (bullet) {
      if (listKind !== "bullets") {
        list = h("ul");
        listKind = "bullets";
        root.append(list);
      }
      list.append(h("li", {}, inlineNodes(bullet[1])));
      return;
    }
    list = null;
    listKind = "";
    if (!line.trim()) return;
    if (line.startsWith("### ")) root.append(h("h3", {}, inlineNodes(line.slice(4))));
    else if (line.startsWith("## ")) root.append(h("h2", {}, inlineNodes(line.slice(3))));
    else if (line.startsWith("# ")) root.append(h("h2", {}, inlineNodes(line.slice(2))));
    else root.append(h("p", {}, inlineNodes(line)));
  });
  return root;
}

function renderNotesEditor(markdown) {
  const area = h("textarea", { value: markdown, "aria-label": "Edit notes", spellcheck: "true" });
  const finish = () => {
    S.editing = false;
    renderMeeting($("#main"));
  };
  setTimeout(() => area.focus(), 0);
  return h(
    "div",
    { class: "notes-edit" },
    area,
    h(
      "div",
      { class: "row-actions" },
      h(
        "button",
        {
          class: "primary",
          onclick: async () => {
            const id = S.selected;
            // What you're saving started from the notes on screen, ticks and all.
            const saved = await replaceMeetingNotes(id, () => api(`/api/meetings/${id}`, { method: "PATCH", body: { notes: area.value } }));
            if (saved && S.selected === id) {
              S.detail.notes = area.value;
              S.editing = false;
              await loadDetail(true);
            }
          },
        },
        "Save",
      ),
      h("button", { onclick: finish }, "Cancel"),
    ),
  );
}

// ---------------------------------------------------------------- transcript

function highlighted(text, query) {
  if (!query) return [text];
  const out = [];
  const lower = text.toLowerCase();
  const needle = query.toLowerCase();
  let at = 0;
  let found;
  while ((found = lower.indexOf(needle, at)) >= 0) {
    if (found > at) out.push(text.slice(at, found));
    out.push(h("mark", {}, text.slice(found, found + needle.length)));
    at = found + needle.length;
  }
  if (at < text.length) out.push(text.slice(at));
  return out;
}

function describeVersion(version, inUse) {
  const when = version.created_at ? new Date(version.created_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "";
  const took = version.seconds ? `${Math.round(version.seconds)} s${version.device ? ` on ${version.device}` : ""}` : "";
  return [version.label, took, when, inUse && "in use"].filter(Boolean).join(" · ");
}

async function showTranscriptVersion(meta, name) {
  const inUse = (meta.transcript_version || S.detail.transcripts.at(-1)?.name) === name;
  if (inUse) {
    S.transcriptVersion = null;
  } else {
    const version = await attempt(() => api(`/api/meetings/${meta.id}/transcripts/${name}`));
    if (!version) return;
    S.transcriptVersion = { name, lines: version.lines };
  }
  renderTab();
}

function confirmUseVersion(meta, name) {
  const use = async (writeNotes) => {
    const done = await attempt(() => api(`/api/meetings/${meta.id}/transcripts/${name}/use`, { method: "POST" }));
    if (!done) return;
    S.transcriptVersion = null;
    if (writeNotes) await process(meta.id, "notes");
    await loadDetail(true);
  };
  dialog("Use this transcript?", "It becomes the one your notes are written from. The other transcripts stay in the list.", [
    ["Cancel", ""],
    ["Just switch", "", () => use(false)],
    ["Switch and write new notes", "primary", () => use(true)],
  ]);
}

function renameSpeaker(meta, who) {
  const names = meta.speaker_names || {};
  const input = h("input", { type: "text", value: names[who] || "", placeholder: who, "aria-label": "Name" });
  const save = async () => {
    const next = { ...names, [who]: input.value.trim() };
    if (await attempt(() => api(`/api/meetings/${meta.id}`, { method: "PATCH", body: { speaker_names: next } }))) await loadDetail(true);
  };
  dialog(`Who is ${who}?`, "The name shows in the transcript. To use it in the notes too, choose Write notes again.", [["Cancel", ""], ["Save", "primary", save]], input);
  setTimeout(() => input.focus(), 0);
}

function renderTranscript(content, transcript, meta) {
  const versions = S.detail.transcripts || [];
  const viewing = S.transcriptVersion;
  const lines = viewing ? viewing.lines : transcript;
  if (versions.length > 1) {
    const active = meta.transcript_version || versions.at(-1).name;
    content.append(
      h(
        "div",
        { class: "version-bar" },
        h(
          "select",
          { "aria-label": "Transcript version", onchange: (event) => showTranscriptVersion(meta, event.target.value) },
          versions.map((version) => h("option", { value: version.name, selected: version.name === (viewing?.name || active) }, describeVersion(version, version.name === active))),
        ),
        viewing && h("button", { onclick: () => confirmUseVersion(meta, viewing.name) }, "Use this transcript"),
      ),
    );
  }
  if (BUSY.includes(meta.status) && meta.compare_engine) {
    content.append(h("div", { id: "progress-slot" }));
    updateProgress();
  }
  if (!lines.length) {
    content.append(emptyNote(BUSY.includes(meta.status) ? "寫" : "空", BUSY.includes(meta.status) ? "The transcript will appear here when it's ready." : "There's no transcript for this one."));
    return;
  }
  const names = meta.speaker_names || {};
  const display = (line) => (line.who ? names[line.who] || line.who : line.speaker);
  const pill = (line) => {
    const kind = line.speaker === "You" ? "you" : "them";
    if (line.who && !viewing) return h("button", { class: `pill ${kind} pill-button`, title: "Name this person", onclick: () => renameSpeaker(meta, line.who) }, display(line));
    return h("span", { class: `pill ${kind}` }, display(line));
  };
  const solo = meta.mode === "solo";
  const rows = h("div", { id: "transcript-rows", class: solo ? "solo" : "" });
  const draw = () => {
    const query = S.transcriptFilter.trim();
    const shown = query ? lines.filter((line) => line.text.toLowerCase().includes(query.toLowerCase())) : lines;
    rows.replaceChildren(
      ...(shown.length
        ? shown.map((line) =>
            h(
              "div",
              { class: "line", "data-start": line.start, "data-end": line.end },
              timeChip(line.start, clock(line.start)),
              !solo && pill(line),
              h("span", { class: "line-text" }, highlighted(line.text, query)),
            ),
          )
        : [emptyNote("無", "Nothing in the transcript matches that.")]),
    );
  };
  content.append(
    h(
      "div",
      { class: "transcript-tools" },
      h("input", {
        type: "text",
        placeholder: "Find in transcript",
        "aria-label": "Find in transcript",
        value: S.transcriptFilter,
        oninput: (event) => {
          S.transcriptFilter = event.target.value;
          draw();
        },
      }),
      h("button", { onclick: () => copyText(lines.map((l) => `[${clock(l.start)}] ${display(l)}: ${l.text}`).join("\n"), "Transcript copied") }, icon("copy"), "Copy"),
    ),
    rows,
  );
  draw();
  // What the echo clean-up took out, in case one of them was really you.
  const version = versions.find((item) => item.name === (viewing?.name || meta.transcript_version)) || versions.at(-1);
  const echoes = version?.echoes || [];
  if (echoes.length) {
    content.append(
      h(
        "details",
        { class: "echo-list" },
        h("summary", {}, echoes.length === 1 ? "1 line taken out as echo" : `${echoes.length} lines taken out as echo`),
        echoes.map((line) => h("div", { class: "line" }, timeChip(line.start, clock(line.start)), h("span", { class: "pill you" }, "You"), h("span", { class: "line-text" }, line.text))),
      ),
    );
  }
}

function highlightLine(seconds) {
  let current = null;
  document.querySelectorAll(".line").forEach((line) => {
    const start = Number(line.dataset.start);
    const end = Number(line.dataset.end);
    const on = seconds >= start && seconds < end + 0.3;
    line.classList.toggle("current", on);
    if (on && !current) current = line;
  });
  return current;
}

// ---------------------------------------------------------------- test models

const SPEECH_LANGUAGES = [["mixed", "Chinese and English mixed"], ["en", "English"], ["zh", "Chinese"], ["auto", "Detect automatically"]];
const HINTS = [["talking", "Talking alone, as for solo notes and prompts"], ["meeting", "A meeting"], ["none", "No hint"]];
const hintName = (value, edited) => `${({ talking: "talking-alone hint", none: "no hint" })[value] || "meeting hint"}${edited ? ", edited" : ""}`;
const SCORE_WORDS = ["", "Poor", "Many mistakes", "Some mistakes", "A few small mistakes", "Perfect"];
const SAMPLES = {
  mixed: [
    "今天的 meeting 主要討論明年的 rate filing。我昨晚 review 了兩個 options，我覺得 option two 比較 safe，因為 medical trend 的 assumption 比較低。",
    "我週三之前會 update 一下 HCC risk adjustment model，然後把 results share 給大家。如果有問題，我們下週二再 sync 一下。",
    "Let me think about that。The main issue is 我們的 claims data 還沒有 final，so the projection might change，所以要先確認 actuary 的 opinion。",
  ],
  en: [
    "We reviewed both options for next year's rate filing. The second one looks safer because the medical trend assumption is lower. Priya will send the updated memo by Friday.",
    "I'll update the HCC risk adjustment model and share the results by Wednesday. Should we also loop in the compliance team on the URRT filing?",
  ],
  zh: [
    "今天我們主要討論明年的費率申報，目前有兩個方案。我覺得第二個方案更穩妥，因為醫療趨勢假設比較低。",
    "我週三之前會更新風險調整模型，然後把結果發給大家。保費漲幅大概是百分之六點二，預算影響大約三十萬美元。",
  ],
};

const languageName = (value) => SPEECH_LANGUAGES.find(([key]) => key === value)?.[1] || value;
const testTitle = (test) => `Test on ${new Date(test.started_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`;
const inUse = (engine, language) => S.settings.speech_engine === engine && S.settings.language === language;

function renderTests(main) {
  if (S.snap?.model_test?.recording) renderTestClip(main);
  else if (S.testId) renderTestResult(main);
  else renderTestHome(main);
}

async function startTest() {
  await attempt(() => api("/api/model-tests/start", { method: "POST", body: { language: S.settings.test_language, hint: S.settings.test_hint } }));
}

async function openTest(id) {
  Player.unload();
  S.testId = id;
  S.test = null;
  renderMain();
}

function toAllTests() {
  Player.unload();
  S.testId = null;
  S.test = null;
  renderMain();
}

function useModel(engine, label, language) {
  saveSetting({ speech_engine: engine, language }, true);
  toast(`New recordings will use ${label}, set to ${languageName(language)}.`);
  renderMain();
}

function useModelButton(engine, label, language) {
  if (inUse(engine, language)) return h("span", { class: "test-in-use" }, icon("check"), "In use");
  return h("button", { class: "ghost", title: `Use ${label} for your recordings, set to ${languageName(language)}.`, onclick: () => useModel(engine, label, language) }, "Use this one");
}

async function renderTestHome(main) {
  if (!$("#test-home")) main.replaceChildren(h("div", { class: "dash-view" }, h("div", { class: "dash", id: "test-home" }, pageTitle("試", "Test speech models"))));
  const data = await attempt(() => api("/api/model-tests"));
  const root = $("#test-home");
  if (!data || !root || S.view !== "tests" || S.testId || S.snap?.model_test?.recording) return;
  const busyRecording = S.snap?.recording?.active;
  root.replaceChildren(...[
    root.querySelector(".page-title"),
    h("p", { class: "test-intro" }, "Talk for a bit, and every speech model on this PC writes down what it heard. Then compare them and give each one a score. Only your microphone is recorded, it all stays on this PC, and tests don't appear with your meetings."),
    h(
      "section",
      { class: "card" },
      selectField("How you'll speak", S.settings.test_language, SPEECH_LANGUAGES, (value) => saveSetting({ test_language: value }, true), "Best of all, talk the way you do on a real call."),
      selectField("Hint to give the models", S.settings.test_hint, HINTS, (value) => saveSetting({ test_hint: value }, true), "A hint is text placed in front of a model, which nudges what it writes. No hint also leaves out your Names and terms. Nemotron always gets its basic instruction, because it can't run without one. You can read and change the hints in Settings, under Hints and prompts."),
      h(
        "div",
        { class: "field" },
        h("div", { class: "field-label" }, "Models to run"),
        data.engines.map((engine) =>
          h(
            "label",
            { class: "toggle" },
            h("input", {
              type: "checkbox",
              checked: !S.settings.test_skip.includes(engine.id),
              onchange: (event) => {
                const others = S.settings.test_skip.filter((id) => id !== engine.id);
                saveSetting({ test_skip: event.target.checked ? others : [...others, engine.id] }, true);
              },
            }),
            h("span", {}, engine.label, engine.summary && h("div", { class: "help" }, engine.summary[0].toUpperCase() + engine.summary.slice(1))),
          ),
        ),
        h("div", { class: "help" }, "They run one at a time, and the first model of a test can take a little longer to load. Your Names and terms list from Settings is used, the same as on a real call."),
      ),
      h(
        "div",
        { class: "row-actions" },
        h("button", { class: "primary test-go", disabled: busyRecording, onclick: startTest }, icon("mic"), "Start talking"),
        busyRecording && h("span", { class: "help" }, "Stop your recording first."),
      ),
    ),
    renderScores(data.scores),
    data.tests.length > 0 &&
      h(
        "section",
        { class: "card" },
        h("h2", {}, "Past tests"),
        data.tests.map((test) =>
          h(
            "div",
            { class: "dash-row spread" },
            h("div", {}, h("button", { class: "link", onclick: () => openTest(test.id) }, testTitle(test)), h("div", { class: "dash-meta" }, [lengthText(test.duration), languageName(test.language)].filter(Boolean).join(" · "))),
            h("span", { class: "dash-meta" }, test.best ? `Best: ${test.best} (${test.best_score} of 5)` : "Not scored yet"),
          ),
        ),
      ),
  ].filter(Boolean));
}

function renderScores(groups) {
  const scored = groups.filter((group) => group.models.some((model) => model.scored));
  if (!scored.length) return null;
  return h(
    "section",
    { class: "card" },
    h("h2", {}, "Your scores so far"),
    scored.map((group) =>
      h(
        "div",
        { class: "score-group" },
        h("h3", {}, `Language set to ${languageName(group.language)}, ${hintName(group.hint, group.hint_edit)}`),
        group.hint_edit && h("div", { class: "dash-meta" }, group.hint_edit),
        // Scored apart, so a rewritten built-in hint isn't averaged in with the old one.
        group.hints === "earlier" && h("div", { class: "dash-meta" }, "With an earlier version of the built-in hints."),
        group.hints === "unknown" && h("div", { class: "dash-meta" }, "From before the app noted which built-in hints each run had."),
        h(
          "table",
          { class: "score-table" },
          h("thead", {}, h("tr", {}, ["Model", "Average", "Scored", "Usual time", ""].map((name) => h("th", { scope: "col" }, name)))),
          h(
            "tbody",
            {},
            group.models.map((model) =>
              h(
                "tr",
                {},
                h("td", {}, model.label),
                h("td", { class: "num" }, model.average ? `${model.average} of 5` : "Not scored"),
                h("td", { class: "num" }, model.scored ? `${model.scored}×` : ""),
                h("td", { class: "num" }, model.seconds !== null ? `${Math.round(model.seconds)} sec` : ""),
                h("td", { class: "use" }, useModelButton(model.engine, model.label, group.language)),
              ),
            ),
          ),
        ),
      ),
    ),
  );
}

function renderTestClip(main) {
  const clip = S.snap.model_test.recording;
  const samples = SAMPLES[S.settings.test_language] || SAMPLES.mixed;
  const sample = h("p", { class: "test-sample" }, samples[S.sample % samples.length]);
  const { view, canvas } = stageView({
    ch: "聽",
    kind: "live",
    word: "Listening to your microphone",
    time: clock(clip.elapsed),
    timeId: "test-time",
    below: h(
      "div",
      { class: "rec-view" },
      h("div", { class: "meters" }, meterRow("you", "You")),
      h(
        "div",
        { class: "rec-actions" },
        h("button", { class: "danger", onclick: () => attempt(() => api("/api/model-tests/stop", { method: "POST" })) }, icon("stop"), "Stop and compare"),
        h("button", {
          class: "pause",
          onclick: () => {
            S.discardingTest = true;
            attempt(() => api("/api/model-tests/discard", { method: "POST" }));
          },
        }, "Cancel"),
      ),
      h("div", { class: "banners", id: "test-banners" }),
      h(
        "section",
        { class: "card test-sample-card" },
        h(
          "div",
          { class: "card-head" },
          h("h2", {}, "Not sure what to say? Read this"),
          h("button", {
            class: "ghost",
            onclick: () => {
              S.sample += 1;
              sample.textContent = samples[S.sample % samples.length];
            },
          }, icon("refresh"), "Another"),
        ),
        sample,
      ),
      h("div", { class: "help test-limit" }, "This stops by itself after 10 minutes."),
    ),
  });
  main.replaceChildren(view);
  S.wave = new Ink.Wave(canvas, STAGE_FADE);
  updateTestClip();
}

function updateTestClip() {
  const clip = S.snap?.model_test?.recording;
  if (!clip || S.view !== "tests") return;
  const time = $("#test-time");
  if (!time) return;
  const text = clock(clip.elapsed);
  Ink.clock(time, text);
  S.wave?.levels(clip.levels.mic, 0, false);
  setMeter($("#fill-you"), clip.levels.mic, "mic");
  setMeterState("#state-you", clip, "mic", "Hearing you");
  const name = clip.devices.mic[0] || "No microphone";
  const nameEl = $("#name-you");
  if (nameEl.textContent !== name) nameEl.textContent = name;
  const messages = [];
  if (clip.error) messages.push({ text: clip.error, kind: "error" });
  for (const notice of clip.notices || []) messages.push({ text: notice });
  if (clip.elapsed > 8 && clip.silent_for.mic > 8) messages.push({ text: "No sound from your microphone yet. Check that it's on and not muted." });
  const banners = $("#test-banners");
  const key = messages.map((message) => message.text).join("|");
  if (banners.dataset.key !== key) {
    banners.dataset.key = key;
    banners.replaceChildren(...messages.map((message) => banner(message.text, message.kind)));
  }
}

async function loadTest() {
  const id = S.testId;
  const data = await attempt(() => api(`/api/model-tests/${id}`));
  if (S.view !== "tests" || S.testId !== id) return;
  if (!data) {
    toAllTests();
    return;
  }
  S.test = data;
  drawTest();
}

function renderTestResult(main) {
  if ($("#test-view")?.dataset.id !== S.testId) {
    main.replaceChildren(
      h(
        "div",
        { class: "dash-view" },
        h(
          "div",
          { class: "dash test-page", id: "test-view", "data-id": S.testId },
          h(
            "div",
            { class: "test-top" },
            h("button", { class: "ghost", onclick: toAllTests }, icon("back"), "All tests"),
            h("div", { id: "test-top-actions" }),
          ),
          h("div", { id: "test-head" }),
          h("div", { class: "test-player", id: "test-player" }),
          h("div", { id: "test-body" }),
        ),
      ),
    );
  }
  loadTest();
}

function drawTest() {
  const test = S.test;
  if (!test || !$("#test-body")) return;
  const running = test.runs.some((run) => ["waiting", "running"].includes(run.state));
  $("#test-head").replaceChildren(
    h("h1", {}, testTitle(test)),
    h("div", { class: "dash-meta test-meta" }, [lengthText(test.duration), languageName(test.language), test.microphone].filter(Boolean).join(" · ")),
  );
  $("#test-top-actions").replaceChildren(
    running
      ? h("button", { class: "ghost", onclick: () => attempt(() => api(`/api/model-tests/${test.id}/cancel`, { method: "POST" })) }, icon("stop"), "Stop the models")
      : h("button", { class: "ghost", onclick: () => confirmDeleteTest(test) }, icon("trash"), "Delete test"),
  );
  if (test.has_audio) Player.load(test.id, $("#test-player"), test.duration, test.playback_gain, `/api/model-tests/${test.id}/audio`);
  const done = test.runs.filter((run) => run.state === "done");
  const languages = new Set(test.runs.map((run) => `${run.language} ${run.hint} ${run.hint_edit || ""}`));
  $("#test-body").replaceChildren(...[
    test.error && banner(test.error, "error"),
    ...(test.warnings || []).map((text) => banner(text)),
    test.silent && banner("The microphone didn't hear anything, so there was nothing to compare. Check your microphone in Settings, then try again."),
    h("div", { class: "test-grid" }, test.runs.map((run, index) => renderRunCard(run, index, languages.size > 1))),
    done.length > 1 && !running && h("p", { class: "help test-legend" }, "Underlined words are ones no other model wrote, so that's where to look first."),
    !running && (test.has_audio || test.can_run) && renderRunAgain(test),
  ].filter(Boolean));
  updateTestProgress();
}

function renderRunCard(run, index, showLanguage) {
  const parts = [];
  if (run.seconds !== undefined && run.seconds !== null) parts.push(`${Math.round(run.seconds)} sec`);
  if (run.device === "CPU") parts.push("on the CPU");
  let body;
  if (run.state === "done") {
    body = run.pieces?.length
      ? h("div", { class: "test-text" }, run.pieces.map(([text, differs]) => (differs ? h("span", { class: "differs" }, text) : text)))
      : h("p", { class: "help" }, "It didn't write anything down.");
  } else if (run.state === "failed") {
    body = banner(run.error || "It stopped unexpectedly.", "error");
  } else if (run.state === "stopped") {
    body = h("p", { class: "help" }, "Stopped before it finished.");
  } else {
    body = h(
      "div",
      { class: "test-working" },
      h("div", { class: "help", id: `run-status-${index}` }, run.state === "waiting" ? "Waiting for its turn" : "Loading the model"),
      run.state === "running" && h("div", { class: "meter you" }, h("span", { id: `run-bar-${index}` })),
    );
  }
  return h(
    "section",
    { class: "card test-card" },
    h("div", { class: "test-card-head" }, h("h2", {}, run.label), h("span", { class: "dash-meta" }, parts.join(" "))),
    (showLanguage || run.hint_edit) && h("div", { class: "dash-meta test-card-language" }, `${languageName(run.language)}, ${hintName(run.hint, run.hint_edit)}${run.hint_edit ? `: ${run.hint_edit}` : ""}`),
    body,
    (run.notes || []).map((note) => banner(note)),
    run.state === "done" && run.pieces?.length > 0 &&
      h(
        "div",
        { class: "test-card-foot" },
        h(
          "div",
          { class: "test-score", role: "group", "aria-label": `Your score for ${run.label}` },
          [1, 2, 3, 4, 5].map((value) =>
            h("button", {
              class: `score-btn ${run.score === value ? "on" : ""}`.trim(),
              title: SCORE_WORDS[value],
              "aria-label": `${value} of 5: ${SCORE_WORDS[value]}`,
              "aria-pressed": String(run.score === value),
              onclick: () => scoreRun(index, run.score === value ? null : value),
            }, value),
          ),
        ),
        useModelButton(run.engine, run.label, run.language),
      ),
  );
}

async function scoreRun(index, score) {
  const test = S.test;
  const saved = await attempt(() => api(`/api/model-tests/${test.id}/score`, { method: "POST", body: { run: index, score } }));
  if (saved && S.test === test) {
    test.runs[index].score = saved.score;
    drawTest();
  }
}

function renderRunAgain(test) {
  let language = test.runs.at(-1)?.language || test.language;
  let hint = test.runs.at(-1)?.hint || test.hint || "meeting";
  return h(
    "section",
    { class: "card test-again" },
    selectField("Try all the models again on this clip, with the language set to", language, SPEECH_LANGUAGES, (value) => {
      language = value;
    }),
    selectField("and this hint", hint, HINTS, (value) => {
      hint = value;
    }),
    h(
      "div",
      { class: "row-actions" },
      h("button", {
        onclick: () => attempt(() => api(`/api/model-tests/${test.id}/run`, { method: "POST", body: { language, hint } })),
      }, icon("refresh"), "Run again"),
    ),
  );
}

function updateTestProgress() {
  const progress = S.snap?.model_test?.progress;
  if (S.view !== "tests" || !S.testId || !progress || S.snap.model_test.current !== S.testId) return;
  const status = $(`#run-status-${progress.run}`);
  if (!status) return;
  const text = progress.stage === "transcribing" ? `Writing it down, ${Math.round(progress.fraction * 100)}%` : "Loading the model";
  if (status.textContent !== text) status.textContent = text;
  const bar = $(`#run-bar-${progress.run}`);
  if (bar) bar.style.transform = `scaleX(${progress.stage === "transcribing" ? progress.fraction : 0})`;
}

function confirmDeleteTest(test) {
  dialog("Delete this test?", "Its audio and what each model heard will go to the Recycle Bin, and its scores will no longer count.", [
    ["Keep it", ""],
    [
      "Delete",
      "danger",
      async () => {
        await attempt(() => api(`/api/model-tests/${test.id}`, { method: "DELETE" }));
        toAllTests();
      },
    ],
  ]);
}

// ---------------------------------------------------------------- prompts

const isCode = (item) => item.kind === "code";
const isProofread = (item) => item.kind === "proofread";
const promptTitle = (item) => item.title || `${isCode(item) ? "Code" : isProofread(item) ? "Proofread" : "Prompt"} on ${new Date(item.started_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`;
const PROMPT_WORKING = ["listening", "hearing", "writing"];
const workingWords = (item) => ({ listening: "Listening", hearing: "Hearing what you said", writing: isProofread(item) ? "Proofreading" : `Writing your ${isCode(item) ? "code" : "prompt"}`, check: "Waiting for you to check it" })[item.status];

function renderPrompts(main) {
  if (S.snap?.prompt?.recording) renderPromptListening(main);
  else if (S.promptId) renderPromptDetail(main);
  else renderPromptHome(main);
}

async function startPrompt(kind = "prompt") {
  const typed = S.typedDraft;
  const started = await attempt(() => api("/api/prompts/start", { method: "POST", body: { typed, kind } }));
  if (started) S.typedDraft = "";
  return started;
}

// From a start button you're looking at this window anyway, so it shows what's going, as a meeting does. The shortcut leaves you on the page you're reading.
async function startPromptAndShow(kind) {
  if (await startPrompt(kind)) setView("prompts");
}

// Without talking. Text from the box goes first. Otherwise it's what you copied just now, and failing that the app waits for you to copy something.
async function startProofread(text = "") {
  showProofread(await attempt(() => api("/api/proofread", { method: "POST", body: { text } })));
}

function showProofread(started) {
  if (!started) return;
  if (started.message) toast(started.message, "error");
  if (started.id) {
    S.proofreadDraft = "";
    openPrompt(started.id);
    return;
  }
  S.promptId = null;
  S.prompt = null;
  // Its box is further down the page, and it's where you'd paste instead.
  S.showProofreadBox = true;
  if (S.view === "prompts") renderMain();
  else setView("prompts");
}

// It listens, so you can say how you want it edited. What's in the box is the text, as if you'd copied it. During a recording the app
// proofreads without listening instead, and that comes back looking like the above.
async function startProofreadTalking() {
  const started = await attempt(() => api("/api/prompts/start", { method: "POST", body: { typed: S.proofreadDraft || "", kind: "proofread" } }));
  if (started?.stage !== undefined) {
    showProofread(started);
    return;
  }
  if (!started) return;
  S.proofreadDraft = "";
  setView("prompts");
}

function togglePromptPause() {
  return attempt(() => api(`/api/prompts/${S.snap?.prompt?.recording?.paused ? "resume" : "pause"}`, { method: "POST" }));
}

function openPrompt(id) {
  Player.unload();
  if (S.view !== "prompts") setView("prompts");
  S.promptId = id;
  S.prompt = null;
  renderMain();
}

function toAllPrompts() {
  Player.unload();
  S.promptId = null;
  S.prompt = null;
  renderMain();
}

function timingText(timing) {
  if (!timing) return "";
  if (timing.write_seconds === undefined) return `Heard in ${timing.hear_seconds} sec`;
  if (timing.total_seconds === undefined) return `Written in ${Math.round(timing.write_seconds)} sec`;
  return `${timing.total_seconds} sec after you stopped: ${timing.hear_seconds} to hear you, ${timing.write_seconds} to write`;
}

async function renderPromptHome(main) {
  if (!$("#prompt-home")) main.replaceChildren(h("div", { class: "dash-view" }, h("div", { class: "dash", id: "prompt-home" }, pageTitle("言", "Prompts, code and edits"))));
  const data = await attempt(() => api("/api/prompts"));
  const root = $("#prompt-home");
  if (!data || !root || S.view !== "prompts" || S.promptId || S.snap?.prompt?.recording) return;
  const blocked = S.snap?.recording?.active;
  root.replaceChildren(...[
    root.querySelector(".page-title"),
    h(
      "ol",
      { class: "prompt-steps" },
      h("li", {}, "Reading something long? Copy a passage, press ", h("kbd", {}, S.settings.hotkey_prompt), " and say what you think of it."),
      h("li", {}, "Press ", h("kbd", {}, S.settings.hotkey_prompt), " again to pause, read on, and repeat as many times as you like. Nothing is recorded while paused."),
      h("li", {}, "Press ", h("kbd", {}, S.settings.hotkey_finish), S.settings.prompt_check_first ? " when you're done, check what it heard and press Write it." : " when you're done.", " When the small bar says it's ready, press Ctrl+V."),
      h("li", {}, "For the code itself rather than a prompt to ask for it, do the same with ", h("kbd", {}, S.settings.hotkey_code), ". All that gets pasted is the code."),
    ),
    h(
      "section",
      { class: "card" },
      h(
        "div",
        { class: "field" },
        h("label", { class: "field-label", for: "prompt-typed" }, "Text to give it ", h("small", {}, "(optional)")),
        h("textarea", { id: "prompt-typed", rows: 3, value: S.typedDraft, placeholder: "Paste an AI's reply, an error or anything else it should know about", oninput: (event) => { S.typedDraft = event.target.value; } }),
        h("div", { class: "help" }, "Anything you copy in the 15 seconds before you start, or at any point before you finish, gets used too. All of it only helps the AI understand you: it's never treated as your request unless you say so out loud."),
      ),
      h("div", { class: "field" }, checkFirstToggle(), addKnowledgeToggle(), includeCopiedToggle()),
      h(
        "div",
        { class: "row-actions" },
        h("button", { class: "primary test-go", disabled: blocked, onclick: () => startPrompt() }, icon("mic"), "Talk for a prompt"),
        h("button", { class: "test-go", disabled: blocked, onclick: () => startPrompt("code") }, icon("mic"), "Talk for code"),
        blocked && h("span", { class: "help" }, "Stop your recording first."),
      ),
    ),
    h(
      "section",
      { class: "card" },
      h("h2", {}, "Proofread"),
      h("div", { class: "help" }, "Copy some text and press ", h("kbd", {}, S.settings.hotkey_proofread), ". Say how you want it edited if you like, such as “make it shorter”, then press ", h("kbd", {}, S.settings.hotkey_finish), ". When the small bar says it's ready, press Ctrl+V. All that gets pasted is the edited text."),
      h("div", { class: "help" }, "To skip the mic, press ", h("kbd", {}, S.settings.hotkey_proofread_text), " instead: one press, and it proofreads what you copied. During a recording, either one works without listening."),
      S.snap?.prompt?.stage === "copy" && banner("Copy the text to proofread, and it starts by itself."),
      h(
        "div",
        { class: "field" },
        h("label", { class: "field-label", for: "proofread-text" }, "Or paste it here"),
        h("textarea", { id: "proofread-text", rows: 3, value: S.proofreadDraft || "", placeholder: "The text to proofread", oninput: (event) => { S.proofreadDraft = event.target.value; } }),
      ),
      h(
        "div",
        { class: "row-actions" },
        h("button", { class: "test-go", onclick: startProofreadTalking }, icon("mic"), "Proofread"),
        h("button", { class: "test-go", onclick: () => startProofread(S.proofreadDraft) }, icon("edit"), "Without talking"),
      ),
    ),
    data.prompts.length > 0 &&
      h(
        "section",
        { class: "card" },
        h("h2", {}, "Recent"),
        data.prompts.map(renderPromptRow),
      ),
  ].filter(Boolean));
  if (S.showProofreadBox) {
    S.showProofreadBox = false;
    $("#proofread-text").focus();
  }
}

function renderPromptRow(item) {
  return h(
    "div",
    { class: "dash-row spread" },
    h("div", { class: "prompt-row" }, h("button", { class: "link", onclick: () => openPrompt(item.id) }, promptTitle(item)), isCode(item) && h("span", { class: "kind-tag" }, item.language || "Code"), isProofread(item) && h("span", { class: "kind-tag" }, "Proofread"), h("div", { class: "dash-meta" }, item.status === "ready" ? item.preview : item.error || workingWords(item) || "Nothing written")),
    h("span", { class: "dash-meta prompt-when" }, item.timing?.total_seconds !== undefined ? `${Math.round(item.timing.total_seconds)} sec` : ""),
  );
}

function renderPromptListening(main) {
  const proofread = S.snap?.prompt?.kind === "proofread";
  const { view, canvas } = stageView({
    ch: "聽",
    kind: "live",
    glyphId: "prompt-glyph",
    word: "Listening to your microphone",
    wordId: "prompt-state",
    time: "00:00",
    timeId: "prompt-time",
    below: h(
      "div",
      { class: "rec-view" },
      h("div", { class: "meters" }, meterRow("you", "You")),
      h(
        "div",
        { class: "rec-actions" },
        h("button", { class: "danger", onclick: finishPrompt }, icon("stop"), proofread ? "Finish and proofread it" : S.settings.prompt_check_first ? "Finish and check it" : "Finish and write it"),
        h("button", { class: "pause", id: "prompt-pause", onclick: togglePromptPause }),
      ),
      h(
        "div",
        { class: "rec-more" },
        h("button", {
          class: "ghost",
          onclick: () => {
            S.discardingPrompt = true;
            attempt(() => api("/api/prompts/cancel", { method: "POST" }));
          },
        }, "Cancel and throw it away"),
      ),
      h("div", { class: "banners", id: "prompt-banners" }),
      h("div", { class: "help prompt-copied", id: "prompt-copied" }),
      h(
        "section",
        { class: "card test-sample-card" },
        proofread
          ? h("label", { class: "field-label", for: "prompt-typed-live" }, "The text to proofread ", h("small", {}, "(or copy it: the last one you give it is the one it does)"))
          : h("label", { class: "field-label", for: "prompt-typed-live" }, "Text to give it ", h("small", {}, "(optional)")),
        h("textarea", {
          id: "prompt-typed-live",
          rows: 3,
          oninput: (event) => saveTyped(S.snap?.prompt?.id, event.target.value),
        }),
      ),
    ),
  });
  main.replaceChildren(view);
  S.wave = new Ink.Wave(canvas, STAGE_FADE);
  updatePromptListening();
}

function updatePromptListening() {
  const prompt = S.snap?.prompt;
  const live = prompt?.recording;
  if (!live) return;
  if (!S.snap.recording.active) updateLiveCard(live, listeningGlyph(live), "Listening");
  if (S.view !== "prompts") return;
  const time = $("#prompt-time");
  if (!time) return;
  const text = clock(live.elapsed);
  Ink.clock(time, text);
  const copyNotice = noticeCopy(prompt);
  Ink.setGlyph($("#prompt-glyph"), copyNotice ? "抄" : live.paused ? "停" : "聽", copyNotice ? "copied" : live.paused ? "still" : "live");
  S.wave?.levels(live.levels.mic, 0, live.paused);
  const state = copyNotice ? copyNotice.said : live.paused ? `Paused after ${live.takes} ${live.takes === 1 ? "take" : "takes"}. Nothing is being recorded.` : `${live.takes > 1 ? `Listening, take ${live.takes}` : "Listening to your microphone"}${{ code: ", for code", proofread: ". Say how to edit it, or just finish" }[prompt.kind] || ""}`;
  const stateEl = $("#prompt-state");
  if (stateEl.textContent !== state) stateEl.textContent = state;
  const pause = $("#prompt-pause");
  const pauseState = live.paused ? "resume" : "pause";
  if (pause.dataset.state !== pauseState) {
    pause.dataset.state = pauseState;
    pause.replaceChildren(icon(live.paused ? "play" : "pause"), live.paused ? "Talk" : "Pause");
  }
  setMeter($("#fill-you"), live.levels.mic, "mic");
  setMeterState("#state-you", live, "mic", "Hearing you");
  const name = live.devices.mic[0] || "No microphone";
  const nameEl = $("#name-you");
  if (nameEl.textContent !== name) nameEl.textContent = name;
  showCopied(prompt, copyNotice);
  const health = live.health;
  const banners = $("#prompt-banners");
  if (banners.dataset.key !== (health?.text || "")) {
    banners.dataset.key = health?.text || "";
    banners.replaceChildren(...(health ? [banner(health.text, health.kind === "error" ? "error" : "")] : []));
  }
}

const COPY_NOTICE_FOR = 6000;

// A copy landing, hard to miss as on the floating bar. Says which copy to announce right now, if any.
function noticeCopy(prompt) {
  const box = $("#prompt-copied");
  if (S.copyFlashes !== undefined && prompt.copy_flashes > S.copyFlashes) {
    S.copyNotice = { key: prompt.latest_copy?.key, until: Date.now() + COPY_NOTICE_FOR };
    box.classList.remove("wash");
    void box.offsetWidth;
    box.classList.add("wash");
  }
  S.copyFlashes = prompt.copy_flashes;
  const copy = prompt.latest_copy;
  const noticing = copy && S.copyNotice?.key === copy.key && Date.now() < S.copyNotice.until;
  box.classList.toggle("marked", Boolean(noticing));
  if (!noticing) box.classList.remove("wash");
  return noticing ? copy : null;
}

function showCopied(prompt, copyNotice) {
  const box = $("#prompt-copied");
  const copy = prompt.latest_copy;
  const key = JSON.stringify([prompt.copied, copy, Boolean(copyNotice)]);
  if (box.dataset.key === key) return;
  box.dataset.key = key;
  box.replaceChildren(
    ...[
      h("div", {}, prompt.copied ? `Using ${prompt.copied} copied ${prompt.copied === 1 ? "text" : "texts"}. Anything else you copy gets added.` : "Anything you copy from now on gets added, in the order you copy it."),
      // One too long to add wasn't added, so there's nothing to take back.
      copy && h("div", { class: "copy-latest" }, h("span", { title: copy.words }, `${copyNotice || copy.added === false ? copy.said : "Latest"}: “${copy.words}”`), copy.added !== false && h("button", { class: "ghost", onclick: () => undoCopy(prompt.id, copy.key) }, "Undo")),
    ].filter(Boolean),
  );
}

async function undoCopy(id, key) {
  if (await attempt(() => api("/api/prompts/undo-copy", { method: "POST", body: { id, key } }))) toast("Took that back. It's still on your clipboard.");
}

async function loadPrompt() {
  const id = S.promptId;
  // Old words from the app mustn't replace what's in the boxes while that can't be saved.
  if (!(await promptSavesDone(id)) && S.prompt?.id === id) return;
  const data = await attempt(() => api(`/api/prompts/${id}`));
  if (S.view !== "prompts" || S.promptId !== id) return;
  if (!data) {
    toAllPrompts();
    return;
  }
  S.prompt = withWaitingEdits(data);
  // Don't redraw under someone who's typing.
  if (!["prompt-text", "prompt-spoken"].includes(document.activeElement?.id)) drawPrompt();
}

function renderPromptDetail(main) {
  if ($("#prompt-view")?.dataset.id !== S.promptId) {
    main.replaceChildren(
      h(
        "div",
        { class: "dash-view" },
        h(
          "div",
          { class: "dash prompt-page", id: "prompt-view", "data-id": S.promptId },
          h(
            "div",
            { class: "test-top" },
            h("button", { class: "ghost", onclick: toAllPrompts }, icon("back"), "All prompts"),
            h("div", { id: "prompt-top-actions" }),
          ),
          h("div", { id: "prompt-head" }),
          h("div", { id: "prompt-body" }),
          h("div", { class: "test-player", id: "prompt-player" }),
        ),
      ),
    );
  }
  loadPrompt();
}

const typedSaves = inOrder();
let typedWaiting = null;

// For the prompt it was typed in: if it arrives after that one has gone, the app drops it rather than giving it to whichever prompt is open by then.
function saveTyped(id, text) {
  clearTimeout(S.typedTimer);
  typedWaiting = () => {
    clearTimeout(S.typedTimer);
    typedWaiting = null;
    return typedSaves(() => attempt(() => api("/api/prompts/typed", { method: "POST", body: { id, text } })));
  };
  S.typedTimer = setTimeout(typedWaiting, 300);
}

// What you've just typed goes first, so it's there when the prompt gets written.
async function finishPrompt() {
  await (typedWaiting ? typedWaiting() : typedSaves(() => undefined));
  attempt(() => api("/api/prompts/stop", { method: "POST" }));
}

// ---- prompt saves: tests/test_prompt_saves.py runs this part by itself.
// One waiting save per box, for the prompt it was typed in, whichever page you've gone on to. They go out in order, and whatever reads the saved words waits for them.
const promptSaves = new Map();
const newestPromptEdit = new Map();
let promptEdits = 0;
let promptSaving = Promise.resolve();

function sendPromptSave(key) {
  const save = promptSaves.get(key);
  clearTimeout(save.timer);
  promptSaves.delete(key);
  promptSaving = promptSaving.then(async () => {
    const saved = await attempt(() => api(`/api/prompts/${save.id}`, { method: "PATCH", body: { [save.field]: save.value } }));
    // Back to waiting, so nothing carries on from the old words and the next try sends it again. Only if it's the newest, though: an older one
    // going out again would overwrite the newer one, even after that has been saved.
    if (!saved && newestPromptEdit.get(key) === save.edit) promptSaves.set(key, { ...save, timer: null });
    return saved;
  });
  return promptSaving;
}

function savePromptField(id, field, value) {
  const key = `${id} ${field}`;
  clearTimeout(promptSaves.get(key)?.timer);
  promptEdits += 1;
  newestPromptEdit.set(key, promptEdits);
  promptSaves.set(key, { id, field, value, edit: promptEdits, timer: setTimeout(() => sendPromptSave(key), 300) });
}

// Says whether everything for this prompt is really saved, or for every prompt if it's given none. That includes saves already on their way,
// and any sent while this waits. If one didn't work, attempt has already said why, and the words are still in the box.
async function promptSavesDone(id) {
  for (;;) {
    let last;
    do {
      last = promptSaving;
      await last;
    } while (last !== promptSaving);
    const waiting = [...promptSaves].filter(([, save]) => id === undefined || save.id === id);
    if (!waiting.length) return true;
    const results = await Promise.all(waiting.map(([key]) => sendPromptSave(key)));
    if (results.some((saved, index) => !saved && promptSaves.has(waiting[index][0]))) return false;
  }
}

// What's still waiting to be saved for this prompt goes on top of what came back from the app.
function withWaitingEdits(prompt) {
  for (const save of promptSaves.values()) {
    if (save.id === prompt.id) prompt[save.field === "spoken" ? "spoken_text" : save.field] = save.value;
  }
  return prompt;
}

function dropPromptSaves(id) {
  for (const [key, save] of promptSaves) {
    if (save.id === id) {
      clearTimeout(save.timer);
      promptSaves.delete(key);
      newestPromptEdit.delete(key);
    }
  }
}
// ---- end of prompt saves

const copiedOr = (updated, words) => (updated.copied === false ? "Done, but it couldn't reach the clipboard. Press Copy to try again." : words);

function promptList(title, items, render) {
  return items?.length > 0 && h("section", { class: "card" }, h("h2", {}, title), h("ul", { class: "prompt-list" }, items.map(render)));
}

function codeCheckBanner(item) {
  if (item.said_not) return banner(`This code can ${item.word}, but what you said was not to. Check it before you run it.`, "error");
  if (item.said) return banner(`This code can ${item.word}. You said that too, so it stays. This is only a reminder to check it's what you meant.`);
  if (item.copied) return banner(`This code can ${item.word}. You didn't say that, but the text you copied does it too. Check it's what you meant before you run it.`);
  return banner(`This code can ${item.word}, and you didn't say that. Check it before you run it.`, "error");
}

function checkBanner(item) {
  if (item.said_not) return banner(`This prompt says "${item.word}", but what you said was not to. Check it before pasting.`, "error");
  if (item.said) return banner(`This prompt says "${item.word}". You said that too, so it stays. This is only a reminder to check it's what you meant.`);
  if (item.copied) return banner(`This prompt says "${item.word}". You didn't say that, but the text you copied does. Check it's what you meant before pasting.`, "error");
  return banner(`This prompt says "${item.word}", but you didn't say that and it isn't in what you copied. Check it before pasting.`, "error");
}

// A proofread whose hearing failed still has what you said in its audio, so trying again means hearing it first: proofreading the copied text
// alone would leave out something like "make it shorter". What it heard is only kept once hearing has finished, so one that heard nothing,
// like one that never listened, was a plain proofread on purpose. And with nothing copied, hearing it again wouldn't help.
function hearingFailed(prompt) {
  return isProofread(prompt) && Boolean(prompt.error) && !prompt.prompt && prompt.can_hear && !prompt.spoken && !prompt.spoken_text.trim() && prompt.text.length > 0;
}

function writeItLabel(prompt) {
  if (prompt.status === "check") return "Write it";
  if (!isProofread(prompt)) return "Write again";
  return hearingFailed(prompt) ? "Proofread without what you said" : "Proofread again";
}

// It failed with nothing written to show. Try again hears it again, where that's the way on.
function promptFailure(prompt, flyFrom) {
  const proofread = isProofread(prompt);
  const said = prompt.spoken_text.trim();
  return h(
    "div",
    { class: "failure" },
    Ink.glyph("錯", "problem", { size: 60, write: Boolean(flyFrom) }),
    h("h3", {}, proofread ? "It couldn't proofread that" : said ? "It couldn't write that" : "It couldn't hear that"),
    h("p", {}, prompt.error),
    (proofread ? hearingFailed(prompt) : !said && prompt.can_hear) && h("button", { class: "primary", onclick: () => attempt(() => api(`/api/prompts/${prompt.id}/hear`, { method: "POST" })) }, icon("refresh"), "Try again"),
  );
}

function drawPrompt() {
  const prompt = S.prompt;
  if (!prompt || !$("#prompt-body")) return;
  const code = isCode(prompt);
  const proofread = isProofread(prompt);
  const working = PROMPT_WORKING.includes(prompt.status);
  $("#prompt-head").replaceChildren(
    h("h1", {}, promptTitle(prompt)),
    h("div", { class: "dash-meta test-meta" }, [code && prompt.language, (!proofread || prompt.has_audio) && lengthText(prompt.duration), prompt.speech_model, timingText(prompt.timing)].filter(Boolean).join(" · ")),
  );
  $("#prompt-top-actions").replaceChildren(
    working
      ? h("button", { class: "ghost", onclick: () => { S.discardingPrompt = true; attempt(() => api("/api/prompts/cancel", { method: "POST" })); } }, icon("stop"), "Cancel")
      : h("button", { class: "ghost", onclick: () => confirmDeletePrompt(prompt) }, icon("trash"), "Delete"),
  );
  if (prompt.has_audio) Player.load(`prompt-${prompt.id}`, $("#prompt-player"), prompt.duration, prompt.playback_gain, `/api/prompts/${prompt.id}/audio`);
  if (working) {
    if ($("#prompt-stage")) {
      $("#prompt-work").textContent = workingWords(prompt);
      return;
    }
    const canvas = h("canvas", { class: "wave" });
    $("#prompt-body").replaceChildren(
      h(
        "div",
        { class: "stage working", id: "prompt-stage" },
        canvas,
        h("div", { class: "stage-status" }, Ink.glyph("寫", "live", { size: 96, write: true }), h("div", {}, h("div", { class: "stage-word", id: "prompt-work" }, workingWords(prompt)), h("div", { class: "help" }, prompt.status === "hearing" && S.settings.prompt_check_first ? "You'll check it before it's sent" : "It'll be ready to paste"))),
      ),
    );
    S.wave = new Ink.Wave(canvas, { fadeFrom: 300, fadeTo: 500 });
    S.wave.work(true);
    return;
  }
  // If you watched it being written, the wave's characters are about to fly into your words.
  const flyFrom = $("#prompt-stage") ? S.wave?.points() : null;
  const hasPrompt = Boolean(prompt.prompt);
  const checking = prompt.status === "check";
  const used = new Set(prompt.used_suggestions || []);
  const box = h("textarea", { id: "prompt-text", class: code ? "prompt-box code-box" : "prompt-box", spellcheck: !code, wrap: code ? "off" : undefined, rows: Math.min(code ? 24 : 16, Math.max(4, Math.ceil(prompt.prompt.length / 70) + prompt.prompt.split("\n").length)), value: prompt.prompt, oninput: (event) => { prompt.prompt = event.target.value; savePromptField(prompt.id, "prompt", prompt.prompt); } });
  const copy = async () => {
    savePromptField(prompt.id, "prompt", box.value);
    if (!(await promptSavesDone(prompt.id))) return;
    const done = await attempt(() => api(`/api/prompts/${prompt.id}/copy`, { method: "POST" }));
    if (done) toast("Copied. Press Ctrl+V where you want it.");
  };
  const seal = Ink.seal({ size: 56 });
  seal.classList.add("prompt-seal");
  $("#prompt-body").replaceChildren(...[
    prompt.error && !hasPrompt && promptFailure(prompt, flyFrom),
    prompt.error && hasPrompt && banner(prompt.error, "error"),
    !hasPrompt && !prompt.error && prompt.status === "empty" && emptyNote("無", "Nothing was heard, so nothing was written."),
    checking && h(
      "section",
      { class: "card prompt-check" },
      Ink.glyph("校", "still", { size: 52, write: Boolean(flyFrom) }),
      h("div", { class: "prompt-check-words" }, h("h2", {}, "Check it, then send it"), h("div", { class: "help" }, "Nothing has gone to the AI yet. Fix anything it misheard, and remove anything you didn't mean to copy.")),
      writeItButton(prompt, "primary"),
    ),
    ...(prompt.notes || []).map((note) => banner(note)),
    ...(prompt.check || []).map(code ? codeCheckBanner : checkBanner),
    hasPrompt && h(
      "section",
      { class: "card prompt-card" },
      seal,
      h("div", { class: "card-head" }, h("h2", {}, code ? "Your code" : proofread ? "Edited text" : "Your prompt"), h("button", { class: "primary", onclick: copy }, icon("copy"), "Copy")),
      box,
      !code && !proofread && prompt.text.length > 0 && h(
        "label",
        { class: "toggle" },
        h("input", {
          type: "checkbox",
          checked: prompt.include_text,
          onchange: async (event) => {
            const on = event.target.checked;
            if (!(await promptSavesDone(prompt.id))) {
              event.target.checked = !on;
              return;
            }
            const updated = await attempt(() => api(`/api/prompts/${prompt.id}`, { method: "PATCH", body: { include_text: on } }));
            if (updated) {
              S.prompt = updated;
              toast(copiedOr(updated, updated.include_text ? "The text you gave it will be pasted too. Copied." : "Just the prompt will be pasted. Copied."));
            }
          },
        }),
        h("span", {}, "Also paste the text I gave it", h("div", { class: "help" }, "Turn this on when you're starting a new chat, so the AI can see what you're talking about.")),
      ),
    ),
    promptList("Added by the AI, for you to check", prompt.added, (item) => h("li", {}, item)),
    promptList(code ? "Worth knowing before you run it" : "Couldn't tell what you meant", prompt.unsure, (item) => h("li", {}, item)),
    promptList("Suggested, not in your prompt", prompt.suggestions, (item, index) =>
      h(
        "li",
        { class: "prompt-suggestion" },
        h("span", {}, item),
        used.has(index)
          ? h("span", { class: "test-in-use" }, icon("check"), "Added")
          : h("button", {
            class: "ghost",
            onclick: async () => {
              if (!(await promptSavesDone(prompt.id))) return;
              const updated = await attempt(() => api(`/api/prompts/${prompt.id}/suggestion`, { method: "POST", body: { index } }));
              if (updated) {
                S.prompt = updated;
                drawPrompt();
                toast(copiedOr(updated, "Added and copied."));
              }
            },
          }, "Add it"),
      ),
    ),
    (!proofread || prompt.has_audio) && h(
      "section",
      { class: "card" },
      h("h2", {}, proofread ? "What you said about how" : "What you said"),
      h("textarea", { id: "prompt-spoken", rows: Math.min(10, Math.max(3, Math.ceil(prompt.spoken_text.length / 70))), value: prompt.spoken_text, oninput: (event) => { prompt.spoken_text = event.target.value; savePromptField(prompt.id, "spoken", prompt.spoken_text); showWriteAgain(prompt); } }),
      h("div", { class: "help" }, checking ? "If it misheard you, fix it here." : proofread ? "Fix or change it here, then press Proofread again. Leave it empty to just proofread." : "If it misheard you, fix it here and press Write again."),
    ),
    prompt.text.length > 0 && h(
      "section",
      { class: "card" },
      h("h2", {}, proofread ? "The original" : "Text you gave it"),
      prompt.text.map((item) =>
        h(
          "div",
          { class: "prompt-given" },
          h(
            "div",
            { class: "dash-meta prompt-given-head" },
            !proofread && h("span", {}, item.kind === "typed" ? "Typed in" : item.at === null ? "Copied before you started" : `Copied at ${clock(item.at)}${item.between_takes ? ", between takes" : ""}`),
            checking && item.kind === "copied" && h("button", { class: "ghost", onclick: () => removeCopied(prompt.id, item.key) }, icon("trash"), "Remove"),
          ),
          h("div", { class: "prompt-given-text" }, item.text),
        ),
      ),
    ),
    (proofread || prompt.spoken_text.trim()) && renderWriteAgain(prompt),
  ].filter(Boolean));
  if (flyFrom && hasPrompt) {
    seal.hidden = true;
    Ink.settle(box, prompt.prompt, flyFrom, () => {
      seal.hidden = false;
      if (Ink.moves()) seal.classList.add("stamped");
    });
  }
}

// Typing in what you said when nothing was heard is another way to get a prompt written, so the button follows the words. So does what
// a proofread's button says: typing in what it couldn't hear means it proofreads with that.
function showWriteAgain(prompt) {
  if (prompt.spoken_text.trim() && !$("#prompt-again")) $("#prompt-body").append(renderWriteAgain(prompt));
  for (const label of document.querySelectorAll(".write-it-label")) label.textContent = writeItLabel(prompt);
}

// It writes from the saved words, so a fix you've just typed has to get there first.
function writeItButton(prompt, kind, body = {}) {
  return h("button", {
    class: kind,
    onclick: async () => {
      if (await promptSavesDone(prompt.id)) attempt(() => api(`/api/prompts/${prompt.id}/write`, { method: "POST", body: typeof body === "function" ? body() : body }));
    },
  }, icon(prompt.status === "check" ? "check" : "refresh"), h("span", { class: "write-it-label" }, writeItLabel(prompt)));
}

async function removeCopied(id, key) {
  if (await attempt(() => api("/api/prompts/undo-copy", { method: "POST", body: { id, key } }))) await loadPrompt();
}

function renderWriteAgain(prompt) {
  const code = isCode(prompt);
  const proofread = isProofread(prompt);
  const set = (name) => S.settings[`${code ? "code" : proofread ? "proofread" : "prompt"}_${name}`];
  const choice = { engine: set("engine"), codex: set("codex_model"), claude: set("claude_model"), adds: S.settings.prompt_add_knowledge };
  choice.effort = choice.engine === "claude" ? set("claude_effort") : set("codex_effort");
  const fields = h("div", { class: "prompt-again" });
  const draw = () => {
    const claude = choice.engine === "claude";
    fields.replaceChildren(
      selectField("Write with", choice.engine, [["codex", "Codex"], ["claude", "Claude Code"]], (value) => {
        choice.engine = value;
        choice.effort = value === "claude" ? set("claude_effort") : set("codex_effort");
        draw();
      }),
      selectField("Model", claude ? choice.claude : choice.codex, code ? (claude ? CODE_CLAUDE_MODELS : CODE_CODEX_MODELS) : claude ? CLAUDE_MODELS : CODEX_MODELS, (value) => {
        choice[claude ? "claude" : "codex"] = value;
      }),
      selectField("Effort", choice.effort, claude ? CLAUDE_EFFORTS : CODEX_EFFORTS, (value) => {
        choice.effort = value;
      }),
    );
  };
  draw();
  const attempts = prompt.attempts || [];
  return h(
    "section",
    { class: "card", id: "prompt-again" },
    h("h2", {}, prompt.status === "check" ? "Write it" : proofread ? "Proofread it again" : "Write it again"),
    fields,
    !code && !proofread && h(
      "label",
      { class: "toggle" },
      h("input", { type: "checkbox", checked: choice.adds, onchange: (event) => { choice.adds = event.target.checked; } }),
      h("span", {}, "Let the AI add what it knows", h("div", { class: "help" }, "Just for this attempt. Turn it off to get only what you said, cleaned up.")),
    ),
    h(
      "div",
      { class: "row-actions" },
      writeItButton(prompt, prompt.status === "check" ? "primary" : "", () => ({ engine: choice.engine, model: choice.engine === "claude" ? choice.claude : choice.codex, effort: choice.effort, adds: choice.adds })),
    ),
    attempts.length > 1 && h(
      "div",
      { class: "field" },
      h("div", { class: "field-label" }, "Every attempt so far"),
      attempts.map((item, index) =>
        h(
          "div",
          { class: "dash-row spread" },
          h("div", {}, h("div", {}, [item.engine, item.model, item.effort, `${item.seconds} sec`, item.adds === false && "nothing added"].filter(Boolean).join(" · ")), h("div", { class: "dash-meta" }, item.prompt.length > 110 ? `${item.prompt.slice(0, 110)}…` : item.prompt)),
          item.prompt === prompt.prompt
            ? h("span", { class: "test-in-use" }, icon("check"), "In use")
            : h("button", {
              class: "ghost",
              onclick: async () => {
                if (!(await promptSavesDone(prompt.id))) return;
                const updated = await attempt(() => api(`/api/prompts/${prompt.id}`, { method: "PATCH", body: { attempt: index } }));
                if (updated) {
                  S.prompt = updated;
                  drawPrompt();
                  toast(copiedOr(updated, "Using that one. Copied."));
                }
              },
            }, "Use this one"),
        ),
      ),
    ),
  );
}

function confirmDeletePrompt(prompt) {
  dialog("Delete this prompt?", "Its audio, what you said and the prompts written from it will go to the Recycle Bin.", [
    ["Keep it", ""],
    [
      "Delete",
      "danger",
      async () => {
        dropPromptSaves(prompt.id);
        await attempt(() => api(`/api/prompts/${prompt.id}`, { method: "DELETE" }));
        toAllPrompts();
      },
    ],
  ]);
}

// ---------------------------------------------------------------- player

const Player = {
  id: null,
  audio: null,
  context: null,
  gains: null,
  lastLine: null,

  load(id, slot, duration, gains, path = `/api/meetings/${id}/audio`) {
    if (this.id === id && this.audio && slot.childElementCount) return;
    this.unload();
    this.id = id;
    this.gains = gains || { you: 1, them: 1 };
    const audio = new Audio(`${path}?token=${encodeURIComponent(token)}`);
    audio.preload = "metadata";
    this.audio = audio;
    const play = h("button", { class: "play", "aria-label": "Play", onclick: () => this.toggle() }, icon("play"));
    const range = h("input", { type: "range", min: 0, max: Math.max(1, Math.round(duration || 1)), value: 0, step: 1, "aria-label": "Position" });
    const time = h("span", { class: "time" }, `00:00 / ${clock(duration)}`);
    const speeds = [1, 1.25, 1.5, 2];
    const speed = h("button", { class: "ghost speed", title: "Playback speed", onclick: () => {
      audio.playbackRate = speeds[(speeds.indexOf(audio.playbackRate) + 1) % speeds.length];
      speed.textContent = `${audio.playbackRate}x`;
    } }, "1x");
    range.addEventListener("input", () => { audio.currentTime = Number(range.value); });
    audio.addEventListener("play", () => { play.replaceChildren(icon("pause")); play.setAttribute("aria-label", "Pause"); });
    audio.addEventListener("pause", () => { play.replaceChildren(icon("play")); play.setAttribute("aria-label", "Play"); });
    audio.addEventListener("timeupdate", () => {
      const total = audio.duration && isFinite(audio.duration) ? audio.duration : duration;
      if (document.activeElement !== range) range.value = audio.currentTime;
      time.textContent = `${clock(audio.currentTime)} / ${clock(total)}`;
      const line = highlightLine(audio.currentTime);
      if (line && line !== this.lastLine && !audio.paused) {
        this.lastLine = line;
        line.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }
    });
    audio.addEventListener("loadedmetadata", () => {
      if (isFinite(audio.duration)) range.max = Math.round(audio.duration);
    });
    slot.replaceChildren(
      h(
        "div",
        { class: "player" },
        play,
        h("button", { class: "ghost skip", title: "Back 15 seconds", onclick: () => this.seek(audio.currentTime - 15) }, "-15s"),
        h("button", { class: "ghost skip", title: "Forward 15 seconds", onclick: () => this.seek(audio.currentTime + 15) }, "+15s"),
        range,
        time,
        speed,
      ),
    );
  },

  // The file holds you on the left and them on the right. Even them out and mix them, so both are heard
  // clearly in both ears. They're added rather than averaged, because averaging would halve each side.
  mono() {
    if (this.context || !this.audio) return;
    try {
      const AudioContextClass = window.AudioContext;
      this.context = new AudioContextClass();
      const source = this.context.createMediaElementSource(this.audio);
      const split = this.context.createChannelSplitter(2);
      const mix = this.context.createGain();
      mix.channelCount = 1;
      mix.channelCountMode = "explicit";
      mix.channelInterpretation = "speakers";
      source.connect(split);
      [this.gains.you, this.gains.them].forEach((gain, channel) => {
        const side = this.context.createGain();
        side.gain.value = gain;
        split.connect(side, channel);
        side.connect(mix);
      });
      mix.connect(this.context.destination);
    } catch {
      this.context = null;
    }
  },

  toggle() {
    if (!this.audio) return;
    this.mono();
    if (this.audio.paused) this.audio.play().catch(() => toast("That audio couldn't be played.", "error"));
    else this.audio.pause();
  },

  seek(seconds, play = false) {
    if (!this.audio) return;
    this.audio.currentTime = Math.max(0, seconds);
    if (play && this.audio.paused) this.toggle();
  },

  unload() {
    if (this.audio) {
      this.audio.pause();
      this.audio.removeAttribute("src");
      this.audio.load();
    }
    if (this.context) this.context.close();
    this.audio = null;
    this.context = null;
    this.id = null;
    this.lastLine = null;
  },
};

// ---------------------------------------------------------------- dialogs

function dialog(title, text, actions, extra) {
  const close = () => $("#modal-root").replaceChildren();
  const overlay = h(
    "div",
    {
      class: "overlay",
      role: "dialog",
      "aria-modal": "true",
      onclick: (event) => {
        if (event.target === overlay) close();
      },
    },
    h(
      "div",
      { class: "dialog" },
      h("h2", {}, title),
      text && h("p", {}, text),
      extra,
      h(
        "div",
        { class: "dialog-actions" },
        actions.map(([label, kind, action]) =>
          h("button", { class: kind, onclick: () => { close(); if (action) action(); } }, label),
        ),
      ),
    ),
  );
  $("#modal-root").replaceChildren(overlay);
  const buttons = overlay.querySelectorAll(".dialog-actions button");
  if (buttons.length) buttons[buttons.length - 1].focus();
}

function confirmDelete(meta) {
  dialog(meta.mode === "solo" ? "Delete this note?" : "Delete this meeting?", `"${meta.title}" and its audio, transcript and notes will go to the Recycle Bin.`, [
    ["Cancel", ""],
    [
      "Delete",
      "danger",
      async () => {
        const done = await attempt(() => api(`/api/meetings/${meta.id}`, { method: "DELETE" }));
        if (done) {
          // Anything still waiting to be saved went with it.
          dropMeetingEdits(meta.id);
          setView("home");
        }
      },
    ],
  ]);
}

function confirmDeleteAudio(meta) {
  dialog("Delete the audio?", "The recording goes to the Recycle Bin. The transcript and notes stay, but you won't be able to play it back or transcribe it again.", [
    ["Cancel", ""],
    [
      "Delete audio",
      "danger",
      async () => {
        Player.unload();
        const slot = $("#player-slot");
        if (slot) slot.replaceChildren();
        await attempt(() => api(`/api/meetings/${meta.id}/delete-audio`, { method: "POST" }));
        await loadDetail(true);
      },
    ],
  ]);
}

function confirmRegenerate(meta) {
  if (meta.notes_edited) {
    dialog("Replace your edited notes?", "New notes will replace the ones you edited. The current version is kept as notes.previous.md in the same folder, and My notes aren't affected.", [
      ["Cancel", ""],
      ["Write new notes", "primary", () => process(meta.id, "notes")],
    ]);
  } else {
    process(meta.id, "notes");
  }
}

function confirmRetranscribe(meta) {
  dialog("Transcribe this again?", "This uses your current language and Names and terms settings, then writes new notes. Do this after changing those settings.", [
    ["Cancel", ""],
    ["Transcribe again", "primary", () => process(meta.id, "transcribe")],
  ]);
}

function welcome() {
  const engine = { codex: "Codex", claude: "Claude Code" }[S.settings?.notes_engine];
  dialog(
    "Welcome to Brushtalk",
    null,
    [
      [
        "Got it",
        "primary",
        () => {
          attempt(() => api("/api/settings", { method: "PATCH", body: { onboarded: true } }));
          if (S.settings) S.settings.onboarded = true;
        },
      ],
    ],
    h(
      "ul",
      {},
      h("li", {}, h("strong", {}, "Meeting"), " ", h("kbd", {}, S.settings?.hotkey || ""), " records your mic and all computer audio, for a call. Press it again to stop."),
      h("li", {}, h("strong", {}, "Solo note"), " ", h("kbd", {}, S.settings?.hotkey_solo || ""), " records only your mic, for thinking out loud."),
      h("li", {}, h("strong", {}, "Prompt"), " ", h("kbd", {}, S.settings?.hotkey_prompt || ""), " turns what you say and copy into a prompt to paste."),
      h("li", {}, h("strong", {}, "Code"), " ", h("kbd", {}, S.settings?.hotkey_code || ""), " does the same, but you get the code itself, and nothing else, to paste and run."),
      h("li", {}, h("strong", {}, "Proofread"), " ", h("kbd", {}, S.settings?.hotkey_proofread || ""), ": copy some text, say how you want it edited if you like, and you get it back edited, and nothing else, to paste. ", h("kbd", {}, S.settings?.hotkey_proofread_text || ""), " does it without the mic, in one press."),
      h("li", {}, "Start any of them from the top of the sidebar, or with its shortcut from anywhere."),
      h("li", {}, "The audio stays on this PC.", engine && [" The transcript goes to ", h("strong", {}, engine), " to write the notes or the prompt."]),
      h("li", {}, "Closing the window leaves it running in the tray, next to the clock, so the shortcuts keep working."),
      h("li", {}, "Everyone on a call should agree to being recorded. There's a notice you can copy on the recording screen."),
    ),
  );
}

// ---------------------------------------------------------------- settings

let saveTimer = null;
let pendingPatch = {};
const settingsSaves = inOrder();

function saveSetting(patch, immediate = false) {
  Object.assign(pendingPatch, patch);
  Object.assign(S.settings, patch);
  S.devicesSummary = null;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(flushSettings, immediate ? 0 : 500);
}

async function flushSettings() {
  const patch = pendingPatch;
  pendingPatch = {};
  const result = await settingsSaves(() => attempt(() => api("/api/settings", { method: "PATCH", body: patch })));
  if (!result) return;
  for (const key of ["hotkey", "hotkey_solo", "hotkey_prompt", "hotkey_code", "hotkey_proofread", "hotkey_proofread_text", "hotkey_finish"]) {
    const error = $(`#${key}-error`);
    if (key in patch && error) error.textContent = result[`${key}_error`] || "";
  }
}

function selectField(label, value, options, onchange, help) {
  const id = `field-${label.replace(/\W+/g, "-").toLowerCase()}`;
  return h(
    "div",
    { class: "field" },
    h("label", { class: "field-label", for: id }, label),
    h(
      "select",
      { id, onchange: (event) => onchange(event.target.value) },
      options.map(([optionValue, optionLabel]) => h("option", { value: optionValue, selected: optionValue === value }, optionLabel)),
    ),
    help && h("div", { class: "help" }, help),
  );
}

function textField(label, key, help, rows = 3, placeholder = "") {
  const id = `field-${key}`;
  return h(
    "div",
    { class: "field" },
    h("label", { class: "field-label", for: id }, label),
    h("textarea", { id, rows, placeholder, value: S.settings[key], oninput: (event) => saveSetting({ [key]: event.target.value }) }),
    help && h("div", { class: "help" }, help),
  );
}

function toggleField(label, key, help) {
  return h(
    "label",
    { class: "toggle" },
    h("input", { type: "checkbox", checked: S.settings[key], onchange: (event) => saveSetting({ [key]: event.target.checked }, true) }),
    h("span", {}, label, help && h("div", { class: "help" }, help)),
  );
}

const addKnowledgeToggle = () => toggleField("Let the AI add what it knows", "prompt_add_knowledge", "It can use the proper name for what you meant and add a well-known pitfall, and it lists what it added. Turn this off to get only what you said, cleaned up. Either way it never adds work you didn't ask for.");
const checkFirstToggle = () => toggleField("Check before sending", "prompt_check_first", "When you finish, it stops after hearing you and opens the prompt, so you can fix what it heard and remove anything you copied. Nothing goes to the AI until you press Write it.");
const includeCopiedToggle = () => toggleField("Also paste the text I gave it", "prompt_include_copied", "Puts what you copied or typed under the prompt, so a new chat can see what you're talking about. This is for new prompts, and each prompt's page has its own switch.");

const STATUS_ICON = { ok: "check", warn: "alert", fail: "x" };
// The same choices, with the same ones recommended, for notes, prompts and proofreading.
const CODEX_MODELS = [
  ["gpt-6.1-terra", "GPT-6.1 Terra (recommended)"],
  ["gpt-6.1-sol", "GPT-6.1 Sol"],
  ["gpt-6-luna", "GPT-6 Luna: fast and affordable"],
  ["gpt-6-astra", "GPT-6 Astra: for the most demanding work"],
];
// Code is the exception: on six hard jobs both of Terra's SQL answers wouldn't run as pasted, and all of Astra's did
// (research_notes/Code mode/Code model comparison.md).
const CODE_CODEX_MODELS = [
  ["gpt-6-astra", "GPT-6 Astra (recommended for code)"],
  ["gpt-6.1-sol", "GPT-6.1 Sol"],
  ["gpt-6.1-terra", "GPT-6.1 Terra: the fastest"],
  ["gpt-6-luna", "GPT-6 Luna: fast and affordable"],
];
// Full names, so the version shown is the version that runs. The claude tool's short names move to each new release.
const CLAUDE_MODELS = [["claude-sonnet-5-5", "Claude Sonnet 5.5 (recommended)"], ["claude-opus-5-5", "Claude Opus 5.5"], ["claude-haiku-5-5", "Claude Haiku 5.5"]];
// The owner's pick for code. On two hard jobs it matched Sonnet, a few seconds slower.
const CODE_CLAUDE_MODELS = [["claude-opus-5-5", "Claude Opus 5.5 (recommended for code)"], ["claude-sonnet-5-5", "Claude Sonnet 5.5: a little faster"], ["claude-haiku-5-5", "Claude Haiku 5.5"]];
const CODEX_EFFORTS = [["low", "Low"], ["medium", "Medium (recommended)"], ["high", "High"], ["xhigh", "Extra high"], ["max", "Max"], ["ultra", "Ultra"]];
const CLAUDE_EFFORTS = [["", "Claude Code's default, which differs by model"], ["low", "Low"], ["medium", "Medium (recommended)"], ["high", "High"], ["xhigh", "Extra high"], ["max", "Max"]];

function renderChecks(target) {
  if (!S.checks) {
    target.replaceChildren(h("div", { class: "help" }, "Checking..."));
    return;
  }
  target.replaceChildren(
    ...S.checks.map((item) =>
      h(
        "div",
        { class: `check ${item.status}` },
        h("span", { class: "state" }, icon(STATUS_ICON[item.status])),
        h("b", {}, item.label),
        h("span", { class: "detail" }, item.detail),
      ),
    ),
  );
}

async function loadChecks(target) {
  S.checks = null;
  renderChecks(target);
  S.checks = await attempt(() => api("/api/checks"));
  if (S.checks && target.isConnected) renderChecks(target);
}

function hotkeyField(key, label, help) {
  let listening = false;
  const input = h("input", { type: "text", class: "hotkey-input", readonly: true, value: S.settings[key], "aria-label": label });
  const stop = () => {
    listening = false;
    input.classList.remove("listening");
    input.value = S.settings[key];
  };
  input.addEventListener("click", () => {
    listening = true;
    input.classList.add("listening");
    input.value = "Press the keys...";
  });
  input.addEventListener("blur", stop);
  input.addEventListener("keydown", (event) => {
    if (!listening) return;
    event.preventDefault();
    if (event.key === "Escape") {
      stop();
      return;
    }
    if (["Control", "Alt", "Shift", "Meta"].includes(event.key)) return;
    const parts = [];
    if (event.ctrlKey) parts.push("Ctrl");
    if (event.altKey) parts.push("Alt");
    if (event.shiftKey) parts.push("Shift");
    if (event.metaKey) parts.push("Win");
    const pressed = event.key.length === 1 ? event.key.toUpperCase() : event.key;
    if (!parts.length || !(/^[A-Z0-9]$/.test(pressed) || /^F\d{1,2}$/.test(pressed) || pressed === "Enter")) {
      $(`#${key}-error`).textContent = "Use Ctrl, Alt, Shift or Win, plus a letter, a number, an F key or Enter.";
      return;
    }
    $(`#${key}-error`).textContent = "";
    S.settings[key] = [...parts, pressed].join("+");
    stop();
    saveSetting({ [key]: S.settings[key] }, true);
    input.blur();
  });
  return h(
    "div",
    { class: "field" },
    h("label", { class: "field-label" }, label),
    input,
    h("div", { class: "help" }, help),
    h("div", { class: "help error", id: `${key}-error` }, S.snap?.hotkey_errors?.[key] || ""),
  );
}

function audioTestBox() {
  const box = h(
    "div",
    { class: "test-box" },
    h("div", { class: "row-actions" }, h("button", { id: "test-btn", onclick: toggleAudioTest }, S.testing ? "Stop test" : "Test audio"), h("span", { class: "help", id: "test-help" }, "Speak, then play any sound.")),
    h("div", { class: "meters", id: "test-meters", hidden: !S.testing }, meterRow("you", "You"), meterRow("them", "Them")),
  );
  return box;
}

async function toggleAudioTest() {
  const running = S.snap?.audio_test;
  const done = await attempt(() => api(`/api/audio-test/${running ? "stop" : "start"}`, { method: "POST" }));
  if (done) S.testing = !running;
  const meters = $("#test-meters");
  const button = $("#test-btn");
  if (meters) meters.hidden = !S.testing;
  if (button) button.textContent = S.testing ? "Stop test" : "Test audio";
}

function updateAudioTest() {
  const test = S.snap?.audio_test;
  if (S.view !== "settings") return;
  const meters = $("#test-meters");
  if (!meters) return;
  if (!test) {
    if (S.testing) {
      S.testing = false;
      meters.hidden = true;
      const button = $("#test-btn");
      if (button) button.textContent = "Test audio";
    }
    return;
  }
  setMeter($("#fill-you"), test.levels.mic, "mic");
  setMeter($("#fill-them"), test.levels.system, "system");
  const you = $("#state-you");
  const them = $("#state-them");
  you.textContent = test.heard.mic ? "Working" : "Speak now";
  you.className = `meter-state ${test.heard.mic ? "good" : ""}`;
  them.textContent = test.heard.system ? "Working" : "Play a sound";
  them.className = `meter-state ${test.heard.system ? "good" : ""}`;
  const micName = test.devices.mic[0] || "No microphone";
  $("#name-you").textContent = micName;
  $("#name-them").textContent = test.devices.system.length > 1 ? `All ${test.devices.system.length} outputs` : test.devices.system[0] || "None";
}

const SOUNDS = [["start", "Start"], ["pause", "Pause"], ["resume", "Talk again"], ["copied", "Copied"], ["finish", "Finish"], ["check", "Check it"], ["ready", "Ready"], ["problem", "Problem"]];

function hearSound(name) {
  if (S.snap?.recording?.active || S.snap?.prompt?.recording || S.snap?.model_test?.recording) {
    toast("Finish what's recording first, or this would end up in it.");
    return;
  }
  new Audio(`/static/sounds/${name}.wav`).play().catch(() => toast("That sound couldn't be played.", "error"));
}

function renderLook(settings) {
  return h(
    "section",
    { class: "card" },
    h("h2", {}, "Look"),
    selectField(
      "Theme",
      settings.theme,
      [["ink", "Black ink"], ["paper", "Rice paper, for daytime"], ["auto", "Follow Windows"]],
      (value) => {
        saveSetting({ theme: value }, true);
        Ink.setLook({ theme: value });
      },
    ),
    selectField(
      "On screen while it works",
      settings.on_screen,
      [["bar", "The full bar"], ["mark", "Low key: a tiny character"], ["tray", "Low key: only the tray icon"]],
      (value) => saveSetting({ on_screen: value }, true),
      "Low key shows only a tiny status character, or only the tray icon beside the clock: 停 paused, 寫 writing, the red 完 when it's ready. Nothing moves and routine pop-ups stay away, but problems still tell you, and so does the reminder that a call is being recorded. Click the tiny character for the full bar, or drag it somewhere else. You can switch from the tray icon's menu too. If you can't see that icon, drag it out from the ^ beside the clock.",
    ),
    h(
      "div",
      { class: "field" },
      toggleField("Let things move", "motion", "The wave and the brush writing. Turn this off for still screens, and the level meters still show what's being heard."),
      toggleField("Sound effects", "sounds", "Short sounds when you start, pause, talk again and finish, when something you copied comes in, when something is ready or needs a look, and when there's a problem. Nearly all of them play while nothing is being recorded, so they stay out of your recordings. The exceptions are a copy landing and a recording going wrong."),
      toggleField("The copy sound", "copy_sound", "The quick double tap when something you copy comes in while you dictate. It's the one sound that plays while you're being recorded, so your mic can pick it up. With this off, the bar still shows the copy."),
      h("div", { class: "field-label sound-label" }, "Hear them"),
      h("div", { class: "sound-row" }, SOUNDS.map(([name, label]) => h("button", { class: "ghost", onclick: () => hearSound(name) }, icon("play"), label))),
    ),
  );
}

async function renderSettings(main) {
  main.replaceChildren(h("div", { class: "settings-view" }, h("div", { class: "settings-inner" }, pageTitle("設", "Settings"))));
  const inner = $(".settings-inner");
  const [settings, devices, about, models] = await Promise.all([api("/api/settings"), api("/api/devices"), api("/api/about"), api("/api/engines")]).catch((error) => {
    toast(error.message, "error");
    return [null, null, null, null];
  });
  if (!settings || S.view !== "settings") return;
  S.settings = settings;
  S.devices = devices;
  S.engines = models.engines;

  const checksBox = h("div");
  const engine = settings.notes_engine;
  const engineFields = h("div", { id: "engine-fields" });
  const drawEngineFields = () => {
    engineFields.replaceChildren();
    if (S.settings.notes_engine === "codex") {
      const efforts = CODEX_EFFORTS.filter(([value]) => value !== "ultra" || S.settings.codex_model !== "gpt-6-luna");
      engineFields.append(
        selectField("Model", S.settings.codex_model, CODEX_MODELS, (value) => {
          const patch = { codex_model: value };
          if (value === "gpt-6-luna" && S.settings.codex_effort === "ultra") patch.codex_effort = "max";
          saveSetting(patch, true);
          drawEngineFields();
        }),
        selectField("Effort", S.settings.codex_effort, efforts, (value) => saveSetting({ codex_effort: value }, true), "More effort takes longer and uses more of your plan."),
      );
    } else if (S.settings.notes_engine === "claude") {
      engineFields.append(
        selectField("Model", S.settings.claude_model, CLAUDE_MODELS, (value) => saveSetting({ claude_model: value }, true)),
        selectField("Effort", S.settings.claude_effort, CLAUDE_EFFORTS, (value) => saveSetting({ claude_effort: value }, true), "More effort takes longer and uses more of your plan."),
      );
    }
  };
  drawEngineFields();

  const promptFields = h("div");
  const drawPromptFields = () => {
    const claude = S.settings.prompt_engine === "claude";
    promptFields.replaceChildren(
      selectField("Write prompts with", S.settings.prompt_engine, [["codex", "Codex, on your ChatGPT plan"], ["claude", "Claude Code, on your Claude plan"]], (value) => {
        saveSetting({ prompt_engine: value }, true);
        drawPromptFields();
      }),
      selectField("Prompt model", claude ? S.settings.prompt_claude_model : S.settings.prompt_codex_model, claude ? CLAUDE_MODELS : CODEX_MODELS, (value) => saveSetting({ [claude ? "prompt_claude_model" : "prompt_codex_model"]: value }, true)),
      selectField("Prompt effort", claude ? S.settings.prompt_claude_effort : S.settings.prompt_codex_effort, claude ? CLAUDE_EFFORTS : CODEX_EFFORTS, (value) => saveSetting({ [claude ? "prompt_claude_effort" : "prompt_codex_effort"]: value }, true), "Less effort comes back sooner. These can differ from the ones for notes, because a prompt is worth waiting less for."),
    );
  };
  drawPromptFields();

  const codeFields = h("div");
  const drawCodeFields = () => {
    const claude = S.settings.code_engine === "claude";
    codeFields.replaceChildren(
      selectField("Write code with", S.settings.code_engine, [["codex", "Codex, on your ChatGPT plan"], ["claude", "Claude Code, on your Claude plan"]], (value) => {
        saveSetting({ code_engine: value }, true);
        drawCodeFields();
      }),
      selectField("Code model", claude ? S.settings.code_claude_model : S.settings.code_codex_model, claude ? CODE_CLAUDE_MODELS : CODE_CODEX_MODELS, (value) => saveSetting({ [claude ? "code_claude_model" : "code_codex_model"]: value }, true)),
      selectField("Code effort", claude ? S.settings.code_claude_effort : S.settings.code_codex_effort, claude ? CLAUDE_EFFORTS : CODEX_EFFORTS, (value) => saveSetting({ [claude ? "code_claude_effort" : "code_codex_effort"]: value }, true), "A separate choice from the one for prompts, because here you may want a stronger model and be happy to wait a little longer."),
    );
  };
  drawCodeFields();

  const proofreadFields = h("div");
  const drawProofreadFields = () => {
    const claude = S.settings.proofread_engine === "claude";
    proofreadFields.replaceChildren(
      selectField("Proofread with", S.settings.proofread_engine, [["codex", "Codex, on your ChatGPT plan"], ["claude", "Claude Code, on your Claude plan"]], (value) => {
        saveSetting({ proofread_engine: value }, true);
        drawProofreadFields();
      }),
      selectField("Proofreading model", claude ? S.settings.proofread_claude_model : S.settings.proofread_codex_model, claude ? CLAUDE_MODELS : CODEX_MODELS, (value) => saveSetting({ [claude ? "proofread_claude_model" : "proofread_codex_model"]: value }, true)),
      selectField("Proofreading effort", claude ? S.settings.proofread_claude_effort : S.settings.proofread_codex_effort, claude ? CLAUDE_EFFORTS : CODEX_EFFORTS, (value) => saveSetting({ [claude ? "proofread_claude_effort" : "proofread_codex_effort"]: value }, true)),
    );
  };
  drawProofreadFields();

  inner.append(
    h("section", { class: "card" }, h("div", { class: "card-head" }, h("h2", {}, "Setup check"), h("button", { class: "ghost", onclick: () => loadChecks(checksBox) }, icon("refresh"), "Check again")), checksBox),
    renderLook(settings),
    h(
      "section",
      { class: "card" },
      h("h2", {}, "Audio"),
      selectField(
        "Your microphone",
        devices.selected_mic,
        [["default", `Windows default${devices.default_mic ? ` (${devices.default_mic})` : ""}`], ...devices.mics.map((name) => [name, name])],
        (value) => saveSetting({ mic_device: value }, true),
        devices.mic_missing ? "That microphone isn't connected right now. The default is used until it's back." : null,
      ),
      selectField(
        "Other people on the call",
        devices.selected_output,
        [["all", "All computer audio (recommended)"], ...devices.outputs.map((name) => [name, `Only ${name}`])],
        (value) => saveSetting({ output_device: value }, true),
        "All computer audio catches the call whichever speaker it plays on. Other sounds on this PC get recorded too, so keep them quiet.",
      ),
      audioTestBox(),
    ),
    h(
      "section",
      { class: "card" },
      h("h2", {}, "Speech to text"),
      selectField(
        "Speech model",
        S.engines.some((engine) => engine.id === settings.speech_engine) ? settings.speech_engine : "whisper",
        S.engines.map((engine) => [engine.id, engine.summary ? `${engine.label}: ${engine.summary}` : engine.label]),
        (value) => saveSetting({ speech_engine: value }, true),
        "To see which suits you, use Test models at the bottom of the sidebar. To compare them on a meeting you've recorded, use Try another speech model in the meeting's menu.",
      ),
      selectField(
        "Language",
        settings.language,
        [["en", "English"], ["auto", "Detect automatically"], ["zh", "Chinese"], ["mixed", "Chinese and English mixed"], ["es", "Spanish"], ["fr", "French"], ["de", "German"], ["ja", "Japanese"], ["ko", "Korean"], ["pt", "Portuguese"]],
        (value) => saveSetting({ language: value }, true),
      ),
      selectField(
        "Chinese characters",
        settings.chinese_script,
        [["traditional", "Traditional"], ["simplified", "As the model writes it, usually Simplified"]],
        (value) => saveSetting({ chinese_script: value }, true),
        "Speech models mostly write Simplified, so this converts what they write, one character at a time. The words themselves aren't changed. It applies to new transcripts.",
      ),
      selectField(
        "Run on",
        settings.compute,
        [["auto", "Graphics card when it's free (recommended)"], ["gpu", "Always the graphics card"], ["cpu", "Always the CPU"]],
        (value) => saveSetting({ compute: value }, true),
        "If a render is using the graphics card, the app switches to the CPU rather than wait.",
      ),
      textField("Names and terms", "terms", "One per line. People, clients and jargon the speech model might mishear. The notes use this list too.", 4, "Priya\nHCC risk adjustment\nURRT"),
      h(
        "div",
        { class: "field" },
        toggleField(
          "Tell apart the people on the other side",
          "speakers",
          models.has_diarizer || S.engines.some((engine) => engine.labels_speakers)
            ? "Labels them Speaker 1, Speaker 2 and so on, and you can type in their names. The labels are automatic and can be wrong."
            : "Needs a speech model or speaker model that can do this, and none is installed.",
        ),
      ),
    ),
    h(
      "section",
      { class: "card" },
      h("h2", {}, "Notes"),
      selectField(
        "Write notes with",
        engine,
        [["codex", "Codex, on your ChatGPT plan"], ["claude", "Claude Code, on your Claude plan"], ["none", "Don't write notes, just transcribe"]],
        (value) => {
          saveSetting({ notes_engine: value }, true);
          drawEngineFields();
        },
      ),
      engineFields,
      selectField(
        "Notes language",
        settings.notes_language,
        [["same", "Same as the call"], ["en", "English"], ["zh", "Chinese (Simplified)"], ["zh-hant", "Chinese (Traditional)"]],
        (value) => saveSetting({ notes_language: value }, true),
      ),
      textField("Extra instructions", "extra_instructions", "Anything you'd like the notes to always do.", 3, "Keep it brief. Always list numbers and dollar amounts."),
      selectField(
        "When a recording stops",
        settings.after_stop,
        [["notes", "Make notes right away (recommended)"], ["save", "Just save the audio, and I'll choose later"]],
        (value) => saveSetting({ after_stop: value }, true),
        "This is for the shortcut, the tray and the floating bar. The recording screen always offers both.",
      ),
    ),
    h(
      "section",
      { class: "card" },
      h("h2", {}, "Prompts"),
      promptFields,
      selectField(
        "Speech model for prompts",
        S.engines.some((item) => item.id === settings.prompt_speech_engine) ? settings.prompt_speech_engine : "whisper",
        S.engines.map((item) => [item.id, item.label]),
        (value) => saveSetting({ prompt_speech_engine: value }, true),
        "A separate choice from the one above, because here a quick answer matters most.",
      ),
      selectField("Write the prompt in", settings.prompt_language, [["en", "English"], ["same", "The language I spoke"], ["zh-hant", "Traditional Chinese"]], (value) => saveSetting({ prompt_language: value }, true)),
      h("div", { class: "field" }, toggleField("Use what I copy", "prompt_use_copied", "Text you copied in the 15 seconds before you started, and anything you copy until you finish, goes to the AI as reference only. Text a password manager marks as private is skipped."), checkFirstToggle(), addKnowledgeToggle(), includeCopiedToggle()),
      textField("How you like your prompts written", "prompt_extra", "Optional. The writer follows this every time.", 2, "Keep it short. Don't use bullet points."),
    ),
    h(
      "section",
      { class: "card" },
      h("h2", {}, "Code"),
      h("div", { class: "help" }, "Code is dictated like a prompt, with the same speech model and copying, and you get only the code on your clipboard. It never runs anything itself. It can still get things wrong, so look before you run anything that matters."),
      codeFields,
      textField("How you like your code written", "code_extra", "Optional. The writer follows this every time.", 2, "Python 3.13. Use pathlib. Always Python, never PowerShell, unless I say so."),
    ),
    h(
      "section",
      { class: "card" },
      h("h2", {}, "Proofread"),
      h("div", { class: "help" }, "Proofreads what you copy, and you get only the edited text on your clipboard. Its shortcut listens like a prompt, with the same speech model, so you can say how you want it edited, and finishing straight away is a plain proofread. The one without talking takes what you copied in the last 15 seconds, or waits a minute for you to copy something, so it never sends what was just sitting on the clipboard."),
      proofreadFields,
      textField("How you like your text edited", "proofread_extra", "Optional. The proofreader follows this every time.", 2, "American spelling. Keep it casual."),
    ),
    h(
      "section",
      { class: "card" },
      h("div", { class: "card-head" }, h("h2", {}, "Hints and prompts"), h("button", { onclick: () => setView("instructions") }, icon("edit"), "View and edit")),
      h("div", { class: "help" }, "Everything the speech models and the AI are told. You can change any of it, and the originals are kept so you can always go back."),
    ),
    h(
      "section",
      { class: "card" },
      h("h2", {}, "Shortcuts and startup"),
      hotkeyField("hotkey", "Start and stop a meeting", "Works from any app. Click, then press the keys you want."),
      hotkeyField("hotkey_solo", "Start a solo note, then pause and resume it", "Records only your mic, for talking through your own thoughts."),
      hotkeyField("hotkey_prompt", "Start a prompt, then pause and resume it", "Pause to read on or to think. Nothing is recorded while paused."),
      hotkeyField("hotkey_code", "Start code, then pause and resume it", "The same as a prompt, but you get the code itself."),
      hotkeyField("hotkey_proofread", "Proofread, saying how if you like", "Copy the text, press this, say how you want it edited or nothing at all, then press Finish. Pressing it again pauses, like a prompt. During a recording it proofreads without listening."),
      hotkeyField("hotkey_proofread_text", "Proofread without talking", "One press, no mic: it proofreads what you just copied."),
      hotkeyField("hotkey_finish", "Finish", "Ends whatever is going. A prompt then gets written, and a note gets made."),
      h(
        "div",
        { class: "field" },
        toggleField("Show a small recording bar on top of other windows", "show_mini"),
        toggleField("Keep running in the tray when I close the window", "close_to_tray"),
        toggleField("Start with Windows, hidden in the tray", "start_with_windows"),
      ),
    ),
    h(
      "section",
      { class: "card" },
      h("h2", {}, "Telling people"),
      textField("Recording notice", "notice_text", "What gets copied when you press Copy a notice on the recording screen.", 3),
    ),
    h(
      "section",
      { class: "card" },
      h("h2", {}, "Files"),
      h("div", { class: "path" }, about.meetings_dir),
      h("div", { class: "help", id: "storage-use" }),
      h(
        "div",
        { class: "row-actions" },
        h("button", { onclick: () => attempt(() => api("/api/open-folder", { method: "POST", body: { which: "meetings" } })) }, icon("folder"), "Open meetings folder"),
        h("button", { class: "ghost", onclick: () => attempt(() => api("/api/open-folder", { method: "POST", body: { which: "logs" } })) }, "Open logs"),
      ),
      selectField("Delete audio older than", String(S.oldAudioMonths), OLD_AUDIO, (value) => { S.oldAudioMonths = Number(value); }, "The transcripts and notes stay, and the audio goes to the Recycle Bin. Recordings that were never transcribed are kept, since the audio is all there is of them."),
      h("div", { class: "row-actions" }, h("button", { onclick: () => confirmOldAudio(S.oldAudioMonths) }, icon("trash"), "Delete audio…")),
    ),
    h(
      "section",
      { class: "card" },
      h("div", { class: "card-head" }, h("div", {}, h("h2", {}, "Quit Brushtalk"), h("div", { class: "help" }, `Stops the shortcut until you open it again. Anything being recorded is saved first. Version ${about.version}.`)), h("button", { onclick: () => attempt(() => api("/api/quit", { method: "POST" })) }, "Quit")),
    ),
  );
  loadChecks(checksBox);
  showStorage();
}

const OLD_AUDIO = [["1", "1 month"], ["3", "3 months"], ["6", "6 months"], ["12", "1 year"]];
S.oldAudioMonths = 6;

function sizeText(bytes) {
  if (!bytes) return "nothing";
  if (bytes >= 1e12) return `${(bytes / 1e12).toFixed(1)} TB`;
  return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${Math.max(1, Math.round(bytes / 1e6))} MB`;
}

// What the recordings take on the disk, worked out when Settings opens and again once old audio has gone.
async function showStorage() {
  const use = await attempt(() => api("/api/storage"));
  const slot = $("#storage-use");
  if (!use || !slot) return;
  const meetings = use.meetings.count === 1 ? "1 meeting" : `${use.meetings.count} meetings`;
  slot.textContent = `Recordings take ${sizeText(use.meetings.bytes)}, for ${meetings}. Prompts and test clips take ${sizeText(use.prompts.bytes + use.tests.bytes)}. ${use.drive} has ${sizeText(use.free)} free.`;
}

// It says what would go, and how much, before anything does.
async function confirmOldAudio(months) {
  const found = await attempt(() => api("/api/old-audio", { method: "POST", body: { months } }));
  if (!found) return;
  const since = new Date(`${found.before}T00:00`).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
  if (!found.count) {
    toast(`No meeting audio is from before ${since}.`);
    return;
  }
  const which = (count) => (count === 1 ? "1 meeting" : `${count} meetings`);
  dialog("Delete the old audio?", `The audio of ${which(found.count)} from before ${since}, ${sizeText(found.bytes)} in all, goes to the Recycle Bin. Their transcripts and notes stay, but you won't be able to play them back.`, [
    ["Cancel", ""],
    [
      "Delete audio",
      "danger",
      async () => {
        const done = await attempt(() => api("/api/old-audio", { method: "POST", body: { months, delete: true } }));
        if (!done) return;
        toast(`The audio of ${which(done.count)} is in the Recycle Bin.`);
        showStorage();
        refreshMeetings();
      },
    ],
  ]);
}

// ---------------------------------------------------------------- hints and prompts

const instructionRows = (text) => Math.max(2, text.split("\n").reduce((rows, line) => rows + Math.max(1, Math.ceil(line.length / 78)), 0));

// One line of saves per instruction for as long as the page is open, whichever row sends them. Leaving Settings and coming back makes new rows.
const instructionQueues = new Map();

function instructionSaves(key) {
  if (!instructionQueues.has(key)) instructionQueues.set(key, inOrder());
  return instructionQueues.get(key);
}

function renderInstructionItem(item) {
  const box = h("textarea", { rows: instructionRows(item.text), value: item.text, "aria-label": item.label });
  const tag = h("span", { class: "instruction-edited" }, "Edited");
  const extras = h("div");
  let timer = null;
  const show = (updated) => {
    item = updated;
    tag.hidden = !item.edited;
    extras.replaceChildren(
      ...[
        item.text.trim() === "" && h("div", { class: "help" }, "This is empty, so the model gets nothing here."),
        item.edited && h(
          "div",
          { class: "row-actions" },
          h("button", { class: "ghost", onclick: () => confirmRestoreInstruction(item, (restored) => { box.value = restored.text; box.rows = instructionRows(restored.text); show(restored); }) }, icon("history"), "Restore the original"),
        ),
        item.edited && h("details", { class: "instruction-original" }, h("summary", {}, "See the original"), h("div", { class: "instruction-text" }, item.original)),
      ].filter(Boolean),
    );
  };
  const save = async () => {
    clearTimeout(timer);
    timer = null;
    const text = box.value;
    const updated = await instructionSaves(item.key)(() => attempt(() => api(`/api/instructions/${item.key}`, { method: "PATCH", body: { text } })));
    if (updated) show(updated);
  };
  box.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(save, 500);
  });
  box.addEventListener("blur", () => {
    if (timer) save();
  });
  show(item);
  return h(
    "details",
    { class: "instruction" },
    h("summary", {}, h("span", {}, item.label), tag),
    item.help && h("div", { class: "help" }, item.help),
    box,
    extras,
  );
}

function confirmRestoreInstruction(item, done) {
  dialog("Restore the original?", `Your edit to "${item.label}" will be gone, and the model gets the original again.`, [
    ["Keep my edit", ""],
    [
      "Restore",
      "primary",
      async () => {
        const restored = await instructionSaves(item.key)(() => attempt(() => api(`/api/instructions/${item.key}/restore`, { method: "POST" })));
        if (restored) done(restored);
      },
    ],
  ]);
}

async function showInstructionPreview(which, label) {
  const data = await attempt(() => api(`/api/instructions-preview/${which}`));
  if (data) dialog(label, "", [["Close", ""]], h("div", { class: "instruction-text instruction-preview" }, data.text));
}

async function renderInstructions(main) {
  main.replaceChildren(
    h(
      "div",
      { class: "settings-view" },
      h(
        "div",
        { class: "settings-inner" },
        h("button", { class: "ghost instruction-back", onclick: () => setView("settings") }, icon("back"), "Settings"),
        pageTitle("示", "Hints and prompts"),
        h("p", { class: "help instruction-intro" }, "This is everything the speech models and the AI are told. Open a line to read or change it. Changes save as you type and apply from the next job. The originals are never touched, so Restore the original always brings them back."),
      ),
    ),
  );
  const data = await attempt(() => api("/api/instructions"));
  if (!data || S.view !== "instructions") return;
  $(".settings-inner").append(
    ...data.groups.map((group) =>
      h(
        "section",
        { class: "card" },
        h("h2", {}, group.title),
        h("div", { class: "help" }, group.help),
        group.previews.length > 0 && h("div", { class: "row-actions instruction-previews" }, group.previews.map(([which, label]) => h("button", { class: "ghost", onclick: () => showInstructionPreview(which, label) }, label))),
        group.items.length > 0 && h("div", { class: "instruction-list" }, group.items.map(renderInstructionItem)),
      ),
    ),
  );
}

// ---------------------------------------------------------------- live state

function onSnapshot(snap) {
  const previous = S.snap;
  S.snap = snap;
  const recording = snap.recording.active;
  const wasRecording = previous?.recording?.active || false;
  const first = !previous;
  // Only when it changes on the app's side, so an old update can't undo a theme you've just picked.
  if (snap.look && JSON.stringify(snap.look) !== JSON.stringify(previous?.look)) Ink.setLook(snap.look);

  const cancelledChanged = (snap.prompt.stage === "cancelled") !== (previous?.prompt?.stage === "cancelled");
  if (first || recording !== wasRecording || Boolean(snap.prompt.recording) !== Boolean(previous?.prompt?.recording) || cancelledChanged) {
    S.meter = { mic: 0, system: 0 };
    renderRecordSlot();
  }
  const shortcutsChanged = MODES.some((mode) => previous?.[mode.key] !== snap[mode.key]) || JSON.stringify(previous?.hotkey_errors) !== JSON.stringify(snap.hotkey_errors);
  if (first && recording) setView("recording");
  else if (recording && !wasRecording) setView("recording");
  else if (!recording && wasRecording) {
    const id = previous.recording.meeting_id;
    if (snap.deleted_recording === id) {
      setView("home");
      refreshMeetings();
      toast("Deleting this recording.");
    } else {
      refreshMeetings().then(() => openMeeting(id));
    }
  } else if (S.view === "home" && shortcutsChanged) {
    renderMain();
  }
  if (shortcutsChanged) renderRecordSlot();
  // Only once it really is in the Recycle Bin.
  if (previous && snap.recycled_recording && snap.recycled_recording !== previous.recycled_recording) toast("Recording deleted. It's in the Recycle Bin.");
  // A failure that couldn't be saved with its meeting, most likely because the disk is what's failing.
  for (const [id, text] of Object.entries(snap.unsaved_failures || {})) {
    if (!previous?.unsaved_failures?.[id]) toast(text, "error");
  }

  const clip = snap.model_test.recording;
  const hadClip = previous?.model_test?.recording;
  if (clip && !hadClip) {
    S.meter = { mic: 0, system: 0 };
    setView("tests");
  } else if (!clip && hadClip) {
    S.meter = { mic: 0, system: 0 };
    const kept = !recording && !S.discardingTest;
    S.discardingTest = false;
    if (S.view === "tests") {
      S.testId = kept ? hadClip.id : null;
      S.test = null;
      renderMain();
    }
  } else if (S.view === "tests" && S.testId && previous && snap.model_test.version !== previous.model_test.version) {
    loadTest();
  }

  const listening = snap.prompt.recording;
  const wasListening = previous?.prompt?.recording;
  if (listening && !wasListening) {
    S.meter = { mic: 0, system: 0 };
    if (S.view === "prompts") {
      S.promptId = null;
      S.prompt = null;
      renderMain();
    }
  } else if (!listening && wasListening) {
    S.meter = { mic: 0, system: 0 };
    const discarded = S.discardingPrompt || !snap.prompt.stage;
    S.discardingPrompt = false;
    if (S.view === "prompts") {
      S.promptId = discarded ? null : snap.prompt.id;
      S.prompt = null;
      renderMain();
    }
  } else if (S.view === "prompts" && previous && snap.prompt.version !== previous.prompt.version) {
    const stoppedWaiting = previous.prompt.stage === "copy";
    // You're looking at this page and the copy it was waiting for has come, so it shows what's going.
    if (stoppedWaiting && snap.prompt.id) openPrompt(snap.prompt.id);
    else if (S.promptId && !snap.prompt.stage && !stoppedWaiting) toAllPrompts();
    else if (S.promptId) loadPrompt();
    // The listening screen updates itself, and drawing it again would empty the box you're typing in.
    else if (!listening) renderMain();
  } else if (S.view === "home" && previous && !listening && snap.prompt.version !== previous.prompt.version) {
    renderMain();
  }
  if (previous && snap.prompt.shows !== previous.prompt.shows && snap.prompt.id) openPrompt(snap.prompt.id);

  if (snap.version !== S.version) {
    S.version = snap.version;
    refreshMeetings().then(() => {
      if (S.view === "home") renderMain();
    });
    if (S.view === "meeting") loadDetail();
  }
  updateRecording();
  updateAudioTest();
  updateTestClip();
  updateTestProgress();
  updatePromptListening();
  updateListProgress();
  if (S.view === "meeting") updateProgress();
}

function connect() {
  const socket = new WebSocket(`ws://${location.host}/ws?token=${encodeURIComponent(token)}`);
  socket.onmessage = (event) => {
    $("#lost-touch")?.remove();
    onSnapshot(JSON.parse(event.data));
  };
  socket.onclose = () => {
    if (!$("#lost-touch")) document.body.append(h("div", { class: "banner error", id: "lost-touch" }, icon("alert"), h("span", {}, "Lost touch with the app, so what you see here may be out of date. Trying to reconnect.")));
    setTimeout(connect, 1000);
  };
}

// ---------------------------------------------------------------- start

function bindGlobal() {
  $("#search-icon").append(icon("search"));
  const settingsButton = $("#settings-btn");
  settingsButton.append(icon("gear"), "Settings");
  settingsButton.addEventListener("click", () => setView(S.view === "settings" ? "home" : "settings"));
  const homeButton = $("#home-btn");
  homeButton.append(icon("grid"), "Overview");
  homeButton.addEventListener("click", () => setView("home"));
  const promptsButton = $("#prompts-btn");
  promptsButton.append(icon("prompt"), "Prompts, code, edits");
  promptsButton.addEventListener("click", () => {
    if (S.view === "prompts" && S.promptId) toAllPrompts();
    else if (S.view !== "prompts") setView("prompts");
  });
  const testsButton = $("#tests-btn");
  testsButton.append(icon("compare"), "Test models");
  testsButton.addEventListener("click", () => {
    if (S.view === "tests" && S.testId) toAllTests();
    else if (S.view !== "tests") setView("tests");
  });
  markNav();

  let searchTimer;
  $("#search").addEventListener("input", (event) => {
    S.query = event.target.value.trim();
    clearTimeout(searchTimer);
    searchTimer = setTimeout(refreshMeetings, 180);
  });

  document.addEventListener("click", () => {
    if (S.menuOpen) {
      S.menuOpen = false;
      if (S.view === "meeting" && S.detail) renderMeeting($("#main"));
    }
  });

  document.addEventListener("keydown", (event) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName);
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "f") {
      event.preventDefault();
      $("#search").focus();
      $("#search").select();
    } else if (event.key === "Escape") {
      $("#modal-root").replaceChildren();
    } else if (event.code === "Space" && !typing && document.activeElement?.tagName !== "BUTTON" && Player.audio) {
      event.preventDefault();
      Player.toggle();
    }
  });
}

async function start() {
  bindGlobal();
  S.settings = await attempt(() => api("/api/settings"));
  if (S.settings) Ink.setLook({ theme: S.settings.theme, motion: S.settings.motion });
  S.engines = (await attempt(() => api("/api/engines")))?.engines || [];
  await refreshMeetings();
  renderRecordSlot();
  renderMain();
  connect();
  if (S.settings && !S.settings.onboarded) welcome();
}

start();
