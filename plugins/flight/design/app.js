/* Flight tracker LED layouts — sample data, semantic layouts, animation loop. */
(function () {
  "use strict";

  // ---- semantic palette (consistent across every sign) ----------------------
  var C = {
    ident:   [255, 255, 255],
    type:    [170, 90, 255],
    alt:     [255, 180, 0],
    speed:   [60, 220, 60],
    track:   [0, 220, 255],
    dist:    [255, 80, 255],
    climb:   [0, 255, 0],
    descend: [255, 60, 60],
    level:   [255, 180, 0],
    label:   [70, 90, 130],
    idle:    [0, 150, 200],
    live:    [0, 255, 0],
  };

  // ---- sample flights overhead ---------------------------------------------
  var FLIGHTS = [
    { flt: "UA2341", type: "B738", alt: 34000, vr: 1200,  gs: 460, trk: 247, dist: "12KM NE", reg: "N12345" },
    { flt: "DL815",  type: "A21N", alt: 28000, vr: -900,  gs: 420, trk: 198, dist: "6KM S",   reg: "N815DN" },
    { flt: "WN88",   type: "B737", alt: 39000, vr: 0,     gs: 480, trk: 90,  dist: "22KM E",  reg: "N7088A" },
    { flt: "BA49H",  type: "B77W", alt: 41000, vr: 0,     gs: 510, trk: 305, dist: "31KM NW", reg: "G-STBA" },
  ];

  // ---- formatting -----------------------------------------------------------
  function altStr(a) { return a.toLocaleString("en-US") + "FT"; }
  function vColor(vr) { return vr > 50 ? C.climb : vr < -50 ? C.descend : C.level; }
  function vGlyph(vr) { return vr > 50 ? "up" : vr < -50 ? "down" : "level"; }

  // ---- airlines: brand-color tail-fin marks (NOT logos — trademark-safe) ----
  // Derived from the callsign alpha prefix. Colors are brand palettes, drawn as
  // a swept vertical-stabiliser silhouette with an accent stripe.
  var AIRLINES = {
    UA: { name: "UNITED",    c1: [40, 95, 210],  c2: [235, 240, 255] },
    DL: { name: "DELTA",     c1: [220, 40, 60],  c2: [30, 80, 150]  },
    WN: { name: "SOUTHWEST", c1: [255, 190, 0],  c2: [220, 45, 55]  },
    BA: { name: "BRITISH",   c1: [40, 95, 175],  c2: [220, 45, 55]  },
  };
  var DEFAULT_AL = { name: "", c1: [150, 160, 175], c2: [90, 100, 115] };
  function airlineOf(flt) {
    var m = flt.match(/^[A-Z]+/);
    var code = m ? m[0].slice(0, 2) : "";
    return AIRLINES[code] || DEFAULT_AL;
  }
  // swept tail fin drawn straight to the framebuffer. x,y,H physical. returns W.
  function drawTail(sign, x, y, H, al, bright) {
    bright = bright == null ? 1 : bright;
    var W = Math.max(4, Math.round(H * 0.82));
    var lean = Math.round(W * 0.52);
    var bandTop = Math.round(H * 0.5), bandH = Math.max(1, Math.round(H * 0.16));
    for (var r = 0; r < H; r++) {
      var frac = r / (H - 1);
      var lx = Math.round(lean * (1 - frac));
      var inBand = r >= bandTop && r < bandTop + bandH;
      var col = inBand ? al.c2 : al.c1;
      for (var xx = lx; xx < W; xx++) sign.px(x + xx, y + r, col, bright);
    }
    return W;
  }
  // custom-draw token: runs fn(sign, x, yTop, opts) inside a row/ticker.
  function tkCustom(w, h, fn) { return { custom: fn, w: w, h: h }; }
  function tkTail(sign, al, H) {
    var W = Math.max(4, Math.round(H * 0.82));
    return tkCustom(W, H, function (s, x, yTop, opts) {
      var b = opts && opts.bright != null ? opts.bright : 1;
      var y = yTop + Math.max(0, ((opts && opts.rowH) || H) - H);
      if (opts && opts.vAlign === "top") y = yTop;
      drawTail(s, x, y, H, al, b);
    });
  }
  // small centred separator dot for use between fields
  function tkSep(sign, H, color) {
    var s = sign.scale, d = s;
    return tkCustom(d, H, function (sg, x, yTop, opts) {
      var b = opts && opts.bright != null ? opts.bright : 1;
      var cy = yTop + Math.round(H / 2) - Math.round(d / 2);
      for (var yy = 0; yy < d; yy++) for (var xx = 0; xx < d; xx++)
        sg.px(x + xx, cy + yy, color || C.label, 0.7 * b);
    });
  }

  // ---- token helpers (all coordinates physical) -----------------------------
  function tkText(sign, val, color, px) {
    var m = LED.rasterize(val, px, "Silkscreen", null, true);
    return { mask: m, expand: sign.scale, color: color, w: m.w * sign.scale, h: m.h * sign.scale };
  }
  function tkHi(sign, val, color, px, wt) {
    var m = sign.hiresMask(val, px, wt || "700");
    return { mask: m, expand: 1, color: color, w: m.w, h: m.h };
  }
  function tkGlyph(sign, name, color) {
    var m = LED.GLYPH[name];
    return { mask: m, expand: sign.scale, color: color, w: m.w * sign.scale, h: m.h * sign.scale };
  }
  function sp(w) { return { spacer: true, w: w }; }

  function rowWidth(tokens) {
    var w = 0; for (var i = 0; i < tokens.length; i++) w += tokens[i].w; return w;
  }
  function drawRow(sign, tokens, x, yTop, opts) {
    opts = opts || {};
    for (var i = 0; i < tokens.length; i++) {
      var t = tokens[i];
      if (t.custom) {
        t.custom(sign, x, yTop, opts);
      } else if (!t.spacer) {
        var yy = yTop + (opts.baseTop ? Math.max(0, (opts.rowH || t.h) - t.h) : 0);
        if (opts.vAlign === "top") yy = yTop;
        sign.blit(t.mask, x, yy, t.color, t.expand, {
          bright: opts.bright == null ? 1 : opts.bright,
          x0: opts.x0, x1: opts.x1, y0: opts.y0, y1: opts.y1,
        });
      }
      x += t.w;
    }
    return x;
  }

  // build a metrics token stream for one flight (BDF, physical space)
  function metricsBDF(sign, f, px, kern) {
    var s = sign.scale;
    var t = [];
    t.push(tkGlyph(sign, vGlyph(f.vr), vColor(f.vr)));
    t.push(sp(1 * s));
    t.push(tkText(sign, altStr(f.alt), C.alt, px)); t.push(sp(kern));
    t.push(tkText(sign, f.gs + "KT", C.speed, px)); t.push(sp(kern));
    t.push(tkText(sign, "" + f.trk, C.track, px)); t.push(tkGlyph(sign, "deg", C.track)); t.push(sp(kern));
    t.push(tkText(sign, f.dist, C.dist, px));
    return t;
  }
  // compact metrics (short) for tight rows
  function metricsCompact(sign, f, px, kern) {
    var s = sign.scale, t = [];
    t.push(tkText(sign, Math.round(f.alt / 1000) + "K", C.alt, px));
    t.push(tkGlyph(sign, vGlyph(f.vr), vColor(f.vr))); t.push(sp(kern));
    t.push(tkText(sign, f.gs + "", C.speed, px)); t.push(sp(kern));
    t.push(tkText(sign, "" + f.trk, C.track, px)); t.push(tkGlyph(sign, "deg", C.track)); t.push(sp(kern));
    t.push(tkText(sign, f.dist.replace(" ", ""), C.dist, px));
    return t;
  }

  function pagingDots(sign, n, cur, physX, physY) {
    var s = sign.scale, step = 2 * s;
    for (var i = 0; i < n; i++) {
      sign.blit(LED.GLYPH.dot, physX + i * step, physY, i === cur ? C.ident : C.label, s, {});
    }
  }

  function scrollOffset(t, speed, pxPerSec, period) {
    if (period <= 0) return 0;
    return ((t / 1000) * pxPerSec * speed) % period;
  }

  // draws a token row scrolling right->left, looped seamlessly, within [0,physW)
  function ticker(sign, tokens, yTop, t, speed, pxPerSec, gapBetween, rowOpts) {
    var content = rowWidth(tokens);
    var period = content + gapBetween;
    var off = scrollOffset(t, speed, pxPerSec, period);
    var x = sign.physW - off;
    // draw enough copies to fill
    var guard = 0;
    while (x < sign.physW && guard < 8) {
      if (x + content > 0) drawRow(sign, tokens, x, yTop, rowOpts);
      x += period; guard++;
    }
  }

  // ---- empty state ----------------------------------------------------------
  function drawEmpty(sign, t, wide) {
    // slow radar scan column
    var period = 3200;
    var sx = Math.floor(((t % period) / period) * sign.physW);
    for (var y = 0; y < sign.physH; y++) {
      var d = Math.abs(y - sign.physH / 2) / (sign.physH / 2);
      sign.px(sx, y, C.idle, 0.10 * (1 - d));
    }
    var pulse = 0.55 + 0.45 * Math.sin(t / 600);
    var label = wide ? "NO TRAFFIC OVERHEAD" : "NO TRAFFIC";
    var px = sign.logH >= 16 ? (sign.scale > 1 ? 8 : (wide ? 12 : 8)) : 8;
    var m = LED.rasterize(label, px, "Silkscreen", null, true);
    var wLog = m.w, hLog = m.h;
    var bx = Math.round((sign.logW - wLog) / 2) * sign.scale;
    var by = Math.round((sign.logH - hLog) / 2) * sign.scale;
    sign.blit(m, bx, by, C.idle, sign.scale, { bright: pulse });
  }

  // ---- refresh pulse (top-right live dot, blinks each ~10s) ------------------
  function livePulse(sign, t) {
    var phase = (t % 10000) / 10000;
    var on = phase < 0.12 ? 1 : 0.18;
    sign.blit(LED.GLYPH.dot, sign.physW - sign.scale * 2, sign.scale, C.live, sign.scale, { bright: on });
  }

  // ======================================================================
  //  LAYOUT VARIANTS
  // ======================================================================
  var LAYOUTS = {

    // ---- SMALLSIGN A: two-row rotator ---------------------------------
    smallA: function (sign, ctx) {
      var fl = ctx.flights, t = ctx.t, sp8 = 8;
      var idx = Math.floor(t / (4500 / ctx.speed)) % fl.length;
      var f = fl[idx];
      // top: ident + type, held
      var top = [tkText(sign, f.flt, C.ident, sp8), sp(6), tkText(sign, f.type, C.type, sp8)];
      drawRow(sign, top, 1, 0, { vAlign: "top" });
      pagingDots(sign, fl.length, idx, sign.physW - fl.length * 2 - 3, 1);
      // bottom: metrics, scroll if overflow
      var met = metricsBDF(sign, f, sp8, 3);
      var w = rowWidth(met);
      if (w <= sign.physW) drawRow(sign, met, 1, 8, { vAlign: "top" });
      else ticker(sign, met, 8, t, ctx.speed, 18, 14, { vAlign: "top" });
      livePulse(sign, t);
    },

    // ---- SMALLSIGN B: single-line 6x12 ticker -------------------------
    smallB: function (sign, ctx) {
      var fl = ctx.flights, t = ctx.t, px = 12;
      var stream = [];
      for (var i = 0; i < fl.length; i++) {
        var f = fl[i];
        var al = airlineOf(f.flt);
        stream.push(tkTail(sign, al, 12)); stream.push(sp(4));
        stream.push(tkText(sign, f.flt, C.ident, px)); stream.push(sp(5));
        stream.push(tkSep(sign, 12)); stream.push(sp(5));
        stream.push(tkText(sign, f.type, C.type, px)); stream.push(sp(5));
        stream.push(tkSep(sign, 12)); stream.push(sp(5));
        stream.push(tkGlyph(sign, vGlyph(f.vr), vColor(f.vr))); stream.push(sp(2));
        stream.push(tkText(sign, altStr(f.alt), C.alt, px)); stream.push(sp(5));
        stream.push(tkSep(sign, 12)); stream.push(sp(5));
        stream.push(tkText(sign, f.gs + "KT", C.speed, px)); stream.push(sp(5));
        stream.push(tkSep(sign, 12)); stream.push(sp(5));
        stream.push(tkText(sign, "" + f.trk, C.track, px)); stream.push(tkGlyph(sign, "deg", C.track)); stream.push(sp(5));
        stream.push(tkSep(sign, 12)); stream.push(sp(5));
        stream.push(tkText(sign, f.dist, C.dist, px)); stream.push(sp(8));
        stream.push(tkSep(sign, 12, C.ident)); stream.push(sp(8));
      }
      var rowH = 0;
      for (var k = 0; k < stream.length; k++) if (stream[k].h > rowH) rowH = stream[k].h;
      var yTop = Math.round((sign.physH - rowH) / 2);
      ticker(sign, stream, yTop, t, ctx.speed, 26, 0, { vAlign: "top" });
      livePulse(sign, t);
    },

    // ---- BIGSIGN A: hi-res hero ident + hi-res metrics ----------------
    bigA: function (sign, ctx) {
      var fl = ctx.flights, t = ctx.t;
      var idx = Math.floor(t / (4200 / ctx.speed)) % fl.length;
      var f = fl[idx];
      var al = airlineOf(f.flt);
      // airline tail fin, left
      var finW = drawTail(sign, 4, 3, 28, al, 1);
      var lx = 4 + finW + 8;
      // ident hero
      sign.hires(f.flt, lx, 1, C.ident, 26, "700");
      // airline name + type, second line under ident
      var ny = 30, nx = lx;
      if (al.name) nx += sign.hires(al.name, lx, ny, al.c1, 10, "700") + 6;
      sign.hires(f.type, nx, ny, C.type, 10, "600");
      // metrics line (hi-res small, colored)
      var arrow = f.vr > 50 ? "\u25B2" : f.vr < -50 ? "\u25BC" : "\u25AC";
      var y = 45, x = 4, px = 12;
      x += sign.hires(arrow, x, y + 1, vColor(f.vr), 10, "700") + 3;
      x += sign.hires(altStr(f.alt), x, y, C.alt, px, "600") + 7;
      x += sign.hires(f.gs + "KT", x, y, C.speed, px, "600") + 7;
      x += sign.hires(f.trk + "\u00B0", x, y, C.track, px, "600") + 7;
      x += sign.hires(f.dist, x, y, C.dist, px, "600");
      pagingDots(sign, fl.length, idx, sign.physW - fl.length * (2 * sign.scale) - 4, sign.physH - sign.scale * 2 - 2);
      livePulse(sign, t);
    },

    // ---- BIGSIGN B: two-row chunky BDF --------------------------------
    bigB: function (sign, ctx) {
      var fl = ctx.flights, t = ctx.t, px = 8;
      var idx = Math.floor(t / (4200 / ctx.speed)) % fl.length;
      var f = fl[idx];
      // top: ident held (type moves to the scrolling row to respect the ~10-char budget)
      var top = [tkText(sign, f.flt, C.ident, px)];
      drawRow(sign, top, 1 * sign.scale, 0, { vAlign: "top" });
      // bottom: type + metrics scroll
      var met = [tkText(sign, f.type, C.type, px), sp(4 * sign.scale)].concat(metricsBDF(sign, f, px, 3));
      var w = rowWidth(met);
      if (w <= sign.physW) drawRow(sign, met, 1 * sign.scale, 8 * sign.scale, { vAlign: "top" });
      else ticker(sign, met, 8 * sign.scale, t, ctx.speed, 46, 20 * sign.scale, { vAlign: "top" });
      livePulse(sign, t);
    },

    // ---- LONGBOI A: dashboard row (Flight Wall analog) ----------------
    longA: function (sign, ctx) {
      var fl = ctx.flights, t = ctx.t;
      var idx = Math.floor(t / (4800 / ctx.speed)) % fl.length;
      var f = fl[idx];
      var al = airlineOf(f.flt);
      // airline tail fin, left
      var finW = drawTail(sign, 6, 6, 32, al, 1);
      var hx = 6 + finW + 10;
      // hero ident
      sign.hires(f.flt, hx, 5, C.ident, 26, "700");
      var iw = sign.hiresMask(f.flt, 26, "700").w;
      // airline name + type under ident
      var uy = 40, ux = hx;
      if (al.name) ux += sign.hires(al.name, hx, uy, al.c1, 12, "700") + 7;
      sign.hires(f.type, ux, uy, C.type, 12, "600");
      // metric columns
      var arrow = f.vr > 50 ? "\u25B2" : f.vr < -50 ? "\u25BC" : "\u25AC";
      var cols = [
        { lab: "ALT FT", val: f.alt.toLocaleString("en-US"), c: C.alt, arr: arrow, ac: vColor(f.vr) },
        { lab: "SPD KT", val: f.gs + "", c: C.speed },
        { lab: "TRK", val: f.trk + "\u00B0", c: C.track },
        { lab: "DIST", val: f.dist, c: C.dist },
      ];
      var x = Math.max(hx + iw + 30, 190);
      var colW = Math.floor((sign.physW - x - 16) / cols.length);
      for (var i = 0; i < cols.length; i++) {
        var cx = x + i * colW;
        sign.hires(cols[i].lab, cx, 8, C.label, 10, "700");
        var vx = cx;
        if (cols[i].arr) { vx += sign.hires(cols[i].arr, cx, 26, cols[i].ac, 11, "700") + 3; }
        sign.hires(cols[i].val, vx, 24, cols[i].c, 16, "700");
      }
      pagingDots(sign, fl.length, idx, sign.physW - fl.length * (2 * sign.scale) - 6, sign.physH - sign.scale * 2 - 3);
      livePulse(sign, t);
    },

    // ---- LONGBOI B: hi-res ticker stream ------------------------------
    longB: function (sign, ctx) {
      var fl = ctx.flights, t = ctx.t, px = 20;
      var stream = [];
      for (var i = 0; i < fl.length; i++) {
        var f = fl[i];
        var arrow = f.vr > 50 ? "\u25B2" : f.vr < -50 ? "\u25BC" : "\u25AC";
        stream.push(tkHi(sign, f.flt, C.ident, px, "700")); stream.push(sp(6));
        stream.push(tkHi(sign, f.type, C.type, px - 4, "600")); stream.push(sp(8));
        stream.push(tkHi(sign, arrow, vColor(f.vr), px - 6, "700")); stream.push(sp(3));
        stream.push(tkHi(sign, altStr(f.alt), C.alt, px - 2, "600")); stream.push(sp(8));
        stream.push(tkHi(sign, f.gs + "KT", C.speed, px - 2, "600")); stream.push(sp(8));
        stream.push(tkHi(sign, f.trk + "\u00B0", C.track, px - 2, "600")); stream.push(sp(8));
        stream.push(tkHi(sign, f.dist, C.dist, px - 2, "600")); stream.push(sp(14));
        stream.push(tkHi(sign, "\u2022", C.label, px, "700")); stream.push(sp(14));
      }
      var yTop = Math.round((sign.physH - stream[0].h) / 2);
      ticker(sign, stream, yTop, t, ctx.speed, 60, 0, { vAlign: "top" });
      livePulse(sign, t);
    },

    // ---- LONGBOI C: two-up stacked rows -------------------------------
    longC: function (sign, ctx) {
      var fl = ctx.flights, t = ctx.t, px = 8;
      // rotate the *pair* shown
      var pairStart = Math.floor(t / (5000 / ctx.speed)) % fl.length;
      for (var r = 0; r < 2; r++) {
        var f = fl[(pairStart + r) % fl.length];
        var y = r * 8;
        var row = [
          tkText(sign, f.flt, C.ident, px), sp(3 * sign.scale),
          tkText(sign, f.type, C.type, px), sp(4 * sign.scale),
          tkGlyph(sign, vGlyph(f.vr), vColor(f.vr)), sp(1 * sign.scale),
          tkText(sign, altStr(f.alt), C.alt, px), sp(3 * sign.scale),
          tkText(sign, f.gs + "KT", C.speed, px), sp(3 * sign.scale),
          tkText(sign, "" + f.trk, C.track, px), tkGlyph(sign, "deg", C.track), sp(3 * sign.scale),
          tkText(sign, f.dist, C.dist, px),
        ];
        var w = rowWidth(row);
        if (w <= sign.physW) drawRow(sign, row, 1 * sign.scale, y * sign.scale, { vAlign: "top" });
        else ticker(sign, row, y * sign.scale, t, ctx.speed, 40, 24 * sign.scale, { vAlign: "top" });
      }
      livePulse(sign, t);
    },
  };

  // ======================================================================
  //  BOOT
  // ======================================================================
  var SIGN_DEFS = {
    smallA: { logW: 160, logH: 16, scale: 1 },
    smallB: { logW: 160, logH: 16, scale: 1 },
    bigA:   { logW: 64,  logH: 16, scale: 4 },
    bigB:   { logW: 64,  logH: 16, scale: 4 },
    longA:  { logW: 128, logH: 16, scale: 4 },
    longB:  { logW: 128, logH: 16, scale: 4 },
    longC:  { logW: 128, logH: 16, scale: 4 },
  };

  var state = { speed: 1, traffic: 4, glow: true, playing: true, clock: 0, last: 0 };
  var signs = [];

  function cellFor(physW) { return Math.max(2, Math.round(920 / physW)); }

  function boot() {
    Object.keys(SIGN_DEFS).forEach(function (id) {
      var cv = document.getElementById("cv-" + id);
      if (!cv) return;
      var def = SIGN_DEFS[id];
      var s = new LED.Sign(cv, {
        logW: def.logW, logH: def.logH, scale: def.scale,
        cell: cellFor(def.logW * def.scale), glow: state.glow,
      });
      signs.push({ id: id, sign: s, draw: LAYOUTS[id] });
    });
    bindControls();
    state.last = performance.now();
    frame();                 // paint immediately
    setInterval(frame, 1000 / 40);
  }

  function frame() {
    var now = performance.now();
    var dt = now - state.last; state.last = now;
    if (dt > 250) dt = 250;  // clamp after tab throttling
    if (state.playing) state.clock += dt;
    var flights = FLIGHTS.slice(0, state.traffic);
    var empty = flights.length === 0;
    var wideMap = { longA: 1, longB: 1, longC: 1, bigA: 0, bigB: 0 };
    for (var i = 0; i < signs.length; i++) {
      var S = signs[i];
      S.sign.glow = state.glow;
      S.sign.clear();
      if (empty) drawEmpty(S.sign, state.clock, S.sign.logW * S.sign.scale >= 200);
      else S.draw(S.sign, { t: state.clock, speed: state.speed, flights: flights });
      S.sign.render();
    }
  }

  function bindControls() {
    var traffic = document.getElementById("ctl-traffic");
    var speed = document.getElementById("ctl-speed");
    var glow = document.getElementById("ctl-glow");
    var play = document.getElementById("ctl-play");
    if (traffic) traffic.addEventListener("change", function () { state.traffic = +traffic.value; });
    if (speed) speed.addEventListener("input", function () {
      state.speed = +speed.value;
      var lbl = document.getElementById("ctl-speed-val");
      if (lbl) lbl.textContent = state.speed.toFixed(1) + "\u00D7";
    });
    if (glow) glow.addEventListener("change", function () { state.glow = glow.checked; });
    if (play) play.addEventListener("click", function () {
      state.playing = !state.playing;
      play.textContent = state.playing ? "\u2759\u2759 Pause" : "\u25B6 Play";
      play.setAttribute("aria-pressed", String(!state.playing));
    });
  }

  // wait for fonts, then boot
  function start() {
    var fonts = [
      document.fonts.load("8px Silkscreen"),
      document.fonts.load("16px Silkscreen"),
      document.fonts.load("700 28px Inter"),
      document.fonts.load("600 14px Inter"),
    ];
    Promise.all(fonts).catch(function () {}).then(function () {
      return document.fonts.ready;
    }).then(boot);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();

  window.FT = { state: state };
})();
