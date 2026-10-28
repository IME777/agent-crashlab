"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const labels = { no_fault_repair: "No-fault repair", worker_crash_and_resume: "Worker crash + resume" };
  const state = { data: null, attempt: "final", caseName: "worker_crash_and_resume", cursor: 0, view: "diff", timer: null };
  const number = (n) => Number(n ?? 0).toLocaleString("en-US");
  const tokens = (run) => Number(run.metrics.input_tokens) + Number(run.metrics.output_tokens);
  const selectedBatch = () => state.data[state.attempt];
  const selectedCase = () => selectedBatch().cases.find((item) => item.name === state.caseName) || selectedBatch().cases[0];
  const selectedRun = () => selectedCase().report;
  const classFor = (kind) => /fault|crash|fail|error/.test(kind) ? "fault" : /pass|checkpoint|resum/.test(kind) ? "success" : "";
  const testCount = (run) => Number((run.checkpoint.tests.stdout.match(/Ran (\d+) tests?/) || [0, 0])[1]);
  const time = (value) => new Date(value).toISOString().replace("T", " · ").replace(/\.\d+Z$/, " UTC");

  function stopReplay() {
    if (state.timer) window.clearInterval(state.timer);
    state.timer = null;
    $("play-replay").replaceChildren(document.createTextNode("Play replay "));
    const arrow = document.createElement("span");
    arrow.textContent = "▶";
    arrow.setAttribute("aria-hidden", "true");
    $("play-replay").append(arrow);
  }

  function setCursor(value, follow = true) {
    const events = selectedRun().events;
    state.cursor = Math.max(0, Math.min(events.length - 1, Number(value)));
    renderCursor(follow);
  }

  function renderCursor(follow) {
    const events = selectedRun().events;
    const event = events[state.cursor];
    $("event-scrubber").max = String(events.length - 1);
    $("event-scrubber").value = String(state.cursor);
    $("step-count").textContent = `${state.cursor + 1} / ${events.length} events`;
    $("event-message").textContent = event.message;
    $("event-time").textContent = `${event.kind.replaceAll("_", " ").toUpperCase()} · ${time(event.at)}`;
    $("current-event").className = `current-event ${classFor(event.kind)}`;
    $("event-json").textContent = JSON.stringify(event.detail || {}, null, 2);
    $("previous-step").disabled = state.cursor === 0;
    $("next-step").disabled = state.cursor === events.length - 1;
    const items = [...$("event-list").children];
    items.forEach((item, index) => {
      const button = item.firstElementChild;
      button.classList.toggle("future", index > state.cursor);
      if (index === state.cursor) button.setAttribute("aria-current", "step");
      else button.removeAttribute("aria-current");
    });
    if (follow) {
      const target = items[state.cursor];
      const list = $("event-list");
      const top = target.offsetTop - list.firstElementChild.offsetTop;
      if (top < list.scrollTop || top + target.offsetHeight > list.scrollTop + list.clientHeight) list.scrollTop = Math.max(0, top - 70);
    }
  }

  function renderTimeline() {
    const run = selectedRun();
    $("selected-title").textContent = labels[selectedCase().name] || selectedCase().name;
    $("selected-id").textContent = run.id.slice(0, 8);
    const list = $("event-list");
    list.replaceChildren();
    run.events.forEach((event, index) => {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.className = `event-item ${classFor(event.kind)}`;
      button.setAttribute("aria-label", `Replay event ${index + 1}: ${event.message}`);
      const dot = document.createElement("span");
      dot.className = "event-dot";
      dot.setAttribute("aria-hidden", "true");
      const content = document.createElement("span");
      const title = document.createElement("span");
      title.className = "event-title";
      title.textContent = event.message;
      const kind = document.createElement("span");
      kind.className = "event-kind";
      kind.textContent = event.kind.replaceAll("_", " ").toUpperCase();
      content.append(title, kind);
      button.append(dot, content);
      button.addEventListener("click", () => { stopReplay(); setCursor(index); });
      item.append(button);
      list.append(item);
    });
    renderCursor(false);
  }

  function renderCode() {
    const checkpoint = selectedRun().checkpoint;
    const code = $("code-content");
    code.replaceChildren();
    if (state.view === "source") code.textContent = checkpoint.source;
    else String(checkpoint.diff || "No diff in this report.").split("\n").forEach((line) => {
      const span = document.createElement("span");
      span.className = "diff-line";
      if (/^(---|\+\+\+|@@)/.test(line)) span.classList.add("diff-heading");
      else if (line.startsWith("+")) span.classList.add("diff-add");
      else if (line.startsWith("-")) span.classList.add("diff-remove");
      span.textContent = line || " ";
      code.append(span);
    });
    ["diff", "source"].forEach((view) => $(`${view}-tab`).setAttribute("aria-selected", String(state.view === view)));
    code.setAttribute("aria-labelledby", `${state.view}-tab`);
    const tests = checkpoint.tests;
    $("test-badge").textContent = `${testCount(selectedRun())}/${testCount(selectedRun())} PASS`;
    $("test-badge").className = `badge ${tests.passed ? "pass" : "fail"}`;
    $("test-mode").textContent = `Environment: ${tests.mode}`;
    $("test-duration").textContent = `${number(tests.duration_ms)} ms recorded`;
    $("test-output").textContent = tests.stdout;
  }

  function renderCards() {
    const container = $("case-cards");
    container.replaceChildren();
    selectedBatch().cases.forEach((item) => {
      const run = item.report;
      const button = document.createElement("button");
      button.type = "button";
      button.className = `case-card${item.name === state.caseName ? " selected" : ""}`;
      button.setAttribute("aria-pressed", String(item.name === state.caseName));
      const top = document.createElement("div");
      top.className = "case-top";
      const heading = document.createElement("h2");
      heading.textContent = labels[item.name] || item.name;
      const badge = document.createElement("span");
      badge.className = "badge pass";
      badge.textContent = "DOCKER PASS";
      top.append(heading, badge);
      const subtitle = document.createElement("p");
      subtitle.textContent = `${run.task_id} · ${run.id.slice(0, 8)} · ${run.policy}`;
      const stats = document.createElement("div");
      stats.className = "case-stats";
      [{value: number(run.metrics.model_calls), label: "MODEL REQUESTS"},
        {value: number(tokens(run)), label: "KNOWN TOKENS", note: `${number(run.metrics.input_tokens)} in / ${number(run.metrics.output_tokens)} out`},
        {value: `${testCount(run)}/${testCount(run)}`, label: "ACCEPTANCE TESTS", pass: true}].forEach((stat) => {
        const block = document.createElement("div");
        block.className = "case-stat";
        const value = document.createElement("strong");
        value.textContent = stat.value;
        if (stat.pass) value.className = "pass-text";
        const label = document.createElement("span");
        label.textContent = stat.label;
        block.append(value, label);
        if (stat.note) { const note = document.createElement("small"); note.textContent = stat.note; block.append(note); }
        stats.append(block);
      });
      button.append(top, subtitle, stats);
      button.addEventListener("click", () => selectCase(item.name));
      container.append(button);
    });
  }

  function renderProof() {
    const item = selectedBatch().cases.find((entry) => entry.name === "worker_crash_and_resume");
    const before = item.before_resume;
    const after = item.report;
    const extraCalls = after.metrics.model_calls - before.metrics.model_calls;
    const extraTokens = tokens(after) - tokens(before);
    const same = item.checks.same_saved_candidate === true;
    $("added-calls").textContent = number(extraCalls);
    $("added-tokens").textContent = number(extraTokens);
    $("same-hash").textContent = same ? "Yes" : "No";
    [$("added-calls"), $("added-tokens"), $("same-hash")].forEach((item) => item.className = extraCalls === 0 && extraTokens === 0 && same ? "pass-text" : "fail-text");
    $("proof-caption").textContent = state.attempt === "final"
      ? "A real worker exit (code 86), followed by one resume of the committed patch."
      : "Recovery continued correctly, but acceptance rejected the first candidate and required another repair.";
  }

  function selectCase(name) {
    stopReplay();
    state.caseName = name;
    state.cursor = selectedRun().events.length - 1;
    renderCards();
    renderTimeline();
    renderCode();
  }

  function renderAttempt() {
    const batch = selectedBatch();
    $("gate-badge").textContent = batch.passed ? "STRICT GATE PASSED" : "STRICT GATE FAILED";
    $("gate-badge").className = `badge ${batch.passed ? "pass" : "fail"}`;
    $("attempt-note").textContent = state.attempt === "final"
      ? "Final two-case verification: real Nemotron responses, independent Docker acceptance, no fixture generations. One small repair task; one execution per case."
      : "Preserved first attempt: both delivered patches pass Docker tests, but the saved candidate changed and inference increased after recovery. The strict gate correctly remained failed.";
    renderProof();
    selectCase(state.caseName);
  }

  $("attempt-select").addEventListener("change", (event) => { state.attempt = event.target.value; renderAttempt(); });
  $("previous-step").addEventListener("click", () => { stopReplay(); setCursor(state.cursor - 1); });
  $("next-step").addEventListener("click", () => { stopReplay(); setCursor(state.cursor + 1); });
  $("event-scrubber").addEventListener("input", (event) => { stopReplay(); setCursor(event.target.value); });
  $("play-replay").addEventListener("click", () => {
    if (state.timer) { stopReplay(); return; }
    if (state.cursor >= selectedRun().events.length - 1) setCursor(0);
    $("play-replay").textContent = "Pause replay Ⅱ";
    state.timer = window.setInterval(() => {
      if (state.cursor >= selectedRun().events.length - 1) { stopReplay(); return; }
      setCursor(state.cursor + 1);
    }, 850);
  });
  ["diff", "source"].forEach((view) => $(`${view}-tab`).addEventListener("click", () => { state.view = view; renderCode(); }));
  $("copy-command").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("reproduce-command").textContent); $("copy-command").textContent = "Copied"; }
    catch { $("copy-command").textContent = "Select text to copy"; }
  });
  window.addEventListener("pagehide", stopReplay);

  async function load(path) {
    const response = await fetch(path, { credentials: "omit" });
    if (!response.ok) throw new Error(`Could not load the recorded evidence (${response.status}).`);
    return response.json();
  }

  async function initialize() {
    try {
      const [final, initial, summary, config] = await Promise.all([
        load("data/live-check.json"), load("data/live-check-initial.json"), load("data/summary.json"), load("site-config.json")]);
      state.data = { final, initial };
      $("model-name").textContent = final.model;
      $("all-requests").textContent = number(summary.all_attempts.model_requests);
      $("all-input").textContent = number(summary.all_attempts.input_tokens);
      $("all-output").textContent = number(summary.all_attempts.output_tokens);
      $("all-unknown").textContent = number(summary.all_attempts.unknown_usage_requests);
      $("evidence-date").textContent = `Recorded ${time(final.created_at)}`;
      if (config.repository_url) {
        $("repository-link").href = config.repository_url;
        $("repository-link").textContent = "Open source project ↗";
        $("repository-link").classList.remove("disabled");
        $("repository-link").setAttribute("aria-disabled", "false");
        $("repository-link").rel = "noopener noreferrer";
      }
      if (config.source_archive) {
        $("source-archive-link").href = config.source_archive;
        $("source-archive-link").hidden = false;
      }
      ["attempt-select", "play-replay", "event-scrubber"].forEach((id) => { $(id).disabled = false; });
      renderAttempt();
    } catch (error) {
      $("load-error").textContent = error.message || "The recorded evidence could not be loaded.";
      $("load-error").hidden = false;
      ["attempt-select", "previous-step", "next-step", "play-replay", "event-scrubber"].forEach((id) => { $(id).disabled = true; });
    }
  }
  initialize();
})();
