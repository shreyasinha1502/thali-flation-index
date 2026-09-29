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

function countUp(el, to, fmt, ms = 1300) {
  if (to == null) { el.textContent = "—"; return; }
  if (reduceMotion()) { el.textContent = fmt(to); return; }
  const t0 = performance.now();
  const step = (t) => {
    const p = Math.min(1, (t - t0) / ms);
    const e = 1 - Math.pow(1 - p, 3);
    el.textContent = fmt(to * e);
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
      const left = Math.min(window.innerWidth - w - 8, Math.max(8, x + 14));
      const top = y - h - 14 < 8 ? y + 18 : y - h - 14;
      tip.style.left = `${left}px`;
      tip.style.top = `${top}px`;
    },
    hide() { tip.classList.remove("on"); },
  };
}

// ---- thali plate -----------------------------------------------------------------------
function plateSVG(items, total) {
  if (!items.length) return `<div class="empty"><div class="icon">🍽️</div>No complete basket yet.</div>`;
  const max = Math.max(...items.map((i) => i.cost));
  // Interleave big and small katoris so neighbours never collide.
  const sorted = [...items].sort((a, b) => b.cost - a.cost);
  const ring = [];
  while (sorted.length) { ring.push(sorted.shift()); if (sorted.length) ring.push(sorted.pop()); }
  const cx = 200, cy = 200, R = 132;
  const katoris = ring.map((it, i) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / ring.length;
    const r = 17 + 25 * Math.sqrt(it.cost / max); // area ∝ ₹
    const x = cx + R * Math.cos(a), y = cy + R * Math.sin(a);
    const alpha = (0.25 + 0.7 * (it.cost / max)).toFixed(2); // single-hue sequential by ₹
    const showRs = r >= 30;
    return `
      <g class="katori" tabindex="0" data-i="${items.indexOf(it)}" style="animation-delay:${(0.35 + i * 0.07).toFixed(2)}s"
         aria-label="${esc(it.label)}: ${esc(inr.format(it.cost))}">
        <circle cx="${x}" cy="${y + 3}" r="${r}" fill="rgba(0,0,0,.18)"/>
        <circle class="bowl-rim" cx="${x}" cy="${y}" r="${r}" fill="url(#steel)" stroke="var(--steel-3)" stroke-width="1.2"/>
        <circle cx="${x}" cy="${y}" r="${r * 0.8}" fill="rgba(245,158,11,${alpha})"/>
        <text x="${x}" y="${y + (showRs ? -2 : 5)}" text-anchor="middle" font-size="${Math.round(r * 0.72)}">${it.emoji}</text>
        ${showRs ? `<text x="${x}" y="${y + r * 0.55}" text-anchor="middle" font-size="11" font-weight="700" fill="var(--text)" class="num">${esc(inr.format(it.cost))}</text>` : ""}
      </g>`;
  }).join("");
  return `
    <svg viewBox="0 0 400 400" role="img" aria-label="Thali plate: each katori's area is proportional to that ingredient's rupee cost; total ${esc(inr.format(total))}">
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
        <text x="200" y="218" text-anchor="middle" font-size="12" fill="var(--text-2)">per thali</text>
        ${katoris}
      </g>
    </svg>`;
}

// ---- trend chart -----------------------------------------------------------------------
function trendChart(el, series, baseDate, tip) {
  const pts = series.map((d) => ({ ...d, t: parseDay(d.date).getTime() }));
  const vals = pts.filter((p) => p.index != null).map((p) => p.index);
  if (!vals.length) { el.innerHTML = `<div class="empty"><div class="icon">📈</div>No computable index yet.</div>`; return; }
  const W = Math.max(320, el.clientWidth), H = el.clientHeight || 250;
  const m = { t: 18, r: 18, b: 30, l: 46 };
  let x0 = Math.min(...pts.map((p) => p.t)), x1 = Math.max(...pts.map((p) => p.t));
  if (x0 === x1) { x0 -= 3 * 864e5; x1 += 3 * 864e5; }
  let y0 = Math.min(...vals, 100), y1 = Math.max(...vals, 100);
  const pad = Math.max(1.5, (y1 - y0) * 0.3); y0 -= pad; y1 += pad;
  const X = (t) => m.l + ((t - x0) / (x1 - x0)) * (W - m.l - m.r);
  const Y = (v) => H - m.b - ((v - y0) / (y1 - y0)) * (H - m.t - m.b);
  const yTicks = [0, 1, 2, 3, 4].map((i) => y0 + (i * (y1 - y0)) / 4);
  const days = pts.map((p) => p.t);
  const every = Math.max(1, Math.ceil(days.length / 7));
  const xTicks = days.filter((_, i) => i % every === 0);

  // Segments break at every day without an index; nothing is interpolated across a gap.
  const segs = []; let cur = [];
  for (const p of pts) { if (p.index == null) { if (cur.length) segs.push(cur); cur = []; } else cur.push(p); }
  if (cur.length) segs.push(cur);
  const path = (s) => s.map((p, i) => `${i ? "L" : "M"}${X(p.t).toFixed(1)},${Y(p.index).toFixed(1)}`).join("");
  const area = (s) => s.length < 2 ? "" : `${path(s)}L${X(s[s.length - 1].t).toFixed(1)},${H - m.b}L${X(s[0].t).toFixed(1)},${H - m.b}Z`;
  const gaps = pts.filter((p) => p.index == null);

  el.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Veg thali index by day; days without data are marked as gaps">
      <defs><linearGradient id="ar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--accent)" stop-opacity=".28"/><stop offset="1" stop-color="var(--accent)" stop-opacity="0"/></linearGradient></defs>
      <g class="axis">${yTicks.map((v) => `<line class="gridline" x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${m.l - 8}" y="${Y(v) + 4}" text-anchor="end">${v.toFixed(1)}</text>`).join("")}
        ${xTicks.map((t) => `<text x="${X(t)}" y="${H - 8}" text-anchor="middle">${esc(fmtT(t, false))}</text>`).join("")}</g>
      <line x1="${m.l}" x2="${W - m.r}" y1="${Y(100)}" y2="${Y(100)}" stroke="var(--muted)" stroke-dasharray="4 4" opacity=".7"/>
      <text x="${W - m.r}" y="${Y(100) - 6}" text-anchor="end" font-size="11" fill="var(--muted)">base ${esc(baseDate ? fmtDay(baseDate) : "")} = 100</text>
      ${gaps.map((g) => `<line x1="${X(g.t)}" x2="${X(g.t)}" y1="${m.t}" y2="${H - m.b}" stroke="var(--critical)" stroke-dasharray="3 4" stroke-width="1.5" opacity=".75"/>`).join("")}
      ${segs.map((s) => `<path d="${area(s)}" fill="url(#ar)"/><path d="${path(s)}" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>`).join("")}
      ${pts.filter((p) => p.index != null).map((p) => `<circle cx="${X(p.t)}" cy="${Y(p.index)}" r="5.5" fill="var(--accent)" stroke="var(--bg-card, #fff)" stroke-width="2"/>`).join("")}
      <line class="xh" y1="${m.t}" y2="${H - m.b}" stroke="var(--text-2)" stroke-width="1" opacity="0"/>
      <rect class="hit" x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent"/>
    </svg>`;
  const svg = el.querySelector("svg"), xh = el.querySelector(".xh");
  el.querySelector(".hit").addEventListener("pointermove", (ev) => {
    const r = svg.getBoundingClientRect();
    const px = ((ev.clientX - r.left) / r.width) * W;
    let best = pts[0];
    for (const p of pts) if (Math.abs(X(p.t) - px) < Math.abs(X(best.t) - px)) best = p;
    xh.setAttribute("x1", X(best.t)); xh.setAttribute("x2", X(best.t)); xh.setAttribute("opacity", ".5");
    tip.show(best.index == null
      ? `<b>${esc(fmtDay(best.date))}</b><br><span class="m">No index: ${esc(best.status.toLowerCase())}</span>`
      : `<b>${esc(fmtDay(best.date))}</b><br>Index <b>${best.index.toFixed(2)}</b><br><span class="m">Thali cost ${esc(inr.format(best.cost))}</span>`, ev.clientX, ev.clientY);
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

  const L = data.latest, items = data.items || [], H = data.history;
  const total = L ? L.cost : null;
  const delta = L && data.previous ? L.cost - data.previous.cost : null;
  const nonveg = data.nonveg;
  const ng = data.geos_without_source || [];

  root.innerHTML = `
  <div class="bar">
    <div class="brand"><div class="logo">🍛</div><div>Thali-flation Index<small>Dish-level food inflation for India</small></div></div>
    <div class="chips">
      <span class="chip"><span class="dot"></span>Updated daily · last as-on ${esc(L ? fmtDay(L.date) : "—")}</span>
      <span class="chip">✓ Real government data only</span>
      <a class="chip btn" href="${esc(data.repo_url)}" target="_blank" rel="noopener">GitHub ↗</a>
    </div>
  </div>

  <section class="hero">
    <div>
      <div class="eyebrow">All-India average · ${esc(L ? fmtDay(L.date) : "")}</div>
      <h1>What does a <em>thali</em> cost India today?</h1>
      <div class="price"><span class="big num" id="big">—</span><span class="per">for one home-cooked veg thali</span></div>
      <p class="lede">Priced from the <b>Department of Consumer Affairs'</b> published All-India average retail prices for <b>${items.length} ingredients</b>: rice, 2 rotis, dal, sabzi, tadka, a little milk. Rebased to <b>100</b> on ${esc(data.base_date ? fmtDay(data.base_date) : "—")}.</p>
      <div class="pills">
        <span class="pill accent">Index <b class="num">${L && L.index != null ? L.index.toFixed(1) : "—"}</b></span>
        <span class="pill">${delta == null ? "First day of the series. The next point comes with DoCA's next update." : `${delta >= 0 ? "▲" : "▼"} <b class="num">${esc(inr.format(Math.abs(delta)))}</b> vs ${esc(fmtDay(data.previous.date, false))}`}</span>
      </div>
      <div class="jump"><a href="#" data-go="trend">Trend ↓</a><a href="#" data-go="gaps">Coverage &amp; gaps ↓</a><a href="#" data-go="method">Method ↓</a></div>
    </div>
    <div>
      <div class="plate-wrap">${plateSVG(items, total ?? 0)}</div>
      <div class="plate-note">Each katori's area is proportional to its ₹ share. Hover or tap a katori for the published price.</div>
    </div>
  </section>

  <section class="kpis reveal">
    <div class="kpi"><div class="k">Thali index</div><div class="v num" id="kidx">—</div><div class="s">base ${esc(data.base_date ? fmtDay(data.base_date) : "—")} = 100</div></div>
    <div class="kpi"><div class="k">Days with a real index</div><div class="v num">${H.ok_days} <span style="font-size:18px;color:var(--muted)">/ ${H.calendar_days}</span></div><div class="s">calendar days since ${esc(fmtDay(H.first_date))}</div></div>
    <div class="kpi"><div class="k">Ingredients priced</div><div class="v num">${items.length} <span style="font-size:18px;color:var(--muted)">/ 10</span></div><div class="s">missing any one → that day is dropped</div></div>
    <div class="kpi"><div class="k">Non-veg thali</div><div class="v">${nonveg && nonveg.status === "EXCLUDED" ? "Excluded" : esc(nonveg ? nonveg.status : "—")}</div><div class="s">${nonveg && nonveg.status === "EXCLUDED" ? "egg unit unverified; no guessing" : ""}</div></div>
  </section>

  <section class="grid2 reveal" id="trend">
    <div class="card">
      <div class="card-head"><div><h2>Veg thali index</h2><div class="sub">One point per day DoCA publishes. Dashed red lines are days with no index; lines never bridge them.</div></div></div>
      <div class="chart" id="chart"></div>
      <div class="note">${H.ok_days === 1 ? `The series started on ${esc(fmtDay(H.first_date))}. Nothing before that was backfilled, because no verifiable source exists.` : `${H.ok_days} real days out of ${H.calendar_days} calendar days.`}</div>
    </div>
    <div class="card">
      <div class="card-head"><div><h2>Top movers</h2><div class="sub">Retail, all 41 published commodities, two latest dates</div></div></div>
      <div id="movers"></div>
    </div>
  </section>

  <section class="card reveal">
    <div class="card-head"><div><h2>Where the ₹ goes</h2><div class="sub">Ingredient cost in one thali = portion × DoCA's published price${L ? ` (as on ${esc(fmtDay(L.date))})` : ""}</div></div></div>
    <div class="rows" id="rows"></div>
  </section>

  <section class="card reveal" id="gaps">
    <div class="card-head"><div><h2>Coverage &amp; gaps</h2><div class="sub">Nothing is hidden. Missing data stays missing and is listed here.</div></div></div>
    <div class="status">
      <div class="st ${L ? "good" : "critical"}"><div class="t">${L ? "✅ Veg thali: complete" : "⛔ Veg thali: not computable"}</div><div class="d">${L ? `${items.length} of 10 ingredients priced on ${esc(fmtDay(L.date))}.` : ""}</div></div>
      <div class="st ${nonveg && nonveg.status === "OK" ? "good" : "critical"}"><div class="t">${nonveg && nonveg.status === "OK" ? "✅" : "⛔"} Non-veg thali: ${esc(nonveg ? nonveg.status.toLowerCase() : "n/a")}</div><div class="d">${nonveg && nonveg.status !== "OK" ? `${esc(nonveg.reason.charAt(0).toUpperCase() + nonveg.reason.slice(1))}. DoCA publishes "Eggs" without stating the unit (dozen or kg), so we don't guess.` : ""}</div></div>
      <div class="st warning"><div class="t">⚠️ ${esc(ng.map((g) => g.geo).join(", ") || "Cities")}: no live source</div><div class="d">City-level prices need DoCA's centre reports (behind a CAPTCHA) or the data.gov.in mandi API (needs a key).</div></div>
      <div class="st warning"><div class="t">⚠️ No history before ${esc(fmtDay(H.first_date))}</div><div class="d">The official retail CSVs on data.gov.in end in 2015 and need an API key. The series grows by one real day per DoCA update.</div></div>
    </div>
    <div class="cov" id="cov"></div>
    <div class="legend"><span><i style="background:var(--accent)"></i>price published &amp; stored</span><span><i style="border:1.5px dashed var(--critical)"></i>no price that day (gap)</span></div>
  </section>

  <section class="card reveal" id="method">
    <div class="card-head"><div><h2>Method &amp; provenance</h2><div class="sub">Everything here can be traced back to a raw page on disk</div></div></div>
    <div class="method">
      <div class="formula">cost(day) = Σ qty<sub>i</sub> × price<sub>i</sub>(day) × unit factor<sub>i</sub><br>index(day) = cost(day) / cost(base) × 100<br><span style="color:var(--muted)">// any ingredient missing → that day is MISSING (no partial sums, no substitutes)</span></div>
      <dl class="kv">
        <dt>Source</dt><dd><a href="${esc(data.source_url)}" target="_blank" rel="noopener">DoCA Price Monitoring Division ↗</a></dd>
        <dt>Last fetch</dt><dd class="num">${esc(data.provenance ? data.provenance.fetched_at.replace("T", " ").slice(0, 19) + " UTC" : "—")}</dd>
        <dt>Raw sha256</dt><dd class="num" title="${esc(data.provenance ? data.provenance.raw_sha256 : "")}">${esc(data.provenance ? data.provenance.raw_sha256.slice(0, 16) + "…" : "—")}</dd>
        <dt>Pipeline</dt><dd>GitHub Actions, daily 19:00 IST. Raw + processed files are committed; this page reads only those.</dd>
        <dt>Docs</dt><dd><a href="${esc(data.repo_url)}/blob/main/docs/sources.md" target="_blank" rel="noopener">sources</a> · <a href="${esc(data.repo_url)}/blob/main/docs/decisions.md" target="_blank" rel="noopener">decisions</a></dd>
      </dl>
    </div>
  </section>

  <div class="foot">No synthetic data. Gaps are shown, never filled. Data: Department of Consumer Affairs, Govt. of India.</div>`;

  const tip = makeTip(parentElement);

  countUp(root.querySelector("#big"), total, (v) => inr.format(v));
  countUp(root.querySelector("#kidx"), L ? L.index : null, (v) => v.toFixed(1));

  // katori tooltips (hover + keyboard focus)
  root.querySelectorAll(".katori").forEach((g) => {
    const it = items[Number(g.dataset.i)];
    const html = `<b>${it.emoji} ${esc(it.label)}</b><br>${esc(it.qty)} ${esc(it.unit)} × ${esc(inr.format(it.price))}${esc(unitLabel[it.source_unit] || "")}<br><b>${esc(inr.format(it.cost))}</b> · ${(it.share * 100).toFixed(1)}% of the thali<br><span class="m">DoCA: "${esc(it.source_commodity)}"</span>`;
    g.addEventListener("pointermove", (e) => tip.show(html, e.clientX, e.clientY));
    g.addEventListener("pointerleave", () => tip.hide());
    g.addEventListener("focus", () => { const r = g.getBoundingClientRect(); tip.show(html, r.right, r.top); });
    g.addEventListener("blur", () => tip.hide());
  });

  // breakdown rows
  const maxShare = Math.max(...items.map((i) => i.share), 0);
  root.querySelector("#rows").innerHTML = items.length ? items.map((it) => `
    <div class="row">
      <div class="em">${it.emoji}</div>
      <div class="nm">${esc(it.label)}<small>${esc(it.qty)} ${esc(it.unit)} · ${esc(inr.format(it.price))}${esc(unitLabel[it.source_unit] || "")}</small></div>
      <div class="track" title="${(it.share * 100).toFixed(1)}%"><div class="fill" data-w="${((it.share / maxShare) * 100).toFixed(1)}"></div></div>
      <div class="rs num">${esc(inr.format(it.cost))}<small>${(it.share * 100).toFixed(1)}%</small></div>
    </div>`).join("") : `<div class="empty">No complete basket yet.</div>`;

  // movers
  const mv = data.movers || { rows: [], reason: "No data." };
  root.querySelector("#movers").innerHTML = mv.reason
    ? `<div class="empty"><div class="icon">⏳</div><div><b>Waiting for day 2</b><br>${esc(mv.reason)}</div></div>`
    : mv.rows.map((r) => `<div class="mv"><div>${esc(r.commodity)}<div style="color:var(--muted);font-size:12px">${esc(inr.format(r.from))} → ${esc(inr.format(r.to))}</div></div><div class="pct num ${r.pct >= 0 ? "up" : "down"}">${r.pct >= 0 ? "▲" : "▼"} ${Math.abs(r.pct).toFixed(1)}%</div></div>`).join("")
      + `<div class="note">${esc(fmtDay(mv.rows[0].date_from, false))} → ${esc(fmtDay(mv.rows[0].date_to, false))} (${mv.rows[0].days_between} day${mv.rows[0].days_between > 1 ? "s" : ""} apart)</div>`;

  // coverage grid
  const cov = data.coverage || { days: [], rows: [] };
  root.querySelector("#cov").innerHTML = cov.rows.length ? `
    <table><thead><tr><th></th>${cov.days.map((d) => `<th>${esc(fmtDay(d, false))}</th>`).join("")}</tr></thead>
    <tbody>${cov.rows.map((r) => `<tr><td class="lbl">${r.emoji} ${esc(r.label)}</td>${r.cells.map((c, j) => `<td><div class="cell ${c ? "on" : "off"}" title="${esc(r.label)} · ${esc(fmtDay(cov.days[j]))}: ${c ? "published" : "no price (gap)"}"></div></td>`).join("")}</tr>`).join("")}</tbody></table>` : "";

  // trend chart (re-rendered on resize)
  const chartEl = root.querySelector("#chart");
  const draw = () => trendChart(chartEl, data.series || [], data.base_date, tip);
  draw();
  const ro = new ResizeObserver(() => draw());
  ro.observe(chartEl);

  // jump links scroll inside the page
  root.querySelectorAll("[data-go]").forEach((a) => a.addEventListener("click", (e) => {
    e.preventDefault();
    root.querySelector(`#${a.dataset.go}`)?.scrollIntoView({ behavior: reduceMotion() ? "auto" : "smooth", block: "start" });
  }));

  // reveal-on-scroll + animate bars when visible
  const io = new IntersectionObserver((entries) => entries.forEach((en) => {
    if (!en.isIntersecting) return;
    en.target.classList.add("in");
    en.target.querySelectorAll(".fill").forEach((f) => { f.style.width = `${f.dataset.w}%`; });
    io.unobserve(en.target);
  }), { threshold: 0.12 });
  root.querySelectorAll(".reveal, .card").forEach((s) => io.observe(s));

  return () => { ro.disconnect(); io.disconnect(); };
}
