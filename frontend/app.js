"use strict";
const $ = (id) => document.getElementById(id);
const state = {token: "", catalog: {champions: {}, items: {}, runes: {}}, status: null, report: null,
  pair: null, busy: false, seenJobs: new Set(), reportSequence: 0, coaching: new Map(), timer: null,
  library: [], visiblePairs: 24};
const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const format = (value, digits = 1) => value == null ? "—" : Number(value).toLocaleString(undefined, {maximumFractionDigits: digits});
const time = (ms) => `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}`;
const pairKey = (pair) => JSON.stringify([pair.champion.toLowerCase(), pair.opponent.toLowerCase(), pair.patch || ""]);
const query = (values) => new URLSearchParams(Object.entries(values).filter(([, v]) => v != null && v !== "")).toString();

async function api(path, data) {
  const response = await fetch(path, data ? {method: "POST", headers: {"Content-Type": "application/json", "X-LaneCoach-Token": state.token}, body: JSON.stringify(data)} : {});
  let result;
  try { result = await response.json(); } catch { throw new Error("The app returned an unreadable response. Refresh and try again."); }
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status}).`);
  return result;
}
function notice(message, error = false) {
  $("notice").textContent = message;
  $("notice").className = error ? "error" : "";
  $("notice").hidden = false;
  clearTimeout(state.timer);
  if (!error) state.timer = setTimeout(() => { $("notice").hidden = true; }, 9000);
}
function championInfo(name) {
  return Object.values(state.catalog.champions).find(c => c.id.toLowerCase() === name.toLowerCase() || c.name.toLowerCase() === name.toLowerCase());
}
function displayName(name) { return championInfo(name)?.name || name; }
function avatar(name, big = false) {
  const info = championInfo(name);
  return info ? `<img class="avatar ${big ? "big" : ""}" src="/api/assets/champions/${encodeURIComponent(info.id)}" alt="${escapeHTML(info.name)}" loading="lazy">` :
    `<span class="avatar ${big ? "big" : ""}" aria-hidden="true">${escapeHTML(name.slice(0, 2).toUpperCase())}</span>`;
}
function metric(label, value, sub = "") { return `<div class="metric"><span>${escapeHTML(label)}</span><strong>${escapeHTML(value)}</strong>${sub ? `<small>${escapeHTML(sub)}</small>` : ""}</div>`; }
function view(name) {
  document.querySelectorAll(".view").forEach(el => { el.hidden = el.id !== `${name}-view`; });
  document.querySelectorAll(".nav").forEach(el => el.classList.toggle("active", el.dataset.view === name));
  $("breadcrumb").textContent = {explore: "Matchup explorer", collect: "Collect games", settings: "Connections"}[name];
}
function tab(name) {
  document.querySelectorAll(".tab-panel").forEach(el => { el.hidden = el.id !== `${name}-tab`; });
  document.querySelectorAll("[data-tab]").forEach(el => { const selected = el.dataset.tab === name; el.classList.toggle("selected", selected); el.setAttribute("aria-selected", String(selected)); });
}
function renderStatus() {
  const status = state.status;
  $("overview").innerHTML = metric("Collected games", format(status.matches, 0)) + metric("Unique matchups", format(status.pairs, 0)) +
    metric("Lane timelines", format(status.timelines, 0)) + metric("Collected patches", format(status.patches.length, 0));
  const currentPatch = $("patch").value;
  $("patch").innerHTML = '<option value="">All collected patches</option>' + [...status.patches].sort((a, b) => b.localeCompare(a, undefined, {numeric: true})).map(p => `<option value="${escapeHTML(p)}">${escapeHTML(p)}</option>`).join("");
  if (currentPatch && !status.patches.includes(currentPatch)) $("patch").add(new Option(currentPatch, currentPatch));
  $("patch").value = currentPatch;
  const names = new Set([...status.champions.map(displayName), ...Object.values(state.catalog.champions).map(c => c.name)]);
  $("champions").innerHTML = [...names].sort().map(n => `<option value="${escapeHTML(n)}"></option>`).join("");
  $("riot-status").innerHTML = `<span class="connection ${status.riot_configured ? "" : "missing"}">${status.riot_configured ? "● Key configured" : "○ Key needed"}</span>`;
  $("openai-status").innerHTML = `<span class="connection ${status.ai_configured ? "" : "missing"}">${status.ai_configured ? "● Key configured · " + escapeHTML(status.model) : "○ Key needed for AI coaching"}</span>`;
  $("catalog-status").textContent = status.catalog_version ? `Cached reference version ${status.catalog_version}` : "No cached references yet. Refresh to load names and portraits.";
  $("ai-badge").textContent = status.ai_configured ? status.model : "SETUP NEEDED";
  renderJobs(status.jobs);
}
function renderJobs(jobs) {
  $("jobs").innerHTML = jobs.length ? jobs.map(job => {
    const p = job.progress || {}, values = job.result && job.kind !== "coaching" ? job.result : p;
    const details = Object.entries(values).filter(([, value]) => typeof value === "number").map(([key, value]) => `${key}: ${value}`).join(" · ");
    const label = job.kind === "collection" ? `${job.parameters.game_name}#${job.parameters.tag_line}` :
      job.parameters.champion ? `${displayName(job.parameters.champion)} vs ${displayName(job.parameters.opponent)}` : "Data Dragon references";
    return `<div class="job"><div class="job-top"><strong>${escapeHTML(job.kind)} · ${escapeHTML(label)}</strong><span class="status ${escapeHTML(job.status)}">${escapeHTML(job.status)}</span></div><p>${escapeHTML(new Date(job.created).toLocaleString())}${details ? " · " + escapeHTML(details) : ""}</p>${job.error ? `<p class="negative">${escapeHTML(job.error)}</p>` : ""}${["running","queued"].includes(job.status) ? '<progress aria-label="Job in progress"></progress>' : ""}</div>`;
  }).join("") : '<p class="muted">No jobs yet. Your next collection or coaching request will appear here.</p>';
}
async function loadLibrary() {
  const result = await api(`/api/matchups?${query({champion: $("library-filter").value, patch: $("patch").value, limit: 1000})}`);
  state.library = result.matchups;
  renderLibrary();
}
function renderLibrary() {
  $("pair-grid").innerHTML = state.library.length ? state.library.slice(0, state.visiblePairs).map((pair, i) =>
    `<button class="pair-card" data-pair-index="${i}"><div class="pair-champions">${avatar(pair.champion)}<div class="pair-names">${escapeHTML(displayName(pair.champion))}<br><span>vs ${escapeHTML(displayName(pair.opponent))}</span></div>${avatar(pair.opponent)}</div><div class="pair-bottom"><span><strong>${format(pair.matches, 0)}</strong> ${pair.matches === 1 ? "game" : "games"}${pair.matches < 30 ? " · small sample" : ""}</span><span><strong>${format(pair.win_rate)}%</strong> game wins</span><span class="arrow">↗</span></div></button>`
  ).join("") : '<div class="empty"><strong>No matchups here yet</strong>Try another champion or patch, or collect more ranked games.<br><button class="secondary" id="empty-collect">Collect games →</button></div>';
  document.querySelectorAll("[data-pair-index]").forEach(button => button.addEventListener("click", () => {
    const pair = state.library[Number(button.dataset.pairIndex)];
    openReport({champion: pair.champion, opponent: pair.opponent, patch: $("patch").value || null}).catch(e => notice(e.message, true));
  }));
  $("empty-collect")?.addEventListener("click", () => view("collect"));
  $("more-pairs").hidden = state.visiblePairs >= state.library.length;
  $("library-count").textContent = `Showing ${Math.min(state.visiblePairs, state.library.length)} of ${state.library.length} matching pairs (up to 1,000). Sorted by sample size. Game win rates describe the first champion in this dataset, not the full player population.`;
}
function statCell(stat) { return `${format(stat.value)}<small>n = ${stat.samples}</small>`; }
function deltaHTML(stat) { return `<strong class="${stat.value > 0 ? "positive" : stat.value < 0 ? "negative" : ""}">${stat.value > 0 ? "+" : ""}${format(stat.value)}</strong><span>n = ${stat.samples}</span>`; }
function asset(ids, kind) {
  return ids.map(id => { const reference = state.catalog[kind][String(id)]; return `<span class="asset">${reference ? `<img loading="lazy" src="/api/assets/${kind}/${encodeURIComponent(id)}" alt="">` : ""}${escapeHTML(reference?.name || `${kind === "items" ? "Item" : "Rune"} ${id}`)}</span>`; }).join("");
}
function renderReport(report) {
  const s = report.summary;
  $("library").hidden = true; $("report").hidden = false;
  $("champion").value = displayName(s.champion); $("opponent").value = displayName(s.opponent);
  $("matchup-heading").innerHTML = `<div class="matchup-title">${avatar(s.champion, true)}<div><h2>${escapeHTML(displayName(s.champion))} <span class="vs">VS</span> ${escapeHTML(displayName(s.opponent))}</h2><p>${escapeHTML(s.patch ? "Patch " + s.patch : "All collected patches")} · ${s.matches} unique games</p></div>${avatar(s.opponent, true)}</div><span class="pill">OBSERVED EVIDENCE</span>`;
  $("report-metrics").innerHTML = metric("Game win rate", s.win_rate == null ? "—" : `${format(s.win_rate)}%`, `${s.wins} wins / ${s.sample_size} appearances`) +
    metric("Unique games", format(s.matches, 0), s.matches < 30 ? "Small sample" : "Selected-player sample") +
    metric("Timeline games", format(report.timeline_matches, 0), "Early-lane evidence") +
    metric("Average CS / min", format(report.champion_stats.cs_per_minute.value), `n = ${report.champion_stats.cs_per_minute.samples}`);
  $("lane-stats").innerHTML = ["10", "15"].map(minute => `<div class="checkpoint"><div><strong>${minute} minutes</strong><br><span>Gold / CS difference</span></div><div class="delta">${deltaHTML(report.timeline[minute].gold_difference)}</div><div class="delta">${deltaHTML(report.timeline[minute].cs_difference)}</div></div>`).join("");
  $("observations").innerHTML = report.observations.map(o => `<p class="observation">${escapeHTML(o)}</p>`).join("");
  $("comparison").innerHTML = `<thead><tr><th>Metric</th><th>${escapeHTML(displayName(s.champion))}</th><th>${escapeHTML(displayName(s.opponent))}</th></tr></thead><tbody>` +
    [["kills", "Kills"], ["deaths", "Deaths"], ["assists", "Assists"], ["cs", "CS"], ["gold", "Gold"], ["cs_per_minute", "CS / minute"]].map(([key, label]) => `<tr><td>${label}</td><td>${statCell(report.champion_stats[key])}</td><td>${statCell(report.opponent_stats[key])}</td></tr>`).join("") + "</tbody>";
  $("warnings").innerHTML = report.warnings.map(w => `<p>${escapeHTML(w)}</p>`).join("") + `<p>Patch distribution: ${escapeHTML(Object.entries(report.patches).map(([patch, count]) => `${patch}: ${count} games`).join(" · ") || "No games")}</p>`;
  $("builds").innerHTML = [[s.champion, report.champion_stats], [s.opponent, report.opponent_stats]].map(([name, stats]) => `<article class="panel"><h2>${escapeHTML(displayName(name))}</h2>` +
    [["runes", "Recorded rune sets"], ["items", "Recorded final inventories"]].map(([key, label]) => `<h3>${label}</h3>${stats[key].length ? stats[key].map(set => `<div class="setup"><small>${set.games} games</small><div class="setup-icons">${asset(set.ids, key)}</div></div>`).join("") : '<p class="muted">No recorded setups.</p>'}`).join("") + "</article>").join("");
  $("games-table").innerHTML = `<thead><tr><th>Game</th><th>Patch</th><th>Result</th><th>K / D / A</th><th>CS</th><th>Gold</th><th>Timeline</th></tr></thead><tbody>` + report.matches.map(match => `<tr><td><button class="text-button game-detail" data-match-id="${escapeHTML(match.match_id)}">${escapeHTML(match.match_id)}</button></td><td>${escapeHTML(match.patch_major_minor || match.patch)}</td><td class="${match.champion_win ? "positive" : "negative"}">${match.champion_win ? "Win" : "Loss"}</td><td>${match.champion_kda.map(n => format(n, 0)).join(" / ")}</td><td>${format(match.champion_cs, 0)}</td><td>${format(match.champion_gold, 0)}</td><td>${match.has_timeline ? "Available" : "Not fetched"}</td></tr>`).join("") + "</tbody>";
  if (!report.matches.length) $("games-table").innerHTML += '<caption>No stored games for this matchup.</caption>';
  document.querySelectorAll(".game-detail").forEach(button => button.addEventListener("click", () => showMatch(button.dataset.matchId).catch(e => notice(e.message, true))));
  $("export").href = `/api/export?${query(state.pair)}`;
  const coaching = state.coaching.get(pairKey(state.pair));
  const lastCoach = state.status?.jobs.find(j => j.kind === "coaching" && pairKey(j.parameters) === pairKey(state.pair));
  $("coach-output").textContent = coaching || (lastCoach?.status === "failed" ? lastCoach.error : state.status?.ai_configured ? "Choose a focus and generate your coaching plan." : "To enable AI coaching, add OPENAI_API_KEY to backend/.env and restart LaneCoach. Reports and observations are already available.");
  $("copy-plan").hidden = !coaching;
  const savedPlan = state.status?.jobs.find(j => j.kind === "coaching" && j.status === "completed" && pairKey(j.parameters) === pairKey(state.pair));
  const basis = savedPlan?.result?.evidence_summary;
  $("coach-provenance").textContent = savedPlan ? `Plan generated ${new Date(savedPlan.created).toLocaleString()}${basis ? ` from ${basis.matches} games and ${basis.timeline_matches} timelines` : ""}. Regenerate after collecting new evidence.` : "";
}
async function openReport(pair, preserveTab = false) {
  const sequence = ++state.reportSequence;
  state.pair = pair;
  view("explore");
  $("search-form").classList.add("loading");
  try {
    const report = await api(`/api/report?${query(pair)}`);
    if (sequence !== state.reportSequence) return;
    state.report = report; state.pair = {champion: report.summary.champion, opponent: report.summary.opponent, patch: report.summary.patch};
    $("patch").value = pair.patch || "";
    history.replaceState(null, "", `#matchup?${query(state.pair)}`);
    if (!preserveTab) tab("overview");
    renderReport(report);
  } finally { if (sequence === state.reportSequence) $("search-form").classList.remove("loading"); }
}
async function startJob(path, data, message) {
  if (state.busy) throw new Error("Wait for the current job to finish.");
  const job = await api(path, data);
  state.busy = true; notice(message);
  if (job.kind === "coaching") $("coach-output").textContent = "Reading your report and preparing a coaching plan…";
  await refreshStatus();
}
async function refreshStatus(initial = false) {
  state.status = await api("/api/status"); state.token = state.status.token;
  state.busy = state.status.jobs.some(j => ["running", "queued"].includes(j.status));
  let dataChanged = false;
  const latestCoaching = new Set();
  for (const job of state.status.jobs) {
    if (["running", "queued"].includes(job.status)) continue;
    if (job.kind === "coaching" && job.status === "completed" && job.result?.text) {
      const key = pairKey(job.parameters);
      if (!latestCoaching.has(key)) state.coaching.set(key, job.result.text);
      latestCoaching.add(key);
    }
    if (!state.seenJobs.has(job.id)) {
      state.seenJobs.add(job.id);
      if (!initial) {
        notice(job.status === "completed" ? `${job.kind} complete.` : job.error || `${job.kind} ${job.status}.`, job.status !== "completed");
        dataChanged = true;
      }
    }
  }
  renderStatus();
  document.querySelectorAll("#collect-form button, #coach-submit, #fetch-timelines, #refresh-catalog").forEach(button => { button.disabled = state.busy; });
  if (dataChanged) {
    state.catalog = await api("/api/catalog"); renderStatus(); await loadLibrary();
    if (state.pair) await openReport(state.pair, true);
  }
}
async function showMatch(id) {
  const {match, timeline} = await api(`/api/matches/${encodeURIComponent(id)}`);
  $("match-detail").innerHTML = `<p class="eyebrow">RECORDED GAME</p><h2>${escapeHTML(displayName(match.champion))} vs ${escapeHTML(displayName(match.opponent))}</h2><p class="muted">${escapeHTML(id)} · ${escapeHTML(match.patch)} · ${format(match.game_duration / 60)} minutes</p>` +
    (timeline ? `<h3>Gold difference over time</h3><p class="muted">Positive = ${escapeHTML(displayName(match.champion))} ahead. Hover to inspect a snapshot.</p><canvas id="gold-chart" class="chart" aria-label="Gold difference between the two top laners over time" role="img"></canvas><p id="chart-readout" class="footnote"></p><h3>Early events involving the top laners</h3><p class="footnote">Events occur anywhere on the map; purchase undo events may reverse earlier purchases. Assists are not solo kills.</p><div id="events"></div>` : '<div class="evidence-note">No timeline has been fetched for this game. Use “Fetch lane timelines” in the matchup report.</div>');
  $("match-dialog").showModal();
  if (timeline) {
    drawChart(timeline, match);
    const who = id => id === timeline.champion_participant_id ? displayName(match.champion) : id === timeline.opponent_participant_id ? displayName(match.opponent) : id === 0 ? "Environment" : `Participant ${id}`;
    $("events").innerHTML = timeline.events.length ? timeline.events.map(event => {
      let description;
      if (event.type === "CHAMPION_KILL") description = `${who(event.killerId)} killed ${who(event.victimId)}${event.assistingParticipantIds?.length ? " · assists: " + event.assistingParticipantIds.map(who).join(", ") : ""}`;
      else if (event.type === "ITEM_UNDO") description = `${who(event.participantId)} undid an item transaction`;
      else description = `${who(event.participantId)} ${event.type === "ITEM_SOLD" ? "sold" : "bought"} ${state.catalog.items[String(event.itemId)]?.name || "item " + event.itemId}`;
      return `<div class="event"><time>${time(event.timestamp)}</time>${escapeHTML(description)}</div>`;
    }).join("") : '<p class="muted">No relevant early events recorded.</p>';
  }
}
function drawChart(timeline, match) {
  const canvas = $("gold-chart"), ctx = canvas.getContext("2d"), ratio = window.devicePixelRatio || 1;
  const width = 800, height = 240; canvas.width = width * ratio; canvas.height = height * ratio; ctx.scale(ratio, ratio);
  const points = timeline.points.filter(p => Number.isFinite(p.champion_gold) && Number.isFinite(p.opponent_gold));
  if (!points.length) { $("chart-readout").textContent = "No numeric gold snapshots available."; return; }
  const maximumTime = Math.max(...points.map(p => p.timestamp), 1), maximumGold = Math.max(...points.map(p => Math.abs(p.champion_gold - p.opponent_gold)), 500);
  const x = p => 62 + p.timestamp / maximumTime * 710, y = p => 115 - (p.champion_gold - p.opponent_gold) / maximumGold * 85;
  ctx.font = "11px Segoe UI"; ctx.lineWidth = 1;
  for (const value of [-maximumGold, 0, maximumGold]) {
    const yy = 115 - value / maximumGold * 85; ctx.strokeStyle = "#2b3930"; ctx.beginPath(); ctx.moveTo(62, yy); ctx.lineTo(772, yy); ctx.stroke();
    ctx.fillStyle = "#92a19c"; ctx.fillText(format(value, 0), 8, yy + 4);
  }
  ctx.fillText("0 min", 62, 224); ctx.fillText(`${format(maximumTime / 60000)} min`, 715, 224);
  ctx.strokeStyle = "#b7ed91"; ctx.lineWidth = 2; ctx.beginPath(); points.forEach((p, i) => { if (!i) ctx.moveTo(x(p), y(p)); else ctx.lineTo(x(p), y(p)); }); ctx.stroke();
  canvas.addEventListener("pointermove", event => {
    const target = (event.offsetX / canvas.clientWidth * width - 62) / 710 * maximumTime;
    const p = points.reduce((best, p) => Math.abs(p.timestamp - target) < Math.abs(best.timestamp - target) ? p : best, points[0]);
    $("chart-readout").textContent = `${time(p.timestamp)} · ${displayName(match.champion)}: ${format(p.champion_gold, 0)} gold, ${format(p.champion_cs, 0)} CS · ${displayName(match.opponent)}: ${format(p.opponent_gold, 0)} gold, ${format(p.opponent_cs, 0)} CS`;
  });
  $("chart-readout").textContent = `${points.length} recorded snapshots. Gold lead does not establish why a player was ahead.`;
}
function handle(action) { return event => { event?.preventDefault(); Promise.resolve().then(() => action(event)).catch(e => notice(e.message, true)); }; }
document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => view(button.dataset.view)));
document.querySelectorAll("[data-tab]").forEach(button => button.addEventListener("click", () => tab(button.dataset.tab)));
document.querySelectorAll("[role='tab']").forEach((button, index, tabs) => button.addEventListener("keydown", event => {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault(); const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
  tabs[next].focus(); tab(tabs[next].dataset.tab);
}));
$("search-form").addEventListener("submit", handle(() => openReport({champion: $("champion").value.trim(), opponent: $("opponent").value.trim(), patch: $("patch").value || null})));
$("swap").addEventListener("click", () => { [$("champion").value, $("opponent").value] = [$("opponent").value, $("champion").value]; });
$("library-filter").addEventListener("change", handle(() => { state.visiblePairs = 24; return loadLibrary(); }));
$("patch").addEventListener("change", handle(() => { state.visiblePairs = 24; return loadLibrary(); }));
$("more-pairs").addEventListener("click", () => { state.visiblePairs += 24; renderLibrary(); });
$("back-library").addEventListener("click", handle(async () => { state.reportSequence++; state.pair = null; $("report").hidden = true; $("library").hidden = false; history.replaceState(null, "", "#"); await loadLibrary(); }));
$("refresh").addEventListener("click", handle(async () => { await refreshStatus(); await loadLibrary(); if (state.pair) await openReport(state.pair, true); notice("Local data refreshed."); }));
$("collect-form").addEventListener("submit", handle(async () => {
  const values = Object.fromEntries(new FormData($("collect-form"))); values.count = Number(values.count); values.start = Number(values.start);
  await startJob("/api/collect", values, "Collection started. Progress appears below; rate limits may cause pauses.");
}));
$("fetch-timelines").addEventListener("click", handle(() => startJob("/api/timelines", {...state.pair, limit: 20}, "Fetching lane timelines. You can keep browsing while this runs.")));
$("refresh-catalog").addEventListener("click", handle(() => startJob("/api/catalog/refresh", {}, "Refreshing public champion, item, and rune references.")));
$("coach-form").addEventListener("submit", handle(() => startJob("/api/coach", {...state.pair, question: $("coach-question").value.trim()}, "AI coaching started.")));
$("copy-plan").addEventListener("click", handle(async () => { await navigator.clipboard.writeText($("coach-output").textContent); notice("Coaching plan copied."); }));
$("close-dialog").addEventListener("click", () => $("match-dialog").close());
document.addEventListener("error", event => { if (event.target.tagName === "IMG") { const fallback = document.createElement("span"); fallback.className = event.target.className || "asset"; fallback.textContent = event.target.alt ? event.target.alt.slice(0, 2).toUpperCase() : ""; event.target.replaceWith(fallback); } }, true);
async function init() {
  state.catalog = await api("/api/catalog"); await refreshStatus(true); await loadLibrary();
  if (location.hash.startsWith("#matchup?")) {
    const params = new URLSearchParams(location.hash.split("?")[1]);
    if (params.get("champion") && params.get("opponent")) await openReport({champion: params.get("champion"), opponent: params.get("opponent"), patch: params.get("patch")});
  }
  setInterval(() => { if (state.busy) refreshStatus().catch(e => notice(e.message, true)); }, 2000);
}
init().catch(e => notice(`${e.message} Make sure the LaneCoach server is running.`, true));
