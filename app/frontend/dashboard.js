// Thali-flation dashboard. Renders ONLY what the Python payload contains (real, committed data).
// Missing values are drawn as gaps / empty states. No value is ever generated here.

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const parseDay = (d) => new Date(`${d}T00:00:00`);
// Format from LOCAL date parts. (toISOString() would shift local midnight to the previous UTC day.)
const fmtT = (ms, year = true) => { const t = new Date(ms); return `${t.getDate()} ${MONTHS[t.getMonth()]}${year ? " " + t.getFullYear() : ""}`; };
const fmtDay = (d, year = true) => fmtT(parseDay(d).getTime(), year);
const reduceMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const unitLabel = { per_kg: "/kg", per_litre: "/litre", per_quintal: "/quintal", per_dozen: "/dozen", per_piece: "/piece" };
const qtyLabel = (it) => `${it.qty} ${it.unit === "piece" ? (it.qty === 1 ? "pc" : "pcs") : it.unit}`;
const SERIES = { veg_thali: "var(--s-veg)", nonveg_thali: "var(--s-nonveg)" };
const colorOf = (k) => SERIES[k] || "var(--accent)";
const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

function countUp(el, to, fmt, ms = 1100) {
  if (to == null) { el.textContent = "—"; return; }
  // Hidden tabs pause requestAnimationFrame; show the final value instead of a stuck "—".
  if (reduceMotion() || document.hidden) { el.textContent = fmt(to); el._last = to; return; }
  const from = el._last ?? 0, t0 = performance.now();
  el._last = to;
  const step = (t) => {
    const p = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - p, 3);
    el.textContent = fmt(from + (to - from) * e);
    if (p < 1) requestAnimationFrame(step); else el.textContent = fmt(to);
  };
  requestAnimationFrame(step);
}

function makeTip(root) {
  const tip = document.createElement("div");
  tip.className = "tip";
  tip.setAttribute("role", "tooltip");
  root.appendChild(tip);
  return {
    show(html, x, y) {
      tip.innerHTML = html;
      tip.classList.add("on");
      const w = tip.offsetWidth, h = tip.offsetHeight;
      tip.style.left = `${Math.min(window.innerWidth - w - 8, Math.max(8, x + 14))}px`;
      tip.style.top = `${y - h - 14 < 8 ? y + 18 : y - h - 14}px`;
    },
    hide() { tip.classList.remove("on"); },
  };
}

// ---- thali plate -----------------------------------------------------------------------
function plateSVG(t) {
  const items = t.items || [];
  if (!items.length) return `<div class="empty"><div class="icon">🍽️</div>${esc(t.label)}: no complete basket yet.</div>`;
  const total = t.latest ? t.latest.cost : 0;
  const max = Math.max(...items.map((i) => i.cost));
  const sorted = [...items].sort((a, b) => b.cost - a.cost);
  const ring = []; // interleave big and small katoris so neighbours never collide
  while (sorted.length) { ring.push(sorted.shift()); if (sorted.length) ring.push(sorted.pop()); }
  const cx = 200, cy = 200, R = 132, col = colorOf(t.key);
  const katoris = ring.map((it, i) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / ring.length;
    const r = 17 + 25 * Math.sqrt(it.cost / max); // area ∝ ₹
    const x = cx + R * Math.cos(a), y = cy + R * Math.sin(a);
    const pct = Math.round(28 + 67 * (it.cost / max)); // single-hue sequential by ₹
    const showRs = r >= 30;
    return `
      <g class="katori" tabindex="0" data-i="${items.indexOf(it)}" style="animation-delay:${(0.2 + i * 0.06).toFixed(2)}s"
         aria-label="${esc(it.label)}: ${esc(inr.format(it.cost))}">
        <circle cx="${x}" cy="${y + 3}" r="${r}" fill="rgba(0,0,0,.18)"/>
        <circle class="bowl-rim" cx="${x}" cy="${y}" r="${r}" fill="url(#steel)" stroke="var(--steel-3)" stroke-width="1.2"/>
        <circle cx="${x}" cy="${y}" r="${r * 0.8}" style="fill: color-mix(in srgb, ${col} ${pct}%, transparent)"/>
        <text x="${x}" y="${y + (showRs ? -2 : 5)}" text-anchor="middle" font-size="${Math.round(r * 0.72)}">${it.emoji}</text>
        ${showRs ? `<text x="${x}" y="${y + r * 0.55}" text-anchor="middle" font-size="11" font-weight="700" fill="var(--text)" class="num">${esc(inr.format(it.cost))}</text>` : ""}
      </g>`;
  }).join("");
  return `
    <svg viewBox="0 0 400 400" role="img" aria-label="${esc(t.label)} plate: each katori's area is proportional to that ingredient's rupee cost; total ${esc(inr.format(total))}">
      <defs>
        <radialGradient id="plate" cx="42%" cy="38%" r="70%">
          <stop offset="0" stop-color="var(--steel-1)"/><stop offset=".72" stop-color="var(--steel-2)"/><stop offset="1" stop-color="var(--steel-3)"/>
        </radialGradient>
        <radialGradient id="steel" cx="35%" cy="30%" r="80%">
          <stop offset="0" stop-color="var(--steel-1)"/><stop offset="1" stop-color="var(--steel-3)"/>
        </radialGradient>
      </defs>
      <g class="plate-in">
        <circle cx="200" cy="206" r="190" fill="rgba(0,0,0,.16)"/>
        <circle cx="200" cy="200" r="190" fill="url(#plate)" stroke="var(--steel-3)" stroke-width="1.5"/>
        <circle cx="200" cy="200" r="166" fill="none" stroke="rgba(255,255,255,.35)" stroke-width="1"/>
        <circle cx="200" cy="200" r="72" fill="var(--steel-1)" opacity=".55"/>
        <text x="200" y="196" text-anchor="middle" class="serif num" font-size="30" font-weight="800" fill="var(--text)">${esc(inr.format(total))}</text>
        <text x="200" y="218" text-anchor="middle" font-size="12" fill="var(--text-2)">per ${esc(t.label.toLowerCase())}</text>
        ${katoris}
      </g>
    </svg>`;
}

// ---- trend chart (one line per thali; lines break at gaps) --------------------------------
function trendChart(el, thalis, order, baseDate, tip) {
  const all = order.map((k) => ({ k, t: thalis[k], pts: thalis[k].series.map((d) => ({ ...d, t: parseDay(d.date).getTime() })) }));
  const vals = all.flatMap((s) => s.pts.filter((p) => p.index != null).map((p) => p.index));
  if (!vals.length) { el.innerHTML = `<div class="empty"><div class="icon">📈</div>No computable index yet.</div>`; return; }
  const W = Math.max(320, el.clientWidth), H = el.clientHeight || 250;
  const m = { t: 18, r: 96, b: 30, l: 46 };
  const times = [...new Set(all.flatMap((s) => s.pts.map((p) => p.t)))].sort((a, b) => a - b);
  let x0 = times[0], x1 = times[times.length - 1];
  if (x0 === x1) { x0 -= 3 * 864e5; x1 += 3 * 864e5; }
  let y0 = Math.min(...vals, 100), y1 = Math.max(...vals, 100);
  const pad = Math.max(1.5, (y1 - y0) * 0.3); y0 -= pad; y1 += pad;
  const X = (t) => m.l + ((t - x0) / (x1 - x0)) * (W - m.l - m.r);
  const Y = (v) => H - m.b - ((v - y0) / (y1 - y0)) * (H - m.t - m.b);
  const yTicks = [0, 1, 2, 3, 4].map((i) => y0 + (i * (y1 - y0)) / 4);
  const every = Math.max(1, Math.ceil(times.length / 7));
  const xTicks = times.filter((_, i) => i % every === 0);
  const gapDays = times.filter((t) => all.some((s) => { const p = s.pts.find((q) => q.t === t); return !p || p.index == null; }));

  const lines = all.map((s) => {
    const segs = []; let cur = [];
    for (const p of s.pts) { if (p.index == null) { if (cur.length) segs.push(cur); cur = []; } else cur.push(p); }
    if (cur.length) segs.push(cur);
    const path = (g) => g.map((p, i) => `${i ? "L" : "M"}${X(p.t).toFixed(1)},${Y(p.index).toFixed(1)}`).join("");
    const last = [...s.pts].reverse().find((p) => p.index != null);
    const c = colorOf(s.k);
    return segs.map((g) => `<path d="${path(g)}" fill="none" stroke="${c}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>`).join("")
      + s.pts.filter((p) => p.index != null).map((p) => `<circle cx="${X(p.t)}" cy="${Y(p.index)}" r="5" fill="${c}" stroke="var(--steel-1)" stroke-width="1.5"/>`).join("")
      + (last ? `<text x="${X(last.t) + 10}" y="${Y(last.index) + 4 + (s.k === "nonveg_thali" ? 14 : 0)}" font-size="12" font-weight="700" fill="var(--text)">${esc(s.t.emoji)} ${esc(s.t.label.replace(" thali", ""))} ${last.index.toFixed(1)}</text>` : "");
  }).join("");

  el.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Thali index by day for each thali; days without data are marked as gaps">
      <g class="axis">${yTicks.map((v) => `<line class="gridline" x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${m.l - 8}" y="${Y(v) + 4}" text-anchor="end">${v.toFixed(1)}</text>`).join("")}
        ${xTicks.map((t) => `<text x="${X(t)}" y="${H - 8}" text-anchor="middle">${esc(fmtT(t, false))}</text>`).join("")}</g>
      <line x1="${m.l}" x2="${W - m.r}" y1="${Y(100)}" y2="${Y(100)}" stroke="var(--muted)" stroke-dasharray="4 4" opacity=".7"/>
      <text x="${m.l + 4}" y="${Y(100) - 6}" font-size="11" fill="var(--muted)">base ${esc(baseDate ? fmtDay(baseDate) : "")} = 100</text>
      ${gapDays.map((t) => `<line x1="${X(t)}" x2="${X(t)}" y1="${m.t}" y2="${H - m.b}" stroke="var(--critical)" stroke-dasharray="3 4" stroke-width="1.5" opacity=".75"/>`).join("")}
      ${lines}
      <line class="xh" y1="${m.t}" y2="${H - m.b}" stroke="var(--text-2)" stroke-width="1" opacity="0"/>
      <rect class="hit" x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent"/>
    </svg>`;
  const svg = el.querySelector("svg"), xh = el.querySelector(".xh");
  el.querySelector(".hit").addEventListener("pointermove", (ev) => {
    const r = svg.getBoundingClientRect();
    const px = ((ev.clientX - r.left) / r.width) * W;
    let best = times[0];
    for (const t of times) if (Math.abs(X(t) - px) < Math.abs(X(best) - px)) best = t;
    xh.setAttribute("x1", X(best)); xh.setAttribute("x2", X(best)); xh.setAttribute("opacity", ".5");
    const rows = all.map((s) => {
      const p = s.pts.find((q) => q.t === best);
      return p && p.index != null
        ? `<span class="swatch" style="--sc:${colorOf(s.k)}"></span> ${esc(s.t.label)}: <b>${p.index.toFixed(2)}</b> <span class="m">(${esc(inr.format(p.cost))})</span>`
        : `<span class="swatch" style="--sc:${colorOf(s.k)}"></span> ${esc(s.t.label)}: <span class="m">no index (${esc((p ? p.status : "no snapshot").toLowerCase())})</span>`;
    });
    tip.show(`<b>${esc(fmtT(best))}</b><br>${rows.join("<br>")}`, ev.clientX, ev.clientY);
  });
  el.querySelector(".hit").addEventListener("pointerleave", () => { tip.hide(); xh.setAttribute("opacity", "0"); });
}

// ---- main ------------------------------------------------------------------------------
export default function (component) {
  const { data, parentElement } = component;
  parentElement.querySelector(".tf-root")?.remove();
  parentElement.querySelector(".tip")?.remove();
  const root = document.createElement("div");
  root.className = "tf-root";
  parentElement.appendChild(root);

  if (!data || !data.ready) {
    root.innerHTML = `<div class="empty"><div class="icon">⏳</div>No index has been built yet. The daily pipeline hasn't produced data.</div>`;
    return;
  }
  if (!data.thalis || !data.order || !data.order.length) {
    root.innerHTML = `<div class="empty"><div class="icon">🔄</div>The dashboard is updating to a new version. Please refresh in a minute.</div>`;
    return;
  }

  const T = data.thalis, order = data.order;
  const veg = T.veg_thali, nonveg = T.nonveg_thali;
  let sel = data.initial in T ? data.initial : order.find((k) => T[k].latest) || order[0];
  const H = T[order[0]].history;
  const ng = data.geos_without_source || [];
  const ratio = veg && nonveg && veg.latest && nonveg.latest ? nonveg.latest.cost / veg.latest.cost : null;
  const asOn = (T[sel].latest || {}).date;

  const statusCard = (t) => {
    if (t.status === "OK") {
      const egg = t.items.some((i) => i.ingredient === "egg");
      return `<div class="st good"><div class="t">✅ ${esc(t.label)}: complete</div><div class="d">${t.items.length} of ${t.n_items} ingredients priced on ${esc(fmtDay(t.latest.date))}.${egg ? ` Egg is priced per dozen, the unit DoCA itself states (<a href="${esc(data.evidence_url)}" target="_blank" rel="noopener">evidence ↗</a>).` : ""}</div></div>`;
    }
    return `<div class="st critical"><div class="t">⛔ ${esc(t.label)}: ${esc(t.status.toLowerCase())}</div><div class="d">${esc(cap(t.reason))}. That day is dropped, with no partial sums and no guessing.</div></div>`;
  };

  root.innerHTML = `
  <div class="bar">
    <div class="brand"><div class="logo">🍛</div><div>Thali-flation Index<small>Dish-level food inflation for India</small></div></div>
    <div class="chips">
      <span class="chip"><span class="dot"></span>Updated daily · last as-on ${esc(asOn ? fmtDay(asOn) : "—")}</span>
      <span class="chip">✓ Real government data only</span>
      <a class="chip btn" href="${esc(data.repo_url)}" target="_blank" rel="noopener">GitHub ↗</a>
    </div>
  </div>

  <section class="hero">
    <div>
      <div class="eyebrow">All-India average · ${esc(asOn ? fmtDay(asOn) : "")}</div>
      <h1>What does a <em>thali</em> cost India today?</h1>
      <div class="seg" role="group" aria-label="Choose thali">
        ${order.map((k) => `<button type="button" data-k="${k}" style="--sc:${colorOf(k)}" aria-pressed="${k === sel}"><span>${T[k].emoji} ${esc(T[k].label.replace(" thali", ""))}</span><span class="p">${T[k].latest ? esc(inr.format(T[k].latest.cost)) : "—"}</span></button>`).join("")}
      </div>
      <div class="price"><span class="big num" id="big">—</span><span class="per" id="per"></span></div>
      <p class="lede" id="lede"></p>
      <div class="pills" id="pills"></div>
      <div class="jump"><a href="#" data-go="trend">Trend ↓</a><a href="#" data-go="gaps">Coverage &amp; gaps ↓</a><a href="#" data-go="method">Method ↓</a></div>
    </div>
    <div>
      <div class="plate-wrap" id="plate"></div>
      <div class="plate-note">Each katori's area is proportional to its ₹ share. Hover or tap a katori for the published price.</div>
    </div>
  </section>

  <section class="kpis reveal">
    ${order.map((k) => `<div class="kpi"><div class="k"><span class="swatch" style="--sc:${colorOf(k)}"></span> ${esc(T[k].label)}</div><div class="v num">${T[k].latest ? esc(inr.format(T[k].latest.cost)) : "—"}<small>${T[k].latest && T[k].latest.index != null ? `idx ${T[k].latest.index.toFixed(1)}` : esc(T[k].status.toLowerCase())}</small></div><div class="s">${T[k].items.length} of ${T[k].n_items} ingredients priced</div></div>`).join("")}
    <div class="kpi"><div class="k">Non-veg vs veg</div><div class="v num">${ratio ? `${ratio.toFixed(2)}×` : "—"}</div><div class="s">${ratio && nonveg.items[0] ? `${esc(nonveg.items[0].label)} alone is ${(nonveg.items[0].share * 100).toFixed(0)}% of the non-veg thali` : ""}</div></div>
    <div class="kpi"><div class="k">Days with a real index</div><div class="v num">${H.ok_days} <span style="font-size:18px;color:var(--muted)">/ ${H.calendar_days}</span></div><div class="s">calendar days since ${esc(fmtDay(H.first_date))}</div></div>
  </section>

  <section class="grid2 reveal" id="trend">
    <div class="card">
      <div class="card-head"><div><h2>Thali index</h2><div class="sub">One point per day DoCA publishes. Dashed red lines are days with no index; lines never bridge them.</div></div></div>
      <div class="chart" id="chart"></div>
      <div class="legend">${order.map((k) => `<span><i style="background:${colorOf(k)};border-radius:50%"></i>${esc(T[k].label)}</span>`).join("")}</div>
      <div class="note">${H.ok_days === 1 ? `The series started on ${esc(fmtDay(H.first_date))}. Nothing before that was backfilled, because no verifiable source exists.` : `${H.ok_days} real days out of ${H.calendar_days} calendar days.`}</div>
    </div>
    <div class="card">
      <div class="card-head"><div><h2>Top movers</h2><div class="sub">Retail, all 41 published commodities, two latest dates</div></div></div>
      <div id="movers"></div>
    </div>
  </section>

  <section class="card reveal">
    <div class="card-head"><div><h2>Where the ₹ goes</h2><div class="sub" id="rowsSub"></div></div></div>
    <div class="rows" id="rows"></div>
  </section>

  <section class="card reveal" id="gaps">
    <div class="card-head"><div><h2>Coverage &amp; gaps</h2><div class="sub">Nothing is hidden. Missing data stays missing and is listed here.</div></div></div>
    <div class="status">
      ${order.map((k) => statusCard(T[k])).join("")}
      <div class="st warning"><div class="t">⚠️ ${esc(ng.map((g) => g.geo).join(", ") || "Cities")}: no live source</div><div class="d">City-level prices need DoCA's centre reports (behind a CAPTCHA) or the data.gov.in mandi API (needs a key).</div></div>
      <div class="st warning"><div class="t">⚠️ No history before ${esc(fmtDay(H.first_date))}</div><div class="d">The official retail CSVs on data.gov.in end in 2015 and need an API key. The series grows by one real day per DoCA update.</div></div>
    </div>
    <div class="cov" id="cov"></div>
    <div class="legend"><span><i style="background:var(--accent)"></i>price published &amp; stored</span><span><i style="border:1.5px dashed var(--critical)"></i>no price that day (gap)</span></div>
  </section>

  <section class="card reveal" id="method">
    <div class="card-head"><div><h2>Method &amp; provenance</h2><div class="sub">Everything here can be traced back to a raw page on disk</div></div></div>
    <div class="method">
      <div class="formula">cost(day) = Σ qty<sub>i</sub> × price<sub>i</sub>(day) × unit factor<sub>i</sub><br>index(day) = cost(day) / cost(base) × 100<br><span style="color:var(--muted)">// any ingredient missing → that day is MISSING (no partial sums, no substitutes)</span><br><span style="color:var(--muted)">// units: /kg, milk /litre, egg /dozen (as stated by DoCA)</span></div>
      <dl class="kv">
        <dt>Source</dt><dd><a href="${esc(data.source_url)}" target="_blank" rel="noopener">DoCA Price Monitoring Division ↗</a></dd>
        <dt>Unit evidence</dt><dd><a href="${esc(data.evidence_url)}" target="_blank" rel="noopener">Lok Sabha answer 4366 (egg per dozen, milk per litre) ↗</a></dd>
        <dt>Last fetch</dt><dd class="num">${esc(data.provenance ? data.provenance.fetched_at.replace("T", " ").slice(0, 19) + " UTC" : "—")}</dd>
        <dt>Raw sha256</dt><dd class="num" title="${esc(data.provenance ? data.provenance.raw_sha256 : "")}">${esc(data.provenance ? data.provenance.raw_sha256.slice(0, 16) + "…" : "—")}</dd>
        <dt>Pipeline</dt><dd>GitHub Actions, daily 19:00 IST. Raw + processed files are committed; this page reads only those.</dd>
        <dt>Docs</dt><dd><a href="${esc(data.repo_url)}/blob/main/docs/sources.md" target="_blank" rel="noopener">sources</a> · <a href="${esc(data.repo_url)}/blob/main/docs/decisions.md" target="_blank" rel="noopener">decisions</a></dd>
      </dl>
    </div>
  </section>

  <div class="foot">No synthetic data. Gaps are shown, never filled. Data: Department of Consumer Affairs, Govt. of India.</div>`;

  const tip = makeTip(parentElement);
  const $ = (s) => root.querySelector(s);

  // ---- selection-dependent parts (hero, plate, breakdown) ----
  const renderSel = () => {
    const t = T[sel], L = t.latest;
    root.querySelectorAll(".seg button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.k === sel)));
    countUp($("#big"), L ? L.cost : null, (v) => inr.format(v));
    $("#per").textContent = `for one home-cooked ${t.label.toLowerCase()}`;
    $("#lede").innerHTML = L
      ? `Priced from the <b>Department of Consumer Affairs'</b> published All-India average retail prices for <b>${t.items.length} ingredients</b>: ${esc(t.blurb)}. Rebased to <b>100</b> on ${esc(data.base_date ? fmtDay(data.base_date) : "—")}.`
      : `${esc(t.label)} is <b>${esc(t.status.toLowerCase())}</b>: ${esc(t.reason)}.`;
    const d = L && t.previous ? L.cost - t.previous.cost : null;
    $("#pills").innerHTML = `<span class="pill accent">Index <b class="num">${L && L.index != null ? L.index.toFixed(1) : "—"}</b></span>
      <span class="pill">${d == null ? "First day of the series. The next point comes with DoCA's next update." : `${d >= 0 ? "▲" : "▼"} <b class="num">${esc(inr.format(Math.abs(d)))}</b> vs ${esc(fmtDay(t.previous.date, false))}`}</span>`;
    $("#plate").innerHTML = plateSVG(t);
    root.querySelectorAll(".katori").forEach((g) => {
      const it = t.items[Number(g.dataset.i)];
      const html = `<b>${it.emoji} ${esc(it.label)}</b><br>${esc(qtyLabel(it))} × ${esc(inr.format(it.price))}${esc(unitLabel[it.source_unit] || "")}<br><b>${esc(inr.format(it.cost))}</b> · ${(it.share * 100).toFixed(1)}% of the thali<br><span class="m">DoCA: "${esc(it.source_commodity)}"</span>`;
      g.addEventListener("pointermove", (e) => tip.show(html, e.clientX, e.clientY));
      g.addEventListener("pointerleave", () => tip.hide());
      g.addEventListener("focus", () => { const r = g.getBoundingClientRect(); tip.show(html, r.right, r.top); });
      g.addEventListener("blur", () => tip.hide());
    });
    $("#rowsSub").textContent = `${t.label}: ingredient cost = portion × DoCA's published price${L ? ` (as on ${fmtDay(L.date)})` : ""}`;
    const maxShare = Math.max(...t.items.map((i) => i.share), 0);
    $("#rows").innerHTML = t.items.length ? t.items.map((it) => `
      <div class="row fade">
        <div class="em">${it.emoji}</div>
        <div class="nm">${esc(it.label)}<small>${esc(qtyLabel(it))} · ${esc(inr.format(it.price))}${esc(unitLabel[it.source_unit] || "")}</small></div>
        <div class="track" title="${(it.share * 100).toFixed(1)}%"><div class="fill ${sel === "nonveg_thali" ? "nonveg" : ""}" data-w="${((it.share / maxShare) * 100).toFixed(1)}"></div></div>
        <div class="rs num">${esc(inr.format(it.cost))}<small>${(it.share * 100).toFixed(1)}%</small></div>
      </div>`).join("") : `<div class="empty">No complete basket for this thali.</div>`;
    const rowsCard = $("#rows").closest(".card");
    if (rowsCard.classList.contains("in")) requestAnimationFrame(() => rowsCard.querySelectorAll(".fill").forEach((f) => { f.style.width = `${f.dataset.w}%`; }));
  };
  root.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => { if (b.dataset.k !== sel) { sel = b.dataset.k; tip.hide(); renderSel(); } }));
  renderSel();

  // ---- movers ----
  const mv = data.movers || { rows: [], reason: "No data." };
  $("#movers").innerHTML = mv.reason
    ? `<div class="empty"><div class="icon">⏳</div><div><b>Waiting for day 2</b><br>${esc(mv.reason)}</div></div>`
    : mv.rows.map((r) => `<div class="mv"><div>${esc(r.commodity)}<div style="color:var(--muted);font-size:12px">${esc(inr.format(r.from))} → ${esc(inr.format(r.to))}</div></div><div class="pct num ${r.pct >= 0 ? "up" : "down"}">${r.pct >= 0 ? "▲" : "▼"} ${Math.abs(r.pct).toFixed(1)}%</div></div>`).join("")
      + `<div class="note">${esc(fmtDay(mv.rows[0].date_from, false))} → ${esc(fmtDay(mv.rows[0].date_to, false))} (${mv.rows[0].days_between} day${mv.rows[0].days_between > 1 ? "s" : ""} apart)</div>`;

  // ---- coverage grid ----
  const cov = data.coverage || { days: [], rows: [] };
  $("#cov").innerHTML = cov.rows.length ? `
    <table><thead><tr><th></th>${cov.days.map((d) => `<th>${esc(fmtDay(d, false))}</th>`).join("")}</tr></thead>
    <tbody>${cov.rows.map((r) => `<tr><td class="lbl">${r.emoji} ${esc(r.label)}</td>${r.cells.map((c, j) => `<td><div class="cell ${c ? "on" : "off"}" title="${esc(r.label)} · ${esc(fmtDay(cov.days[j]))}: ${c ? "published" : "no price (gap)"}"></div></td>`).join("")}</tr>`).join("")}</tbody></table>` : "";

  // ---- trend (re-rendered on resize) ----
  const chartEl = $("#chart");
  const draw = () => trendChart(chartEl, T, order, data.base_date, tip);
  draw();
  const ro = new ResizeObserver(() => draw());
  ro.observe(chartEl);

  root.querySelectorAll("[data-go]").forEach((a) => a.addEventListener("click", (e) => {
    e.preventDefault();
    root.querySelector(`#${a.dataset.go}`)?.scrollIntoView({ behavior: reduceMotion() ? "auto" : "smooth", block: "start" });
  }));

  const io = new IntersectionObserver((entries) => entries.forEach((en) => {
    if (!en.isIntersecting) return;
    en.target.classList.add("in");
    en.target.querySelectorAll(".fill").forEach((f) => { f.style.width = `${f.dataset.w}%`; });
    io.unobserve(en.target);
  }), { threshold: 0.12 });
  root.querySelectorAll(".reveal, .card").forEach((s) => io.observe(s));

  return () => { ro.disconnect(); io.disconnect(); };
}
