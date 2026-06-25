// Four-unit data story. Flat functions, no framework. Renders from web/data.json.

const INK = "#1b2a4a";
const ACCENT = "#c65b3c";

function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
function shortModel(label) {
  return label.replace(" Instruct", "").replace("Meta Llama", "Llama").replace("Google ", "")
    .replace("xAI ", "").replace("Z.ai ", "").replace(" Flash Lite", " Lite").replace(" Small", "");
}

// shared floating-tooltip positioner (keeps the box on screen near the cursor)
function placeTip(box, ev) {
  const pad = 14, w = box.offsetWidth, h = box.offsetHeight;
  let x = ev.clientX + pad, y = ev.clientY + pad;
  if (x + w > window.innerWidth - 8) x = ev.clientX - w - pad;
  if (y + h > window.innerHeight - 8) y = ev.clientY - h - pad;
  box.style.left = Math.max(8, x) + "px";
  box.style.top = Math.max(8, y) + "px";
}

// markup for a hoverable model name (wired by wireModelHovers)
function modelChip(label) {
  return `<span class="mhint" data-model="${label}">${shortModel(label)}</span>`;
}
function modelTip(label, m) {
  if (!m) return `<strong>${label}</strong>`;
  const cls = { frontier: "frontier-class", large: "large", mid: "mid-size", small: "small" }[m.param_class];
  const mo = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const bits = [];
  if (m.maker) bits.push(m.maker);
  if (cls) bits.push(cls + " model");
  if (m.cutoff) { const [y, mm] = m.cutoff.split("-"); bits.push("knowledge cutoff " + (mo[+mm - 1] || "") + " " + y); }
  return `<strong>${label}</strong><br>${bits.join(" · ")}`;
}
function wireModelHovers(models) {
  const tip = document.getElementById("tip");
  if (!tip || !models) return;
  document.querySelectorAll("[data-model]").forEach(el => {
    const label = el.getAttribute("data-model");
    el.addEventListener("mouseenter", e => { tip.innerHTML = modelTip(label, models[label]); tip.style.display = "block"; placeTip(tip, e); });
    el.addEventListener("mousemove", e => { if (tip.style.display === "block") placeTip(tip, e); });
    el.addEventListener("mouseleave", () => { tip.style.display = "none"; });
  });
}

/* ---- 1. example card (one lookup) ---- */
function renderExample(data, el) {
  const ex = data.example;
  const bars = ex.bars.map(b =>
    `<div class="cb-row"><span class="cb-model">${modelChip(b.model)}</span>` +
    `<span class="cb-track"><span class="cb-fill" style="width:${b.score}%"></span></span>` +
    `<span class="cb-score${b.score ? "" : " zero"}">${b.score}</span></div>`).join("");
  const url = `https://en.wikipedia.org/wiki/${encodeURIComponent(ex.name)}`;
  el.innerHTML =
    `<div class="card-head"><div class="card-name">` +
    `<a class="wiki-hit" href="${url}" target="_blank" rel="noopener" data-wiki="${encodeURIComponent(ex.name)}">${ex.name}</a></div>` +
    `<div class="card-desc">${ex.descriptor || cap(ex.category)}</div></div>` +
    `<div class="card-bars">${bars}</div>`;
  const descEl = document.getElementById("ex-desc");
  if (descEl) {
    const desc = ex.descriptor || ex.category;
    descEl.textContent = `${/^[aeiou]/i.test(desc) ? "an" : "a"} ${desc}`;
  }
}

/* ---- 2. fame gradient scatter ---- */
function renderGradient(data, el) {
  const pts = data.gradient;
  const W = 680, H = 380, mL = 58, mR = 16, mT = 12, mB = 56;
  const xs = pts.map(p => Math.log10(p.pv));
  const xmin = Math.min(...xs), xmax = Math.max(...xs);
  const x = v => mL + (Math.log10(v) - xmin) / (xmax - xmin) * (W - mL - mR);
  const y = s => mT + (1 - s / 100) * (H - mT - mB);
  const ticks = [100, 1000, 10000, 100000, 1000000].filter(t => t >= 10 ** xmin && t <= 10 ** xmax);
  const tlab = { 100: "100", 1000: "1K", 10000: "10K", 100000: "100K", 1000000: "1M" };

  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="recognition vs how often looked up">`;
  for (const g of [0, 25, 50, 75, 100]) {
    svg += `<line x1="${mL}" y1="${y(g)}" x2="${W - mR}" y2="${y(g)}" stroke="#ece5d8"/>`;
    svg += `<text class="ax" x="${mL - 8}" y="${y(g) + 4}" text-anchor="end">${g}</text>`;
  }
  for (const t of ticks)
    svg += `<text class="ax" x="${x(t)}" y="${H - 32}" text-anchor="middle">${tlab[t]}</text>`;
  svg += `<text class="ax-title" x="${(mL + W - mR) / 2}" y="${H - 10}" text-anchor="middle">Wikipedia pageviews / month  (log scale) →</text>`;
  svg += `<text class="ax-title" transform="translate(16,${(mT + H - mB) / 2}) rotate(-90)" text-anchor="middle">avg score across 13 models →</text>`;
  for (const p of pts) {
    const enc = encodeURIComponent(p.name);
    svg += `<a class="wiki-hit" href="https://en.wikipedia.org/wiki/${enc}" target="_blank" rel="noopener" data-wiki="${enc}" data-score="${p.score}">` +
           `<circle cx="${x(p.pv).toFixed(1)}" cy="${y(p.score).toFixed(1)}" r="4.5" fill="${INK}" fill-opacity="0.42"/></a>`;
  }

  // call out a few telling outliers so the scatter is readable (placement tuned by hand);
  // each is a link to its Wikipedia page and shows a hover preview (see wireWikiHovers).
  // name = display label; showScore appends the live score; wiki = exact article title.
  // If a person is no longer in the data, HL[p.name] simply never matches → no broken label.
  const HL = {
    "Taylor Swift": { name: "Taylor Swift", showScore: false, dx: -2, dy: 26, anchor: "end", wiki: "Taylor Swift" },
    "Antonio Carlo Napoleone Gallenga": { name: "Antonio Gallenga", showScore: true, dx: 8, dy: 4, anchor: "start", wiki: "Antonio Carlo Napoleone Gallenga" },
    "Lucien Laurent": { name: "Lucien Laurent", showScore: true, dx: 8, dy: -7, anchor: "start", wiki: "Lucien Laurent" },
  };
  for (const p of pts) {
    const h = HL[p.name];
    if (!h) continue;
    const cx = x(p.pv), cy = y(p.score);
    const label = h.showScore ? `${h.name} · ${p.score}` : h.name;
    const url = `https://en.wikipedia.org/wiki/${encodeURIComponent(h.wiki)}`;
    svg += `<a class="wiki-hit" href="${url}" target="_blank" rel="noopener" data-wiki="${encodeURIComponent(h.wiki)}" data-score="${p.score}">`;
    svg += `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="5" fill="${ACCENT}"/>`;
    svg += `<text class="pt-label" x="${(cx + h.dx).toFixed(1)}" y="${(cy + h.dy).toFixed(1)}" text-anchor="${h.anchor}">${label}</text>`;
    svg += `</a>`;
  }
  svg += `</svg>`;
  el.innerHTML = svg;
}

/* ---- Wikipedia hover preview for any .wiki-hit element (scatter points + example card) ---- */
function wireWikiHovers() {
  const card = document.getElementById("wiki-card");
  if (!card) return;
  const cache = {};
  let timer = null;
  const hide = () => { clearTimeout(timer); card.style.display = "none"; };
  // delay before a hover commits, so sweeping across the dense cluster doesn't fire 100 fetches
  const show = (title, ev, score) => {
    clearTimeout(timer);
    const foot = score == null ? "" : ` · recognition ${score}/100`;
    timer = setTimeout(() => {
      card.style.display = "block";
      if (cache[title]) { card.innerHTML = cache[title]; placeTip(card, ev); return; }
      card.innerHTML = `<span class="wc-title">${title}</span><span class="wc-foot">Loading…${foot}</span>`;
      placeTip(card, ev);
      fetch(`https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(title)}`)
        .then(r => { if (!r.ok) throw 0; return r.json(); })
        .then(d => {
          const img = d.thumbnail ? `<img src="${d.thumbnail.source}" alt="">` : "";
          cache[title] = `${img}<span class="wc-title">${d.title}</span>` +
            `<span>${d.extract || ""}</span><span class="wc-foot">Wikipedia · click to open${foot}</span>`;
          if (card.style.display === "block") { card.innerHTML = cache[title]; placeTip(card, ev); }
        })
        .catch(() => {
          card.innerHTML = `<span class="wc-title">${title}</span>` +
            `<span class="wc-foot">Wikipedia preview unavailable${foot}</span>`;
        });
    }, 140);
  };
  document.querySelectorAll(".wiki-hit").forEach(a => {
    const title = decodeURIComponent(a.getAttribute("data-wiki"));
    const score = a.getAttribute("data-score");
    a.addEventListener("mouseenter", e => show(title, e, score));
    a.addEventListener("mousemove", e => { if (card.style.display === "block") placeTip(card, e); });
    a.addEventListener("mouseleave", hide);
  });
}

/* ---- 2b. recognition by occupation ---- */
function renderOccupations(data) {
  const el = document.getElementById("occupations");
  const occ = data.occupations;
  if (!el || !occ) { if (el) el.closest("section").style.display = "none"; return; }
  el.innerHTML = occ.map(o =>
    `<div class="lu-row"><div class="lu-name">${cap(o.category)}s</div>` +
    `<div class="lu-track"><div class="lu-fill" style="width:${o.mean}%;background:${o.category === "athlete" ? ACCENT : INK}"></div></div>` +
    `<div class="lu-val">${o.mean}</div></div>`).join("");
}

/* ---- 3. model lineup ---- */
function renderModelLineup(data, el) {
  el.innerHTML = data.model_lineup.map(m =>
    `<div class="lu-row"><div class="lu-name">${modelChip(m.label)}</div>` +
    `<div class="lu-track"><div class="lu-fill" style="width:${m.mean}%;background:${INK}"></div></div>` +
    `<div class="lu-val">${m.mean}</div></div>`).join("");
  const ml = data.model_lineup;
  const hi = document.getElementById("lineup-hi"), lo = document.getElementById("lineup-lo");
  if (hi) hi.textContent = ml[0].mean;
  if (lo) lo.textContent = ml[ml.length - 1].mean;
}

/* ---- 3b. do the models agree on who? (rank correlation per model) ---- */
function renderModelAgreement(data) {
  const el = document.getElementById("model-agreement");
  const ma = data.model_agreement;
  if (!el || !ma) { if (el) el.closest("section").style.display = "none"; return; }
  el.innerHTML = ma.models.map(m =>
    `<div class="lu-row"><div class="lu-name">${modelChip(m.label)}</div>` +
    `<div class="lu-track"><div class="lu-fill" style="width:${(m.rho * 100).toFixed(0)}%;background:${INK}"></div></div>` +
    `<div class="lu-val">${m.rho.toFixed(2)}</div></div>`).join("");
  const note = document.getElementById("agree-note");
  if (note) note.textContent =
    `Each bar = how closely that model's ordering of the people matches the other twelve, on ` +
    `average (rank correlation, 0–1). Most-alike pair: ${shortModel(ma.most.a)} and ` +
    `${shortModel(ma.most.b)} (${ma.most.rho.toFixed(2)}); least-alike: ${shortModel(ma.least.a)} ` +
    `and ${shortModel(ma.least.b)} (${ma.least.rho.toFixed(2)}).`;
  const am = document.getElementById("agree-mean");
  if (am) am.textContent = ma.mean.toFixed(2);
}

/* ---- inline hint tooltips (hover a .hint span for a small explainer) ---- */
function wireHints() {
  const tip = document.getElementById("tip");
  if (!tip) return;
  document.querySelectorAll(".hint").forEach(el => {
    el.addEventListener("mouseenter", e => { tip.innerHTML = el.getAttribute("data-tip"); tip.style.display = "block"; placeTip(tip, e); });
    el.addEventListener("mousemove", e => { if (tip.style.display === "block") placeTip(tip, e); });
    el.addEventListener("mouseleave", () => { tip.style.display = "none"; });
  });
}

/* ---- 4. name experiment ---- */
function renderNameExperiment(data) {
  const el = document.getElementById("name-experiment");
  const note = document.getElementById("name-exp-note");
  const ne = data.name_experiment;
  if (!ne) { el.closest("section").style.display = "none"; return; }

  const bandOrder = ["lo", "mid", "hi"];
  const rows = bandOrder.map(key => {
    const b = ne.bands[key];
    const max = 100;
    const gapAbs = Math.abs(b.gap);
    const gapColor = gapAbs >= 10 ? "#dc2626" : gapAbs >= 5 ? "#d97706" : "#16a34a";
    const gapBg   = gapAbs >= 10 ? "#fef2f2"  : gapAbs >= 5 ? "#fff7ed"  : "#f0fdf4";
    const bar = (v, color) =>
      `<div class="pb-track" style="flex:1"><div class="pb-fill" style="width:${(v/max*100).toFixed(0)}%;background:${color}"></div></div>` +
      `<div class="pb-val" style="color:${color}">${Math.round(v)}</div>`;
    const ex = b.examples;
    const exHtml = ex
      ? `<div class="ne-examples">` +
        `<span class="ne-ex ne-ex-u">${ex.uniq.name} <strong>${ex.uniq.score}</strong></span>` +
        `<span class="ne-ex ne-ex-s">${ex.shared.name} <strong>${ex.shared.score}</strong></span>` +
        `</div>`
      : "";
    return `<div class="ne-row">` +
      `<div class="ne-band"><strong>${b.label}</strong><span class="ne-pv">${b.pv_label}</span>${exHtml}</div>` +
      `<div class="ne-cell">${bar(b.unique.mean, INK)}</div>` +
      `<div class="ne-cell">${bar(b.shared.mean, "#94a3b8")}</div>` +
      `<div class="ne-gap" style="background:${gapBg};color:${gapColor}">${b.gap >= 0 ? "−" : "+"}${gapAbs.toFixed(0)} pts</div>` +
      `</div>`;
  }).join("");

  const header =
    `<div class="ne-row ne-header">` +
    `<div class="ne-band"></div>` +
    `<div class="ne-cell ne-col-label">Unique name</div>` +
    `<div class="ne-cell ne-col-label">Shared name (4+)</div>` +
    `<div class="ne-gap ne-col-label">Gap</div>` +
    `</div>`;

  el.innerHTML = header + rows;
  if (note) note.textContent = ne.caption;
}

function init() {
  fetch("data.json").then(r => {
    if (!r.ok) throw new Error(`could not load data.json (${r.status})`);
    return r.json();
  }).then(data => {
    const m = document.getElementById("meta-line");
    if (m) m.textContent = `${data.meta.n_people} people · ${data.meta.n_models} models · scores from intheweights.com`;
    document.querySelectorAll(".n-total").forEach(e => { e.textContent = data.meta.n_people; });
    const sc = document.getElementById("n-scatter");
    if (sc && data.meta.n_scatter) sc.textContent = data.meta.n_scatter;
    renderExample(data, document.getElementById("example-card"));
    renderGradient(data, document.getElementById("gradient"));
    renderOccupations(data);
    renderModelLineup(data, document.getElementById("model-lineup"));
    renderModelAgreement(data);
    renderNameExperiment(data);
    wireWikiHovers();
    wireModelHovers(data.models);
    wireHints();
  });
}

init();
