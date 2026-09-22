'use strict';
// Experiment console. Vanilla JS, no dependencies. The server only sends numbers.
(() => {
  const $ = (s) => document.querySelector(s);
  const W = 720, H = 540, TAU = Math.PI * 2;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const lerp = (a, b, t) => a + (b - a) * t;
  const angLerp = (a, b, t) => { const d = ((b - a + Math.PI) % TAU + TAU) % TAU - Math.PI; return a + d * t; };
  const MONO = 'ui-monospace, "SF Mono", Menlo, Consolas, monospace';
  const SANS = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
  const C = { bg: '#0b0e12', grid: '#18202a', grid2: '#243040', line: '#242b35', text: '#d6dce4', muted: '#7c8794',
    faint: '#515b67', data: '#4fb3d9', eth: '#e0a340', alert: '#e25c5c', ok: '#5fbf8f' };
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const fmt = (v, d = 2) => (v === undefined || v === null || Number.isNaN(v)) ? '–' : Number(v).toFixed(d).replace('.', ',');

  // ---------------------------------------------------------------- state
  let hello = null, cur = null, prev = null, tCur = 0, frames = 0;
  const subs = {};
  const trail = [];                    // arena trajectory (20 s)
  const ethHist = [];                  // 120 s
  const chHist = [];                   // 20 s of channel frames
  const csv = [];                      // exported data, 10 Hz
  let lastCsvT = -1, lastChT = -1, lastEthT = -1;
  let scXY = null, scKind = null, scAspect = 1, scRates = null;
  let demoOn = false, recording = false;
  let prevSip = false, prevLorr = false, prevDown = false, prevPuddles = new Map();
  let intakes = 0;
  window.__mosca = { frames: () => frames, state: () => cur };

  // ---------------------------------------------------------------- canvases
  function fit(c, h) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = c.clientWidth || 300, hh = h || c.clientHeight || 150;
    if (c.width !== Math.round(w * dpr) || c.height !== Math.round(hh * dpr)) {
      c.width = Math.round(w * dpr); c.height = Math.round(hh * dpr);
    }
    const g = c.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    return [g, w, hh];
  }
  const arena = $('#table');
  function fitArena() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = arena.clientWidth || W;
    const px = Math.round(w * dpr), py = Math.round(w * dpr * H / W);
    if (arena.width !== px) { arena.width = px; arena.height = py; }
    const g = arena.getContext('2d');
    g.setTransform(px / W, 0, 0, py / H, 0, 0);
    return g;
  }

  // ---------------------------------------------------------------- phase label (level only)
  function phaseOf(m) {
    if (m.lorr) return ['Pérdida del reflejo de enderezamiento', 'bad'];
    if (m.down) return ['Caída', 'bad'];
    const a = m.a;
    if (a < 0.15) return ['Basal', 'good'];
    if (a < 0.6) return ['Estimulación', 'warn'];
    if (a < 0.7) return ['Hipotonía motora', 'warn'];
    return ['Sedación', 'bad'];
  }

  // ---------------------------------------------------------------- arena
  function drawArena(now) {
    const g = fitArena();
    g.fillStyle = C.bg; g.fillRect(0, 0, W, H);
    // grid: 30 u
    g.lineWidth = 1;
    for (let x = 0; x <= W; x += 30) { g.strokeStyle = x % 150 === 0 ? C.grid2 : C.grid; g.beginPath(); g.moveTo(x + .5, 0); g.lineTo(x + .5, H); g.stroke(); }
    for (let y = 0; y <= H; y += 30) { g.strokeStyle = y % 150 === 0 ? C.grid2 : C.grid; g.beginPath(); g.moveTo(0, y + .5); g.lineTo(W, y + .5); g.stroke(); }
    // arena boundary (walls at 30 u)
    g.strokeStyle = '#4a5666'; g.setLineDash([4, 4]); g.strokeRect(30.5, 30.5, W - 61, H - 61); g.setLineDash([]);
    if (!cur) { hud(g); return; }
    const s = interp(now);
    // odour field (faint isolines)
    for (const p of cur.puddles) {
      const sub = subs[p.kind] || {};
      for (const r of [60, 120, 200]) {
        g.strokeStyle = hexA(sub.color || '#888888', 0.08 * p.amt);
        g.beginPath(); g.arc(p.x, p.y, r, 0, TAU); g.stroke();
      }
    }
    // drops
    for (const p of cur.puddles) {
      const sub = subs[p.kind] || { name: p.kind, color: '#999999', abv: 0 };
      const r = 5 + 11 * Math.sqrt(clamp(p.amt, 0, 1));
      g.fillStyle = hexA(sub.color, 0.35); g.strokeStyle = hexA(sub.color, 0.9); g.lineWidth = 1.2;
      g.beginPath(); g.arc(p.x, p.y, r, 0, TAU); g.fill(); g.stroke();
      g.fillStyle = '#aab4c0'; g.font = `11px ${MONO}`; g.textBaseline = 'middle';
      const label = `${sub.name} ${Math.round(sub.abv * 100)}% · ${Math.round(p.amt * 100)}%`;
      const right = p.x + r + 5 + g.measureText(label).width < W - 34;      // keep the label inside the arena
      g.textAlign = right ? 'left' : 'right';
      g.fillText(label, right ? p.x + r + 5 : p.x - r - 5, p.y);
    }
    // trajectory, coloured by ethanol level
    for (let i = 1; i < trail.length; i++) {
      const a = trail[i - 1], b = trail[i];
      if (Math.hypot(b.x - a.x, b.y - a.y) > 40) continue;
      const age = (now - b.t) / 20000;
      g.strokeStyle = mixColor(C.data, C.eth, clamp(b.a / 0.8, 0, 1), 0.85 * (1 - age));
      g.lineWidth = 1.3;
      g.beginPath(); g.moveTo(a.x, a.y); g.lineTo(b.x, b.y); g.stroke();
    }
    drawFly(g, s, now);
    hud(g);
  }

  function drawFly(g, s, now) {
    g.save();
    g.translate(s.x, s.y);
    const down = s.pose !== 'up';
    const scale = 1.7 * (1 + 0.35 * s.z);        // drawn 1.7x so the posture is readable
    if (s.z > 0.05) {                         // shadow when airborne
      g.fillStyle = 'rgba(0,0,0,0.35)';
      g.beginPath(); g.ellipse(6 * s.z, 8 * s.z, 9, 5, s.th, 0, TAU); g.fill();
    }
    g.rotate(s.th);
    g.scale(scale, scale);
    const body = down ? '#6f6557' : '#c2ab80';
    // legs: three pairs, stepping phase from distance travelled
    const ph = legPhase;
    g.strokeStyle = down ? '#5d5448' : '#a8926b'; g.lineWidth = 0.9;
    for (let k = 0; k < 3; k++) {
      for (const side of [-1, 1]) {
        const base = -3 + k * 3;
        const swing = down ? Math.sin(now / 90 + k + side) * 0.5 : Math.sin(ph + (k % 2 === (side > 0 ? 0 : 1) ? 0 : Math.PI)) * 0.35;
        const ang = side * (Math.PI / 2 + (k - 1) * 0.55 + swing);
        const L = down ? 6 : 8;
        g.beginPath(); g.moveTo(base, side * 1.6);
        g.lineTo(base + Math.cos(ang) * L, side * 1.6 + Math.sin(ang) * L); g.stroke();
      }
    }
    // wings
    const fly = s.z > 0.05;
    g.fillStyle = 'rgba(200,215,230,0.22)'; g.strokeStyle = 'rgba(200,215,230,0.5)'; g.lineWidth = 0.6;
    for (const side of [-1, 1]) {
      const open = fly ? 1.1 : (s.wing > 0.1 && side > 0 ? 1.4 * s.wing : 0.18);
      g.save(); g.rotate(Math.PI + side * open);
      g.beginPath(); g.ellipse(-8, 0, 8, 2.6, 0, 0, TAU); g.fill(); g.stroke();
      g.restore();
    }
    // abdomen, thorax, head
    g.fillStyle = body;
    g.beginPath(); g.ellipse(-6, 0, 6.5, 3.6, 0, 0, TAU); g.fill();
    g.fillStyle = down ? '#5a5146' : '#8f7a57';
    for (let k = 0; k < 3; k++) { g.fillRect(-9 + k * 2.6, -3.2, 1, 6.4); }
    g.fillStyle = body;
    g.beginPath(); g.ellipse(1.5, 0, 3.8, 3.2, 0, 0, TAU); g.fill();
    g.fillStyle = down ? '#6b3a36' : '#a3453c';
    g.beginPath(); g.ellipse(6, 0, 2.4, 3.1, 0, 0, TAU); g.fill();
    // proboscis (MN9), graded
    if (s.prob > 0.05) {
      g.strokeStyle = s.act === 'sip' ? C.data : '#8fb8c9'; g.lineWidth = 1.2;
      g.beginPath(); g.moveTo(8.2, 0); g.lineTo(8.2 + 5 * s.prob, 0); g.stroke();
    }
    g.restore();
    // tags
    const tags = [];
    if (cur.lorr) tags.push(['LORR', C.alert]);
    else if (cur.down) tags.push(['CAÍDA', C.alert]);
    if (cur.sip) tags.push(['PER · ingesta', C.data]);
    if (s.z > 0.1) tags.push(['VUELO', C.ok]);
    g.font = `10px ${MONO}`; g.textBaseline = 'middle';
    tags.forEach(([txt, col], i) => {
      const x = s.x + 16, y = s.y - 14 - i * 14;
      const w = g.measureText(txt).width + 8;
      g.fillStyle = 'rgba(7,9,12,0.8)'; g.fillRect(x, y - 6, w, 12);
      g.strokeStyle = col; g.lineWidth = 1; g.strokeRect(x + .5, y - 5.5, w - 1, 11);
      g.fillStyle = col; g.textAlign = 'left'; g.fillText(txt, x + 4, y + 0.5);
    });
  }

  function hud(g) {
    g.font = `12px ${MONO}`; g.textAlign = 'left'; g.textBaseline = 'top'; g.fillStyle = '#aab4c0';
    const t = cur ? cur.tt : 0;
    g.fillText(`t = ${fmt(t, 1)} s`, 38, 38);
    if (cur) {
      g.fillStyle = C.eth; g.fillText(`EtOH = ${fmt(cur.a, 3)}`, 38, 55);
    }
    // scale bar: 100 u
    g.strokeStyle = '#aab4c0'; g.lineWidth = 1.5;
    g.beginPath(); g.moveTo(W - 140, H - 42); g.lineTo(W - 40, H - 42); g.stroke();
    g.beginPath(); g.moveTo(W - 140, H - 46); g.lineTo(W - 140, H - 38); g.moveTo(W - 40, H - 46); g.lineTo(W - 40, H - 38); g.stroke();
    g.fillStyle = '#aab4c0'; g.textAlign = 'center'; g.textBaseline = 'bottom'; g.fillText('100 u', W - 90, H - 47);
    if (recording) { g.fillStyle = C.alert; g.textAlign = 'right'; g.textBaseline = 'top'; g.fillText('● REC', W - 38, 38); }
  }

  let legPhase = 0, lastRender = 0;
  function interp(now) {
    if (!prev) return cur.f;
    const u = clamp((now - tCur) / 33.3, 0, 1);
    const a = prev.f, b = cur.f;
    return { ...b, x: lerp(a.x, b.x, u), y: lerp(a.y, b.y, u), th: angLerp(a.th, b.th, u), z: lerp(a.z, b.z, u),
      prob: lerp(a.prob, b.prob, u), wing: lerp(a.wing, b.wing, u) };
  }

  // ---------------------------------------------------------------- plots
  function drawEth() {
    const [g, w, h] = fit($('#ethPlot'), 110);
    g.clearRect(0, 0, w, h);
    const pad = { l: 30, r: 6, t: 6, b: 16 };
    const X = (t) => pad.l + (1 - (performance.now() - t) / 120000) * (w - pad.l - pad.r);
    const Y = (a) => pad.t + (1 - a) * (h - pad.t - pad.b);
    g.font = `9px ${MONO}`; g.fillStyle = C.faint; g.textAlign = 'right'; g.textBaseline = 'middle';
    for (const [v, lab] of [[0, '0'], [0.5, '0,5'], [1, '1']]) {
      g.strokeStyle = C.line; g.beginPath(); g.moveTo(pad.l, Y(v) + .5); g.lineTo(w - pad.r, Y(v) + .5); g.stroke();
      g.fillText(lab, pad.l - 4, Y(v));
    }
    g.setLineDash([3, 3]);
    for (const v of [0.15, 0.6, 0.7]) {
      g.strokeStyle = v === 0.7 ? 'rgba(226,92,92,.55)' : 'rgba(224,163,64,.4)';
      g.beginPath(); g.moveTo(pad.l, Y(v) + .5); g.lineTo(w - pad.r, Y(v) + .5); g.stroke();
    }
    g.setLineDash([]);
    g.textAlign = 'left'; g.textBaseline = 'top'; g.fillStyle = C.faint;
    g.fillText('−120 s', pad.l, h - pad.b + 3); g.textAlign = 'right'; g.fillText('ahora', w - pad.r, h - pad.b + 3);
    if (ethHist.length < 2) return;
    g.strokeStyle = C.eth; g.lineWidth = 1.5; g.beginPath();
    ethHist.forEach((p, i) => { const x = X(p.t), y = Y(clamp(p.a, 0, 1)); if (i) g.lineTo(x, y); else g.moveTo(x, y); });
    g.stroke();
  }

  function laneScale(key) {
    const thr = hello && hello.thresholds ? hello.thresholds[key] : null;
    const hi = Math.max(8, thr ? thr * 3 : 0);
    return { lo: 0.05, hi, thr };
  }
  function drawTraces() {
    const c = $('#traces');
    const [g, w, h] = fit(c);
    g.clearRect(0, 0, w, h);
    if (!hello || !hello.channels) return;
    const ch = hello.channels, n = ch.length;
    const labW = Math.min(170, w * 0.36), valW = 48, top = 4, bot = 18;
    const laneH = (h - top - bot) / n;
    const x0 = labW, x1 = w - valW;
    const now = performance.now();
    const X = (t) => x0 + (1 - (now - t) / 20000) * (x1 - x0);
    g.font = `10px ${SANS}`;
    for (let i = 0; i < n; i++) {
      const y0 = top + i * laneH, y1 = y0 + laneH - 4;
      const { lo, hi, thr } = laneScale(ch[i].key);
      const Y = (v) => y1 - (Math.log10(clamp(v, lo, hi)) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo)) * (y1 - y0);
      g.fillStyle = i % 2 ? '#0c1015' : '#0a0d11'; g.fillRect(0, y0 - 2, w, laneH);
      g.strokeStyle = C.line; g.setLineDash([2, 3]); g.beginPath(); g.moveTo(x0, Y(1) + .5); g.lineTo(x1, Y(1) + .5); g.stroke(); g.setLineDash([]);
      if (thr) { g.strokeStyle = 'rgba(226,92,92,.7)'; g.beginPath(); g.moveTo(x0, Y(thr) + .5); g.lineTo(x1, Y(thr) + .5); g.stroke(); }
      g.fillStyle = C.muted; g.textAlign = 'left'; g.textBaseline = 'middle';
      g.fillText(ch[i].label, 6, (y0 + y1) / 2);
      if (chHist.length > 1) {
        g.strokeStyle = C.data; g.lineWidth = 1.2; g.beginPath();
        let first = true;
        for (const p of chHist) {
          const x = X(p.t); if (x < x0) continue;
          const y = Y(p.v[i]);
          if (first) { g.moveTo(x, y); first = false; } else g.lineTo(x, y);
        }
        g.stroke();
        const v = chHist[chHist.length - 1].v[i];
        g.fillStyle = thr && v >= thr ? C.alert : C.text; g.font = `10px ${MONO}`; g.textAlign = 'right';
        g.fillText(fmt(v, v >= 100 ? 0 : 2), w - 4, (y0 + y1) / 2); g.font = `10px ${SANS}`;
      }
    }
    g.fillStyle = C.faint; g.font = `9px ${MONO}`; g.textAlign = 'left'; g.textBaseline = 'bottom';
    g.fillText('−20 s', x0, h - 3); g.textAlign = 'right'; g.fillText('ahora', x1, h - 3);
  }

  const SYN = [
    ['mono', 'Monoaminas (OA, DA, 5-HT)', 0, 2, '×'],
    ['exc', 'Excitación (ACh)', 0, 2, '×'],
    ['inh', 'Inhibición (GABA, Glu, His)', 0, 2, '×'],
    ['olf', 'Sensibilidad olfativa', 0, 2, '×'],
    ['noise', 'Ruido sináptico (σ)', 0, 0.5, ''],
    ['delay', 'Retraso sensorial', 0, 400, ' ms'],
  ];
  function buildSyn() {
    const box = $('#synapse'); box.textContent = '';
    for (const [k, lab, lo, hi] of SYN) {
      const row = document.createElement('div'); row.className = 'row';
      row.innerHTML = `<span class="lab">${lab}</span><span class="track"><i></i>${hi === 2 ? '<b></b>' : ''}</span><span class="val">–</span>`;
      if (hi === 2) row.querySelector('b').style.left = '50%';
      row.dataset.k = k; row.dataset.lo = lo; row.dataset.hi = hi;
      box.append(row);
    }
  }
  function updateSyn(e) {
    for (const row of $('#synapse').children) {
      const k = row.dataset.k, lo = +row.dataset.lo, hi = +row.dataset.hi;
      const v = e[k];
      const bar = row.querySelector('i');
      if (hi === 2) {                                  // multiplier: bar grows from 1
        const a = clamp((Math.min(v, 1) - lo) / (hi - lo), 0, 1), b = clamp((Math.max(v, 1) - lo) / (hi - lo), 0, 1);
        bar.style.left = a * 100 + '%'; bar.style.width = (b - a) * 100 + '%';
        bar.style.background = v < 1 ? '#7f8fd6' : C.eth;
      } else {
        bar.style.left = '0'; bar.style.width = clamp((v - lo) / (hi - lo), 0, 1) * 100 + '%';
      }
      const suffix = SYN.find((s) => s[0] === k)[4];
      row.querySelector('.val').textContent = suffix === '×' ? '×' + fmt(v, 2) : fmt(v, k === 'delay' ? 0 : 2) + suffix;
    }
  }

  function drawPop() {
    const c = $('#brain');
    if (!c.offsetParent) return;
    const [g, w, h] = fit(c);
    g.fillStyle = C.bg; g.fillRect(0, 0, w, h);
    if (!scXY) return;
    const pad = 10;
    let bw = w - 2 * pad, bh = h - 2 * pad;
    if (bw / bh > scAspect) bw = bh * scAspect; else bh = bw / scAspect;
    const ox = (w - bw) / 2, oy = (h - bh) / 2;
    for (let i = 0; i < scKind.length; i++) {
      const x = ox + (scXY[2 * i] / 255) * bw, y = oy + (scXY[2 * i + 1] / 255) * bh;
      const u = scRates ? scRates[i] / 255 : 0;
      const k = scKind[i];
      const base = k === 1 ? [138, 127, 214] : k === 0 ? [79, 179, 217] : [217, 180, 95];
      const lum = 0.12 + 0.88 * clamp(u * 1.8, 0, 1);
      g.fillStyle = `rgba(${base[0]},${base[1]},${base[2]},${lum})`;
      if (k === 1) g.fillRect(x - 1.2, y - 1.2, 2.4, 2.4);
      else { g.beginPath(); g.arc(x, y, k === 0 ? 1.8 : 1.3, 0, TAU); g.fill(); }
    }
    g.fillStyle = C.faint; g.font = `9px ${MONO}`; g.textAlign = 'left'; g.textBaseline = 'top';
    g.fillText('cerebro', 6, 6); g.textBaseline = 'bottom'; g.fillText('cordón ventral', 6, h - 6);
  }

  // ---------------------------------------------------------------- render loop
  function render(now) {
    requestAnimationFrame(render);
    if (cur) {
      const s = cur.f;
      if (!reduceMotion) legPhase += (Math.abs(s.v) * Math.max(0, now - lastRender) / 1000) / 5;
    }
    lastRender = now;
    drawArena(now);
    if (now - sideT > 66) { sideT = now; drawTraces(); drawEth(); drawPop(); }
  }
  let sideT = 0;

  // ---------------------------------------------------------------- event log
  function clockStr(t) {
    const s = Math.max(0, t);
    const hh = Math.floor(s / 3600), mm = Math.floor(s / 60) % 60, ss = s % 60;
    return `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}:${ss.toFixed(1).padStart(4, '0')}`;
  }
  let nLog = 0;
  function log(text, cls = 'ev-user', t = cur ? cur.tt : 0) {
    const li = document.createElement('li');
    const s = Math.max(0, t);
    li.innerHTML = `<span class="t">${String(Math.floor(s / 60)).padStart(2, '0')}:${(s % 60).toFixed(1).padStart(4, '0')}</span><span class="${cls}"></span>`;
    li.lastChild.textContent = text;
    const box = $('#log'); box.prepend(li);
    while (box.children.length > 300) box.lastChild.remove();
    nLog++; $('#logCount').textContent = `${nLog} eventos`;
  }

  function detectEvents(m) {
    const ch = hello && hello.channels ? Object.fromEntries(hello.channels.map((c, i) => [c.key, m.ch[i]])) : {};
    for (const fx of m.fx || []) {
      if (fx === 'fall') log(`Caída · tono motor de las patas ${fmt(m.tone, 2)} × sobrio (umbral ${fmt(hello.thresholds.tone_fall, 2)})`, 'ev-alert');
      else if (fx === 'wake') log(`Enderezamiento · tono motor ${fmt(m.tone, 2)} × sobrio`, 'ev-ok');
      else if (fx === 'escape') log(`Despegue · DNp01 ${fmt(ch.DNp01, 0)} × reposo (umbral ${fmt(hello.thresholds.DNp01, 0)})`, 'ev-neuro');
      else if (fx === 'tap') log('Estímulo mecánico aplicado (órgano de Johnston)', 'ev-user');
      else if (fx === 'shower') log('Lavado: etanol a 0', 'ev-user');
      else if (fx === 'vapor') log('Exposición a vapor de etanol: entra en la hemolinfa sin ingesta', 'ev-eth');
    }
    if (m.sip && !prevSip) {
      const p = nearestPuddle(m);
      const sub = p ? subs[p.kind] : null;
      intakes++;
      log(`PER · MN9 ${fmt(ch.MN9, 2)} × reposo > umbral ${fmt(hello.thresholds.MN9, 2)} · ingesta${sub ? ' de ' + sub.name.toLowerCase() : ''}`, 'ev-neuro');
    } else if (!m.sip && prevSip) log('Fin de la ingesta', 'ev-neuro');
    if (m.lorr && !prevLorr) log('LORR: sin recuperación postural en 3 s', 'ev-alert');
    if (!m.lorr && prevLorr) log('Fin de LORR', 'ev-ok');
    // drops: new ones and those that disappear without being drunk
    const seen = new Map(m.puddles.map((p) => [p.id, p]));
    for (const [id, p] of prevPuddles) {
      if (!seen.has(id)) {
        const sub = subs[p.kind] || { name: p.kind };
        log(p.amt < 0.05 ? `Gota de ${sub.name.toLowerCase()} consumida` : `Gota de ${sub.name.toLowerCase()} evaporada sin tocar`, 'ev-eth');
      }
    }
    prevPuddles = seen;
    prevSip = m.sip; prevLorr = m.lorr; prevDown = m.down;
  }
  function nearestPuddle(m) {
    let best = null, bd = 1e9;
    for (const p of m.puddles) { const d = Math.hypot(p.x - m.f.x, p.y - m.f.y); if (d < bd) { bd = d; best = p; } }
    return best;
  }

  // ---------------------------------------------------------------- messages
  function b64bytes(s) { const bin = atob(s); const u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return u; }
  function onHello(m) {
    hello = m;
    const body = $('#substances'); body.textContent = '';
    for (const d of m.substances || []) {
      subs[d.id] = d;
      const tr = document.createElement('tr');
      const note = d.impurity > 0.1 ? 'con impurezas' : (d.sugar >= 0.5 ? 'dulce' : (d.abv >= 0.35 ? 'amarga' : ''));
      tr.innerHTML = `<td><span class="swatch" style="background:${d.color}"></span>${d.name}<span class="note">${note}</span></td>
        <td class="num">${Math.round(d.abv * 100)} %</td><td class="num">${fmt(d.sugar, 2)}</td><td class="num">${fmt(d.dose, 2)}</td>
        <td><button class="btn small" type="button">Administrar</button></td>`;
      tr.querySelector('button').addEventListener('click', (e) => administer(d.id, e.currentTarget));
      body.append(tr);
    }
    if (m.scatter && m.scatter.n) {
      scXY = b64bytes(m.scatter.xy); scKind = b64bytes(m.scatter.kind); scAspect = m.scatter.aspect || 1;
      $('#popMeta').textContent = `${m.scatter.n.toLocaleString('es')} somas de ${m.model ? m.model.N.toLocaleString('es') : '–'}`;
    }
    if (m.model) {
      $('#subject').textContent = `Dm-${String(m.model.seed).slice(-6)}`;
      $('#modelLine').textContent = `Modelo: ${m.model.N.toLocaleString('es')} neuronas (${m.model.sensory.toLocaleString('es')} sensoriales, ` +
        `${m.model.descending.toLocaleString('es')} descendentes, ${m.model.motor} motoneuronas) · ${m.model.edges.toLocaleString('es')} conexiones · ${m.model.f_brain} Hz · MaleCNS v1.0`;
    }
    buildSyn();
    if (!nLog) log('Registro iniciado', 'ev-user');
  }

  function onFrame(m) {
    const now = performance.now();
    prev = cur; cur = m; tCur = now; frames++;
    if (prev && Math.hypot(m.f.x - prev.f.x, m.f.y - prev.f.y) > 80) prev = null;
    trail.push({ x: m.f.x, y: m.f.y, a: m.a, t: now });
    while (trail.length && now - trail[0].t > 20000) trail.shift();
    if (now - lastEthT > 250) { ethHist.push({ t: now, a: m.a }); lastEthT = now; }
    while (ethHist.length && now - ethHist[0].t > 121000) ethHist.shift();
    if (m.ch && now - lastChT > 60) { chHist.push({ t: now, v: m.ch }); lastChT = now; }
    while (chHist.length && now - chHist[0].t > 20500) chHist.shift();
    if (m.tt - lastCsvT >= 0.1 || m.tt < lastCsvT) { csv.push(csvRow(m)); lastCsvT = m.tt; if (csv.length > 36000) csv.shift(); }
    if (hello) detectEvents(m);
    if (m.sc) scRates = b64bytes(m.sc);
    updateState(m);
  }

  function updateState(m) {
    const f = m.f;
    $('#clock').textContent = clockStr(m.tt);
    $('#viewers').textContent = m.viewers;
    const [ph, cls] = phaseOf(m);
    const phEl = $('#phase'); phEl.textContent = ph;
    phEl.style.color = cls === 'bad' ? C.alert : cls === 'warn' ? C.eth : C.ok;
    const eth = $('#mEth'); eth.textContent = fmt(m.a, 3); eth.className = 'v mono' + (m.a >= 0.7 ? ' bad' : m.a >= 0.15 ? ' warn' : '');
    const pose = $('#mPose');
    pose.textContent = m.lorr ? 'LORR' : m.down ? 'Caída' : f.z > 0.1 ? 'En vuelo' : 'Erguida';
    pose.className = 'v' + (m.lorr || m.down ? ' bad' : ' good');
    $('#mPoseNote').textContent = m.lorr ? 'sin enderezamiento' : '';
    const tone = $('#mTone'); tone.textContent = fmt(m.tone, 2);
    tone.className = 'v mono' + (hello && m.tone < hello.thresholds.tone_fall ? ' bad' : m.tone < 0.75 ? ' warn' : '');
    $('#mSpeed').textContent = fmt(Math.abs(f.v), 0);
    const per = $('#mPer'); per.textContent = m.sip ? 'Extendida' : f.prob > 0.3 ? 'Parcial' : 'Retraída';
    per.className = 'v' + (m.sip ? ' good' : '');
    $('#mPerNote').textContent = m.sip ? 'ingesta' : '';
    $('#mDrunk').textContent = intakes;
    const hu = $('#mHunger'); hu.textContent = fmt(m.hunger, 2);
    hu.className = 'v mono' + (m.hunger < 0.2 ? ' good' : '');
    $('#mHungerNote').textContent = m.hunger < 0.2 ? 'saciada' : m.hunger > 0.7 ? 'hambrienta' : '';
    $('#mCrop').textContent = fmt(m.crop, 2);
    $('#mMem').textContent = fmt(m.mb * 100, 1);
    const vb = $('#vapor');
    if (m.vapor > 0) { vb.classList.add('on'); vb.textContent = `Vapor de etanol · ${Math.ceil(m.vapor)} s`; }
    else if (vb.classList.contains('on')) { vb.classList.remove('on'); vb.textContent = 'Vapor de etanol (20 s)'; }
    $('#hud').textContent = `x ${fmt(f.x, 0)} · y ${fmt(f.y, 0)} · θ ${fmt(f.th, 2)} rad · v ${fmt(f.v, 1)} u/s · ω ${fmt(f.w, 2)} rad/s · z ${fmt(f.z, 2)}`;
    if (m.eth) updateSyn(m.eth);
    if (m.demo !== demoOn) {
      demoOn = m.demo; const b = $('#demo');
      b.classList.toggle('on', demoOn); b.textContent = demoOn ? 'Detener protocolo' : 'Protocolo automático';
    }
  }

  // ---------------------------------------------------------------- CSV
  function csvRow(m) {
    const f = m.f;
    return [m.tt, m.a, f.x, f.y, f.th, f.z, f.v, f.w, m.lorr ? 'lorr' : m.down ? 'caida' : 'erguida', m.sip ? 1 : 0,
      m.tone, m.hunger, m.crop, m.mb, m.vapor, ...(m.ch || [])].map((v) => typeof v === 'number' ? +v.toFixed(4) : v).join(',');
  }
  function exportCsv() {
    if (!csv.length) return;
    const head = ['t_s', 'etanol', 'x', 'y', 'theta', 'z', 'v', 'w', 'postura', 'ingesta', 'tono_patas', 'hambre', 'buche', 'memoria_kc_mbon', 'vapor_s',
      ...((hello && hello.channels) || []).map((c) => c.key.replace('|', '_'))].join(',');
    const blob = new Blob([head + '\n' + csv.join('\n') + '\n'], { type: 'text/csv' });
    const a = document.createElement('a');
    const d = new Date(), p = (n) => String(n).padStart(2, '0');
    a.download = `exp-dm20k-${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}.csv`;
    a.href = URL.createObjectURL(blob); document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    log(`Datos exportados: ${csv.length} muestras a 10 Hz`, 'ev-user');
  }

  // ---------------------------------------------------------------- video
  function record() {
    if (recording || !arena.captureStream || !window.MediaRecorder) return;
    const type = ['video/mp4;codecs=avc1', 'video/mp4', 'video/webm;codecs=vp9', 'video/webm'].find((t) => MediaRecorder.isTypeSupported(t)) || '';
    const rec = new MediaRecorder(arena.captureStream(30), type ? { mimeType: type, videoBitsPerSecond: 4e6 } : undefined);
    const chunks = [];
    rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
    rec.onstop = () => {
      recording = false;
      const b = $('#rec'); b.classList.remove('on'); b.textContent = 'Grabar vídeo 10 s';
      const blob = new Blob(chunks, { type: rec.mimeType || type || 'video/webm' });
      const a = document.createElement('a');
      a.download = `exp-dm20k-arena.${(rec.mimeType || type).includes('mp4') ? 'mp4' : 'webm'}`;
      a.href = URL.createObjectURL(blob); document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    };
    recording = true; rec.start(250);
    const b = $('#rec'); b.classList.add('on');
    let left = 10; b.textContent = `Grabando… ${left}`;
    const iv = setInterval(() => { left--; b.textContent = `Grabando… ${left}`; if (left <= 0) { clearInterval(iv); rec.stop(); } }, 1000);
  }

  // ---------------------------------------------------------------- colour helpers
  function hexRgb(h) { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
  function hexA(h, a) { const [r, g, b] = hexRgb(h); return `rgba(${r},${g},${b},${a})`; }
  function mixColor(h1, h2, t, a) {
    const c1 = hexRgb(h1), c2 = hexRgb(h2);
    return `rgba(${Math.round(lerp(c1[0], c2[0], t))},${Math.round(lerp(c1[1], c2[1], t))},${Math.round(lerp(c1[2], c2[2], t))},${a})`;
  }

  // ---------------------------------------------------------------- websocket
  let ws = null, backoff = 500, everLive = false;
  function setConn(state) {
    const c = $('#conn');
    c.className = 'status ' + (state === 'live' ? 'live' : 'wait');
    c.textContent = state === 'live' ? 'registrando' : (everLive ? 'reconectando' : 'conectando');
    $('#offline').hidden = state === 'live' || !everLive;
  }
  function connect() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${proto}//${location.host}/ws${location.search}`);
    ws.onopen = () => { backoff = 500; everLive = true; setConn('live'); };
    ws.onmessage = (ev) => {
      let m; try { m = JSON.parse(ev.data); } catch { return; }
      if (m.t === 'frame') onFrame(m);
      else if (m.t === 'hello') onHello(m);
      else if (m.t === 'toast') log(m.text, 'ev-user');
    };
    ws.onclose = () => { setConn('wait'); setTimeout(connect, backoff); backoff = Math.min(backoff * 2, 8000); };
    ws.onerror = () => { try { ws.close(); } catch { /* ignore */ } };
  }
  function send(o) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(o)); }
  function administer(kind, btn) {
    send({ t: 'drink', kind });
    btn.disabled = true; setTimeout(() => { btn.disabled = false; }, 1500);
  }

  // ---------------------------------------------------------------- wiring
  $('#tap').addEventListener('click', () => { send({ t: 'tap' }); const b = $('#tap'); b.disabled = true; setTimeout(() => { b.disabled = false; }, 3000); });
  $('#shower').addEventListener('click', () => send({ t: 'reset' }));
  $('#vapor').addEventListener('click', () => { send({ t: 'vapor' }); const b = $('#vapor'); b.disabled = true; setTimeout(() => { b.disabled = false; }, 10000); });
  $('#demo').addEventListener('click', () => send({ t: 'demo', on: !demoOn }));
  $('#csv').addEventListener('click', exportCsv);
  $('#rec').addEventListener('click', record);
  const dlg = $('#methods');
  $('#methodsLink').addEventListener('click', (e) => { e.preventDefault(); if (dlg.showModal) dlg.showModal(); else dlg.setAttribute('open', ''); });
  $('#methodsClose').addEventListener('click', () => (dlg.close ? dlg.close() : dlg.removeAttribute('open')));
  setConn('wait');
  connect();
  requestAnimationFrame(render);
})();
