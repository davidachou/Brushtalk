"use strict";

const token = new URLSearchParams(location.search).get("token") || "";
const $ = (id) => document.getElementById(id);
const ICONS = {
  pause: '<path d="M9 5v14M15 5v14"/>',
  play: '<path d="M7 4.5v15l12-7.5z" fill="currentColor" stroke="none"/>',
  hide: '<path d="M6 12h12"/>',
  close: '<path d="M18 6 6 18M6 6l12 12"/>',
};
const SEAL_SIZE = 46;
const ARMED_FOR = 3000;
const FLASH_FOR = 5000;
const COPY_NOTICE_FOR = 6000;
const TOOK_BACK_FOR = 3000;
const UNDO_GAP = 700;
const WASH_FOR = 1600;
const DOUBLE_CLICK = 500;
const CLOSE_UP_CHECK = 2000;
const DRAGGED = 3;
const WINDOW_CATCHES_UP = 150;
let latest = null;
let stale = false;
let flashed = null;
let paused = null;
let promptId = null;
let promptStage = "";
let wave = null;
let promptWave = null;
let sealed = false;
let armed = null;
let alerts = null;
let copyFlashes = null;
let copyNotice = null;
let tookBack = null;
let undoReady = true;
let pressedAt = null;
let openedUpAt = 0;
let closeUpWatch = null;

function svg(name) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  node.setAttribute("viewBox", "0 0 24 24");
  node.innerHTML = ICONS[name];
  return node;
}

// Says whether it worked. If it didn't, the bar says so: a button that seems to do nothing is worse than an error.
async function post(path, body) {
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: { "X-Token": token, "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (response.ok) return true;
    const data = await response.json().catch(() => ({}));
    flash(data.detail || "That didn't work. Try again.");
  } catch {
    flash("That didn't reach the app. Try again.");
  }
  return false;
}

function flash(text) {
  flashed = { text, until: Date.now() + FLASH_FOR };
  redraw();
  setTimeout(redraw, FLASH_FOR + 50);
}

function trouble(health) {
  if (stale) return { kind: "error", text: "Lost touch with the app, so what you see here may be out of date. Trying to reconnect.", short: "Lost touch with the app" };
  if (flashed && Date.now() < flashed.until) return { kind: "error", text: flashed.text, short: flashed.text };
  return health || null;
}

function showHealth(shown) {
  $("meters").hidden = Boolean(shown);
  $("health").hidden = !shown;
  $("bar").classList.toggle("trouble", shown?.kind === "error");
  if (shown) {
    if ($("health").textContent !== shown.short) $("health").textContent = shown.short;
    $("health").title = shown.text;
    $("health").className = shown.kind;
  }
}

function redraw() {
  if (latest) {
    showSize(latest.bar);
    update(latest.recording);
    updatePrompt(latest.prompt, latest.recording);
    // A tiny character can't say much, so holding the mouse on it does.
    document.body.title = document.body.classList.contains("tiny") ? (latest.recording.active ? `Recording ${$("time").textContent}` : $("p-title").textContent) : "";
  }
}

function showSize(bar) {
  document.body.classList.toggle("tiny", bar?.on_screen === "mark" && !bar.opened_up);
  if (bar?.opened_up && !closeUpWatch) {
    openedUpAt = Date.now();
    // A regular look rather than waiting to be told the mouse left, because the window changing size under the mouse can hide that from the page.
    closeUpWatch = setInterval(() => {
      if (!document.documentElement.matches(":hover")) post("/api/mini", { action: "close-up" });
    }, CLOSE_UP_CHECK);
  } else if (!bar?.opened_up && closeUpWatch) {
    clearInterval(closeUpWatch);
    closeUpWatch = null;
  }
}

// In low key, a click anywhere on the tiny character brings out the full bar. Dragging it just moves it. The moment after, a click is ignored,
// so a double click can't land on a button that has just come up under the mouse, such as the one that throws a prompt away.
function clickedWhileTiny(event) {
  const tiny = document.body.classList.contains("tiny");
  if (!tiny && Date.now() - openedUpAt > DOUBLE_CLICK) return;
  event.stopPropagation();
  event.preventDefault();
  if (tiny && !wasDragged(event)) post("/api/mini", { action: "open-up" });
}

function wasDragged(event) {
  return Boolean(pressedAt) && Math.hypot(event.screenX - pressedAt[0], event.screenY - pressedAt[1]) > DRAGGED;
}

// The app keeps where you leave it, and goes by this, so that only your own drags count. It reads the window a moment later, once it has caught up with the mouse.
function letGo(event) {
  if (wasDragged(event)) setTimeout(() => post("/api/mini", { action: "dragged" }), WINDOW_CATCHES_UP);
}

function clock(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = String(total % 60).padStart(2, "0");
  return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${secs}` : `${String(minutes).padStart(2, "0")}:${secs}`;
}

function disarm() {
  clearTimeout(armed);
  armed = null;
  $("cancel").classList.remove("armed");
  $("cancel").replaceChildren(svg("close"));
}

// Two clicks: the first asks, and if nothing follows, it goes back to how it was.
function cancelClicked() {
  if (armed) {
    disarm();
    stopRecording({ after: "delete" });
    return;
  }
  $("cancel").classList.add("armed");
  $("cancel").textContent = "Delete?";
  armed = setTimeout(disarm, ARMED_FOR);
}

async function stopRecording(body) {
  $("stop").disabled = true;
  if (!(await post("/api/recording/stop", body))) $("stop").disabled = false;
}

function update(recording) {
  if (!recording.active) {
    $("stop").disabled = false;
    if (armed) disarm();
    wave?.levels(0, 0, true);
    return;
  }
  Ink.clock($("time"), clock(recording.elapsed));
  const solo = recording.mode === "solo";
  $("them-row").hidden = solo;
  if (!wave) wave = new Ink.Bars($("wave"));
  wave.setLanes(solo ? "mic" : "both");
  wave.levels(recording.levels.mic, recording.levels.system, recording.paused || stale);
  const shown = trouble(recording.health);
  showHealth(shown);
  const [ch, kind] = shown?.kind === "error" ? ["錯", "problem"] : recording.paused ? ["停", "still"] : [solo ? "記" : "錄", "live"];
  Ink.setGlyph($("glyph"), ch, kind, { seconds: 0.6 });
  if (paused !== recording.paused) {
    paused = recording.paused;
    $("pause").replaceChildren(svg(paused ? "play" : "pause"));
    $("pause").title = paused ? "Resume" : "Pause";
    $("pause").setAttribute("aria-label", $("pause").title);
  }
}

function setText(id, text) {
  if ($(id).textContent !== text) {
    $(id).textContent = text;
    $(id).title = text;
  }
}

// The status character: 聽 listening, 停 paused, 寫 writing, 抄 a copy just landed or one being waited for, 校 waiting for you to check it, 錯 a problem. Ready is the red 完 seal, stamped once.
function showMark(stage, isPaused, working, problem, copying) {
  const mark = $("p-mark");
  if (stage === "ready" && !problem) {
    if (!sealed) {
      sealed = true;
      mark.replaceChildren(Ink.seal({ size: SEAL_SIZE - 4, stamp: true }));
    }
    return;
  }
  if (sealed || !$("p-glyph")) {
    sealed = false;
    const canvas = document.createElement("canvas");
    canvas.id = "p-glyph";
    canvas.className = "glyph";
    canvas.width = canvas.height = 192;
    mark.replaceChildren(canvas);
    sizeGlyphs();
  }
  const [ch, kind] = problem ? ["錯", "problem"] : copying ? ["抄", "copied"] : isPaused ? ["停", "still"] : stage === "listening" ? ["聽", "live"] : working ? ["寫", "live"] : stage === "check" ? ["校", "still"] : stage === "copy" ? ["抄", "still"] : stage === "empty" ? ["無", "still"] : stage === "cancelled" ? ["停", "still"] : ["錯", "problem"];
  Ink.setGlyph($("p-glyph"), ch, kind, { seconds: copying ? 0.4 : 0.6 });
}

// The class comes off again afterwards, or the animation would run once more whenever this bar next shows.
function playOnce(element, name) {
  element.classList.remove(name);
  void element.offsetWidth;
  element.classList.add(name);
  setTimeout(() => element.classList.remove(name), WASH_FOR);
}

// Only a rise counts, so connecting again partway through a recording doesn't announce an old problem.
function noticeAlerts(count) {
  if (alerts !== null && count > alerts) {
    playOnce($("bar"), "wash-alarm");
    playOnce($("prompt-bar"), "wash-alarm");
  }
  alerts = count;
}

// Hard to miss, because it's on its way to an AI and it's easy to copy something without meaning to. The app plays a sound for it too.
function copyLanded(copy) {
  copyNotice = { key: copy?.key, until: Date.now() + COPY_NOTICE_FOR };
  tookBack = null;
  // One too long to add washes red, because what you meant to send isn't going.
  playOnce($("prompt-bar"), copy?.added === false ? "wash-alarm" : "wash");
  playOnce($("p-mark"), "copy-pop");
  // Written afresh, even when the last copy's character is still up.
  if ($("p-glyph")) delete $("p-glyph").dataset.ch;
  setTimeout(redraw, COPY_NOTICE_FOR + 50);
}

async function undoCopy() {
  // Just after a Cancel, the same button brings the dictation back.
  if (latest?.prompt.stage === "cancelled") {
    post("/api/prompts/undo-cancel");
    return;
  }
  const copy = latest?.prompt.latest_copy;
  if (!copy || !undoReady) return;
  // So a double click takes back one passage, not two.
  undoReady = false;
  setTimeout(() => { undoReady = true; }, UNDO_GAP);
  if (await post("/api/prompts/undo-copy", { id: promptId, key: copy.key })) {
    copyNotice = null;
    tookBack = { words: copy.words, until: Date.now() + TOOK_BACK_FOR };
    setTimeout(redraw, TOOK_BACK_FOR + 50);
    redraw();
  }
}

function sizeGlyphs() {
  for (const id of ["glyph", "p-glyph"]) {
    if ($(id)) {
      $(id).style.width = `${SEAL_SIZE}px`;
      $(id).style.height = `${SEAL_SIZE}px`;
    }
  }
}

function updatePrompt(prompt, recording) {
  // Only a rise counts, so connecting again partway through a prompt doesn't announce an old copy.
  if (copyFlashes !== null && prompt.copy_flashes > copyFlashes) copyLanded(prompt.latest_copy);
  copyFlashes = prompt.copy_flashes;
  const showing = !recording.active && Boolean(prompt.stage);
  $("bar").hidden = showing;
  $("prompt-bar").hidden = !showing;
  if (!showing) {
    promptStage = "";
    promptWave?.levels(0, 0, true);
    return;
  }
  promptId = prompt.id;
  const code = prompt.kind === "code";
  const proofread = prompt.kind === "proofread";
  const waitingForCopy = prompt.stage === "copy";
  const listening = prompt.stage === "listening";
  const live = listening ? prompt.recording : null;
  const isPaused = Boolean(live?.paused);
  if (!live) promptWave?.levels(0, 0, true);
  const working = prompt.stage === "hearing" || prompt.stage === "writing";
  const done = prompt.stage === "ready";
  const notCopied = done && Boolean(prompt.message);
  const lookFirst = done && !notCopied && prompt.check > 0;
  // Once, as it gets there, because you're about to paste without looking.
  if (done && promptStage !== "ready") {
    if (notCopied) playOnce($("prompt-bar"), "wash-alarm");
    else if (lookFirst) playOnce($("prompt-bar"), "wash");
  }
  promptStage = prompt.stage;
  const copy = listening ? prompt.latest_copy : null;
  const noticing = Boolean(copy) && copyNotice?.key === copy.key && Date.now() < copyNotice.until;
  // It holds still under your mouse, so Undo doesn't move just as you reach for it.
  if (noticing && $("prompt-bar").matches(":hover")) copyNotice.until = Math.max(copyNotice.until, Date.now() + 1500);
  const shown = trouble(live?.health);
  $("prompt-bar").classList.toggle("trouble", shown?.kind === "error" || notCopied);
  $("prompt-bar").classList.toggle("marked", noticing || lookFirst);
  showMark(prompt.stage, isPaused, working, shown?.kind === "error" || notCopied, noticing);
  const cancelled = prompt.stage === "cancelled";
  $("p-undo").hidden = !cancelled && (!copy || copy.added === false);
  if (cancelled) {
    $("p-undo").dataset.key = "";
    $("p-undo").title = "Bring it back, paused";
  } else if (copy && $("p-undo").dataset.key !== copy.key) {
    $("p-undo").dataset.key = copy.key;
    $("p-undo").title = `Take this back: “${copy.words}”`;
  }
  // The wave gives up its place so there's room to say what came in.
  $("p-meter").hidden = !listening || isPaused || noticing;
  $("p-stop").hidden = !listening;
  $("p-pause").hidden = !listening;
  $("p-see").hidden = listening || working || prompt.stage === "empty" || cancelled || !prompt.id;
  $("p-close").title = cancelled ? "Throw it away now" : listening || working || waitingForCopy ? (proofread ? "Cancel this" : "Cancel this prompt") : "Close this bar";
  if (listening) {
    const copied = prompt.copied ? `${prompt.copied} copied` : "";
    const takes = live?.takes || 1;
    if ($("p-pause").textContent !== (isPaused ? "Talk" : "Pause")) $("p-pause").textContent = isPaused ? "Talk" : "Pause";
    if (noticing) {
      setText("p-title", copy.said);
      setText("p-sub", `“${copy.words}”`);
    } else if (tookBack && Date.now() < tookBack.until) {
      setText("p-title", "Took that back");
      setText("p-sub", `“${tookBack.words}”`);
    } else if (isPaused) {
      setText("p-title", `${code ? "Code · " : proofread ? "Proofread · " : ""}Paused, ${takes} ${takes === 1 ? "take" : "takes"}`);
      setText("p-sub", proofread ? (prompt.copied ? "Got the text. Talk again, or finish" : "Copy the text to proofread") : copied || "Copy anything, then talk again");
    } else {
      const time = live ? clock(live.elapsed) : "";
      if (code || proofread) setText("p-title", `${code ? "Code" : "Proofread"}${takes > 1 ? ` take ${takes}` : ""} ${time}`);
      else setText("p-title", takes > 1 ? `Take ${takes} · ${time}` : `Listening ${time}`);
      // Copying is the one thing proofreading needs. Saying how is up to you.
      setText("p-sub", proofread ? (prompt.copied ? "Got the text. Say how, or finish" : "Copy the text, then say how") : copied || "Copy text to add it");
    }
    if (live) {
      if (!promptWave && !$("p-meter").hidden) promptWave = new Ink.Bars($("p-wave"));
      promptWave?.levels(live.levels.mic, 0, isPaused);
    }
  } else if (waitingForCopy) {
    setText("p-title", "Copy the text to proofread");
    setText("p-sub", "It starts as soon as you copy");
  } else if (working) {
    setText("p-title", prompt.stage === "hearing" ? "Hearing what you said" : proofread ? "Proofreading" : `Writing your ${code ? "code" : "prompt"}`);
    setText("p-sub", prompt.stage === "hearing" && prompt.check_first ? "You'll check it before it's sent" : "It'll be ready to paste");
  } else if (prompt.stage === "check") {
    setText("p-title", "Check it, then send it");
    setText("p-sub", "Nothing has gone to the AI yet");
  } else if (cancelled) {
    setText("p-title", "Cancelled");
    setText("p-sub", "Undo brings it back · ✕ throws it away");
  } else if (done) {
    setText("p-title", notCopied ? "Written, but not copied" : lookFirst ? "Check it, then press Ctrl+V" : "Ready: press Ctrl+V");
    const words = prompt.check_words || [];
    const others = prompt.check - words.length;
    const toCheck = words.length
      ? `${code ? `It can ${words.join(" and ")}` : `It says ${words.map((word) => `“${word}”`).join(" and ")}`}${others ? `, and ${others} more to check` : ", so check first"}`
      : prompt.check && `${prompt.check} ${prompt.check === 1 ? "thing" : "things"} to check first`;
    const added = prompt.added && `${prompt.added} added by the AI`;
    setText("p-sub", notCopied ? "Press See it, then Copy" : [toCheck, added, prompt.about].filter(Boolean).join(" · ") || "It's on your clipboard");
  } else {
    setText("p-title", prompt.stage === "empty" ? "Nothing to paste" : "It couldn't finish that");
    setText("p-sub", prompt.message);
  }
  if (shown) {
    setText("p-sub", shown.short);
    $("p-sub").title = shown.text;
  }
  $("p-sub").dataset.kind = shown?.kind || (notCopied ? "error" : lookFirst ? "warn" : "");
}

function connect() {
  const socket = new WebSocket(`ws://${location.host}/ws?token=${encodeURIComponent(token)}`);
  socket.onmessage = (event) => {
    const snap = JSON.parse(event.data);
    if (snap.look) Ink.setLook(snap.look);
    stale = false;
    latest = snap;
    noticeAlerts(snap.alerts);
    redraw();
  };
  socket.onclose = () => {
    stale = true;
    redraw();
    setTimeout(connect, 1000);
  };
}

sizeGlyphs();
document.addEventListener("mousedown", (event) => { pressedAt = [event.screenX, event.screenY]; }, true);
document.addEventListener("mouseup", letGo, true);
document.addEventListener("click", clickedWhileTiny, true);
$("p-close").append(svg("close"));
$("p-stop").addEventListener("click", () => post("/api/prompts/stop"));
$("p-pause").addEventListener("click", () => post($("p-pause").textContent === "Talk" ? "/api/prompts/resume" : "/api/prompts/pause"));
$("p-undo").addEventListener("click", undoCopy);
$("p-see").addEventListener("click", () => post("/api/mini", { action: "open-prompt", id: promptId }));
$("p-close").addEventListener("click", () => {
  // Closing it while you could still bring a cancelled one back means you won't: it goes now.
  post(["listening", "hearing", "writing", "copy", "cancelled"].includes(promptStage) ? "/api/prompts/cancel" : "/api/mini", { action: "hide" });
});
$("hide").append(svg("hide"));
$("cancel").append(svg("close"));
$("cancel").addEventListener("click", cancelClicked);
$("pause").append(svg("pause"));
$("stop").addEventListener("click", () => stopRecording());
$("pause").addEventListener("click", () => post(`/api/recording/${paused ? "resume" : "pause"}`));
$("hide").addEventListener("click", () => post("/api/mini", { action: "hide" }));
$("time-btn").addEventListener("click", () => post("/api/mini", { action: "open" }));
$("health").addEventListener("click", () => post("/api/mini", { action: "open" }));
connect();
