"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const state = { config: null, tasks: [], runs: [], selected: null, view: "diff", busy: false, timer: null, generation: 0 };
  const activeStatuses = new Set(["queued", "running"]);
  const statusNames = { queued: "QUEUED", running: "RUNNING", crashed: "INTERRUPTED", passed: "PASSED", failed: "FAILED", blocked: "BLOCKED" };

  async function request(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: { "Accept": "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers },
    });
    let data;
    try { data = await response.json(); } catch { throw new Error(`The server returned an unreadable response (${response.status}).`); }
    if (!response.ok) {
      const detail = data?.error || data?.detail || data?.message;
      throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status}).`);
    }
    return data;
  }

  function showError(error) {
    $("error-message").textContent = error instanceof Error ? error.message : String(error);
    $("error-banner").hidden = false;
  }

  function formatNumber(value) {
    return Number.isFinite(Number(value)) ? Number(value).toLocaleString() : "—";
  }

  function formatDuration(ms) {
    if (!Number.isFinite(Number(ms))) return "—";
    const seconds = Number(ms) / 1000;
    if (seconds < 1) return `${Math.round(Number(ms))} ms`;
    if (seconds < 60) return `${seconds.toFixed(1)} s`;
    return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  }

  function readableTime(value) {
    if (!value) return "";
    const date = new Date(typeof value === "number" && value < 1e12 ? value * 1000 : value);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  }

  function taskTitle(id) {
    return state.tasks.find((task) => task.id === id)?.title || id || "Repair task";
  }

  function liveReady() {
    return Boolean(state.config?.nebius_key_configured && state.config?.nebius_model && state.config?.docker_available && state.config?.docker_test_image_available);
  }

  function renderConfiguration() {
    const liveOption = $("provider").querySelector('option[value="nebius"]');
    liveOption.disabled = !liveReady();
    if (!liveReady() && $("provider").value === "nebius") $("provider").value = "fixture";
    const missing = [];
    if (!state.config?.nebius_key_configured) missing.push("Nebius API key");
    if (!state.config?.nebius_model) missing.push("NVIDIA model ID");
    if (!state.config?.docker_available) missing.push("Docker daemon");
    if (!state.config?.docker_test_image_available) missing.push("Docker test image");
    $("live-readiness").textContent = liveReady()
      ? `Live mode ready · ${state.config.nebius_model}`
      : `Live mode needs: ${missing.join(", ")}.`;
    renderModeNote();
    renderControls();
  }

  function renderModeNote() {
    const live = $("provider").value === "nebius";
    $("mode-note").classList.toggle("live", live);
    $("mode-note-text").textContent = live
      ? "Live model — makes metered requests to Nebius."
      : "Offline fixture — no model API calls.";
  }

  function renderTasks() {
    const select = $("task");
    select.replaceChildren();
    if (!state.tasks.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No tasks available";
      select.append(option);
    }
    state.tasks.forEach((task) => {
      const option = document.createElement("option");
      option.value = task.id;
      option.textContent = task.title;
      select.append(option);
    });
    renderTaskDescription();
    renderControls();
  }

  function renderTaskDescription() {
    $("task-description").textContent = state.tasks.find((task) => task.id === $("task").value)?.description || "A small codebase with independent acceptance tests.";
  }

  function renderControls() {
    const selected = state.selected;
    $("run-button").disabled = state.busy || !$("task").value || !state.config || ($("provider").value === "nebius" && !liveReady());
    $("run-button").firstElementChild.textContent = state.busy ? "Working…" : "Run experiment";
    $("crash-button").disabled = state.busy || selected?.status !== "running";
    $("resume-button").disabled = state.busy || !["crashed", "queued", "blocked"].includes(selected?.status);
    $("resume-button").firstChild.textContent = selected?.status === "blocked" ? "Retry run " : selected?.policy === "restart" ? "Restart run " : selected?.status === "queued" ? "Start run " : "Resume run ";
    const report = $("download-report");
    report.classList.toggle("disabled", !selected);
    report.setAttribute("aria-disabled", String(!selected));
    if (selected) {
      report.href = `/api/runs/${encodeURIComponent(selected.id)}/report`;
      report.download = `crashlab-${selected.id}.json`;
    } else report.removeAttribute("href");
  }

  function upsertRun(run) {
    const index = state.runs.findIndex((item) => item.id === run.id);
    if (index < 0) state.runs.unshift(run);
    else state.runs[index] = run;
    renderHistory();
  }

  function renderHistory() {
    const history = $("run-history");
    history.replaceChildren();
    if (!state.runs.length) {
      const empty = document.createElement("p");
      empty.className = "empty-history";
      empty.textContent = "No experiments yet.";
      history.append(empty);
      return;
    }
    state.runs.slice(0, 8).forEach((run) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `history-item${run.id === state.selected?.id ? " selected" : ""}`;
      button.setAttribute("aria-pressed", String(run.id === state.selected?.id));
      const line = document.createElement("span");
      line.className = "history-first-line";
      const title = document.createElement("span");
      title.className = "history-title";
      title.textContent = taskTitle(run.task_id);
      const status = document.createElement("span");
      status.className = `history-state ${Object.hasOwn(statusNames, run.status) ? run.status : ""}`;
      status.textContent = statusNames[run.status] || run.status || "unknown";
      line.append(title, status);
      const detail = document.createElement("span");
      detail.className = "history-detail";
      detail.textContent = `${String(run.id).slice(0, 8)} · ${run.provider === "nebius" ? "NEBIUS" : "FIXTURE"} · ${readableTime(run.created_at)}`;
      button.append(line, detail);
      button.addEventListener("click", () => selectRun(run.id));
      history.append(button);
    });
  }

  function renderPatch() {
    const checkpoint = state.selected?.checkpoint || {};
    const value = state.view === "source" ? checkpoint.source : checkpoint.diff;
    const code = $("patch-code");
    code.replaceChildren();
    code.className = value ? "" : "empty-code";
    if (!value) {
      code.textContent = state.view === "source"
        ? "The saved source will appear after the model step."
        : "A generated patch will appear after the model step.";
    } else if (state.view === "diff") {
      String(value).split("\n").forEach((line) => {
        const span = document.createElement("span");
        span.className = "diff-line";
        if (line.startsWith("+") && !line.startsWith("+++")) span.classList.add("diff-add");
        else if (line.startsWith("-") && !line.startsWith("---")) span.classList.add("diff-remove");
        else if (line.startsWith("@@") || line.startsWith("+++") || line.startsWith("---")) span.classList.add("diff-heading");
        span.textContent = line || " ";
        code.append(span);
      });
    } else code.textContent = String(value);
    ["diff", "source"].forEach((view) => {
      $(`${view}-tab`).classList.toggle("active", view === state.view);
      $(`${view}-tab`).setAttribute("aria-selected", String(view === state.view));
    });
    $("patch-content").setAttribute("aria-labelledby", `${state.view}-tab`);
  }

  function renderTimeline(events) {
    const timeline = $("timeline");
    const openDetails = new Set([...timeline.querySelectorAll("details[open]")].map((detail) => detail.dataset.eventId));
    const followEnd = timeline.scrollHeight - timeline.scrollTop - timeline.clientHeight < 45;
    const previousScroll = timeline.scrollTop;
    timeline.replaceChildren();
    $("event-count").textContent = `${events.length} event${events.length === 1 ? "" : "s"}`;
    if (!events.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      const symbol = document.createElement("div");
      symbol.className = "empty-symbol";
      symbol.setAttribute("aria-hidden", "true");
      symbol.textContent = "↳";
      const heading = document.createElement("h3");
      heading.textContent = "The worker has not recorded an event yet.";
      const paragraph = document.createElement("p");
      paragraph.textContent = "Execution steps and injected faults will appear here.";
      empty.append(symbol, heading, paragraph);
      timeline.append(empty);
      return;
    }
    events.forEach((event, index) => {
      const kind = String(event.kind || "event");
      const item = document.createElement("div");
      item.className = "timeline-event";
      if (/crash|fault|fail|error|blocked|429/i.test(kind)) item.classList.add("fault");
      else if (/pass|complete|saved|checkpoint|resume|recover/i.test(kind)) item.classList.add("success");
      else if (index === events.length - 1 && state.selected?.status === "running") item.classList.add("active");
      const dot = document.createElement("span");
      dot.className = "event-dot";
      dot.setAttribute("aria-hidden", "true");
      const content = document.createElement("div");
      const head = document.createElement("div");
      head.className = "event-head";
      const message = document.createElement("span");
      message.className = "event-message";
      message.textContent = event.message || kind;
      const time = document.createElement("time");
      time.className = "event-time";
      time.textContent = readableTime(event.at);
      head.append(message, time);
      const tag = document.createElement("div");
      tag.className = "event-kind";
      tag.textContent = kind.toUpperCase().replaceAll("_", " ");
      content.append(head, tag);
      if (event.detail && Object.keys(event.detail).length) {
        const details = document.createElement("details");
        details.className = "event-details";
        details.dataset.eventId = String(event.id ?? index);
        details.open = openDetails.has(details.dataset.eventId);
        const summary = document.createElement("summary");
        summary.textContent = "Inspect event data";
        const pre = document.createElement("pre");
        pre.textContent = JSON.stringify(event.detail, null, 2);
        details.append(summary, pre);
        content.append(details);
      }
      item.append(dot, content);
      timeline.append(item);
    });
    timeline.scrollTop = followEnd ? timeline.scrollHeight : previousScroll;
  }

  function renderRun() {
    const run = state.selected;
    if (!run) return;
    const metrics = run.metrics || {};
    const tests = run.checkpoint?.tests;
    const isLiveProvider = run.provider === "nebius";
    $("run-title").textContent = taskTitle(run.task_id);
    $("run-subtitle").textContent = `${String(run.id).slice(0, 12)} · ${run.policy === "restart" ? "restart policy" : "checkpoint recovery"} · ${String(run.fault || "none").replaceAll("_", " ")}`;
    $("run-status").textContent = statusNames[run.status] || String(run.status || "unknown").toUpperCase();
    $("run-status").className = `badge status-${Object.hasOwn(statusNames, run.status) ? run.status : "idle"}`;
    $("run-mode").classList.toggle("live", Boolean(run.eligibility?.live_nvidia_model));
    $("run-mode").textContent = isLiveProvider
      ? (run.eligibility?.live_nvidia_model ? "LIVE NVIDIA MODEL · NEBIUS" : "NEBIUS CONFIGURED · LIVE USAGE NOT YET VERIFIED")
      : "OFFLINE FIXTURE · NO API CALLS";
    $("metric-verdict").textContent = tests ? (tests.passed ? "Pass" : tests.error ? "Blocked" : "Fail") : "—";
    $("metric-verdict").className = `verdict-value${tests ? (tests.passed ? " pass" : " fail") : ""}`;
    $("metric-verdict-note").textContent = tests ? (tests.passed ? "Independent checks passed" : tests.error ? "Test environment needs attention" : "Inspect test output below") : "Waiting for independent tests";
    $("metric-calls-label").textContent = isLiveProvider ? "MODEL CALLS" : "FIXTURE MODEL STEPS";
    $("metric-calls").textContent = formatNumber(isLiveProvider ? (metrics.model_calls ?? 0) : (metrics.fixture_calls ?? metrics.model_calls ?? 0));
    $("metric-calls-note").textContent = isLiveProvider ? `${formatNumber(metrics.retries ?? 0)} recorded retries` : "Synthetic steps · no API calls";
    const inputTokens = Number(metrics.input_tokens || 0);
    const outputTokens = Number(metrics.output_tokens || 0);
    $("metric-tokens").textContent = formatNumber(inputTokens + outputTokens);
    $("metric-tokens-note").textContent = isLiveProvider
      ? `${formatNumber(inputTokens)} in / ${formatNumber(outputTokens)} out${metrics.unknown_usage_requests ? ` · ${formatNumber(metrics.unknown_usage_requests)} requests with unknown usage` : ""}`
      : "Offline fixture · no billed tokens";
    $("metric-time").textContent = formatDuration(metrics.elapsed_ms ?? 0);
    $("metric-time-note").textContent = `${formatNumber(metrics.restarts ?? 0)} restart${Number(metrics.restarts) === 1 ? "" : "s"} · excludes idle wait`;
    $("current-phase").textContent = String(run.phase || run.status || "pending").replaceAll("_", " ").toUpperCase();
    $("tests-badge").textContent = tests ? (tests.passed ? "PASS" : tests.error ? "BLOCKED" : "FAIL") : "NOT RUN";
    $("tests-badge").className = `test-badge${tests ? (tests.passed ? " pass" : " fail") : ""}`;
    $("test-environment").textContent = `Environment: ${tests?.mode || "—"}`;
    $("test-duration").textContent = tests ? formatDuration(tests.duration_ms) : "—";
    $("test-output").textContent = tests ? ([tests.error, tests.stdout].filter(Boolean).join("\n\n") || "The test runner returned no output.") : "No acceptance tests have run.";
    renderTimeline(Array.isArray(run.events) ? run.events : []);
    renderPatch();
    renderControls();
  }

  function schedulePoll() {
    clearTimeout(state.timer);
    if (!state.selected || !activeStatuses.has(state.selected.status)) return;
    const id = state.selected.id;
    const generation = state.generation;
    state.timer = setTimeout(async () => {
      try {
        const run = await request(`/api/runs/${encodeURIComponent(id)}`);
        if (state.generation !== generation || state.selected?.id !== id) return;
        state.selected = run;
        upsertRun(run);
        renderRun();
        schedulePoll();
      } catch (error) { showError(error); }
    }, 1000);
  }

  async function selectRun(id) {
    if (state.busy) return;
    clearTimeout(state.timer);
    const generation = ++state.generation;
    try {
      const run = await request(`/api/runs/${encodeURIComponent(id)}`);
      if (generation !== state.generation) return;
      state.selected = run;
      upsertRun(run);
      renderRun();
      schedulePoll();
    } catch (error) { showError(error); }
  }

  async function changeRun(action) {
    if (!state.selected || state.busy) return;
    const id = state.selected.id;
    clearTimeout(state.timer);
    const generation = ++state.generation;
    state.busy = true;
    renderControls();
    try {
      const run = await request(`/api/runs/${encodeURIComponent(id)}/${action}`, { method: "POST", body: "{}" });
      upsertRun(run);
      if (generation === state.generation) {
        state.selected = run;
        renderRun();
        schedulePoll();
      }
    } catch (error) { showError(error); schedulePoll(); }
    finally { state.busy = false; renderControls(); }
  }

  $("run-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.busy || !$("task").value) return;
    state.busy = true;
    $("error-banner").hidden = true;
    renderControls();
    try {
      const body = { task_id: $("task").value, provider: $("provider").value, policy: $("policy").value, fault: $("fault").value };
      const created = await request("/api/runs", { method: "POST", body: JSON.stringify(body) });
      clearTimeout(state.timer);
      ++state.generation;
      state.selected = created;
      upsertRun(created);
      renderRun();
      const started = await request(`/api/runs/${encodeURIComponent(created.id)}/start`, { method: "POST", body: "{}" });
      state.selected = started;
      upsertRun(started);
      renderRun();
      schedulePoll();
    } catch (error) { showError(error); }
    finally { state.busy = false; renderControls(); }
  });

  $("task").addEventListener("change", renderTaskDescription);
  $("provider").addEventListener("change", () => { renderModeNote(); renderControls(); });
  $("dismiss-error").addEventListener("click", () => { $("error-banner").hidden = true; });
  $("crash-button").addEventListener("click", () => changeRun("crash"));
  $("resume-button").addEventListener("click", () => changeRun(state.selected?.status === "queued" ? "start" : "resume"));
  ["diff", "source"].forEach((view) => $(`${view}-tab`).addEventListener("click", () => { state.view = view; renderPatch(); }));
  $("refresh-runs").addEventListener("click", async () => {
    try {
      const runs = await request("/api/runs");
      state.runs = Array.isArray(runs) ? runs : [];
      renderHistory();
      if (state.selected) await selectRun(state.selected.id);
    } catch (error) { showError(error); }
  });

  async function initialize() {
    const results = await Promise.allSettled([request("/api/config"), request("/api/tasks"), request("/api/runs")]);
    if (results[0].status === "fulfilled") { state.config = results[0].value; renderConfiguration(); }
    if (results[1].status === "fulfilled") { state.tasks = Array.isArray(results[1].value) ? results[1].value : []; renderTasks(); }
    if (results[2].status === "fulfilled") { state.runs = Array.isArray(results[2].value) ? results[2].value : []; renderHistory(); }
    const failures = results.filter((result) => result.status === "rejected");
    if (failures.length) showError(failures.map((result) => result.reason.message).join(" "));
    if (state.runs.length) await selectRun(state.runs[0].id);
  }

  initialize();
})();
