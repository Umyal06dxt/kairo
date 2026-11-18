"use strict";
(() => {
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") e.className = v; else if (k === "text") e.textContent = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null) e.append(kid.nodeType ? kid : document.createTextNode(kid));
  return e;
}
const fmtMs = (v) => v == null ? "–" : v >= 100 ? Math.round(v).toLocaleString() + " ms" : v >= 10 ? v.toFixed(0) + " ms" : v.toFixed(1) + " ms";
const pct = (v) => v == null ? "–" : Math.round(v * 100) + "%";
const clock = (ms) => { const s = Math.max(0, Math.round(ms / 1000)); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); };
const store = { get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
                set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} } };

const S = { ws: null, ready: null, lamps: new Map(), meta: new Map(), tags: new Map(), t0: 0, cur: null,
            info: null, settings: store.get("kairo.settings", {}), autoplay: false,
            audioCtx: null, audioQ: [], playing: false, mic: null };

/* ===================================================== tabs */
function showTab(name) {
  $$(".tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
  $$(".tab").forEach((t) => (t.hidden = t.id !== "tab-" + name));
  if (name === "exp") loadExperiments();
  if (name === "res") renderResearch();
  history.replaceState(null, "", "#" + name);
}
$$(".tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));

/* ===================================================== websocket */
function connect() {
  const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
  S.ws = ws;
  ws.onopen = () => { setConn(true, "Connected"); hello(); };
  ws.onclose = () => { setConn(false, "Disconnected. Retrying…"); setTimeout(connect, 1500); };
  ws.onmessage = (ev) => { try { handle(JSON.parse(ev.data)); } catch (e) { console.error(e); } };
}
const send = (m) => S.ws && S.ws.readyState === 1 && S.ws.send(JSON.stringify(m));
function setConn(ok, text) { const c = $("#conn"); c.dataset.ok = ok; c.textContent = text; }
function hello() { resetCallUI(); send({ t: "hello", settings: S.settings }); }

function handle(m) {
  switch (m.t) {
    case "ready": return onReady(m);
    case "status": return setConn(true, m.state === "loading" ? m.message : "Connected");
    case "cache": return onCache(m);
    case "turn_start": return onTurnStart(m);
    case "token": return onToken(m);
    case "turn": return onTurn(m);
    case "slow": return onSlow(m);
    case "transcript": return onTranscript(m);
    case "audio_out": return enqueueAudio(m);
    case "autoplay": return onAutoplay(m);
    case "error": return notice(m.message, true);
  }
}

/* ===================================================== ready / board */
function resetCallUI() {
  $("#log").innerHTML = ""; $("#ledger").innerHTML = ""; $("#intro").hidden = false;
  S.t0 = 0; S.cur = null; S.autoplay = false; updateAutoplayBar();
  ["#c-hit", "#c-wait", "#c-draft"].forEach((s) => ($(s).textContent = "–"));
}

function onReady(m) {
  S.ready = m;
  $("#domain-title").textContent = m.domain.title;
  $("#domain-blurb").textContent = m.domain.blurb;
  $("#composer #say").placeholder = m.domain.key === "bank" ? "Ask about fees, cards, loans, hours…" : "Ask about pricing, the API, security…";
  const sc = $("#scenario-list"); sc.innerHTML = "";
  sc.append(h("p", { class: "sub", text: "Listen in on a scripted call" }));
  for (const s of m.domain.scenarios)
    sc.append(h("button", { type: "button", onclick: () => { S.t0 = 0; send({ t: "autoplay", scenario: s.key }); } },
      h("span", { text: s.key }), h("small", { text: s.turns + " questions" })));
  const notes = $("#notes"); notes.innerHTML = "";
  m.notes.forEach((n) => notes.append(h("p", { text: n })));
  notes.hidden = m.notes.length === 0;
  buildBoard(m.board);
  const c = m.config, p = m.profile;
  $("#config-line").textContent = p.cache
    ? `${p.label}. Prediction: ${c.strategy === "none" ? "none" : c.strategy === "llm" ? "GPT" : c.strategy === "neighbors" ? "nearby pages" : "GPT + nearby pages"}`
      + `${c.drafts ? ", pre-drafted answers" : ""}${c.verify ? ", checked against the database" : ""}. Strictness ${c.tau}. Answers by ${m.llm === "openai" ? "GPT" : "the offline stand-in"}; embeddings ${m.embedder}.`
    : `${p.label}: every question goes to the database. No memory, no prediction. Answers by ${m.llm === "openai" ? "GPT" : "the offline stand-in"}.`;
  setMic(m.voice.stt);
  $("#board-sub").textContent = p.cache ? "Each lamp is a page of the knowledge base. A lit lamp is in memory." : "This mode has no memory, so the board stays dark.";
  setConn(true, "Connected");
}

function buildBoard(board) {
  const root = $("#board"); root.innerHTML = ""; S.lamps.clear(); S.meta.clear(); S.tags.clear();
  const lamp = (id, doc) => { const l = h("i", { class: "l", "data-id": id }); S.lamps.set(id, l); S.meta.set(id, doc); return l; };
  for (const d of board.docs.filter((x) => !x.extra))
    root.append(h("div", { class: "brow", "data-doc": d.name },
      h("span", { class: "name", title: d.title, text: d.title }), h("div", { class: "lamps" }, d.chunks.map((c) => lamp(c, d)))));
  const extra = board.docs.filter((x) => x.extra);
  if (extra.length) {
    root.append(h("p", { class: "extra-head", text: `Background pages (${extra.length}). Other products and services a real knowledge base would hold.` }));
    root.append(h("div", { class: "extras" }, extra.flatMap((d) => d.chunks.map((c) => lamp(c, d)))));
  }
  $("#c-mem").textContent = "0 / " + board.n_chunks;
}

function onCache(m) {
  const ids = new Set();
  for (const e of m.entries) {
    ids.add(e.id); S.tags.set(e.id, e);
    const l = S.lamps.get(e.id); if (!l) continue;
    l.className = "l on " + e.tag;
  }
  for (const [id, l] of S.lamps) if (!ids.has(id)) { l.className = "l"; S.tags.delete(id); }
  $("#c-mem").textContent = `${ids.size} / ${S.lamps.size}`;
}

function pulse(ids) {
  for (const id of ids) {
    const l = S.lamps.get(id); if (!l) continue;
    l.classList.remove("used"); void l.offsetWidth; l.classList.add("used");
    setTimeout(() => l.classList.remove("used"), 1800);
  }
  $$(".brow.gold").forEach((r) => r.classList.remove("gold"));
}
const tipEl = $("#tip");
$("#board").addEventListener("pointerover", (e) => {
  const l = e.target.closest(".l"); if (!l) return;
  const id = l.dataset.id, d = S.meta.get(id), t = S.tags.get(id);
  const why = { direct: "asked directly", predicted: "predicted", neighbor: "nearby page", partial: "heard while typing", miss: "fetched after a miss" };
  tipEl.replaceChildren(h("b", { text: d ? d.title : id }), h("span", { text: t ? `In memory: ${why[t.tag] || t.tag}. Used ${t.hits} time${t.hits === 1 ? "" : "s"}.` : "Not in memory" }));
  const r = l.getBoundingClientRect(); tipEl.hidden = false;
  tipEl.style.left = Math.min(innerWidth - 320, r.left) + "px"; tipEl.style.top = r.bottom + 8 + "px";
});
$("#board").addEventListener("pointerout", () => (tipEl.hidden = true));

/* ===================================================== conversation */
function notice(msg, bad) {
  const n = $("#notes"); n.hidden = false; n.append(h("p", { text: msg }));
  if (bad && S.cur) S.cur.a.classList.remove("pending");
}
function onTurnStart(m) {
  $("#intro").hidden = true;
  if (!S.t0) S.t0 = performance.now();
  const a = h("p", { class: "a pending" });
  const li = h("li", { class: "turn" },
    m.via === "voice" ? h("p", { class: "you", text: "You said" }) : m.via === "script" ? h("p", { class: "you", text: "Caller" }) : null,
    h("p", { class: "q", text: m.q }), a);
  $("#log").append(li); S.cur = { li, a, text: "" };
  scroll();
}
function onToken(m) { if (S.cur) { S.cur.text += m.s; S.cur.a.textContent = S.cur.text; scroll(); } }
function scroll() { const c = $(".transcript"); c.scrollTop = c.scrollHeight; }

const BADGES = (m, cache) => {
  if (!cache) return ["miss", "Looked it up in the database", "This mode has no memory."];
  if (m.store_failed) return ["miss", "Database unavailable", "Answered without any pages."];
  if (m.corrected) return ["miss", "Memory was wrong, so it looked again", "The database disagreed with what was remembered; the answer was regenerated before any speech."];
  if (m.source === "draft") return ["draft", "Answered from a pre-drafted answer", "Guessed this question earlier and wrote the answer in advance. No wait for the language model."];
  if (m.hit) return ["neighbor", "Answered from memory", m.verified ? "Checked against the database in parallel: it agreed." : "Served from memory without checking the database."];
  return ["miss", "Looked it up in the database", "Nothing useful was in memory yet."];
};

function onTurn(m) {
  const cur = S.cur; if (!cur) return;
  cur.a.classList.remove("pending"); cur.a.textContent = m.answer || cur.text;
  cur.li.classList.add("src-" + m.source); if (m.corrected) cur.li.classList.add("corrected");
  const [kind, title, why] = BADGES(m, S.ready.profile.cache);
  const total = Math.max(1, m.embed_ms + m.retrieval_ms + (m.llm_ms || 0));
  const seg = (cls, v) => h("i", { class: cls, style: `width:${(v / total) * 100}%` });
  cur.li.append(
    h("div", { class: "badge" }, h("i", { class: "l on " + (kind === "draft" ? "draft" : kind) }), title),
    h("p", { class: "hint", text: why }),
    h("div", { class: "route", title: "Time before the first word" },
      h("div", { class: "strip" }, seg("e", m.embed_ms), seg("r", m.retrieval_ms), seg("l", m.llm_ms || 0)),
      h("div", { class: "route-meta" },
        h("span", {}, "Wait ", h("b", { text: fmtMs(m.user_ms) })),
        h("span", { text: "understanding " + fmtMs(m.embed_ms) }), h("span", { text: "lookup " + fmtMs(m.retrieval_ms) }),
        h("span", { text: m.source === "draft" ? "no model wait" : "first word " + fmtMs(m.llm_ms) }))));
  if (m.chunk_ids.length) {
    const ev = h("div", { class: "evidence", "aria-label": "Pages used" });
    m.chunk_ids.forEach((id, i) => ev.append(h("i", { class: "l on " + (m.tags[i] || "direct"), title: (S.meta.get(id)?.title || id) })));
    ev.append(h("small", { text: m.chunk_ids.length + " page" + (m.chunk_ids.length === 1 ? "" : "s") + " used" }));
    cur.li.append(ev);
  }
  if (m.gold) {
    const g = h("p", { class: "gold" });
    const mark = (ok, yes, no) => h("span", { class: ok ? "ok" : "no", text: ok ? yes : no });
    if (m.gold.doc_ok != null) g.append(mark(m.gold.doc_ok, "Right source page used", "Wrong source page"));
    if (m.gold.answer_ok != null) g.append(" · ", mark(m.gold.answer_ok, "Answer has the expected facts", "Answer is missing expected facts"));
    cur.li.append(g);
  }
  pulse(m.chunk_ids);
  const st = m.stats;
  $("#c-hit").textContent = `${st.hits}/${st.turns}`; $("#c-wait").textContent = fmtMs(st.avg_user_ms); $("#c-draft").textContent = st.drafts;
  ledger("turn", `Answered in ${fmtMs(m.user_ms)}`, m.source === "draft" ? "from a pre-drafted answer" : m.hit ? "from memory" : m.corrected ? "memory was wrong, corrected" : "from the database");
  scroll();
}
function onTranscript(m) { setMicState(false); $("#mic-hint").textContent = m.text ? "" : "Didn't catch that. Hold the button and try again."; }

/* ===================================================== ledger (what the background agent does) */
function ledger(kind, text, sub, items) {
  const t = S.t0 ? clock(performance.now() - S.t0) : "0:00";
  const li = h("li", { class: "k-" + kind }, h("time", { text: t }), h("i", { class: "l" }),
    h("div", {}, text, sub ? h("small", { text: sub }) : null, items ? h("ul", {}, items.map((x) => h("li", { text: x }))) : null));
  const root = $("#ledger"); root.prepend(li);
  while (root.children.length > 120) root.lastChild.remove();
}
const q = (s) => "“" + (s.length > 60 ? s.slice(0, 57) + "…" : s) + "”";
function onSlow(m) {
  switch (m.kind) {
    case "utterance": return ledger("direct", "Heard " + q(m.text));
    case "prefetch": {
      const n = (m.added || []).length, tot = (m.returned || []).length;
      const label = { direct: `Looked up ${q(m.query)}`, predicted: "Loaded pages for a prediction", neighbor: "Loaded pages near one it just found",
                      partial: `Heard while you typed: ${q(m.query)}`, miss: `Memory missed. Fetched ${q(m.query)}` }[m.source] || "Loaded pages";
      return ledger(m.source, label, `${tot} pages checked, ${n} new in memory${m.source === "predicted" ? " · for " + q(m.query) : ""}`);
    }
    case "predicted": return ledger("predicted", "Expecting you to ask next", "", m.predictions.map((p) => p.question || p.topic));
    case "drafted": return ledger("draft", "Wrote an answer in advance for " + q(m.question), m.answer);
    case "cancelled": return ledger("miss", "Dropped a plan", "You moved on before it finished.");
    case "corrected": return ledger("corrected", "Memory was wrong", "Fetched the right pages and answered again before speaking.");
  }
}

/* ===================================================== composer, partials, scripted calls */
let partialTimer = null;
$("#say").addEventListener("input", (e) => {
  clearTimeout(partialTimer);
  const v = e.target.value.trim();
  if (v.length >= 12) partialTimer = setTimeout(() => send({ t: "partial", text: v }), 300);
});
$("#composer").addEventListener("submit", (e) => {
  e.preventDefault(); const inp = $("#say"), v = inp.value.trim(); if (!v) return;
  clearTimeout(partialTimer); if (!S.t0) S.t0 = performance.now();
  send({ t: "say", text: v }); inp.value = "";
});
function onAutoplay(m) { S.autoplay = m.state === "start"; updateAutoplayBar(m); }
function updateAutoplayBar(m) {
  let bar = $("#ap-bar");
  if (!S.autoplay) { if (bar) bar.remove(); return; }
  if (!bar) { bar = h("div", { id: "ap-bar", class: "notes" }); bar.append(h("span", { text: "Playing a scripted call. " }),
    h("button", { type: "button", class: "ghost", onclick: () => send({ t: "stop" }) }, "Stop")); $("#log").before(bar); }
}

/* ===================================================== voice (browser mic -> server Whisper -> spoken reply) */
function setMic(stt) {
  const b = $("#mic"), ok = !!(navigator.mediaDevices && window.MediaRecorder);
  b.disabled = !(ok && stt === "ready");
  $("#mic-hint").textContent = !ok ? "This browser can't record audio."
    : stt === "ready" ? "Hold the microphone button to talk." : stt === "loading" ? "Loading speech recognition…"
    : stt === "error" ? "Speech recognition failed to load. You can still type." : "Voice is off (server started with --no-voice).";
  if (stt === "loading") setTimeout(async () => { try { const i = await (await fetch("/api/info")).json(); setMic(i.stt); } catch {} }, 3000);
}
function setMicState(on) { $("#mic").setAttribute("aria-pressed", String(on)); }
async function micStart() {
  if ($("#mic").disabled || S.mic) return;
  ensureAudio();
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    const mime = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"].find((m) => MediaRecorder.isTypeSupported(m));
    const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined), chunks = [];
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    rec.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop()); S.mic = null;
      const blob = new Blob(chunks, { type: rec.mimeType });
      if (blob.size < 2000) { setMicState(false); $("#mic-hint").textContent = "That was too short. Hold the button while you speak."; return; }
      $("#mic-hint").textContent = "Transcribing…";
      const b64 = await new Promise((res) => { const fr = new FileReader(); fr.onload = () => res(String(fr.result).split(",")[1]); fr.readAsDataURL(blob); });
      if (!S.t0) S.t0 = performance.now(); send({ t: "audio", data: b64, mime: rec.mimeType });
    };
    rec.start(); S.mic = { rec, stream }; setMicState(true); $("#mic-hint").textContent = "Listening… release to send.";
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;   // optional: interim text -> early retrieval
    if (SR) { const r = new SR(); r.interimResults = true; r.lang = "en-US"; S.mic.sr = r;
      r.onresult = (e) => { const t = [...e.results].map((x) => x[0].transcript).join(" ").trim(); if (t.length >= 12) send({ t: "partial", text: t }); };
      r.onerror = () => {}; try { r.start(); } catch {} }
  } catch (e) { $("#mic-hint").textContent = "Couldn't open the microphone. Check the browser's permission for this site."; }
}
function micStop() { if (!S.mic) return; try { S.mic.sr && S.mic.sr.stop(); } catch {} try { S.mic.rec.stop(); } catch {} }
const mic = $("#mic");
mic.addEventListener("pointerdown", (e) => { e.preventDefault(); micStart(); });
["pointerup", "pointerleave", "pointercancel"].forEach((ev) => mic.addEventListener(ev, micStop));
mic.addEventListener("keydown", (e) => { if (e.key === " " || e.key === "Enter") { e.preventDefault(); if (!e.repeat) micStart(); } });
mic.addEventListener("keyup", (e) => { if (e.key === " " || e.key === "Enter") micStop(); });

function ensureAudio() { if (!S.audioCtx) S.audioCtx = new (window.AudioContext || window.webkitAudioContext)(); if (S.audioCtx.state === "suspended") S.audioCtx.resume(); }
async function enqueueAudio(m) { S.audioQ.push(m); if (!S.playing) playNext(); }
async function playNext() {
  const m = S.audioQ.shift(); if (!m) { S.playing = false; return; }
  S.playing = true;
  try {
    ensureAudio();
    const bin = atob(m.data), buf = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
    const audio = await S.audioCtx.decodeAudioData(buf.buffer);
    const src = S.audioCtx.createBufferSource(); src.buffer = audio; src.connect(S.audioCtx.destination);
    src.onended = playNext; src.start();
  } catch { playNext(); }
}

/* ===================================================== settings dialog */
async function loadInfo() {
  try { S.info = await (await fetch("/api/info")).json(); } catch { return; }
  const dom = $("#s-domain"); dom.innerHTML = "";
  S.info.domains.forEach((d) => dom.append(h("option", { value: d.key, text: d.title })));
  const fill = (root, name, checked) => {
    root.innerHTML = "";
    S.info.profiles.forEach((p) => root.append(h("label", {}, h("input", { type: name === "x" ? "checkbox" : "radio", name: name === "x" ? "xp" : "profile", value: p.key,
      checked: name === "x" ? ["baseline", "paper", "optimized"].includes(p.key) : p.key === checked }),
      h("b", { text: p.label }), h("small", { text: profileBlurb(p) }))));
  };
  fill($("#s-profiles"), "s", S.settings.profile || "optimized");
  fill($("#x-profiles"), "x");
  const sw = $("#x-sweep"); S.info.profiles.filter((p) => p.cache).forEach((p) => sw.append(h("option", { value: p.key, text: p.label })));
}
function profileBlurb(p) {
  if (!p.cache) return "Every question goes to the database. The comparison point.";
  const bits = [{ none: "No prediction", llm: "GPT predicts the next topics", neighbors: "Prefetches nearby pages (no GPT)", hybrid: "GPT plus nearby pages" }[p.strategy]];
  if (p.drafts) bits.push("pre-drafts answers"); if (p.verify) bits.push("verifies hits");
  return bits.join(", ") + ".";
}
$("#open-settings").addEventListener("click", () => {
  const f = $("#settings-form"), s = S.settings;
  f.elements.domain.value = s.domain || "bank"; f.elements.embedder.value = s.embedder || "local"; f.elements.llm.value = s.llm || "auto";
  f.elements.store_latency_ms.value = s.store_latency_ms ?? 110; f.elements.distractors.checked = s.distractors !== false; f.elements.speak.checked = !!s.speak;
  f.elements.tau.value = s.tau ?? 0.6; $("#o-tau").textContent = s.tau == null ? "default" : s.tau;
  $("#o-lat").textContent = (s.store_latency_ms ?? 110) + " ms";
  const r = $$("#s-profiles input").find((i) => i.value === (s.profile || "optimized")); if (r) r.checked = true;
  $("#settings").showModal();
});
$("#s-tau").addEventListener("input", (e) => { S.tauTouched = true; $("#o-tau").textContent = e.target.value; });
$("#s-lat").addEventListener("input", (e) => ($("#o-lat").textContent = e.target.value + " ms"));
$("#settings-form").addEventListener("submit", (e) => {
  if (e.submitter && e.submitter.value !== "apply") return;
  const f = e.target.elements;
  S.settings = { domain: f.domain.value, profile: ($$("#s-profiles input").find((i) => i.checked) || {}).value || "optimized",
    embedder: f.embedder.value, llm: f.llm.value, store_latency_ms: +f.store_latency_ms.value, distractors: f.distractors.checked, speak: f.speak.checked,
    tau: S.tauTouched || S.settings.tau != null ? +f.tau.value : null };
  store.set("kairo.settings", S.settings); hello();
});

/* ===================================================== experiments */
let pollTimer = null, saved = [];
async function loadExperiments() {
  if (!S.info) await loadInfo();
  const d = await (await fetch("/api/experiments")).json();
  saved = d.saved; const sel = $("#x-saved"); sel.innerHTML = "";
  saved.forEach((r) => sel.append(h("option", { value: r.id, text: `${r.generated || r.id} · ${r.domain} · ${r.env}` })));
  if (saved.length) renderResult(saved[0]);
  if (d.current && d.current.state === "running") poll();
}
$("#x-saved").addEventListener("change", (e) => renderResult(saved.find((r) => r.id === e.target.value)));
$("#exp-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const spec = { domain: $("input[name=domain]:checked").value, profiles: $$("#x-profiles input:checked").map((i) => i.value),
    embedder: $("#x-embedder").value, llm: $("#x-llm").value, sweep: $("#x-sweep").value, distractors: $("#x-distract").checked ? 64 : 0 };
  const live = spec.llm === "openai" || spec.embedder === "openai";
  if (live && !confirm("This run calls the OpenAI API with your key and costs a few cents. Run it?")) return;
  spec.confirm = live;
  const r = await fetch("/api/experiments", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(spec) });
  const j = await r.json(); $("#x-msg").textContent = r.ok ? "Running…" : j.error;
  if (r.ok) { $("#x-run").disabled = true; poll(); }
});
function poll() {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => {
    const d = await (await fetch("/api/experiments")).json(), c = d.current;
    if (c && c.state === "running") {
      $("#x-run").disabled = true; const p = $("#x-progress"); p.hidden = false; p.textContent = c.progress.join("\n"); return poll();
    }
    $("#x-run").disabled = false;
    if (c && c.state === "error") $("#x-msg").textContent = "The run failed: " + c.error;
    if (c && c.state === "done") { $("#x-msg").textContent = "Done."; await loadExperiments(); }
  }, 1200);
}

function bestIdx(vals, higher, isRate) {
  // Only mark a winner when it clearly beats the runner-up; one run of ~100 turns can't resolve less.
  const ok = vals.map((v, i) => [v, i]).filter(([v]) => v != null); if (ok.length < 2) return -1;
  const sorted = [...ok].sort((a, b) => (higher ? b[0] - a[0] : a[0] - b[0]));
  const gap = Math.abs(sorted[0][0] - sorted[1][0]), scale = Math.max(Math.abs(sorted[1][0]), 1e-9);
  return (isRate ? gap >= 0.04 : gap / scale >= 0.08) ? sorted[0][1] : -1;
}
function renderResult(r) {
  const root = $("#x-results"); root.innerHTML = ""; if (!r) return;
  const keys = Object.keys(r.profiles), P = keys.map((k) => ({ k, ...r.profiles[k], s: r.profiles[k].summary }));
  root.append(h("p", { class: "note", text: `${r.env}. ${r.generated || ""}` }), ...(r.notes || []).map((n) => h("p", { class: "note", text: n })));
  const cols = [["Hit rate", "hit_rate", true, pct], ["Right page", "evidence", true, pct], ["Answer correct", "accuracy", true, pct], ["Hit fidelity", "fidelity", true, pct],
                ["Wait p50", "user_p50", false, fmtMs], ["Wait p90", "user_p90", false, fmtMs], ["First word", "llm_ms", false, fmtMs]];
  const best = cols.map(([, key, hi, f]) => bestIdx(P.map((p) => p.s[key]), hi, f === pct));
  root.append(h("h3", { text: "Results" }), h("div", { class: "tblwrap" }, h("table", {},
    h("thead", {}, h("tr", {}, h("th", { text: "Strategy" }), cols.map(([t]) => h("th", { text: t })))),
    h("tbody", {}, P.map((p, i) => h("tr", {}, h("td", { text: p.label }),
      cols.map(([, key, , f], c) => h("td", { class: best[c] === i ? "best" : "", text: f(p.s[key]) }))))))));
  root.append(h("p", { class: "note", text: "Bold green marks a clear winner (4+ points, or 8%+ faster); smaller gaps are within the noise of a single run. Wait is the time before the first word: understanding the question, looking up pages, and the model's first token. “Right page” is how often the page holding the answer was among those used. Fidelity is how often a memory hit served the same pages the database would have." }));
  root.append(h("h3", { text: "How long the caller waits (median and slowest 10%)" }), waitChart(P));
  if (r.sweep && r.sweep.length) root.append(h("h3", { text: "Memory strictness: more hits or better hits?" }), sweepChart(r.sweep));
}
const NS = "http://www.w3.org/2000/svg";
function svg(tag, attrs, ...kids) { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v); kids.flat().forEach((k) => k != null && e.append(k.nodeType ? k : document.createTextNode(k))); return e; }
function waitChart(P) {
  const W = 720, rowH = 44, left = 230, H = P.length * rowH + 28, max = Math.max(...P.map((p) => p.s.user_p90 || 0), 1);
  const root = svg("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Wait before first word per strategy" });
  P.forEach((p, i) => {
    const y = i * rowH + 8, w50 = (p.s.user_p50 / max) * (W - left - 70), w90 = (p.s.user_p90 / max) * (W - left - 70);
    root.append(svg("text", { x: 0, y: y + 16 }, p.label), svg("rect", { x: left, y, width: Math.max(2, w90), height: 14, rx: 3, fill: "var(--mooring)" }),
      svg("rect", { x: left, y, width: Math.max(2, w50), height: 14, rx: 3, fill: "var(--accent)" }),
      svg("text", { x: left + Math.max(w50, w90) + 8, y: y + 12 }, fmtMs(p.s.user_p50)),
      svg("text", { class: "muted", x: left, y: y + 32 }, `slowest 10%: ${fmtMs(p.s.user_p90)}`));
  });
  return root;
}
function sweepChart(sw) {
  const pts = [...sw].sort((a, b) => a.tau - b.tau), W = 720, H = 260, L = 44, B = 36, T = 14, R = 110;
  const x = (t) => L + ((t - pts[0].tau) / Math.max(0.01, pts.at(-1).tau - pts[0].tau)) * (W - L - R), y = (v) => T + (1 - v) * (H - T - B);
  const root = svg("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Hit rate, right page and fidelity against threshold" });
  [0, 0.25, 0.5, 0.75, 1].forEach((g) => root.append(svg("line", { class: "grid", x1: L, x2: W - R, y1: y(g), y2: y(g) }), svg("text", { class: "muted", x: 4, y: y(g) + 4 }, Math.round(g * 100) + "%")));
  pts.forEach((p) => root.append(svg("text", { class: "muted", x: x(p.tau) - 12, y: H - 14 }, p.tau.toFixed(2))));
  const series = [["hit_rate", "Hit rate", "var(--predicted)"], ["evidence", "Right page", "var(--accent)"], ["fidelity", "Fidelity", "var(--partial)"]];
  for (const [k, name, color] of series) {
    const line = pts.filter((p) => p.summary[k] != null);
    root.append(svg("polyline", { fill: "none", stroke: color, "stroke-width": 2.5, points: line.map((p) => `${x(p.tau)},${y(p.summary[k])}`).join(" ") }));
    line.forEach((p) => root.append(svg("circle", { cx: x(p.tau), cy: y(p.summary[k]), r: 3.5, fill: color })));
    const last = line.at(-1); if (last) root.append(svg("text", { x: W - R + 8, y: y(last.summary[k]) + 4 }, name));
  }
  return root;
}

/* ===================================================== research */
function renderResearch() {
  fetch("/api/experiments").then((r) => r.json()).then((d) => paintResearch(d.saved || []));
}
function paintResearch(runs) {
  const isLive = (r) => /llm=openai/.test(r.env), isOff = (r) => /llm=extractive/.test(r.env);
  const liveBase = runs.find((r) => isLive(r) && r.profiles.baseline);      // has the plain-RAG comparison
  const liveOpt = runs.find((r) => isLive(r) && r.profiles.optimized);     // newest optimized settings
  const off = runs.find((r) => isOff(r) && r.profiles.reactive && r.profiles.baseline);
  const S_ = (r, k) => (r && r.profiles[k] ? r.profiles[k].summary : null);
  const f = $("#findings"); f.innerHTML = "";
  const sec = (title, status, cls, ...body) => f.append(h("h2", {}, title, h("span", { class: "status " + cls, text: status })), ...body);
  const num = (t) => h("span", { class: "num", text: t });
  const need = (what) => h("p", { class: "empty", text: `Run ${what} on the Experiments tab to fill in the measured numbers here.` });
  const base = S_(liveBase, "baseline"), opt = S_(liveOpt, "optimized"), paper = S_(liveBase, "paper"), fast = S_(liveBase, "fast");
  const rea = S_(off, "reactive"), nei = S_(off, "neighbors"), obase = S_(off, "baseline"), ver = S_(off, "verified");

  sec("1. The wait that matters is not the database", "measured", "yes",
    h("p", {}, "The paper reports a 316x faster lookup on a cache hit, from 110 ms to 0.35 ms. That is real, but a caller waits for three things: understanding the question, finding pages, and the model's first word. Measured here, embedding the question through an API took ", num("about 680 ms"), " and GPT-4o-mini's first token ", num("about 1.2 s"), ". The database trip the cache removes is a small slice of that. Embedding on the device (", num("5 ms"), ") and not waiting for the model at all are bigger levers."));

  sec("2. Answer before being asked", "built, measured", "part",
    h("p", {}, "While the caller listens, the background agent can write the answer to the question it expects. If the caller then asks something close enough, and the pages behind the draft are in memory and confirmed by the database, Kairo speaks the draft with no model wait. This borrows the draft-then-verify structure of Speculative RAG (Wang et al., Google)."),
    base && opt ? h("p", {}, `On 100 scripted calls with GPT answers, the tuned strategy's median wait was `, num(fmtMs(opt.user_p50)), " against ", num(fmtMs(base.user_p50)), " for traditional RAG, with answers correct ", num(pct(opt.accuracy)), " vs ", num(pct(base.accuracy)), ". Pre-drafted answers served ", num(pct(opt.draft_rate)), " of turns. The slowest 10% got worse, ", num(fmtMs(opt.user_p90)), " vs ", num(fmtMs(base.user_p90)), ", because background speculation shares the API with the live answer and corrections cost a second pass.") : need("a live comparison (GPT answers, baseline and optimized)"),
    h("p", {}, "So the median gain is modest when the model's first token takes about a second, and drafts are the only lever that removes it. Raising the share of turns they cover, without serving a wrong draft, is the open question."));

  sec("3. Is a hit a good hit?", "measured", "yes",
    h("p", {}, "A hit rate counts every time memory held something above the similarity threshold. It does not check that those pages are the ones the database would have returned."),
    rea && obase ? h("p", {}, "With a 157-page knowledge base and on-device embeddings, a memory-only cache hit ", num(pct(rea.hit_rate)), " of the time, but the pages it served matched the database's top three only ", num(pct(rea.fidelity)), " of the time, and the right source page was used ", num(pct(rea.evidence)), " of the time against ", num(pct(obase.evidence)), " for a plain lookup.") : need("an offline comparison"),
    paper && fast ? h("p", {}, "The same gap shows up in answers. With GPT, the paper's design answered ", num(pct(paper.accuracy)), " correctly and an unverified, faster variant ", num(pct(fast.accuracy)), ", against ", num(pct(base?.accuracy)), " for plain RAG.") : null,
    h("p", {}, "The fix borrows from RaLMSpec: speculate, then verify. On a hit, start the model with remembered pages and check the database in parallel. The check takes about 110 ms and the first token about a second, so it finishes before anything is spoken. If the top database page is missing, cancel and answer again. Hit rate drops because wrong hits become corrections, and accuracy returns to plain-RAG level."),
    off ? h("div", { class: "tblwrap" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", { text: "Offline run" }), ["Hit rate", "Right page", "Fidelity", "Wait p50"].map((t) => h("th", { text: t })))),
      h("tbody", {}, Object.entries(off.profiles).map(([k, p]) => h("tr", {}, h("td", { text: p.label }), h("td", { text: pct(p.summary.hit_rate) }), h("td", { text: pct(p.summary.evidence) }), h("td", { text: pct(p.summary.fidelity) }), h("td", { text: fmtMs(p.summary.user_p50) })))))) : null);

  sec("4. Predict without a language model", "measured", "part",
    h("p", {}, "Asking GPT for follow-ups costs a call per turn. A cheaper guess: after finding the pages for this question, load the pages nearest to them. No model, no embedding call."),
    rea && nei ? h("p", {}, "On the offline runs it matched memory-only hit rates (", num(pct(nei.hit_rate)), " vs ", num(pct(rea.hit_rate)), ") and served better-matching pages (fidelity ", num(pct(nei.fidelity)), " vs ", num(pct(rea.fidelity)), "). Whether it competes with GPT prediction on conversations that jump topics needs the live comparison.") : need("an offline comparison"));

  sec("5. Start before the caller finishes", "built, not yet measured", "open",
    h("p", {}, "Stream RAG (Arora et al.) predicts tool calls while the user is still speaking. Kairo does the retrieval half: partial text, typed or from the browser's speech recognition, triggers a lookup that fills memory before the final transcript arrives. Violet lamps on the board show it. We have not measured how much it helps; the experiment is to replay calls word by word and compare time-to-first-word."));

  f.append(h("h2", { text: "What this builds on" }),
    h("div", { class: "tblwrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["Work", "Idea", "Used here as"].map((t) => h("th", { text: t })))), h("tbody", {},
      [["VoiceAgentRAG (Qiu et al., 2026)", "Background agent prefetches into a semantic cache", "The base system, reproduced"],
       ["Speculative RAG (Wang et al., 2024)", "Small drafts from document subsets, verified once", "Pre-drafted answers; smaller context per answer"],
       ["Stream RAG (Arora et al., 2025)", "Retrieve while the user is still speaking", "Partial-transcript lookups"],
       ["RaLMSpec (Zhang et al., 2024)", "Speculative retrieval with batched verification", "Verify hits against the database in parallel"]]
      .map((r) => h("tr", {}, r.map((c) => h("td", { text: c }))))))));

  f.append(h("h2", { text: "Open problems" }),
    h("ul", {}, [
      "Real calls. The scripted calls are predictable by construction. The first thing to learn is how predictable real callers are, from transcripts of a support line.",
      "A learned predictor. Replace GPT with a small model over topic transitions learned from call logs, so prediction costs nothing and gets better with use.",
      "When is a draft safe to speak? Rates and fees change. Drafts need provenance, expiry tied to knowledge-base edits, and a policy for answers that must never be stale.",
      "Barge-in. People interrupt. Interrupting should cancel the answer in progress and re-aim the background agent at the new question.",
      "Cost. Speculation spends model calls on questions never asked. A cost per saved millisecond, by strategy, would tell an operator what to turn on.",
      "Bigger knowledge bases. With thousands of pages, hit rates fall and prediction matters more. The experiments here use 157."].map((t) => h("li", { text: t }))));

  f.append(h("h2", { text: "Reproduce it" }),
    h("p", {}, h("span", { class: "num", text: "kairo bench --domain bank --distractors 64 --profiles baseline,paper,optimized --embedder local --llm openai --json data/experiments/run.json" })),
    h("p", { text: "Everything on the Experiments tab can be run from the command line, and the same scripted calls drive the Call tab." }));
}

/* ===================================================== boot */
(async function boot() {
  await loadInfo();
  const tab = location.hash.slice(1); if (["call", "exp", "res"].includes(tab)) showTab(tab);
  connect();
})();
})();
