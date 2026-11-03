"use strict";

// The moving parts of the look: brush characters written stroke by stroke, the wave made of letters and characters, and words settling
// into place. One loop runs them all, and only while something is moving, so a screen where nothing moves costs nothing.
const Ink = (() => {
  const SIZE = 192;
  const FAMILY = '"Instrument Sans", "Microsoft JhengHei UI", "Microsoft JhengHei", sans-serif';
  const html = document.documentElement;
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const lerp = (a, b, t) => a + (b - a) * t;
  const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
  const dpr = () => Math.min(2, window.devicePixelRatio || 1);

  // ---------------------------------------------------------------- theme and motion

  const light = matchMedia("(prefers-color-scheme: light)");
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  // The server writes your choices into the page, so a window opens in the right colours from its first moment.
  const look = { theme: html.dataset.lookTheme || "ink", motion: html.dataset.lookMotion !== "off" };
  let generation = 0;
  let tones = new Map();

  const moves = () => look.motion !== false && !reduced.matches;

  function applyLook() {
    const theme = look.theme === "auto" ? (light.matches ? "paper" : "ink") : look.theme === "paper" ? "paper" : "ink";
    const changed = html.dataset.theme !== theme;
    html.dataset.theme = theme;
    html.dataset.motion = moves() ? "on" : "off";
    if (changed) {
      tones = new Map();
      generation += 1;
    }
    return changed;
  }

  function setLook(next) {
    if (!next) return;
    if ((next.theme ?? look.theme) === look.theme && (next.motion ?? look.motion) === look.motion) return;
    look.theme = next.theme ?? look.theme;
    look.motion = next.motion ?? look.motion;
    if (applyLook()) repaint();
    for (const wave of waves) wave.lookChanged();
  }

  function tone(name) {
    if (!tones.has(name)) {
      const hex = getComputedStyle(html).getPropertyValue(name).trim() || "#888888";
      tones.set(name, { css: hex, rgb: [1, 3, 5].map((at) => parseInt(hex.slice(at, at + 2), 16)) });
    }
    return tones.get(name);
  }

  // ---------------------------------------------------------------- the one loop

  const movers = new Set();
  let raf = 0;

  function frame(now) {
    raf = 0;
    for (const mover of movers) if (!mover.step(now)) movers.delete(mover);
    if (movers.size && !document.hidden) raf = requestAnimationFrame(frame);
  }

  function wake() {
    if (!raf && movers.size && !document.hidden) raf = requestAnimationFrame(frame);
  }

  function run(mover) {
    movers.add(mover);
    wake();
  }

  document.addEventListener("visibilitychange", wake);

  // ---------------------------------------------------------------- brush characters

  // Each character's picture holds, for every drop of ink, when it goes down in stroke order (left half) and how dark it is (right half).
  const sheets = new Map();

  function sheet(ch) {
    if (!sheets.has(ch)) {
      sheets.set(ch, new Promise((done) => {
        const image = new Image();
        image.onload = () => {
          const canvas = document.createElement("canvas");
          canvas.width = SIZE * 2;
          canvas.height = SIZE;
          const context = canvas.getContext("2d", { willReadFrequently: true });
          context.drawImage(image, 0, 0);
          const pixels = context.getImageData(0, 0, SIZE * 2, SIZE).data;
          const when = new Float32Array(SIZE * SIZE);
          const ink = new Float32Array(SIZE * SIZE);
          for (let y = 0; y < SIZE; y++) {
            for (let x = 0; x < SIZE; x++) {
              when[y * SIZE + x] = pixels[(y * SIZE * 2 + x) * 4] / 255;
              ink[y * SIZE + x] = pixels[(y * SIZE * 2 + x + SIZE) * 4] / 255;
            }
          }
          done({ when, ink });
        };
        image.onerror = () => done(null);
        image.src = `/static/glyphs/u${ch.codePointAt(0).toString(16)}.png`;
      }));
    }
    return sheets.get(ch);
  }

  const KINDS = { live: "--glyph-live", still: "--glyph-still", problem: "--glyph-problem", copied: "--glyph-problem", faint: "--glyph-faint" };
  // A little past the last stroke, so the fresh ink has finished cooling.
  const DONE = 1.1;

  function paint(canvas, drawn, progress, kind) {
    const color = tone(KINDS[kind] || KINDS.still).rgb;
    const hot = tone("--glyph-hot").rgb;
    const context = canvas.getContext("2d");
    const image = context.createImageData(SIZE, SIZE);
    const out = image.data;
    for (let i = 0; i < SIZE * SIZE; i++) {
      const ink = drawn.ink[i];
      if (ink <= 0.01) continue;
      const age = progress - drawn.when[i];
      if (age <= 0) continue;
      // The ink just laid down glows, like the tip of the brush in Written in Light.
      const fresh = clamp(1 - age / 0.09);
      const at = i * 4;
      out[at] = lerp(color[0], hot[0], fresh);
      out[at + 1] = lerp(color[1], hot[1], fresh);
      out[at + 2] = lerp(color[2], hot[2], fresh);
      out[at + 3] = 255 * ink * clamp(age / 0.012);
    }
    context.putImageData(image, 0, 0);
  }

  // Shows a character in a canvas, writing it stroke by stroke when asked. The same character in the same colour does nothing.
  async function setGlyph(canvas, ch, kind = "still", { write = true, seconds = 0.8 } = {}) {
    if (!canvas || (canvas.dataset.ch === ch && canvas.dataset.kind === kind)) return;
    canvas.dataset.ch = ch;
    canvas.dataset.kind = kind;
    canvas.setAttribute("aria-label", ch);
    const drawn = await sheet(ch);
    if (!drawn || canvas.dataset.ch !== ch || canvas.dataset.kind !== kind) return;
    if (canvas.writing) movers.delete(canvas.writing);
    if (!write || !moves()) {
      paint(canvas, drawn, DONE, kind);
      return;
    }
    const started = performance.now();
    const writing = {
      step(now) {
        const progress = clamp((now - started) / (seconds * 1000)) * DONE;
        if (!canvas.isConnected) return false;
        paint(canvas, drawn, progress, kind);
        return progress < DONE;
      },
    };
    canvas.writing = writing;
    run(writing);
  }

  function glyph(ch, kind = "still", { size = 44, write = false, seconds, id } = {}) {
    const canvas = document.createElement("canvas");
    canvas.width = SIZE;
    canvas.height = SIZE;
    canvas.className = "glyph";
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;
    if (id) canvas.id = id;
    setGlyph(canvas, ch, kind, { write, seconds });
    return canvas;
  }

  function repaint() {
    document.querySelectorAll("canvas.glyph").forEach(async (canvas) => {
      const drawn = await sheet(canvas.dataset.ch);
      if (drawn) paint(canvas, drawn, DONE, canvas.dataset.kind);
    });
  }

  // Big Shoulders' digits differ in width, and a clock in it would shake as it counts, so each digit gets a cell of its own.
  function clock(element, text) {
    if (!element || (element.textContent === text && element.firstElementChild)) return;
    element.replaceChildren(...[...text].map((ch) => {
      const cell = document.createElement("span");
      cell.className = ch === ":" ? "colon" : "digit";
      cell.textContent = ch;
      return cell;
    }));
  }

  function seal({ size = 72, stamp = false, id } = {}) {
    const image = document.createElement("img");
    image.src = "/static/glyphs/seal.png";
    image.alt = "完";
    image.className = stamp && moves() ? "seal stamped" : "seal";
    image.style.width = `${size}px`;
    image.style.height = `${size}px`;
    if (id) image.id = id;
    return image;
  }

  // ---------------------------------------------------------------- the wave

  // Speech only becomes words after it's been heard, so while listening the bright line is this phrase, not what you're saying.
  const WORDS = "聽寫 · listen and write · 聲音變文字 · voice into words · ";
  const BODY = "聲音語言文字聽寫記筆墨紙字句話說想看問答abcdefghijklmnopqrstuvwxyz";
  const CELL = 12;
  const ROW = 14;
  const waves = new Set();

  function hash(a, b) {
    let h = (a * 73856093) ^ (b * 19349663);
    h = (h ^ (h >>> 13)) * 1274126177;
    return (h ^ (h >>> 16)) >>> 0;
  }

  // Characters are drawn once, then reused many times a frame, which is why the wave is cheap.
  function sprites(px, color, glow) {
    const made = new Map();
    const ratio = dpr();
    return (ch) => {
      let sprite = made.get(ch);
      if (sprite) return sprite;
      const pad = glow ? 7 : 2;
      const canvas = document.createElement("canvas");
      const size = Math.ceil((px * 1.35 + pad * 2) * ratio);
      canvas.width = canvas.height = size;
      const context = canvas.getContext("2d");
      context.font = `${px * ratio}px ${FAMILY}`;
      context.textAlign = "center";
      context.textBaseline = "middle";
      context.fillStyle = color;
      if (glow) {
        context.shadowColor = glow;
        context.shadowBlur = 6 * ratio;
      }
      context.fillText(ch, size / 2, size / 2);
      sprite = { canvas, size };
      made.set(ch, sprite);
      return sprite;
    };
  }

  // The mic can be very quiet, as on an Antlion, so each side of the wave measures itself against its own recent loudest and quietest.
  function autoGain() {
    let floor = 0.1;
    let peak = 0.35;
    return (level) => {
      floor = level < floor ? lerp(floor, level, 0.2) : Math.min(0.45, floor + 0.0007);
      peak = level > peak ? lerp(peak, level, 0.5) : Math.max(floor + 0.2, peak - 0.0007);
      return clamp((level - floor - 0.04) / Math.max(peak - floor - 0.04, 0.05)) ** 1.3;
    };
  }

  // A reduced-motion or motion-off window still gets the still line of writing, and the level meters tell it what's being heard.
  class Wave {
    constructor(canvas, { lanes = "mic", fadeFrom = 0, fadeTo = 0, idle = false } = {}) {
      this.canvas = canvas;
      this.context = canvas.getContext("2d");
      this.lanes = lanes;
      this.fadeFrom = fadeFrom;
      this.fadeTo = fadeTo;
      this.idle = idle;
      this.width = 0;
      this.height = 0;
      this.columns = 0;
      this.maxRows = 0;
      this.up = new Float32Array(0);
      this.down = new Float32Array(0);
      this.head = 0;
      this.scroll = 0;
      this.drawnAt = 0;
      this.targets = [0, 0];
      this.now = [0, 0];
      this.gains = [autoGain(), autoGain()];
      this.calm = 1;
      this.paused = false;
      this.working = false;
      this.workClock = 0;
      this.generation = -1;
      this.observer = new ResizeObserver(() => this.resize());
      this.observer.observe(canvas);
      waves.add(this);
      this.resize();
      document.fonts.load(`12px ${FAMILY}`).then(() => {
        this.generation = -1;
        this.draw();
      });
      if (!idle) this.go();
    }

    go() {
      if (moves()) run(this);
    }

    lookChanged() {
      this.generation = -1;
      this.draw();
      if (!this.idle && !this.paused) this.go();
    }

    dispose() {
      this.observer.disconnect();
      waves.delete(this);
    }

    resize() {
      const rect = this.canvas.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const ratio = dpr();
      this.width = rect.width;
      this.height = rect.height;
      this.canvas.width = Math.round(rect.width * ratio);
      this.canvas.height = Math.round(rect.height * ratio);
      this.columns = Math.ceil(rect.width / CELL) + 2;
      this.maxRows = Math.floor((rect.height * 0.42) / ROW);
      const keep = (old) => {
        const next = new Float32Array(this.columns);
        next.set(old.subarray(Math.max(0, old.length - this.columns)), Math.max(0, this.columns - old.length));
        return next;
      };
      this.up = keep(this.up);
      this.down = keep(this.down);
      this.draw();
    }

    // Called with each update from the app, about 12 times a second. Levels run from 0 to 1.
    levels(mic, system, paused) {
      if (this.paused !== paused) {
        this.paused = paused;
        if (!paused) {
          // Talking again starts from a clean line, with the new sound coming in from the right.
          this.up.fill(0);
          this.down.fill(0);
          this.calm = 1;
          this.now = [0, 0];
          this.go();
        }
      }
      this.targets = paused ? [0, 0] : [this.gains[0](mic), this.gains[1](system)];
    }

    // While it's turning sound into words there's no sound to show, so the wave breathes.
    work(on) {
      this.working = on;
      if (on) this.go();
    }

    prepare() {
      // A new theme needs new colours, and a screen with a different display scale needs them at a new size.
      if (this.generation === generation && this.ratio === dpr()) return;
      this.generation = generation;
      this.ratio = dpr();
      const glowing = (name) => (html.dataset.theme === "paper" ? null : tone(name).css);
      this.line = sprites(12, tone("--wave-line").css, glowing("--wave-line-glow"));
      this.body = sprites(11, tone("--wave-body").css, null);
      this.crestYou = sprites(11, tone("--wave-you").css, glowing("--wave-you-glow"));
      this.crestThem = sprites(11, tone(this.lanes === "both" ? "--wave-them" : "--wave-you").css, glowing(this.lanes === "both" ? "--wave-them-glow" : "--wave-you-glow"));
    }

    put(sprite, x, y, alpha) {
      const ratio = dpr();
      this.context.globalAlpha = alpha;
      this.context.drawImage(sprite.canvas, x * ratio - sprite.size / 2, y * ratio - sprite.size / 2);
    }

    faded(x) {
      return this.fadeTo > this.fadeFrom ? clamp((x - this.fadeFrom) / (this.fadeTo - this.fadeFrom)) : 1;
    }

    wordAt(column) {
      return WORDS[(this.head + column) % WORDS.length];
    }

    bodyAt(column, row, side) {
      return BODY[hash(this.head + column, row * side + 40) % BODY.length];
    }

    draw() {
      if (!this.width) return;
      this.prepare();
      const { context } = this;
      const middle = this.height * 0.5;
      context.setTransform(1, 0, 0, 1, 0, 0);
      context.clearRect(0, 0, this.canvas.width, this.canvas.height);
      for (let column = 0; column < this.columns; column++) {
        const x = column * CELL - this.scroll;
        const shade = this.faded(x);
        if (shade <= 0) continue;
        this.put(this.line(this.wordAt(column)), x, middle, shade * (this.idle ? 0.8 : 1));
        for (const side of [-1, 1]) {
          const extent = (side < 0 ? this.up : this.down)[column] * this.calm * this.maxRows;
          for (let row = 1; row <= Math.ceil(extent); row++) {
            const fall = clamp(1 - (row - 1) / (extent + 0.6));
            const alpha = shade * fall ** 0.6 * 0.95;
            const edge = row >= extent - 1 && extent > this.maxRows * 0.3;
            if (alpha < 0.03 && !edge) continue;
            const crest = side < 0 ? this.crestYou : this.crestThem;
            this.put((edge ? crest : this.body)(this.bodyAt(column, row, side)), x, middle + side * row * ROW, edge ? shade : alpha);
          }
        }
      }
      context.globalAlpha = 1;
    }

    step(now) {
      if (!this.canvas.isConnected) {
        this.dispose();
        return false;
      }
      // A window you aren't looking at doesn't need sixty frames a second.
      if (now - this.drawnAt < (document.hasFocus() ? 14 : 38)) return true;
      const dt = Math.min(0.1, (now - this.drawnAt) / 1000);
      this.drawnAt = now;
      if (this.working) {
        this.workClock += dt;
        const swell = 0.16 + 0.1 * Math.sin(this.workClock * 1.3) + 0.06 * Math.sin(this.workClock * 3.7 + 1);
        this.targets = [swell, swell];
      }
      for (const lane of [0, 1]) {
        const target = this.targets[lane];
        this.now[lane] += (target - this.now[lane]) * clamp(dt * (target > this.now[lane] ? 30 : 9));
      }
      if (this.paused && !this.working) {
        // It lies down into one line of writing, then nothing is drawn until you talk again.
        this.calm = Math.max(0, this.calm - dt / 0.7);
      } else {
        this.scroll += 78 * dt;
        while (this.scroll >= CELL) {
          this.scroll -= CELL;
          this.up.copyWithin(0, 1);
          this.down.copyWithin(0, 1);
          this.up[this.columns - 1] = this.now[0];
          this.down[this.columns - 1] = this.lanes === "both" ? this.now[1] : this.now[0];
          this.head += 1;
        }
      }
      this.draw();
      return !(this.paused && !this.working && this.calm <= 0);
    }

    // Where the wave's characters are right now, on screen, for them to fly from.
    points() {
      const rect = this.canvas.getBoundingClientRect();
      const out = [];
      if (!this.width) return out;
      const middle = this.height * 0.5;
      for (let column = 0; column < this.columns; column++) {
        const x = column * CELL - this.scroll;
        if (this.faded(x) <= 0) continue;
        out.push({ x: rect.left + x, y: rect.top + middle, ch: this.wordAt(column) });
        for (const side of [-1, 1]) {
          const extent = (side < 0 ? this.up : this.down)[column] * this.calm * this.maxRows;
          for (let row = 1; row <= Math.ceil(extent); row++) out.push({ x: rect.left + x, y: rect.top + middle + side * row * ROW, ch: this.bodyAt(column, row, side) });
        }
      }
      return out;
    }
  }

  // ---------------------------------------------------------------- the small wave, for the floating bar

  class Bars {
    constructor(canvas, { lanes = "mic" } = {}) {
      this.canvas = canvas;
      this.context = canvas.getContext("2d");
      this.lanes = lanes;
      this.up = new Float32Array(0);
      this.down = new Float32Array(0);
      this.targets = [0, 0];
      this.gains = [autoGain(), autoGain()];
      this.now = [0, 0];
      this.paused = false;
      this.calm = 1;
      this.drawnAt = 0;
      this.pushedAt = 0;
      this.observer = new ResizeObserver(() => this.resize());
      this.observer.observe(canvas);
      waves.add(this);
      this.resize();
      this.go();
    }

    go() {
      if (moves()) run(this);
    }

    lookChanged() {
      this.draw();
      if (!this.paused) this.go();
    }

    setLanes(lanes) {
      this.lanes = lanes;
    }

    resize() {
      const rect = this.canvas.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const ratio = dpr();
      this.width = rect.width;
      this.height = rect.height;
      this.canvas.width = Math.round(rect.width * ratio);
      this.canvas.height = Math.round(rect.height * ratio);
      this.count = Math.floor(rect.width / 4);
      const keep = (old) => {
        const next = new Float32Array(this.count);
        next.set(old.subarray(Math.max(0, old.length - this.count)), Math.max(0, this.count - old.length));
        return next;
      };
      this.up = keep(this.up);
      this.down = keep(this.down);
      this.draw();
    }

    levels(mic, system, paused) {
      if (this.paused !== paused) {
        this.paused = paused;
        if (!paused) {
          this.up.fill(0);
          this.down.fill(0);
          this.calm = 1;
          this.go();
        }
      }
      this.targets = paused ? [0, 0] : [this.gains[0](mic), this.gains[1](system)];
      // With motion off this still shows you're being heard, because the bar has no other meter. It just updates with each message.
      if (!moves()) {
        this.up.copyWithin(0, 1);
        this.down.copyWithin(0, 1);
        this.up[this.count - 1] = this.targets[0];
        this.down[this.count - 1] = this.lanes === "both" ? this.targets[1] : this.targets[0];
        this.draw();
      }
    }

    draw() {
      if (!this.width) return;
      const { context } = this;
      const ratio = dpr();
      const middle = this.height / 2;
      const you = tone("--you-fill").css;
      const them = this.lanes === "both" ? tone("--them-fill").css : you;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, this.width, this.height);
      const room = middle - 1;
      for (let i = 0; i < this.count; i++) {
        const age = i / Math.max(this.count - 1, 1);
        context.globalAlpha = 0.28 + 0.72 * age;
        const x = i * 4 + 0.5;
        const up = this.up[i] * this.calm * room;
        const down = this.down[i] * this.calm * room;
        context.fillStyle = you;
        context.fillRect(x, middle - Math.max(up, 0.5), 2.2, Math.max(up, 0.5));
        context.fillStyle = them;
        context.fillRect(x, middle, 2.2, Math.max(down, 0.5));
      }
      context.globalAlpha = 1;
    }

    step(now) {
      if (!this.canvas.isConnected) {
        this.observer.disconnect();
        waves.delete(this);
        return false;
      }
      if (now - this.drawnAt < 33) return true;
      const dt = Math.min(0.1, (now - this.drawnAt) / 1000);
      this.drawnAt = now;
      for (const lane of [0, 1]) {
        const target = this.targets[lane];
        this.now[lane] += (target - this.now[lane]) * clamp(dt * (target > this.now[lane] ? 30 : 9));
      }
      if (this.paused) {
        this.calm = Math.max(0, this.calm - dt / 0.5);
      } else if (now - this.pushedAt > 70 && this.count) {
        this.pushedAt = now;
        this.up.copyWithin(0, 1);
        this.down.copyWithin(0, 1);
        this.up[this.count - 1] = this.now[0];
        this.down[this.count - 1] = this.lanes === "both" ? this.now[1] : this.now[0];
      }
      this.draw();
      return !(this.paused && this.calm <= 0);
    }
  }

  // ---------------------------------------------------------------- words settling

  // Where each character of a text sits inside a text box. A text box can't say, so a hidden copy with the same shape measures it.
  function layoutOf(box, text) {
    const style = getComputedStyle(box);
    const mirror = document.createElement("div");
    for (const key of ["fontFamily", "fontSize", "fontWeight", "fontStretch", "lineHeight", "letterSpacing", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "borderTopWidth", "borderRightWidth", "borderBottomWidth", "borderLeftWidth", "borderTopStyle", "borderRightStyle", "borderBottomStyle", "borderLeftStyle"]) mirror.style[key] = style[key];
    mirror.style.position = "fixed";
    mirror.style.left = "0";
    mirror.style.top = "0";
    mirror.style.visibility = "hidden";
    mirror.style.boxSizing = "border-box";
    // The text box's scrollbar takes up room that the copy has to leave out, or its lines would break in different places.
    const scrollbar = box.offsetWidth - box.clientWidth - parseFloat(style.borderLeftWidth) - parseFloat(style.borderRightWidth);
    mirror.style.width = `${box.offsetWidth - scrollbar}px`;
    // Code doesn't wrap.
    mirror.style.whiteSpace = style.whiteSpace === "pre" ? "pre" : "pre-wrap";
    mirror.style.overflowWrap = "break-word";
    mirror.textContent = text;
    document.body.append(mirror);
    const node = mirror.firstChild;
    const range = document.createRange();
    const boxRect = box.getBoundingClientRect();
    const slots = [];
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (ch === " " || ch === "\n" || ch === "\r" || ch === "\t") continue;
      range.setStart(node, i);
      range.setEnd(node, i + 1);
      const rect = range.getClientRects()[0];
      if (!rect) continue;
      const y = boxRect.top + rect.top + rect.height / 2 - box.scrollTop;
      if (y > boxRect.bottom) break;
      slots.push({ ch, x: boxRect.left + rect.left + rect.width / 2, y });
    }
    mirror.remove();
    return { slots, font: `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`, size: parseFloat(style.fontSize) };
  }

  // The wave's characters fly to their places in your real words, turning into them on the way. It costs a couple of seconds of drawing
  // only when the page is in front of you. Nothing waits for it: the words are already on the clipboard.
  function settle(box, text, from, done) {
    if (!moves() || document.hidden || !box.isConnected) {
      done?.();
      return;
    }
    const { slots, font, size } = layoutOf(box, text);
    if (!slots.length || slots.length > 1800) {
      done?.();
      return;
    }
    const ratio = dpr();
    const canvas = document.createElement("canvas");
    canvas.className = "flight";
    canvas.width = Math.round(innerWidth * ratio);
    canvas.height = Math.round(innerHeight * ratio);
    document.body.append(canvas);
    const context = canvas.getContext("2d");
    const color = getComputedStyle(box).color;
    const made = new Map();
    const sprite = (ch, faint) => {
      const key = ch + (faint ? "0" : "1");
      if (!made.has(key)) {
        const piece = document.createElement("canvas");
        const side = Math.ceil(size * 1.6 * ratio);
        piece.width = piece.height = side;
        const pen = piece.getContext("2d");
        pen.font = font.replace(/([\d.]+)px/, (_, px) => `${px * ratio}px`);
        pen.textAlign = "center";
        pen.textBaseline = "middle";
        pen.fillStyle = faint ? tone("--wave-body").css : color;
        pen.fillText(ch, side / 2, side / 2);
        made.set(key, { piece, side });
      }
      return made.get(key);
    };
    const pool = from && from.length ? from : [{ x: box.getBoundingClientRect().left + 40, y: box.getBoundingClientRect().top - 60, ch: "聲" }];
    slots.forEach((slot, index) => {
      const source = pool[hash(index, 7) % pool.length];
      slot.fromX = source.x;
      slot.fromY = source.y;
      slot.fromCh = source.ch;
      slot.delay = (index / slots.length) * 0.95 + (hash(index, 3) % 100) / 500;
    });
    box.classList.add("settling");
    const started = performance.now();
    const finish = () => {
      canvas.remove();
      box.classList.remove("settling");
      done?.();
    };
    run({
      step(now) {
        if (!box.isConnected) {
          finish();
          return false;
        }
        const elapsed = (now - started) / 1000;
        context.setTransform(1, 0, 0, 1, 0, 0);
        context.clearRect(0, 0, canvas.width, canvas.height);
        let busy = false;
        for (const slot of slots) {
          const progress = clamp((elapsed - slot.delay) / 0.9);
          if (progress < 1) busy = true;
          if (progress <= 0) continue;
          const eased = easeInOut(progress);
          const { piece, side } = progress < 0.7 ? sprite(slot.fromCh, true) : sprite(slot.ch, false);
          const scale = lerp(0.72, 1, eased);
          context.globalAlpha = 0.5 + 0.5 * eased;
          const drawn = side * scale;
          context.drawImage(piece, lerp(slot.fromX, slot.x, eased) * ratio - drawn / 2, lerp(slot.fromY, slot.y, eased) * ratio - drawn / 2, drawn, drawn);
        }
        if (!busy) {
          finish();
          return false;
        }
        return true;
      },
    });
  }

  applyLook();
  // Moving the window to a screen with a different display scale fires this too.
  window.addEventListener("resize", () => {
    for (const wave of waves) wave.resize();
  });
  light.addEventListener("change", () => {
    if (look.theme === "auto" && applyLook()) {
      repaint();
      for (const wave of waves) wave.lookChanged();
    }
  });
  reduced.addEventListener("change", () => {
    applyLook();
    for (const wave of waves) wave.lookChanged();
  });

  return { glyph, setGlyph, clock, seal, Wave, Bars, settle, setLook, moves };
})();
