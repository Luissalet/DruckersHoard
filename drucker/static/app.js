import { TEXT } from "/static/i18n.js";

const main = document.getElementById("main");
let lang = (() => { try { return localStorage.getItem("drucker-lang"); } catch { return null; } })() || (navigator.language || "es").slice(0, 2);
if (!TEXT[lang]) lang = "es";
const t = (k) => TEXT[lang][k] ?? k;
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const $ = (sel, root = main) => root.querySelector(sel);
const $$ = (sel, root = main) => [...root.querySelectorAll(sel)];
const ctx = { page: "", engagement: null, deliverable: null };

async function api(path, method = "GET", body) {
  const res = await fetch(path, { method, headers: { "X-Lang": lang, ...(body ? { "Content-Type": "application/json" } : {}) }, body: body ? JSON.stringify(body) : undefined });
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : await res.text();
  if (!res.ok) { const e = new Error(data.error || data.detail || res.statusText); e.data = data; throw e; }
  return data;
}
let toastTimer;
function toast(msg, bad = false) {
  const el = document.getElementById("toast");
  el.textContent = msg; el.className = "show" + (bad ? " err" : "");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (el.className = ""), 4500);
}
const fail = (e) => toast(e.message, true);
const guard = (fn) => async (...a) => { try { await fn(...a); } catch (e) { fail(e); } };
const opts = (list, cur, labelFn = (x) => t("v_" + x)) => list.map((v) => `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(labelFn(v))}</option>`).join("");
const lines = (s) => s.split("\n").map((x) => x.trim()).filter(Boolean);
const range = (h) => (h.max === h.min ? `${h.min}` : `${h.min}–${h.max}`) + " " + t("hours");
const money = (m) => (m ? ` · ${m.min}–${m.max} ${esc(m.currency)}` : "");
const shortHash = (h) => (h ? h.slice(0, 10) + "…" : t("hash_unknown"));

// ---------- shell
function shell() {
  document.documentElement.lang = lang;
  document.getElementById("tagline").textContent = t("tagline");
  $$("[data-lang]", document).forEach((b) => b.setAttribute("aria-pressed", b.dataset.lang === lang));
  const routes = [["encargos", "nav_eng"], ["comparar", "nav_cmp"], ["propuesta", "nav_prop"], ["revision", "nav_rev"], ["paquete", "nav_pkg"]];
  const cur = location.hash.split("/")[1] || "encargos";
  document.getElementById("nav").innerHTML = routes.map(([r, k]) => `<a href="#/${r}"${cur === r ? ' aria-current="page"' : ""}>${esc(t(k))}</a>`).join("") + `<a href="/docs">${esc(t("api"))}</a>`;
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-lang]");
  if (b) { lang = b.dataset.lang; try { localStorage.setItem("drucker-lang", lang); } catch {} route(); }
});
window.addEventListener("hashchange", route);

async function route() {
  shell();
  const [, page = "encargos", id] = location.hash.split("/");
  ctx.page = page;
  try {
    if (page === "encargos") return id ? await fileView(id) : await listView();
    if (page === "comparar") return await compareView();
    if (page === "propuesta") return await proposalView();
    if (page === "revision") return await reviewView();
    if (page === "paquete") return await packageView();
    location.hash = "#/encargos";
  } catch (e) { main.innerHTML = `<div class="errbox">${esc(t("err_load"))} ${esc(e.message)}</div>`; }
}

async function engagementPicker(selected, onChange, extra = "") {
  const list = await api("/api/engagements");
  const html = `<label>${esc(t("pick_eng"))}<select id="eng"><option value="">${esc(t("select"))}</option>${list.map((e) => `<option value="${e.id}"${e.id === selected ? " selected" : ""}>${esc(e.name)}</option>`).join("")}</select></label>`;
  return { html, bind: () => $("#eng").addEventListener("change", (ev) => { ctx.engagement = ev.target.value || null; onChange(ev.target.value); }) };
}

// ---------- Encargos: list
async function listView() {
  ctx.engagement = null;
  const list = await api("/api/engagements");
  main.innerHTML = `<h1>${esc(t("engagements"))}</h1><p class="intro">${esc(t("people_note"))}</p>
  <div class="bar"><button id="ex">${esc(t("load_example"))}</button></div>
  <div class="scroll"><table><thead><tr><th>${esc(t("name"))}</th><th>${esc(t("client"))}</th><th>${esc(t("status"))}</th><th>${esc(t("budget"))}</th><th>${esc(t("milestones"))}</th></tr></thead><tbody>
  ${list.map((e) => `<tr class="click" data-id="${e.id}" tabindex="0"><td>${esc(e.name)}</td><td>${esc(e.client_name)}</td><td><span class="chip">${esc(t("s_" + e.status))}</span></td><td class="num">${budgetText(e)}</td><td class="num">${e.milestones}</td></tr>`).join("") || `<tr><td colspan="5" class="muted">${esc(t("none"))}</td></tr>`}
  </tbody></table></div>
  <h2>${esc(t("new_eng"))}</h2><form id="new" class="grid">
    <label>${esc(t("name"))}<input name="name" required /></label><label>${esc(t("client"))}<input name="client_name" /></label>
    <label>${esc(t("budget_min"))}<input name="budget_min" type="number" min="0" step="any" /></label><label>${esc(t("budget_max"))}<input name="budget_max" type="number" min="0" step="any" /></label>
    <label>${esc(t("currency"))}<input name="currency" value="EUR" maxlength="3" /></label>
    <label class="wide">${esc(t("origin"))}<textarea name="origin"></textarea></label>
    <div><button class="primary">${esc(t("create"))}</button></div></form>`;
  $$("tr.click").forEach((r) => { const go = () => (location.hash = "#/encargos/" + r.dataset.id); r.onclick = go; r.onkeydown = (e) => e.key === "Enter" && go(); });
  $("#ex").onclick = guard(async () => { const e = await api("/api/example/load", "POST"); location.hash = "#/encargos/" + e.id; });
  $("#new").onsubmit = guard(async (ev) => { ev.preventDefault(); const e = await api("/api/engagements", "POST", formBody(ev.target)); location.hash = "#/encargos/" + e.id; });
}
const budgetText = (e) => (e.budget_min == null && e.budget_max == null ? "—" : `${e.budget_min ?? "?"}–${e.budget_max ?? "?"} ${esc(e.currency)}`);
function formBody(form) {
  const o = {};
  for (const [k, v] of new FormData(form)) { if (v === "") continue; o[k] = k.startsWith("budget") || k === "amount" ? Number(v) : v; }
  return o;
}

// ---------- Encargos: file
const KINDS = {
  scope: { cols: ["title", "status", "origin", "deliverable"], fields: [["title", "text"], ["detail", "text"], ["status", "select", ["proposed", "agreed", "done", "dropped"]], ["origin", "select", ["initial", "agreement", "change"]], ["deliverable", "text"]] },
  milestone: { cols: ["title", "due", "status"], fields: [["title", "text"], ["due", "date"], ["status", "select", ["planned", "in_progress", "done", "late", "blocked"]], ["note", "text"]] },
  material: { cols: ["title", "kind", "ref"], fields: [["title", "text"], ["kind", "select", ["path", "url", "atlas", "note"]], ["ref", "text"], ["note", "text"]] },
  decision: { cols: ["what", "why", "date", "who"], fields: [["what", "text"], ["why", "text"], ["date", "date"], ["who", "text"]] },
  payment: { cols: ["title", "kind", "amount", "status", "date", "source"], fields: [["title", "text"], ["kind", "select", ["invoice", "payment"]], ["amount", "number"], ["currency", "text"], ["status", "select", ["planned", "issued", "paid", "overdue"]], ["date", "date"], ["ledger_id", "text"]] },
};
const FIELD_LABEL = { ledger_id: "ledger_ref", origin: "origin_f" };
let tab = "scope";

async function fileView(id) {
  ctx.engagement = id;
  const e = await api("/api/engagements/" + id);
  const tabs = ["scope", "milestone", "material", "decision", "deliverables", "payment", "history"];
  main.innerHTML = `<p><a href="#/encargos">← ${esc(t("back"))}</a></p><h1>${esc(e.name)}</h1><p class="intro">${esc(t("people_note"))}</p>
  <form id="head" class="grid">
    <label>${esc(t("name"))}<input name="name" value="${esc(e.name)}" required /></label>
    <label>${esc(t("client"))}<input name="client_name" value="${esc(e.client_name)}" /></label>
    <label>${esc(t("client_ref"))}<input name="people_id" value="${esc(e.client_ref?.id || "")}" /></label>
    <label>${esc(t("status"))}<select name="status">${opts(["lead", "active", "paused", "closed"], e.status, (x) => t("s_" + x))}</select></label>
    <label>${esc(t("budget_min"))}<input name="budget_min" type="number" min="0" step="any" value="${e.budget_min ?? ""}" /></label>
    <label>${esc(t("budget_max"))}<input name="budget_max" type="number" min="0" step="any" value="${e.budget_max ?? ""}" /></label>
    <label>${esc(t("currency"))}<input name="currency" value="${esc(e.currency)}" maxlength="3" /></label>
    <label class="wide">${esc(t("origin"))}<textarea name="origin">${esc(e.origin)}</textarea></label>
    <label class="wide">${esc(t("notes"))}<textarea name="notes">${esc(e.notes)}</textarea></label>
    <div class="bar"><button class="primary">${esc(t("save"))}</button><button type="button" id="del" class="danger">${esc(t("delete"))}</button></div></form>
  <div class="tabs" role="tablist">${tabs.map((k) => `<button role="tab" data-tab="${k}" aria-selected="${k === tab}">${esc(t("tab_" + k))}</button>`).join("")}</div><div id="pane"></div>`;
  $("#head").onsubmit = guard(async (ev) => {
    ev.preventDefault();
    const f = new FormData(ev.target), body = {};
    for (const k of ["name", "client_name", "status", "currency", "origin", "notes"]) body[k] = f.get(k);
    for (const k of ["budget_min", "budget_max"]) body[k] = f.get(k) === "" ? null : Number(f.get(k));
    const pid = f.get("people_id").trim();
    body.client_ref = pid ? { app: "people", id: pid, label: f.get("client_name") } : null;
    await api("/api/engagements/" + id, "PUT", body); toast(t("saved")); await fileView(id);
  });
  $("#del").onclick = guard(async () => { if (confirm(t("delete") + "?")) { await api("/api/engagements/" + id, "DELETE"); location.hash = "#/encargos"; } });
  $$("[data-tab]").forEach((b) => (b.onclick = () => { tab = b.dataset.tab; fileView(id).catch(fail); }));
  await pane(e);
}

async function pane(e) {
  const el = $("#pane");
  if (tab === "history") {
    const h = await api(`/api/engagements/${e.id}/history`);
    el.innerHTML = h.length ? `<ul class="plain">${h.map((x) => `<li><span class="muted small">${esc(x.ts.replace("T", " ").slice(0, 16))}</span> <span class="chip">${esc(x.action)}</span> ${esc(x.summary)}</li>`).join("")}</ul>` : `<p class="muted">${esc(t("history_empty"))}</p>`;
    return;
  }
  if (tab === "deliverables") {
    el.innerHTML = (e.deliverables.map((d) => `<div class="card"><strong>${esc(d.name)}</strong> <span class="chip">${d.versions.length} ${esc(t("versions"))}</span> ${d.to_deliver ? `<span class="chip ok">${esc(t("to_deliver"))}: v${d.to_deliver}</span>` : ""}
      <div><a href="#/revision" data-open="${d.id}">${esc(t("open_review"))}</a></div></div>`).join("") || `<p class="muted">${esc(t("none"))}</p>`) +
      `<form id="nd" class="bar"><label>${esc(t("new_deliverable"))}<input name="name" required /></label><label>${esc(t("kind"))}<input name="kind" placeholder="pdf, glb…" /></label><button class="primary">${esc(t("add"))}</button></form>`;
    $$("[data-open]").forEach((a) => (a.onclick = () => { ctx.engagement = e.id; ctx.deliverable = a.dataset.open; }));
    $("#nd").onsubmit = guard(async (ev) => { ev.preventDefault(); await api(`/api/engagements/${e.id}/deliverables`, "POST", formBody(ev.target)); await fileView(e.id); });
    return;
  }
  const def = KINDS[tab], items = e.items[tab];
  const cell = (it, c) => {
    if (c === "source") return `<span class="chip ${it.source === "ledger" ? "ok" : "warn"}">${esc(t(it.source))}</span>`;
    const v = it[c];
    return ["status", "origin", "kind"].includes(c) && v ? esc(t("v_" + v)) : esc(v ?? "");
  };
  el.innerHTML = `<div class="scroll"><table><thead><tr>${def.cols.map((c) => `<th>${esc(t(FIELD_LABEL[c] === "origin_f" ? "origin_f" : c))}</th>`).join("")}<th></th></tr></thead><tbody>
    ${items.map((it) => `<tr>${def.cols.map((c) => `<td class="${c === "amount" ? "num" : ""}">${cell(it, c)}</td>`).join("")}<td class="num"><button class="small" data-edit="${it.id}">${esc(t("edit"))}</button> <button class="small danger" data-rm="${it.id}">×</button></td></tr>`).join("") || `<tr><td colspan="${def.cols.length + 1}" class="muted">${esc(t("none"))}</td></tr>`}</tbody></table></div>
    <form id="itemf" class="grid card"></form>`;
  const form = $("#itemf");
  const draw = (it = {}) => {
    form.innerHTML = def.fields.map(([k, type, list]) => {
      const lbl = esc(t(FIELD_LABEL[k] || k));
      const v = k === "ledger_id" ? it.ledger?.id : it[k];
      if (type === "select") return `<label>${lbl}<select name="${k}">${opts(list, v ?? list[0])}</select></label>`;
      return `<label>${lbl}<input name="${k}" type="${type}"${type === "number" ? ' min="0" step="any"' : ""} value="${esc(v ?? (k === "currency" ? e.currency : ""))}" /></label>`;
    }).join("") + `<div class="bar"><input type="hidden" name="__id" value="${it.id || ""}" /><button class="primary">${esc(it.id ? t("save") : t("add"))}</button>${it.id ? `<button type="button" id="cx">${esc(t("cancel"))}</button>` : ""}</div>`;
    const cx = $("#cx", form); if (cx) cx.onclick = () => draw();
  };
  draw();
  form.onsubmit = guard(async (ev) => {
    ev.preventDefault();
    const f = new FormData(form), body = {}, itemId = f.get("__id");
    for (const [k, v] of f) { if (k === "__id") continue; if (v === "" && !itemId) continue; body[k] = k === "amount" ? (v === "" ? null : Number(v)) : v === "" ? (k === "date" || k === "due" ? null : "") : v; }
    if (body.ledger_id !== undefined) { body.ledger = body.ledger_id ? { app: "ledger", id: body.ledger_id } : null; delete body.ledger_id; }
    await api(`/api/engagements/${e.id}/items/${tab}` + (itemId ? "/" + itemId : ""), itemId ? "PUT" : "POST", body);
    toast(t("saved")); await fileView(e.id);
  });
  $$("[data-edit]").forEach((b) => (b.onclick = () => { draw(items.find((i) => i.id === b.dataset.edit)); form.scrollIntoView({ block: "nearest" }); }));
  $$("[data-rm]").forEach((b) => (b.onclick = guard(async () => { await api(`/api/engagements/${e.id}/items/${b.dataset.rm}`, "DELETE"); await fileView(e.id); })));
}

// ---------- Comparar alcance
async function compareView() {
  const picker = await engagementPicker(ctx.engagement, () => {});
  main.innerHTML = `<h1>${esc(t("cmp_title"))}</h1><p class="intro">${esc(t("cmp_intro"))}</p>
  <form id="cmp"><div class="bar">${picker.html}<button type="button" id="ex">${esc(t("example"))}</button></div>
  <div class="grid"><label>${esc(t("initial"))}<textarea name="initial"></textarea></label><label>${esc(t("agreement"))}<textarea name="agreement"></textarea></label><label>${esc(t("request"))}<textarea name="request" required></textarea></label></div>
  <div class="bar"><label>${esc(t("mode"))}<select name="request_mode"><option value="delta">${esc(t("m_delta"))}</option><option value="full">${esc(t("m_full"))}</option></select></label>
  <label>${esc(t("rate_min"))}<input name="rate_min" type="number" min="0" step="any" /></label><label>${esc(t("rate_max"))}<input name="rate_max" type="number" min="0" step="any" /></label>
  <label>${esc(t("currency"))}<input name="rate_cur" value="EUR" maxlength="3" size="4" /></label><button class="primary">${esc(t("compare"))}</button></div></form>
  <details id="bands"><summary>${esc(t("bands"))}</summary><div id="bands-body"></div></details><div id="out"></div>`;
  picker.bind();
  await bandsEditor();
  const form = $("#cmp");
  $("#ex").onclick = guard(async () => { const ex = (await api("/api/example")).scope_compare; form.initial.value = ex.initial.join("\n"); form.agreement.value = ex.agreement.join("\n"); form.request.value = ex.request; form.dataset.ctx = JSON.stringify(ex.context); });
  form.onsubmit = guard(async (ev) => {
    ev.preventDefault();
    const body = { request: form.request.value, request_mode: form.request_mode.value, lang };
    if (form.initial.value.trim()) body.initial = form.initial.value;
    if (form.agreement.value.trim()) body.agreement = form.agreement.value;
    if (ctx.engagement) body.engagement_id = ctx.engagement;
    if (form.dataset.ctx) body.context = JSON.parse(form.dataset.ctx);
    if (form.rate_min.value && form.rate_max.value) body.hourly_rate = { min: Number(form.rate_min.value), max: Number(form.rate_max.value), currency: form.rate_cur.value.toUpperCase() };
    renderCompare(await api("/api/scope/compare", "POST", body));
  });
}
// Effort bands saved for every comparison (drucker_settings / PUT /api/settings {bands})
async function bandsEditor() {
  const st = await api("/api/settings");
  const rows = Object.entries(st.bands).flatMap(([fam, parts]) => Object.entries(parts).map(([part, [lo, hi]]) => {
    const custom = st.bands_custom?.[fam]?.[part];
    return `<tr data-fam="${esc(fam)}" data-part="${esc(part)}"><td>${esc(t("bf_" + fam))}</td><td>${esc(t("bp_" + part))}</td>
      <td><input type="number" min="0" step="any" class="lo" value="${esc(lo)}" aria-label="${esc(t("band_min"))}" /></td>
      <td><input type="number" min="0" step="any" class="hi" value="${esc(hi)}" aria-label="${esc(t("band_max"))}" /></td>
      <td class="muted small">${custom ? esc(t("band_custom")) : esc(t("band_default"))} (${st.default_bands[fam][part].join("–")})</td></tr>`;
  })).join("");
  $("#bands-body").innerHTML = `<p class="muted small">${esc(t("bands_intro"))}</p>
    <table class="bands"><thead><tr><th>${esc(t("band_family"))}</th><th>${esc(t("band_part"))}</th><th>${esc(t("band_min"))}</th><th>${esc(t("band_max"))}</th><th></th></tr></thead><tbody>${rows}</tbody></table>
    <div class="bar"><button type="button" id="bands-save">${esc(t("save_bands"))}</button><button type="button" id="bands-reset">${esc(t("reset_bands"))}</button></div>`;
  $("#bands-save").onclick = guard(async () => {
    const bands = {};
    $$("#bands-body tr[data-fam]").forEach((tr) => {
      const { fam, part } = tr.dataset, pair = [Number($(".lo", tr).value), Number($(".hi", tr).value)];
      const def = st.default_bands[fam][part], custom = st.bands_custom?.[fam]?.[part];
      if (custom || pair[0] !== def[0] || pair[1] !== def[1]) (bands[fam] ||= {})[part] = pair;  // only what the owner changed
    });
    if (!Object.keys(bands).length) return toast(t("saved"));
    await api("/api/settings", "PUT", { bands }); toast(t("saved")); await bandsEditor();
  });
  $("#bands-reset").onclick = guard(async () => { await api("/api/settings", "PUT", { bands: {} }); toast(t("saved")); await bandsEditor(); });
}
function renderCompare(r) {
  const card = (i) => `<div class="card"><span class="chip ${i.class}">${esc(t("c_" + i.class))}</span> <strong>${esc(i.text)}</strong>
    <div class="muted small">${esc(i.reason)}${i.note ? " " + esc(i.note) : ""}</div>
    ${i.match ? `<div class="muted small">${esc(t("matches"))}: “${esc(i.match.text)}” (${i.match.score})</div>` : ""}
    ${i.effort && i.effort.kind !== "none" && i.effort.kind !== "removal" ? `<div>${esc(t("effort"))}: <span class="range">${i.effort.hours ? range(i.effort.hours) + money(i.effort.money) : esc(t("unestimated"))}</span> <span class="chip">${esc(t("k_" + i.effort.kind))}</span><div class="muted small">${esc(i.effort.reason)}</div></div>` : ""}
    ${i.alternatives ? `<div class="small"><strong>${esc(t("options"))}</strong><ul class="plain">${i.alternatives.map((a) => `<li>${a.option === i.recommended ? "★ " : ""}<strong>${esc(a.label || t("o_" + a.option))}</strong>: ${esc(a.summary)}</li>`).join("")}${i.recommended === "clarify" ? `<li>★ <strong>${esc(t("o_clarify"))}</strong></li>` : ""}</ul></div>` : ""}</div>`;
  $("#out").innerHTML = `<h2>${Object.entries(r.counts).map(([k, v]) => `<span class="chip ${k}">${esc(t("c_" + k))} ${v}</span>`).join(" ")}</h2>
    <div class="okbox">${esc(t("total"))}: <span class="range">${range(r.totals.hours)}</span> · ${esc(t("certain"))}: ${range(r.totals.certain_hours)} · ${esc(t("up_to"))} +${r.totals.uncertain_hours_max} ${esc(t("hours"))}${r.totals.unestimated_items ? ` · <strong>+ ${r.totals.unestimated_items} ${esc(t("unestimated_items"))}</strong>` : ""}</div>
    ${r.items.map(card).join("")}${r.removed.map(card).join("")}<p class="muted small">${esc(r.method)}</p>`;
}

// ---------- Propuesta
async function proposalView() {
  const picker = await engagementPicker(ctx.engagement, () => proposalView().catch(fail));
  const st = await api("/api/settings");
  main.innerHTML = `<h1>${esc(t("prop_title"))}</h1><p class="intro">${esc(t("prop_intro"))}</p><div class="bar">${picker.html}
  <label>${esc(t("lang"))}<select id="plang"><option value="es"${lang === "es" ? " selected" : ""}>Español</option><option value="en"${lang === "en" ? " selected" : ""}>English</option></select></label>
  <button class="primary" id="gen">${esc(t("generate"))}</button></div><div id="out"></div>
  <h2>${esc(t("denylist"))}</h2><div class="bar"><input id="deny" size="50" value="${esc(st.denylist.join(", "))}" /><button id="sd">${esc(t("save_denylist"))}</button></div>`;
  picker.bind();
  $("#sd").onclick = guard(async () => { await api("/api/settings", "PUT", { denylist: $("#deny").value.split(",").map((s) => s.trim()).filter(Boolean) }); toast(t("saved")); });
  if (!ctx.engagement) return;
  const run = guard(async () => {
    const l = $("#plang").value;
    const d = await api(`/api/engagements/${ctx.engagement}/proposal`, "POST", { format: "json", lang: l });
    const secs = Object.keys(d.sections).filter((k) => d.sentences.some((s) => s.section === k));
    $("#out").innerHTML = `<h2>${esc(d.title)}</h2>
      ${d.violations.length ? `<div class="errbox"><strong>${esc(t("not_ready"))}</strong> ${[...new Set(d.violations.map((v) => v.term))].map(esc).join(", ")}<ul class="plain">${d.violations.map((v) => `<li class="small">“${esc(v.text)}”</li>`).join("")}</ul></div>` : `<div class="okbox">${esc(t("client_ready"))}</div>`}
      <div class="bar">${Object.entries(d.counts).map(([k, v]) => `<span class="chip ${k}">${esc(t("t_" + k))} ${v}</span>`).join(" ")}
      ${d.violations.length ? "" : `<a href="/api/engagements/${ctx.engagement}/proposal.md?lang=${l}">${esc(t("dl_md"))}</a> <a href="/api/engagements/${ctx.engagement}/proposal.html?lang=${l}">${esc(t("dl_html"))}</a>`}</div>
      ${secs.map((k) => `<div class="card"><strong>${esc(d.sections[k])}</strong><ul class="plain">${d.sentences.filter((s) => s.section === k).map((s) => `<li><span class="chip ${s.tag}">${esc(t("t_" + s.tag))}</span> ${esc(s.text)}${s.source ? ` <span class="muted small">(${esc(t("source_lbl"))}: ${esc(s.source.kind)})</span>` : ""}</li>`).join("")}</ul></div>`).join("")}
      <div class="grid"><form id="fa" class="bar"><label>${esc(t("add_assumption"))}<input name="text" required /></label><button>${esc(t("add"))}</button></form>
      <form id="fq" class="bar"><label>${esc(t("add_question"))}<input name="text" required /></label><button>${esc(t("add"))}</button></form></div>`;
    for (const [fid, kind] of [["fa", "assumption"], ["fq", "question"]]) $("#" + fid).onsubmit = guard(async (ev) => { ev.preventDefault(); await api(`/api/engagements/${ctx.engagement}/items/${kind}`, "POST", { text: ev.target.text.value }); await run(); });
  });
  $("#gen").onclick = run; run();
}

// ---------- Revisión
async function pickDeliverable(onChange) {
  const picker = await engagementPicker(ctx.engagement, () => { ctx.deliverable = null; onChange(); });
  let dels = [];
  if (ctx.engagement) dels = (await api("/api/engagements/" + ctx.engagement)).deliverables;
  if (!dels.some((d) => d.id === ctx.deliverable)) ctx.deliverable = dels[0]?.id || null;
  const html = picker.html + `<label>${esc(t("pick_del"))}<select id="del"><option value="">${esc(t("select"))}</option>${dels.map((d) => `<option value="${d.id}"${d.id === ctx.deliverable ? " selected" : ""}>${esc(d.name)}</option>`).join("")}</select></label>`;
  return { html, bind() { picker.bind(); $("#del").onchange = (e) => { ctx.deliverable = e.target.value || null; onChange(); }; }, dels };
}
async function reviewView() {
  const pick = await pickDeliverable(() => reviewView().catch(fail));
  main.innerHTML = `<h1>${esc(t("rev_title"))}</h1><p class="intro">${esc(t("rev_intro"))}</p><div class="bar">${pick.html}</div><div id="desk"></div>`;
  pick.bind();
  if (!ctx.deliverable) return;
  const draw = async (d) => {
    d = d || (await api("/api/deliverables/" + ctx.deliverable));
    const vopts = d.versions.map((v) => `<option value="${v.id}">v${v.n}</option>`).join("");
    $("#desk").innerHTML = `<h2>${esc(d.name)} ${d.ready_deliver ? `<span class="chip ok">${esc(t("ready_deliver"))}</span>` : `<span class="chip warn">${esc(t("not_ready_deliver"))}</span>`}</h2>
    ${d.warnings.map((w) => `<div class="warnbox">${esc(w)}</div>`).join("")}
    <div class="scroll"><table><thead><tr><th>v</th><th>${esc(t("file_ref"))}</th><th>SHA-256</th><th>${esc(t("note"))}</th><th></th></tr></thead><tbody>
    ${d.versions.map((v) => `<tr><td>v${v.n}</td><td>${esc(v.file_ref.ref)}</td><td class="num" title="${esc(v.sha256 || "")}">${esc(shortHash(v.sha256))}</td><td>${esc(v.note)}</td>
      <td>${d.to_deliver === v.n ? `<span class="chip ok">${esc(t("to_deliver"))}</span>` : `<button class="small" data-deliver="${v.n}">${esc(t("mark_deliver"))}</button>`}</td></tr>`).join("") || `<tr><td colspan="5" class="muted">${esc(t("none"))}</td></tr>`}</tbody></table></div>
    <form id="av" class="bar"><label>${esc(t("file_ref"))}<input name="file_ref" required size="36" /></label><label>${esc(t("sha"))}<input name="sha256" size="20" /></label><label>${esc(t("note"))}<input name="note" /></label><button class="primary">${esc(t("add_version"))}</button></form>
    <h2>${esc(t("comments"))}</h2>
    ${d.comments.map((c) => `<div class="card"><span class="chip ${c.status}">${esc(t("c_" + c.status))}</span> ${c.stale ? `<span class="chip stale">${esc(t("stale"))}</span>` : ""} <strong>v${c.version}</strong>
      ${c.anchor ? `<span class="chip">${esc(t("a_" + c.anchor.kind))}: ${esc(typeof c.anchor.value === "object" ? JSON.stringify(c.anchor.value) : c.anchor.value)}</span>` : ""} ${esc(c.author)}
      <div>${esc(c.text)}</div><div class="muted small">${esc(c.note)}</div>
      <div class="bar">${c.status === "open" ? `<label>${esc(t("fixed_in"))}<select data-fx="${c.id}">${d.versions.filter((v) => v.n > c.version).map((v) => `<option value="${v.n}">v${v.n}</option>`).join("")}</select></label><button class="small" data-fix="${c.id}">${esc(t("mark_fixed"))}</button><button class="small" data-wont="${c.id}">${esc(t("wont"))}</button>` : `<button class="small" data-reopen="${c.id}">${esc(t("reopen"))}</button>`}</div></div>`).join("") || `<p class="muted">${esc(t("none"))}</p>`}
    ${d.versions.length ? `<form id="ac" class="grid card"><label>${esc(t("on_version"))}<select name="version_id">${vopts}</select></label><label>${esc(t("author"))}<input name="author" /></label>
      <label>${esc(t("anchor"))}<select name="anchor_kind"><option value="">${esc(t("a_none"))}</option>${["page", "region", "time", "object"].map((k) => `<option value="${k}">${esc(t("a_" + k))}</option>`).join("")}</select></label><label>${esc(t("anchor_value"))}<input name="anchor_value" placeholder="3 · 10,20,100,50 · 12.5-18 · B7" /></label>
      <label class="wide">${esc(t("text"))}<textarea name="text" required></textarea></label><div><button class="primary">${esc(t("add_comment"))}</button></div></form>` : ""}`;
    $("#av").onsubmit = guard(async (ev) => { ev.preventDefault(); const b = formBody(ev.target); await draw(await api(`/api/deliverables/${d.id}/versions`, "POST", b)); });
    $$("[data-deliver]").forEach((b) => (b.onclick = guard(async () => draw(await api(`/api/deliverables/${d.id}/deliver`, "POST", { version: Number(b.dataset.deliver) })))));
    const patch = (id, body) => api("/api/comments/" + id, "PATCH", body).then(draw);
    $$("[data-fix]").forEach((b) => (b.onclick = guard(async () => patch(b.dataset.fix, { status: "fixed", fixed_in: Number($(`[data-fx="${b.dataset.fix}"]`).value) }))));
    $$("[data-wont]").forEach((b) => (b.onclick = guard(async () => patch(b.dataset.wont, { status: "wontfix" }))));
    $$("[data-reopen]").forEach((b) => (b.onclick = guard(async () => patch(b.dataset.reopen, { status: "open" }))));
    const ac = $("#ac");
    if (ac) ac.onsubmit = guard(async (ev) => {
      ev.preventDefault();
      const f = ac, body = { text: f.text.value, author: f.author.value };
      const k = f.anchor_kind.value, raw = f.anchor_value.value.trim();
      if (k && raw) {
        let value = raw;
        if (k === "page" && /^\d+$/.test(raw)) value = Number(raw);
        if (k === "region") value = raw.split(",").map(Number);
        if (k === "time") { const [a, b] = raw.split("-").map(Number); value = { start: a, end: b ?? a }; }
        body.anchor = { kind: k, value };
      }
      await draw(await api(`/api/versions/${f.version_id.value}/comments`, "POST", body));
    });
  };
  await draw();
}

// ---------- Paquete
async function packageView() {
  const pick = await pickDeliverable(() => packageView().catch(fail));
  main.innerHTML = `<h1>${esc(t("pkg_title"))}</h1><p class="intro">${esc(t("pkg_intro"))}</p><div class="bar">${pick.html}</div><div id="pk"></div>`;
  pick.bind();
  const d = pick.dels.find((x) => x.id === ctx.deliverable);
  if (!d) return;
  $("#pk").innerHTML = `<form id="pf" class="grid"><label>${esc(t("version"))}<select name="version">${d.versions.map((v) => `<option value="${v.n}"${v.n === (d.to_deliver || d.latest) ? " selected" : ""}>v${v.n}</option>`).join("")}</select></label>
    <label class="wide">${esc(t("editable"))}<textarea name="editable"></textarea></label><label class="wide">${esc(t("exports"))}<textarea name="exports"></textarea></label>
    <label class="wide">${esc(t("examples"))}<textarea name="examples"></textarea></label><label class="wide">${esc(t("sources"))}<textarea name="sources"></textarea></label>
    <label class="wide">${esc(t("instructions"))}<textarea name="instructions"></textarea></label><label class="wide">${esc(t("limitations"))}<textarea name="limitations"></textarea></label>
    <div class="bar"><button type="button" id="vf">${esc(t("verify"))}</button><button class="primary" id="bd">${esc(t("build"))}</button></div></form><div id="res"></div>`;
  const spec = () => {
    const f = $("#pf"), s = { instructions: f.instructions.value, limitations: lines(f.limitations.value) };
    if (lines(f.editable.value).length) s.editable_files = lines(f.editable.value);
    s.exports = lines(f.exports.value); s.examples = lines(f.examples.value);
    s.data_sources = lines(f.sources.value).map((l) => { const [name, ok = ""] = l.split("|").map((x) => x.trim()); return { name, authorised: /^(si|sí|yes|true|1)$/i.test(ok) }; });
    return { version: Number(f.version.value), spec: s };
  };
  const show = (r, built) => {
    $("#res").innerHTML = `<div class="${r.ready ? "okbox" : "errbox"}"><strong>${esc(r.ready ? t("pkg_ready") : t("pkg_failed"))}</strong>
      ${built && r.zip_path ? ` <a href="/api/packages/${r.id}/zip">${esc(t("download_zip"))}</a>` : ""}</div>
      <h2>${esc(t("checks"))}</h2><ul class="plain">${r.checks.map((c) => `<li><span class="chip ${c.ok ? "ok" : "bad"}">${c.ok ? "OK" : "✗"}</span> ${esc(c.label)} <span class="muted small">${esc(c.detail)}</span></li>`).join("")}</ul>`;
  };
  $("#vf").onclick = guard(async () => show(await api(`/api/deliverables/${d.id}/package/verify`, "POST", spec()), false));
  $("#pf").onsubmit = guard(async (ev) => { ev.preventDefault(); show(await api(`/api/deliverables/${d.id}/package`, "POST", spec()), true); });
}

// The family copilot reads what is on screen, never a DOM guess.
window.hoardCopilot = {
  context: async () => ({
    active_objects: [ctx.engagement && { object_id: ctx.engagement, kind: "engagement" }, ctx.deliverable && { object_id: ctx.deliverable, kind: "deliverable" }].filter(Boolean),
    editor: { kind: "engagement_office", page: ctx.page, tab },
  }),
  onTurnEnd: () => route(),
};
route();
