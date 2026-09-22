'use strict';
// 3D view of the arena: a small bar counter at fly scale (1 u = 0,1 mm). Tiny WebGL renderer, no
// dependencies. It only DRAWS what the server sends (position, heading, height, posture, proboscis,
// wings): nothing here decides anything about the fly.
(() => {
  const TAU = Math.PI * 2;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const MAT_H = 8;                        // beer mat under the arena (0,8 mm)

  // ---------------------------------------------------------------- matrices (column-major)
  const I = () => new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
  function mul(a, b) {
    const o = new Float32Array(16);
    for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) {
      o[c * 4 + r] = a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] + a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3];
    }
    return o;
  }
  const T = (x, y, z) => { const m = I(); m[12] = x; m[13] = y; m[14] = z; return m; };
  const S = (x, y, z) => { const m = I(); m[0] = x; m[5] = y; m[10] = z; return m; };
  function RX(a) { const m = I(), c = Math.cos(a), s = Math.sin(a); m[5] = c; m[6] = s; m[9] = -s; m[10] = c; return m; }
  function RY(a) { const m = I(), c = Math.cos(a), s = Math.sin(a); m[0] = c; m[2] = -s; m[8] = s; m[10] = c; return m; }
  function RZ(a) { const m = I(), c = Math.cos(a), s = Math.sin(a); m[0] = c; m[1] = s; m[4] = -s; m[5] = c; return m; }
  function RA(ax, a) {                    // rotation about a unit axis
    const [x, y, z] = ax, c = Math.cos(a), s = Math.sin(a), t = 1 - c, m = I();
    m[0] = t * x * x + c; m[1] = t * x * y + s * z; m[2] = t * x * z - s * y;
    m[4] = t * x * y - s * z; m[5] = t * y * y + c; m[6] = t * y * z + s * x;
    m[8] = t * x * z + s * y; m[9] = t * y * z - s * x; m[10] = t * z * z + c;
    return m;
  }
  const chain = (...ms) => ms.reduce((a, b) => mul(a, b));
  function perspective(fovy, asp, n, f) {
    const t = 1 / Math.tan(fovy / 2), m = new Float32Array(16);
    m[0] = t / asp; m[5] = t; m[10] = (f + n) / (n - f); m[11] = -1; m[14] = 2 * f * n / (n - f);
    return m;
  }
  function lookAt(e, c, up) {
    let zx = e[0] - c[0], zy = e[1] - c[1], zz = e[2] - c[2];
    let l = Math.hypot(zx, zy, zz); zx /= l; zy /= l; zz /= l;
    let xx = up[1] * zz - up[2] * zy, xy = up[2] * zx - up[0] * zz, xz = up[0] * zy - up[1] * zx;
    l = Math.hypot(xx, xy, xz); xx /= l; xy /= l; xz /= l;
    const yx = zy * xz - zz * xy, yy = zz * xx - zx * xz, yz = zx * xy - zy * xx;
    const m = I();
    m[0] = xx; m[4] = xy; m[8] = xz; m[1] = yx; m[5] = yy; m[9] = yz; m[2] = zx; m[6] = zy; m[10] = zz;
    m[12] = -(xx * e[0] + xy * e[1] + xz * e[2]); m[13] = -(yx * e[0] + yy * e[1] + yz * e[2]);
    m[14] = -(zx * e[0] + zy * e[1] + zz * e[2]);
    return m;
  }
  function normalMat(m) {                 // inverse-transpose of the upper 3x3
    const a = m[0], b = m[1], c = m[2], d = m[4], e = m[5], f = m[6], g = m[8], h = m[9], i = m[10];
    const A = e * i - f * h, B = -(d * i - f * g), C = d * h - e * g;
    const det = a * A + b * B + c * C || 1e-9;
    return new Float32Array([A / det, B / det, C / det,
      -(b * i - c * h) / det, (a * i - c * g) / det, -(a * h - b * g) / det,
      (b * f - c * e) / det, -(a * f - c * d) / det, (a * e - b * d) / det]);
  }

  // ---------------------------------------------------------------- geometry
  function lathe(profile, seg = 24) {
    // profile: [[r, y], ...] from bottom to top. Hard edges where the profile bends > 40 degrees.
    const P = [], N = [];
    const sn = [];
    for (let i = 0; i < profile.length - 1; i++) {
      const [r0, y0] = profile[i], [r1, y1] = profile[i + 1];
      const l = Math.hypot(r1 - r0, y1 - y0) || 1;
      sn.push([(y1 - y0) / l, -(r1 - r0) / l]);
    }
    const vn = (i, end) => {              // normal of segment i at its start (end=0) or end (end=1)
      const j = end ? i + 1 : i - 1;
      const a = sn[i];
      if (j < 0 || j >= sn.length) return a;
      const b = sn[j];
      if (a[0] * b[0] + a[1] * b[1] < 0.77) return a;
      const x = a[0] + b[0], y = a[1] + b[1], l = Math.hypot(x, y) || 1;
      return [x / l, y / l];
    };
    for (let i = 0; i < profile.length - 1; i++) {
      const [r0, y0] = profile[i], [r1, y1] = profile[i + 1];
      const n0 = vn(i, 0), n1 = vn(i, 1);
      for (let k = 0; k < seg; k++) {
        const a0 = k / seg * TAU, a1 = (k + 1) / seg * TAU;
        const v = (r, y, a, n) => { P.push(r * Math.cos(a), y, r * Math.sin(a)); N.push(n[0] * Math.cos(a), n[1], n[0] * Math.sin(a)); };
        v(r0, y0, a0, n0); v(r1, y1, a1, n1); v(r1, y1, a0, n1);
        v(r0, y0, a0, n0); v(r0, y0, a1, n0); v(r1, y1, a1, n1);
      }
    }
    return { P, N };
  }
  function sphereProfile(n = 12) {
    const p = [];
    for (let i = 0; i <= n; i++) { const a = -Math.PI / 2 + i / n * Math.PI; p.push([Math.cos(a), Math.sin(a)]); }
    p[0][0] = 0; p[n][0] = 0;
    return p;
  }
  function box() {
    const P = [], N = [];
    const F = [[[1, 0, 0], [0, 1, 0], [0, 0, 1]], [[-1, 0, 0], [0, 1, 0], [0, 0, -1]], [[0, 1, 0], [0, 0, 1], [1, 0, 0]],
      [[0, -1, 0], [0, 0, -1], [1, 0, 0]], [[0, 0, 1], [1, 0, 0], [0, 1, 0]], [[0, 0, -1], [-1, 0, 0], [0, 1, 0]]];
    for (const [n, u, v] of F) {
      const c = (s, t) => [0, 1, 2].map((i) => n[i] + s * u[i] + t * v[i]);
      const q = [c(-1, -1), c(1, -1), c(1, 1), c(-1, -1), c(1, 1), c(-1, 1)];
      for (const p of q) { P.push(...p); N.push(...n); }
    }
    return { P, N };
  }

  // ---------------------------------------------------------------- shaders
  const VS = `attribute vec3 aP; attribute vec3 aN;
uniform mat4 uM; uniform mat4 uVP; uniform mat3 uNm;
varying vec3 vN; varying vec3 vW; varying vec3 vL;
void main(){ vec4 w = uM * vec4(aP, 1.0); vW = w.xyz; vL = aP; vN = uNm * aN; gl_Position = uVP * w; }`;
  const FS = `#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
uniform vec3 uC; uniform float uA; uniform int uMat; uniform vec3 uEye; uniform float uSpec;
varying vec3 vN; varying vec3 vW; varying vec3 vL;
float h(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
void main(){
  vec3 n = normalize(vN);
  if (!gl_FrontFacing) n = -n;
  vec3 c = uC;
  if (uMat == 1) {                       // varnished wood, grain along x
    float t = vW.z * 0.03 + 3.0 * sin(vW.x * 0.0009 + vW.z * 0.0004) + 0.7 * sin(vW.x * 0.0041);
    float g = 0.5 + 0.5 * sin(t);
    float fine = 0.5 + 0.5 * sin(vW.z * 0.55 + 2.0 * sin(vW.x * 0.003));
    c = mix(vec3(0.23, 0.12, 0.06), vec3(0.36, 0.2, 0.1), smoothstep(0.2, 0.9, g));
    c *= 0.93 + 0.1 * fine;
  } else if (uMat == 2) {                // abdomen bands
    float b = step(0.72, fract((vL.x + 1.0) * 2.6)) * step(vL.x, 0.55);
    c = mix(c, c * 0.45, b);
  } else if (uMat == 4) {                // printed beer mat: border and a faint grid
    float e = max(abs(vL.x), abs(vL.z));
    c = e > 0.975 ? vec3(0.45, 0.1, 0.08) : (e > 0.965 ? vec3(0.8, 0.72, 0.55) : c * (0.96 + 0.04 * sin(vW.x * 0.05) * sin(vW.z * 0.043)));
  }
  if (uMat == 3) { gl_FragColor = vec4(c, uA); return; }
  vec3 L1 = normalize(vec3(0.35, 1.0, 0.55)), L2 = normalize(vec3(-0.6, 0.5, -0.4));
  vec3 v = normalize(uEye - vW);
  float d1 = max(dot(n, L1), 0.0), d2 = max(dot(n, L2), 0.0);
  float sp = pow(max(dot(n, normalize(L1 + v)), 0.0), 48.0) * uSpec;
  vec3 col = c * (0.42 + 0.8 * d1 * vec3(1.0, 0.93, 0.8) + 0.22 * d2 * vec3(0.7, 0.8, 1.0)) + sp * vec3(1.0, 0.95, 0.85);
  float dist = length(uEye - vW);
  float fog = clamp((dist - 2500.0) / 9000.0, 0.0, 0.85);
  col = mix(col, vec3(0.07, 0.045, 0.03), fog);
  gl_FragColor = vec4(col, uA);
}`;
  const LVS = `attribute vec3 aP; attribute vec4 aC; uniform mat4 uVP; varying vec4 vC;
void main(){ vC = aC; gl_Position = uVP * vec4(aP, 1.0); }`;
  const LFS = `precision mediump float; varying vec4 vC; void main(){ gl_FragColor = vC; }`;

  function hex(h) { const n = parseInt(h.slice(1), 16); return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255]; }

  function create(canvas, overlay) {
    const gl = canvas.getContext('webgl', { antialias: true, preserveDrawingBuffer: true, alpha: false });
    if (!gl) return null;
    function prog(vs, fs) {
      const p = gl.createProgram();
      for (const [t, s] of [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]]) {
        const sh = gl.createShader(t); gl.shaderSource(sh, s); gl.compileShader(sh);
        if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh));
        gl.attachShader(p, sh);
      }
      gl.linkProgram(p);
      return p;
    }
    const pr = prog(VS, FS), lp = prog(LVS, LFS);
    const loc = {}, lloc = {};
    for (const n of ['uM', 'uVP', 'uNm', 'uC', 'uA', 'uMat', 'uEye', 'uSpec']) loc[n] = gl.getUniformLocation(pr, n);
    loc.aP = gl.getAttribLocation(pr, 'aP'); loc.aN = gl.getAttribLocation(pr, 'aN');
    lloc.uVP = gl.getUniformLocation(lp, 'uVP'); lloc.aP = gl.getAttribLocation(lp, 'aP'); lloc.aC = gl.getAttribLocation(lp, 'aC');
    function mesh(g) {
      const b = gl.createBuffer(), n = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(g.P), gl.STATIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER, n); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(g.N), gl.STATIC_DRAW);
      return { b, n, count: g.P.length / 3 };
    }
    const M = {
      box: mesh(box()),
      sphere: mesh(lathe(sphereProfile(12), 18)),
      ball: mesh(lathe(sphereProfile(6), 10)),
      cyl: mesh(lathe([[0, 0], [1, 0], [1, 1], [0, 1]], 18)),
      tube: mesh(lathe([[1, 0], [1, 1]], 10)),
      glass: mesh(lathe([[0, 0], [0.92, 0], [0.95, 0.08], [1, 1], [0.97, 1], [0.92, 0.1], [0, 0.1]], 40)),
      bottle: mesh(lathe([[0, 0], [1, 0], [1, 0.62], [0.9, 0.72], [0.45, 0.8], [0.34, 0.86], [0.34, 0.98], [0.38, 1], [0, 1]], 32)),
      drop: mesh(lathe([[0, 0]].concat(sphereProfile(10).filter((q) => q[1] >= 0)), 20)),
    };
    let VP = I(), eye = [0, 0, 0], opaque = [], transp = [];
    function draw(m, model, color, { alpha = 1, mat = 0, spec = 0.25 } = {}) {
      (alpha < 1 ? transp : opaque).push({ m, model, color, alpha, mat, spec });
    }
    function flush(list) {
      for (const o of list) {
        gl.uniformMatrix4fv(loc.uM, false, o.model);
        gl.uniformMatrix3fv(loc.uNm, false, normalMat(o.model));
        gl.uniform3fv(loc.uC, o.color); gl.uniform1f(loc.uA, o.alpha); gl.uniform1i(loc.uMat, o.mat);
        gl.uniform1f(loc.uSpec, o.spec);
        gl.bindBuffer(gl.ARRAY_BUFFER, o.m.b); gl.vertexAttribPointer(loc.aP, 3, gl.FLOAT, false, 0, 0);
        gl.bindBuffer(gl.ARRAY_BUFFER, o.m.n); gl.vertexAttribPointer(loc.aN, 3, gl.FLOAT, false, 0, 0);
        gl.drawArrays(gl.TRIANGLES, 0, o.m.count);
      }
    }
    const lineBuf = gl.createBuffer();

    // ---------------------------------------------------------------- camera
    const cam = { yaw: 0.35, pitch: 0.42, dist: 190, tx: 360, ty: 12, tz: 270, follow: true, snap: true };
    const home = { yaw: 0.35, pitch: 0.42, dist: 190 };
    let drag = null;
    const pts = new Map();                // two fingers: pinch to zoom
    let pinch = 0;
    overlay.addEventListener('pointerdown', (e) => {
      pts.set(e.pointerId, [e.clientX, e.clientY]);
      overlay.setPointerCapture(e.pointerId);
      if (pts.size === 2) { const [a, b] = [...pts.values()]; pinch = Math.hypot(a[0] - b[0], a[1] - b[1]); drag = null; }
      else drag = { x: e.clientX, y: e.clientY, id: e.pointerId };
    });
    overlay.addEventListener('pointermove', (e) => {
      if (pts.has(e.pointerId)) pts.set(e.pointerId, [e.clientX, e.clientY]);
      if (pts.size === 2 && pinch > 0) {
        const [a, b] = [...pts.values()], d = Math.hypot(a[0] - b[0], a[1] - b[1]);
        if (d > 0) zoom(pinch / d);
        pinch = d;
        return;
      }
      if (!drag || e.pointerId !== drag.id) return;
      cam.yaw -= (e.clientX - drag.x) * 0.008;
      cam.pitch = clamp(cam.pitch + (e.clientY - drag.y) * 0.006, 0.06, 1.45);
      drag.x = e.clientX; drag.y = e.clientY;
    });
    const end = (e) => { pts.delete(e.pointerId); if (pts.size < 2) pinch = 0; drag = null; };
    overlay.addEventListener('pointerup', end); overlay.addEventListener('pointercancel', end);
    overlay.addEventListener('wheel', (e) => { e.preventDefault(); zoom(Math.exp(clamp(e.deltaY, -300, 300) * 0.0025)); }, { passive: false });
    overlay.addEventListener('dblclick', () => { Object.assign(cam, home); });
    function zoom(k) { cam.dist = clamp(cam.dist * k, 45, 4200); }

    // ---------------------------------------------------------------- static bar
    const WOOD = [0.35, 0.2, 0.1];
    let AW = 2160, AH = 1620;                 // arena size, from the server's hello
    function setArena(w, h) { AW = w; AH = h; cam.tx = AW / 2; cam.tz = AH / 2; }
    function bar() {
      const cx = AW / 2, cz = AH / 2;
      // counter top (surface at y = 0)
      draw(M.box, chain(T(cx, -60, cz - 400), S(AW / 2 + 5000, 60, AH / 2 + 3400)), WOOD, { mat: 1, spec: 0.5 });
      // beer mat under the arena, with a printed border
      draw(M.box, chain(T(cx, MAT_H / 2, cz), S(AW / 2 + 50, MAT_H / 2, AH / 2 + 50)), [0.74, 0.68, 0.56], { mat: 4, spec: 0.05 });
      // pint of beer, at fly scale it towers over the arena
      const gx = AW + 700, gz = AH * 0.25;
      draw(M.tube, chain(T(gx, 0, gz), S(300, 1150, 300)), [0.82, 0.5, 0.1], { alpha: 0.78, spec: 0.6 });
      draw(M.cyl, chain(T(gx, 1150, gz), S(300, 130, 300)), [0.96, 0.93, 0.85], { spec: 0.1 });
      draw(M.glass, chain(T(gx, 0, gz), S(330, 1500, 330)), [0.85, 0.92, 0.95], { alpha: 0.16, spec: 1.2 });
      draw(M.cyl, chain(T(gx, 0.5, gz), S(340, 1, 340)), [0, 0, 0], { alpha: 0.25, mat: 3 });
      // bottle
      const bx = -800, bz = -300;
      draw(M.bottle, chain(T(bx, 0, bz), S(290, 2500, 290)), [0.1, 0.3, 0.14], { alpha: 0.9, spec: 1.0 });
      draw(M.tube, chain(T(bx, 700, bz), S(296, 650, 296)), [0.9, 0.84, 0.66], { spec: 0.1 });
      draw(M.cyl, chain(T(bx, 2490, bz), S(105, 60, 105)), [0.75, 0.62, 0.2], { spec: 0.8 });
      // crown cap, peanuts, napkin (outside the arena)
      draw(M.cyl, chain(T(AW + 420, 0, AH * 0.85), S(140, 30, 140)), [0.7, 0.1, 0.08], { spec: 0.8 });
      for (const [x, z, r] of [[-260, 0.55, 0.3], [-160, 0.62, 1.9], [-330, 0.7, 1.1], [-120, 0.8, 2.6]]) {
        draw(M.sphere, chain(T(x, 30, AH * z), RY(r), S(85, 32, 42)), [0.62, 0.42, 0.24], { spec: 0.15 });
      }
      draw(M.box, chain(T(-1000, 3, AH + 250), RY(0.35), S(520, 3, 520)), [0.93, 0.93, 0.9], { spec: 0.02 });
      // acrylic arena walls at 30 u (the antennae feel them)
      const wall = [0.75, 0.88, 1.0], hW = 45, lx = (AW - 60) / 2 + 3, lz = (AH - 60) / 2 + 3;
      draw(M.box, chain(T(cx, MAT_H + hW / 2, 30), S(lx, hW / 2, 3)), wall, { alpha: 0.14, spec: 1.4 });
      draw(M.box, chain(T(cx, MAT_H + hW / 2, AH - 30), S(lx, hW / 2, 3)), wall, { alpha: 0.14, spec: 1.4 });
      draw(M.box, chain(T(30, MAT_H + hW / 2, cz), S(3, hW / 2, lz)), wall, { alpha: 0.14, spec: 1.4 });
      draw(M.box, chain(T(AW - 30, MAT_H + hW / 2, cz), S(3, hW / 2, lz)), wall, { alpha: 0.14, spec: 1.4 });
      // back bar: wall, shelves and bottles, far away and in the fog
      draw(M.box, chain(T(cx, 3000, -5200), S(10000, 5000, 60)), [0.16, 0.09, 0.05], { mat: 1, spec: 0.1 });
      const cols = ['#2f6b3a', '#8a5a1c', '#b8b8c8', '#6b1f2a', '#c29a3a', '#2a4f7a', '#7a3b12'];
      for (let s = 0; s < 2; s++) {
        const y = 900 + s * 2600;
        draw(M.box, chain(T(cx, y - 60, -4900), S(8500, 60, 320)), [0.3, 0.17, 0.08], { mat: 1, spec: 0.3 });
        for (let i = 0; i < 15; i++) {
          const x = cx - 6500 + i * 930 + (s ? 400 : 0);
          draw(M.bottle, chain(T(x, y, -4900), S(230, 2100 + ((i * 7 + s * 3) % 5) * 180, 230)), hex(cols[(i + s * 3) % cols.length]), { alpha: 0.92, spec: 0.9 });
        }
      }
    }

    // ---------------------------------------------------------------- the fly (drawn only)
    function seg(base, p, q, r, color) {
      const d = [q[0] - p[0], q[1] - p[1], q[2] - p[2]], L = Math.hypot(...d) || 1e-6;
      const u = [d[0] / L, d[1] / L, d[2] / L];
      const ax = [u[2], 0, -u[0]], al = Math.hypot(ax[0], ax[2]);
      const R = al < 1e-6 ? (u[1] > 0 ? I() : RX(Math.PI)) : RA([ax[0] / al, 0, ax[2] / al], Math.acos(clamp(u[1], -1, 1)));
      draw(M.tube, chain(base, T(...p), R, S(r, L, r)), color, { spec: 0.2 });
    }
    function fly(s, now, legPhase) {
      const down = s.pose !== 'up', asleep = s.pose === 'asleep';
      const lift = s.z * 150;
      const roll = down ? (asleep || s.pose === 'back' ? Math.PI : Math.PI / 2) : 0;
      const base = chain(T(s.x, MAT_H + lift + (down ? -1.2 : 0), s.y), RY(-s.th), T(0, 5, 0), RX(roll), T(0, -5, 0));
      // shadow on the mat
      const sh = 1 + s.z * 1.5;
      draw(M.cyl, chain(T(s.x - 1.5, MAT_H + 0.15, s.y), RY(-s.th), S(10 * sh, 0.05, 5.5 * sh)), [0.12, 0.08, 0.04], { alpha: 0.28 * (1 - 0.6 * s.z), mat: 3 });
      const tan = down ? [0.55, 0.47, 0.37] : [0.86, 0.68, 0.42];
      const legC = down ? [0.4, 0.33, 0.25] : [0.58, 0.45, 0.28];
      // legs: tripod gait from the distance walked; tucked in flight; twitching when down
      const flying = s.z > 0.05;
      for (let k = 0; k < 3; k++) {
        for (const side of [-1, 1]) {
          const a = [4.2 - k * 2.6, 3.4, side * 1.7];
          const tri = (k % 2 === 0) === (side > 0) ? 0 : Math.PI;
          let foot;
          if (flying) foot = [a[0] - 2 - k, 0.8, side * 4];
          else if (down) {
            const tw = Math.sin(now / 110 + k * 1.7 + side) * (asleep ? 0.3 : 1.2);
            foot = [a[0] + (1 - k) * 4, -1 + tw, side * (7 + tw)];
          } else {
            const ph = legPhase + tri;
            const sw = Math.sin(ph) * 2.6, up = Math.max(0, Math.cos(ph)) * 1.6;
            foot = [[a[0] + 6.5, 0, side * 6.5], [a[0] + 0.5, 0, side * 8.5], [a[0] - 5.5, 0, side * 7.5]][k];
            foot[0] += sw; foot[1] += up;
            if (s.act === 'groom' && k === 0) foot = [10.5 + Math.sin(now / 80) * 1.2, 5.5, side * 1.4];
          }
          const knee = [(a[0] + foot[0]) / 2, Math.max(a[1], foot[1]) + 3.2, (a[2] + foot[2]) / 2 + side * 1.6];
          seg(base, a, knee, 0.42, legC);
          seg(base, knee, foot, 0.34, legC);
        }
      }
      // abdomen (banded), thorax, head, eyes
      draw(M.sphere, chain(base, T(-5.8, 4.7, 0), S(7, 3.4, 3.7)), tan, { mat: 2, spec: 0.35 });
      draw(M.sphere, chain(base, T(1.8, 5.2, 0), S(4.3, 3.6, 3.4)), tan, { spec: 0.35 });
      draw(M.sphere, chain(base, T(7.6, 5.4, 0), S(2.2, 2.7, 3.0)), tan, { spec: 0.3 });
      for (const side of [-1, 1]) draw(M.sphere, chain(base, T(7.9, 5.6, side * 2.2), S(1.9, 2.4, 1.3)), down ? [0.45, 0.14, 0.12] : [0.72, 0.16, 0.12], { spec: 0.9 });
      for (const side of [-1, 1]) seg(base, [9.3, 6.4, side * 0.8], [11.2, 7.4, side * 1.4], 0.25, legC);
      // proboscis (MN9), graded
      if (s.prob > 0.05) seg(base, [9.2, 3.4, 0], [10.2 + 1.2 * s.prob, 3.4 - 3.6 * s.prob, 0], 0.5, s.act === 'sip' ? [0.35, 0.7, 0.85] : [0.6, 0.5, 0.36]);
      // wings: folded over the abdomen; open and beating in flight; one extended for song
      for (const side of [-1, 1]) {
        let yaw = side * 0.16, flap = 0.05 * side;
        if (flying) { yaw = side * 1.25; flap = Math.sin(now * 0.09) * 0.9; }
        else if (s.wing > 0.1 && side > 0) yaw = side * (0.16 + 1.3 * s.wing);
        const w = chain(base, T(2.5, 7.8, side * 1.3), RY(-yaw), RX(flap), T(-6.4, 0, 0), S(6.6, 0.12, 2.3));
        draw(M.sphere, w, [0.9, 0.94, 1.0], { alpha: 0.2, spec: 1.4 });
      }
    }

    // ---------------------------------------------------------------- frame
    function render(st) {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = canvas.clientWidth || 720, h = canvas.clientHeight || 540;
      for (const c of [canvas, overlay]) {
        if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); }
      }
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.clearColor(0.07, 0.045, 0.03, 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      const s = st.s;
      if (s && cam.follow) {                         // the camera follows the fly, smoothly
        const k = cam.snap ? 1 : 0.08;
        cam.snap = false;
        cam.tx += (s.x - cam.tx) * k; cam.tz += (s.y - cam.tz) * k;
        cam.ty += (MAT_H + 6 + s.z * 150 - cam.ty) * k;
      }
      eye = [cam.tx + cam.dist * Math.cos(cam.pitch) * Math.sin(cam.yaw), cam.ty + cam.dist * Math.sin(cam.pitch),
        cam.tz + cam.dist * Math.cos(cam.pitch) * Math.cos(cam.yaw)];
      VP = mul(perspective(0.72, w / h, Math.max(0.5, cam.dist * 0.02), 30000), lookAt(eye, [cam.tx, cam.ty, cam.tz], [0, 1, 0]));
      opaque = []; transp = [];
      bar();
      const drops = [];
      for (const p of (st.puddles || [])) {
        const sub = st.subs[p.kind] || { color: '#999999' };
        const r = 5 + 11 * Math.sqrt(clamp(p.amt, 0, 1));
        draw(M.drop, chain(T(p.x, MAT_H + 0.2, p.y), S(r, r * 0.42, r)), hex(sub.color), { alpha: 0.62, spec: 1.6 });
        drops.push([p, sub, r]);
      }
      if (s) fly(s, st.now, st.legPhase);
      gl.useProgram(pr);
      gl.enableVertexAttribArray(loc.aP); gl.enableVertexAttribArray(loc.aN);
      gl.uniformMatrix4fv(loc.uVP, false, VP); gl.uniform3fv(loc.uEye, eye);
      gl.enable(gl.DEPTH_TEST); gl.disable(gl.BLEND); gl.depthMask(true); gl.disable(gl.CULL_FACE);
      flush(opaque);
      // trajectory on the mat, coloured by ethanol level
      if (st.trail && st.trail.length > 1) {
        const v = [];
        const c0 = [0.31, 0.7, 0.85], c1 = [0.88, 0.64, 0.25];
        for (let i = 1; i < st.trail.length; i++) {
          const a = st.trail[i - 1], b = st.trail[i];
          if (Math.hypot(b.x - a.x, b.y - a.y) > 40) continue;
          const t = clamp(b.a / 0.8, 0, 1), al = 0.8 * (1 - (st.now - b.t) / 20000);
          const c = [c0[0] + (c1[0] - c0[0]) * t, c0[1] + (c1[1] - c0[1]) * t, c0[2] + (c1[2] - c0[2]) * t, al];
          v.push(a.x, MAT_H + 0.25, a.y, ...c, b.x, MAT_H + 0.25, b.y, ...c);
        }
        gl.disableVertexAttribArray(loc.aN);
        gl.useProgram(lp);
        gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
        gl.uniformMatrix4fv(lloc.uVP, false, VP);
        gl.bindBuffer(gl.ARRAY_BUFFER, lineBuf); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(v), gl.DYNAMIC_DRAW);
        gl.enableVertexAttribArray(lloc.aP); gl.enableVertexAttribArray(lloc.aC);
        gl.vertexAttribPointer(lloc.aP, 3, gl.FLOAT, false, 28, 0); gl.vertexAttribPointer(lloc.aC, 4, gl.FLOAT, false, 28, 12);
        gl.drawArrays(gl.LINES, 0, v.length / 7);
        gl.disableVertexAttribArray(lloc.aC);
        gl.useProgram(pr);
        gl.enableVertexAttribArray(loc.aP); gl.enableVertexAttribArray(loc.aN);
      }
      // transparent last, far to near
      gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA); gl.depthMask(false);
      const dz = (o) => { const x = o.model[12] - eye[0], y = o.model[13] - eye[1], z = o.model[14] - eye[2]; return x * x + y * y + z * z; };
      transp.sort((a, b) => dz(b) - dz(a));
      flush(transp);
      gl.depthMask(true);
      overlayText(st, drops, w, h, dpr);
    }

    function project(x, y, z, w, h) {
      const m = VP, cx = m[0] * x + m[4] * y + m[8] * z + m[12], cy = m[1] * x + m[5] * y + m[9] * z + m[13];
      const cw = m[3] * x + m[7] * y + m[11] * z + m[15];
      if (cw <= 0) return null;
      return [(cx / cw * 0.5 + 0.5) * w, (1 - (cy / cw * 0.5 + 0.5)) * h];
    }
    function overlayText(st, drops, w, h, dpr) {
      const g = overlay.getContext('2d');
      g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
      const MONO = 'ui-monospace, "SF Mono", Menlo, Consolas, monospace';
      g.font = `11px ${MONO}`; g.textBaseline = 'middle';
      for (const [p, sub, r] of drops) {
        const q = project(p.x, MAT_H + r * 0.5, p.y, w, h);
        if (!q) continue;
        g.fillStyle = 'rgba(7,9,12,0.55)';
        const label = `${sub.name || p.kind} ${Math.round((sub.abv || 0) * 100)}%`;
        const tw = g.measureText(label).width;
        g.fillRect(q[0] + 8, q[1] - 16, tw + 8, 14);
        g.fillStyle = '#e6ddd0'; g.textAlign = 'left'; g.fillText(label, q[0] + 12, q[1] - 9);
      }
      const s = st.s;
      if (s) {
        const q = project(s.x, MAT_H + 14 + s.z * 150, s.y, w, h);
        if (q) st.tags.forEach(([txt, col], i) => {
          const tw = g.measureText(txt).width + 8, x = q[0] + 14, y = q[1] - 12 - i * 15;
          g.fillStyle = 'rgba(7,9,12,0.8)'; g.fillRect(x, y - 6, tw, 12);
          g.strokeStyle = col; g.lineWidth = 1; g.strokeRect(x + .5, y - 5.5, tw - 1, 11);
          g.fillStyle = col; g.textAlign = 'left'; g.fillText(txt, x + 4, y + 0.5);
        });
      }
      g.font = `12px ${MONO}`; g.textBaseline = 'top'; g.textAlign = 'left';
      g.fillStyle = 'rgba(15,11,8,0.62)'; g.fillRect(6, 6, 150, 38);
      g.fillStyle = '#efe6da'; g.fillText(`t = ${st.hud.t} s`, 12, 10);
      g.fillStyle = '#f0a53a'; g.fillText(`alcohol = ${st.hud.a}`, 12, 27);
      const hint = w < 520 ? 'arrastra · pellizca · doble toque' : 'arrastra: girar · rueda: zoom · doble clic: reiniciar';
      g.font = `10px ${MONO}`;
      g.fillStyle = 'rgba(15,11,8,0.55)'; g.fillRect(6, h - 22, g.measureText(hint).width + 12, 16);
      g.fillStyle = 'rgba(239,230,218,0.8)'; g.fillText(hint, 12, h - 19);
      if (st.hud.rec) { g.fillStyle = '#e25c5c'; g.textAlign = 'right'; g.font = `12px ${MONO}`; g.fillText('● REC', w - 12, 10); }
    }

    return { render, zoom, cam, setArena, reset: () => Object.assign(cam, home) };
  }

  window.Scene3D = { create };
})();
