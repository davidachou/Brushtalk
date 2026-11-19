"use strict";

// The edit card. The app says what you copied and what it heard. The choices stay on this page until you press Edit, and start afresh each time
// the card opens.
const token = new URLSearchParams(location.search).get("token") || "";
const $ = (id) => document.getElementById(id);
const ICONS = {
  close: '<path d="M18 6 6 18M6 6l12 12"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  stop: '<rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor" stroke="none"/>',
};
const JOBS = [
  { key: "polish", name: "Polish", ch: "潤", about: "Fixes mistakes and awkward wording, in any style you pick" },
  { key: "fill", name: "Fill in", ch: "補", about: "Writes only what each [[blank]] asks for, and leaves the rest as it is" },
  { key: "format", name: "Format", ch: "排", about: "Makes a table, a list, steps or an email layout" },
  { key: "translate", name: "Translate", ch: "譯", about: "Into English or Traditional Chinese, in any style you pick" },
];
// What each choice says, as the AI is told it in Settings, under Hints and prompts.
const ROWS = {
  formality: ["Formality", [["", "As written"], ["casual", "Casual", "Like to a colleague you know well"], ["neutral", "Neutral", "Plain and polite, neither chatty nor stiff"], ["professional", "Professional", "Fit for a client or a manager"]]],
  tone: ["Tone", [["", "As written"], ["warm", "Warm", "Friendly"], ["tactful", "Tactful", "Softens anything blunt"], ["playful", "Playful", "A light touch of humor"], ["wry", "Wry", "Dry humor, not mean"], ["sarcastic", "Sarcastic", "A biting, ironic edge"], ["firm", "Firm", "Clear about what's needed, without being rude"], ["demanding", "Demanding", "Insists, with no softening"]]],
  length: ["Length", [["", "As written"], ["shorter", "Shorter", "Every point, fewer words"], ["longer", "Longer", "Adds context where it helps, inventing nothing"]]],
  into: ["Into", [["table", "Table"], ["list", "List"], ["steps", "Steps"], ["email", "Email layout"]]],
  dest: ["For", [["email", "Email, Teams, Word", "Pastes as a real table or list"], ["slack", "Slack", "Lined-up columns in a code box, since Slack can't show a table"], ["plain", "Plain text", "Lined-up columns"]]],
  lang: ["Into", [["english", "English"], ["chinese", "繁體中文"]]],
};
const OPTIONS = { polish: ["formality", "tone", "length"], fill: [], format: ["into", "dest"], translate: ["lang", "formality", "tone", "length"] };
const START = { job: "polish", formality: "", tone: "", length: "", into: "table", dest: "email", lang: "english" };
const FLASH_FOR = 5000;
const ASKED_TALLEST = 96;

let latest = null; // the card as the app last described it, or null while it's closed
let opens = null; // which opening of the card this page is showing
let pick = { ...START };
let heardShown = 0; // how many things you said are already in the box
let drawn = ""; // what the card was last drawn from
let sending = false;
let flashed = null;
let level = null;
let reported = 0;

function svg(name) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  node.setAttribute("viewBox", "0 0 24 24");
  node.innerHTML = ICONS[name];
  return node;
}

function el(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (value === undefined || value === false || value === null) continue;
    if (name.startsWith("on")) node.addEventListener(name.slice(2), value);
    else if (name === "class") node.className = value;
    else node.setAttribute(name, value === true ? "" : value);
  }
  node.append(...children.flat().filter((child) => child !== null && child !== undefined && child !== false));
  return node;
}

// Says whether it worked. If it didn't, the card says so, since a button that seems to do nothing is worse than an error.
async function post(body) {
  try {
    const response = await fetch("/api/picker", { method: "POST", headers: { "X-Token": token, "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (response.ok) return (await response.json().catch(() => ({}))) || {};
    const data = await response.json().catch(() => ({}));
    flash(data.detail || "That didn't work. Try again.");
  } catch {
    flash("That didn't reach the app. Try again.");
  }
  return null;
}

function flash(text) {
  flashed = { text, until: Date.now() + FLASH_FOR };
  draw(true);
  setTimeout(() => draw(true), FLASH_FOR + 50);
}

const many = (count) => `${count} ${count === 1 ? "blank" : "blanks"}`;
const and = (items) => (items.length > 1 ? `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}` : items[0]);
const label = (row, value) => ROWS[row][1].find(([key]) => key === value)?.[1] || value;

// What will happen, in a sentence, so you know before you press Edit.
function describe() {
  const blanks = latest?.blank_count || 0;
  const own = $("asked").value.trim() ? ", plus what you asked" : "";
  if (pick.job === "fill") return blanks ? `Fill in your ${many(blanks)} and leave the rest as it is${own}.` : "There are no [[blanks]] in what you copied, so there's nothing to fill in.";
  const style = OPTIONS[pick.job].includes("tone") ? [pick.formality, pick.tone, pick.length].filter(Boolean).map((value) => value.toLowerCase()) : [];
  const parts = [];
  if (pick.job === "polish") parts.push("fix mistakes and awkward wording");
  else if (pick.job === "format") parts.push(pick.into === "email" ? "lay it out as an email" : `make ${{ table: "a table", list: "a list", steps: "numbered steps" }[pick.into]} for ${{ email: "email, Teams or Word", slack: "Slack", plain: "plain text" }[pick.dest]}`);
  else parts.push(`translate it into ${pick.lang === "english" ? "English" : "Traditional Chinese"}`);
  if (style.length) parts.push(`make it ${and(style)}`);
  if (blanks) parts.push(`fill in your ${many(blanks)}`);
  const sentence = parts.length === 1 ? parts[0] : `${parts.slice(0, -1).join(", ")}, and ${parts[parts.length - 1]}`;
  return `${sentence[0].toUpperCase()}${sentence.slice(1)}${own}.`;
}

function tiles() {
  if (!$("tiles").childElementCount) {
    JOBS.forEach((job, index) => {
      $("tiles").append(
        el("button", { class: "tile", role: "radio", "data-job": job.key, title: job.about, onclick: () => choose(job.key) }, Ink.glyph(job.ch, "still", { size: 38 }), el("span", { class: "name" }, el("kbd", {}, String(index + 1)), job.name)),
      );
    });
  }
  for (const tile of $("tiles").children) {
    const on = tile.dataset.job === pick.job;
    tile.classList.toggle("on", on);
    tile.setAttribute("aria-checked", on ? "true" : "false");
    // The one you pick is written out again in red.
    Ink.setGlyph(tile.querySelector("canvas"), JOBS.find((job) => job.key === tile.dataset.job).ch, on ? "live" : "still", { write: on, seconds: 0.5 });
  }
}

function chips(row) {
  const [name, values] = ROWS[row];
  return el(
    "div",
    { class: "row" },
    el("span", { class: "label" }, name),
    el(
      "div",
      {},
      el("div", { class: "chips" }, values.map(([value, text, about]) => el("button", { class: `chip${value ? "" : " as-is"}${pick[row] === value ? " on" : ""}`, title: about, onclick: () => setChoice(row, value) }, text))),
      row === "dest" && el("div", { class: "note" }, latest?.app ? `Guessed from where you were: ${latest.app}.` : "Guessed from where you were."),
    ),
  );
}

function options() {
  const rows = OPTIONS[pick.job].filter((row) => row !== "dest" || pick.into !== "email");
  $("options").replaceChildren(...rows.map(chips));
}

function blanksLine() {
  const count = latest?.blank_count || 0;
  $("blanks").hidden = !count && pick.job !== "fill";
  const text = $("blanks-text");
  text.classList.toggle("none", !count);
  if (pick.job === "fill") text.textContent = count ? `${many(count)} in [[ ]] to fill: ${latest.blanks.map((blank) => `“${blank}”`).join(", ")}${count > latest.blanks.length ? "…" : ""}` : "There are no [[blanks]] in what you copied.";
  else text.textContent = `Also fills in your ${many(count)} in [[ ]].`;
  text.title = latest?.blanks?.join("\n") || "";
}

function mic() {
  const listening = Boolean(latest?.listening);
  const hearing = Boolean(latest?.hearing);
  const why = latest?.mic;
  $("mic").replaceChildren(svg(listening ? "stop" : "mic"));
  $("mic").classList.toggle("live", listening);
  $("mic").disabled = Boolean(why && !listening) || hearing;
  $("mic").title = why || (listening ? "Done talking" : `Say it (or press ${latest?.hotkey || "the shortcut"} again)`);
  $("asked").placeholder = why ? "Anything else? Type how you want it" : "Anything else? Type how you want it, or press the mic and say it";
  $("listening").hidden = !listening && !hearing;
  $("level").hidden = !listening;
  $("listening-text").textContent = hearing ? "Hearing what you said…" : `Listening. Press the mic or ${latest?.hotkey || "the shortcut"} again when you're done.`;
  if (listening && !level) level = new Ink.Bars($("level"));
  level?.levels(latest?.level || 0, 0, !listening);
  $("go").disabled = sending || listening || hearing;
}

function message() {
  const local = flashed && Date.now() < flashed.until ? flashed.text : "";
  const text = local || latest?.message || "";
  $("message").hidden = !text;
  $("message").textContent = text;
}

// Drawn again only when something it shows has changed, so a chip doesn't flicker under your mouse as updates arrive.
function draw(force = false) {
  if (!latest) return;
  const key = JSON.stringify([pick, latest.opens, latest.words, latest.chars, latest.blank_count, latest.app, latest.mic, latest.listening, latest.hearing, latest.message, latest.heard.length, sending, flashed?.until]);
  if (force || key !== drawn) {
    drawn = key;
    $("copied").textContent = `“${latest.words}${latest.chars > latest.words.length ? "…" : ""}” · ${latest.chars.toLocaleString()} ${latest.chars === 1 ? "character" : "characters"}`;
    $("copied").title = latest.words;
    tiles();
    $("about").textContent = `${JOBS.find((job) => job.key === pick.job).about}.`;
    options();
    blanksLine();
    message();
  }
  mic();
  $("summary").textContent = describe();
}

function choose(job) {
  pick.job = job;
  draw();
}

function setChoice(row, value) {
  pick[row] = value;
  draw();
}

function fitAsked() {
  const box = $("asked");
  box.style.height = "auto";
  box.style.height = `${Math.min(box.scrollHeight + 2, ASKED_TALLEST)}px`;
}

// Its window is only as tall as the card, so the app is told whenever that changes.
function report() {
  const height = Math.ceil($("card").getBoundingClientRect().height);
  if (latest && Math.abs(height - reported) > 1) {
    reported = height;
    post({ action: "size", height });
  }
}

async function go() {
  if (!latest || sending || latest.listening || latest.hearing) return;
  if (pick.job === "fill" && !latest.blank_count) {
    flash("There are no [[blanks]] in what you copied, so there's nothing to fill in.");
    return;
  }
  sending = true;
  draw();
  const choices = { job: pick.job };
  for (const row of OPTIONS[pick.job]) choices[row] = pick[row];
  await post({ action: "edit", choices, asked: $("asked").value });
  sending = false;
  draw();
}

function close() {
  post({ action: "close" });
}

function opened(next) {
  opens = next.opens;
  pick = { ...START, dest: next.dest || "email" };
  heardShown = 0;
  sending = false;
  flashed = null;
  $("asked").value = "";
  fitAsked();
  // Written out afresh each time, to show it's a new card.
  delete $("seal").dataset.ch;
  Ink.setGlyph($("seal"), "改", "live", { seconds: 0.6 });
  document.activeElement?.blur?.();
  $("card").focus();
}

function update(snapshot) {
  if (snapshot.look) Ink.setLook(snapshot.look);
  const next = snapshot.picker;
  if (!next) {
    latest = null;
    return;
  }
  if (next.opens !== opens) opened(next);
  latest = next;
  // What you said goes at the end of the box, after anything you typed, for you to fix before you press Edit.
  for (; heardShown < next.heard.length; heardShown++) {
    const box = $("asked");
    box.value = box.value.trim() ? `${box.value.trimEnd()} ${next.heard[heardShown]}` : next.heard[heardShown];
    fitAsked();
  }
  draw();
}

function connect() {
  const socket = new WebSocket(`ws://${location.host}/ws?token=${encodeURIComponent(token)}`);
  socket.onmessage = (event) => update(JSON.parse(event.data));
  socket.onclose = () => setTimeout(connect, 1000);
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    event.preventDefault();
    close();
    return;
  }
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    // Enter on the close button or the mic does what they do. Anywhere else it's Edit.
    if (document.activeElement === $("close") || document.activeElement === $("mic")) return;
    event.preventDefault();
    go();
    return;
  }
  const typing = document.activeElement === $("asked");
  if (typing || event.ctrlKey || event.altKey || event.metaKey || event.key.length !== 1) return;
  if (event.key >= "1" && event.key <= String(JOBS.length)) {
    event.preventDefault();
    choose(JOBS[Number(event.key) - 1].key);
    return;
  }
  // Start typing anywhere and it goes into the box.
  $("asked").focus();
});

// A clicked choice doesn't keep the keyboard, so the number keys and Enter go on working.
document.addEventListener("click", (event) => {
  if (event.target.closest(".tile, .chip")) $("card").focus();
});
$("close").append(svg("close"));
$("close").addEventListener("click", close);
$("mic").addEventListener("click", () => post({ action: "listen" }));
$("go").addEventListener("click", go);
$("asked").addEventListener("input", () => {
  fitAsked();
  $("summary").textContent = describe();
});
Ink.setGlyph($("seal"), "改", "live", { write: false });
new ResizeObserver(report).observe($("card"));
connect();
