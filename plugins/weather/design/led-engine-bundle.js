/* @ds-bundle: {"format":4,"namespace":"LedTickerFlightTracker_b04365","components":[],"sourceHashes":{"app.js":"410527722342","design_handoff_led_flight_tracker/app.js":"410527722342","design_handoff_led_flight_tracker/led-engine.js":"286c61141731","design_handoff_stock_ticker/led-engine.js":"286c61141731","design_handoff_stock_ticker/stocks.js":"995b4992c7f7","led-engine.js":"286c61141731","stocks.js":"995b4992c7f7"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.LedTickerFlightTracker_b04365 = window.LedTickerFlightTracker_b04365 || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// app.js
try { (() => {
/* Flight tracker LED layouts — sample data, semantic layouts, animation loop. */
(function () {
  "use strict";

  // ---- semantic palette (consistent across every sign) ----------------------
  var C = {
    ident: [255, 255, 255],
    type: [170, 90, 255],
    alt: [255, 180, 0],
    speed: [60, 220, 60],
    track: [0, 220, 255],
    dist: [255, 80, 255],
    climb: [0, 255, 0],
    descend: [255, 60, 60],
    level: [255, 180, 0],
    label: [70, 90, 130],
    idle: [0, 150, 200],
    live: [0, 255, 0]
  };

  // ---- sample flights overhead ---------------------------------------------
  var FLIGHTS = [{
    flt: "UA2341",
    type: "B738",
    alt: 34000,
    vr: 1200,
    gs: 460,
    trk: 247,
    dist: "12KM NE",
    reg: "N12345"
  }, {
    flt: "DL815",
    type: "A21N",
    alt: 28000,
    vr: -900,
    gs: 420,
    trk: 198,
    dist: "6KM S",
    reg: "N815DN"
  }, {
    flt: "WN88",
    type: "B737",
    alt: 39000,
    vr: 0,
    gs: 480,
    trk: 90,
    dist: "22KM E",
    reg: "N7088A"
  }, {
    flt: "BA49H",
    type: "B77W",
    alt: 41000,
    vr: 0,
    gs: 510,
    trk: 305,
    dist: "31KM NW",
    reg: "G-STBA"
  }];

  // ---- formatting -----------------------------------------------------------
  function altStr(a) {
    return a.toLocaleString("en-US") + "FT";
  }
  function vColor(vr) {
    return vr > 50 ? C.climb : vr < -50 ? C.descend : C.level;
  }
  function vGlyph(vr) {
    return vr > 50 ? "up" : vr < -50 ? "down" : "level";
  }

  // ---- airlines: brand-color tail-fin marks (NOT logos — trademark-safe) ----
  // Derived from the callsign alpha prefix. Colors are brand palettes, drawn as
  // a swept vertical-stabiliser silhouette with an accent stripe.
  var AIRLINES = {
    UA: {
      name: "UNITED",
      c1: [40, 95, 210],
      c2: [235, 240, 255]
    },
    DL: {
      name: "DELTA",
      c1: [220, 40, 60],
      c2: [30, 80, 150]
    },
    WN: {
      name: "SOUTHWEST",
      c1: [255, 190, 0],
      c2: [220, 45, 55]
    },
    BA: {
      name: "BRITISH",
      c1: [40, 95, 175],
      c2: [220, 45, 55]
    }
  };
  var DEFAULT_AL = {
    name: "",
    c1: [150, 160, 175],
    c2: [90, 100, 115]
  };
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
    var bandTop = Math.round(H * 0.5),
      bandH = Math.max(1, Math.round(H * 0.16));
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
  function tkCustom(w, h, fn) {
    return {
      custom: fn,
      w: w,
      h: h
    };
  }
  function tkTail(sign, al, H) {
    var W = Math.max(4, Math.round(H * 0.82));
    return tkCustom(W, H, function (s, x, yTop, opts) {
      var b = opts && opts.bright != null ? opts.bright : 1;
      var y = yTop + Math.max(0, (opts && opts.rowH || H) - H);
      if (opts && opts.vAlign === "top") y = yTop;
      drawTail(s, x, y, H, al, b);
    });
  }
  // small centred separator dot for use between fields
  function tkSep(sign, H, color) {
    var s = sign.scale,
      d = s;
    return tkCustom(d, H, function (sg, x, yTop, opts) {
      var b = opts && opts.bright != null ? opts.bright : 1;
      var cy = yTop + Math.round(H / 2) - Math.round(d / 2);
      for (var yy = 0; yy < d; yy++) for (var xx = 0; xx < d; xx++) sg.px(x + xx, cy + yy, color || C.label, 0.7 * b);
    });
  }

  // ---- token helpers (all coordinates physical) -----------------------------
  function tkText(sign, val, color, px) {
    var m = LED.rasterize(val, px, "Silkscreen", null, true);
    return {
      mask: m,
      expand: sign.scale,
      color: color,
      w: m.w * sign.scale,
      h: m.h * sign.scale
    };
  }
  function tkHi(sign, val, color, px, wt) {
    var m = sign.hiresMask(val, px, wt || "700");
    return {
      mask: m,
      expand: 1,
      color: color,
      w: m.w,
      h: m.h
    };
  }
  function tkGlyph(sign, name, color) {
    var m = LED.GLYPH[name];
    return {
      mask: m,
      expand: sign.scale,
      color: color,
      w: m.w * sign.scale,
      h: m.h * sign.scale
    };
  }
  function sp(w) {
    return {
      spacer: true,
      w: w
    };
  }
  function rowWidth(tokens) {
    var w = 0;
    for (var i = 0; i < tokens.length; i++) w += tokens[i].w;
    return w;
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
          x0: opts.x0,
          x1: opts.x1,
          y0: opts.y0,
          y1: opts.y1
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
    t.push(tkText(sign, altStr(f.alt), C.alt, px));
    t.push(sp(kern));
    t.push(tkText(sign, f.gs + "KT", C.speed, px));
    t.push(sp(kern));
    t.push(tkText(sign, "" + f.trk, C.track, px));
    t.push(tkGlyph(sign, "deg", C.track));
    t.push(sp(kern));
    t.push(tkText(sign, f.dist, C.dist, px));
    return t;
  }
  // compact metrics (short) for tight rows
  function metricsCompact(sign, f, px, kern) {
    var s = sign.scale,
      t = [];
    t.push(tkText(sign, Math.round(f.alt / 1000) + "K", C.alt, px));
    t.push(tkGlyph(sign, vGlyph(f.vr), vColor(f.vr)));
    t.push(sp(kern));
    t.push(tkText(sign, f.gs + "", C.speed, px));
    t.push(sp(kern));
    t.push(tkText(sign, "" + f.trk, C.track, px));
    t.push(tkGlyph(sign, "deg", C.track));
    t.push(sp(kern));
    t.push(tkText(sign, f.dist.replace(" ", ""), C.dist, px));
    return t;
  }
  function pagingDots(sign, n, cur, physX, physY) {
    var s = sign.scale,
      step = 2 * s;
    for (var i = 0; i < n; i++) {
      sign.blit(LED.GLYPH.dot, physX + i * step, physY, i === cur ? C.ident : C.label, s, {});
    }
  }
  function scrollOffset(t, speed, pxPerSec, period) {
    if (period <= 0) return 0;
    return t / 1000 * pxPerSec * speed % period;
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
      x += period;
      guard++;
    }
  }

  // ---- empty state ----------------------------------------------------------
  function drawEmpty(sign, t, wide) {
    // slow radar scan column
    var period = 3200;
    var sx = Math.floor(t % period / period * sign.physW);
    for (var y = 0; y < sign.physH; y++) {
      var d = Math.abs(y - sign.physH / 2) / (sign.physH / 2);
      sign.px(sx, y, C.idle, 0.10 * (1 - d));
    }
    var pulse = 0.55 + 0.45 * Math.sin(t / 600);
    var label = wide ? "NO TRAFFIC OVERHEAD" : "NO TRAFFIC";
    var px = sign.logH >= 16 ? sign.scale > 1 ? 8 : wide ? 12 : 8 : 8;
    var m = LED.rasterize(label, px, "Silkscreen", null, true);
    var wLog = m.w,
      hLog = m.h;
    var bx = Math.round((sign.logW - wLog) / 2) * sign.scale;
    var by = Math.round((sign.logH - hLog) / 2) * sign.scale;
    sign.blit(m, bx, by, C.idle, sign.scale, {
      bright: pulse
    });
  }

  // ---- refresh pulse (top-right live dot, blinks each ~10s) ------------------
  function livePulse(sign, t) {
    var phase = t % 10000 / 10000;
    var on = phase < 0.12 ? 1 : 0.18;
    sign.blit(LED.GLYPH.dot, sign.physW - sign.scale * 2, sign.scale, C.live, sign.scale, {
      bright: on
    });
  }

  // ======================================================================
  //  LAYOUT VARIANTS
  // ======================================================================
  var LAYOUTS = {
    // ---- SMALLSIGN A: two-row rotator ---------------------------------
    smallA: function (sign, ctx) {
      var fl = ctx.flights,
        t = ctx.t,
        sp8 = 8;
      var idx = Math.floor(t / (4500 / ctx.speed)) % fl.length;
      var f = fl[idx];
      // top: ident + type, held
      var top = [tkText(sign, f.flt, C.ident, sp8), sp(6), tkText(sign, f.type, C.type, sp8)];
      drawRow(sign, top, 1, 0, {
        vAlign: "top"
      });
      pagingDots(sign, fl.length, idx, sign.physW - fl.length * 2 - 3, 1);
      // bottom: metrics, scroll if overflow
      var met = metricsBDF(sign, f, sp8, 3);
      var w = rowWidth(met);
      if (w <= sign.physW) drawRow(sign, met, 1, 8, {
        vAlign: "top"
      });else ticker(sign, met, 8, t, ctx.speed, 18, 14, {
        vAlign: "top"
      });
      livePulse(sign, t);
    },
    // ---- SMALLSIGN B: single-line 6x12 ticker -------------------------
    smallB: function (sign, ctx) {
      var fl = ctx.flights,
        t = ctx.t,
        px = 12;
      var stream = [];
      for (var i = 0; i < fl.length; i++) {
        var f = fl[i];
        var al = airlineOf(f.flt);
        stream.push(tkTail(sign, al, 12));
        stream.push(sp(4));
        stream.push(tkText(sign, f.flt, C.ident, px));
        stream.push(sp(5));
        stream.push(tkSep(sign, 12));
        stream.push(sp(5));
        stream.push(tkText(sign, f.type, C.type, px));
        stream.push(sp(5));
        stream.push(tkSep(sign, 12));
        stream.push(sp(5));
        stream.push(tkGlyph(sign, vGlyph(f.vr), vColor(f.vr)));
        stream.push(sp(2));
        stream.push(tkText(sign, altStr(f.alt), C.alt, px));
        stream.push(sp(5));
        stream.push(tkSep(sign, 12));
        stream.push(sp(5));
        stream.push(tkText(sign, f.gs + "KT", C.speed, px));
        stream.push(sp(5));
        stream.push(tkSep(sign, 12));
        stream.push(sp(5));
        stream.push(tkText(sign, "" + f.trk, C.track, px));
        stream.push(tkGlyph(sign, "deg", C.track));
        stream.push(sp(5));
        stream.push(tkSep(sign, 12));
        stream.push(sp(5));
        stream.push(tkText(sign, f.dist, C.dist, px));
        stream.push(sp(8));
        stream.push(tkSep(sign, 12, C.ident));
        stream.push(sp(8));
      }
      var rowH = 0;
      for (var k = 0; k < stream.length; k++) if (stream[k].h > rowH) rowH = stream[k].h;
      var yTop = Math.round((sign.physH - rowH) / 2);
      ticker(sign, stream, yTop, t, ctx.speed, 26, 0, {
        vAlign: "top"
      });
      livePulse(sign, t);
    },
    // ---- BIGSIGN A: hi-res hero ident + hi-res metrics ----------------
    bigA: function (sign, ctx) {
      var fl = ctx.flights,
        t = ctx.t;
      var idx = Math.floor(t / (4200 / ctx.speed)) % fl.length;
      var f = fl[idx];
      var al = airlineOf(f.flt);
      // airline tail fin, left
      var finW = drawTail(sign, 4, 3, 28, al, 1);
      var lx = 4 + finW + 8;
      // ident hero
      sign.hires(f.flt, lx, 1, C.ident, 26, "700");
      // airline name + type, second line under ident
      var ny = 30,
        nx = lx;
      if (al.name) nx += sign.hires(al.name, lx, ny, al.c1, 10, "700") + 6;
      sign.hires(f.type, nx, ny, C.type, 10, "600");
      // metrics line (hi-res small, colored)
      var arrow = f.vr > 50 ? "\u25B2" : f.vr < -50 ? "\u25BC" : "\u25AC";
      var y = 45,
        x = 4,
        px = 12;
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
      var fl = ctx.flights,
        t = ctx.t,
        px = 8;
      var idx = Math.floor(t / (4200 / ctx.speed)) % fl.length;
      var f = fl[idx];
      // top: ident held (type moves to the scrolling row to respect the ~10-char budget)
      var top = [tkText(sign, f.flt, C.ident, px)];
      drawRow(sign, top, 1 * sign.scale, 0, {
        vAlign: "top"
      });
      // bottom: type + metrics scroll
      var met = [tkText(sign, f.type, C.type, px), sp(4 * sign.scale)].concat(metricsBDF(sign, f, px, 3));
      var w = rowWidth(met);
      if (w <= sign.physW) drawRow(sign, met, 1 * sign.scale, 8 * sign.scale, {
        vAlign: "top"
      });else ticker(sign, met, 8 * sign.scale, t, ctx.speed, 46, 20 * sign.scale, {
        vAlign: "top"
      });
      livePulse(sign, t);
    },
    // ---- LONGBOI A: dashboard row (Flight Wall analog) ----------------
    longA: function (sign, ctx) {
      var fl = ctx.flights,
        t = ctx.t;
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
      var uy = 40,
        ux = hx;
      if (al.name) ux += sign.hires(al.name, hx, uy, al.c1, 12, "700") + 7;
      sign.hires(f.type, ux, uy, C.type, 12, "600");
      // metric columns
      var arrow = f.vr > 50 ? "\u25B2" : f.vr < -50 ? "\u25BC" : "\u25AC";
      var cols = [{
        lab: "ALT FT",
        val: f.alt.toLocaleString("en-US"),
        c: C.alt,
        arr: arrow,
        ac: vColor(f.vr)
      }, {
        lab: "SPD KT",
        val: f.gs + "",
        c: C.speed
      }, {
        lab: "TRK",
        val: f.trk + "\u00B0",
        c: C.track
      }, {
        lab: "DIST",
        val: f.dist,
        c: C.dist
      }];
      var x = Math.max(hx + iw + 30, 190);
      var colW = Math.floor((sign.physW - x - 16) / cols.length);
      for (var i = 0; i < cols.length; i++) {
        var cx = x + i * colW;
        sign.hires(cols[i].lab, cx, 8, C.label, 10, "700");
        var vx = cx;
        if (cols[i].arr) {
          vx += sign.hires(cols[i].arr, cx, 26, cols[i].ac, 11, "700") + 3;
        }
        sign.hires(cols[i].val, vx, 24, cols[i].c, 16, "700");
      }
      pagingDots(sign, fl.length, idx, sign.physW - fl.length * (2 * sign.scale) - 6, sign.physH - sign.scale * 2 - 3);
      livePulse(sign, t);
    },
    // ---- LONGBOI B: hi-res ticker stream ------------------------------
    longB: function (sign, ctx) {
      var fl = ctx.flights,
        t = ctx.t,
        px = 20;
      var stream = [];
      for (var i = 0; i < fl.length; i++) {
        var f = fl[i];
        var arrow = f.vr > 50 ? "\u25B2" : f.vr < -50 ? "\u25BC" : "\u25AC";
        stream.push(tkHi(sign, f.flt, C.ident, px, "700"));
        stream.push(sp(6));
        stream.push(tkHi(sign, f.type, C.type, px - 4, "600"));
        stream.push(sp(8));
        stream.push(tkHi(sign, arrow, vColor(f.vr), px - 6, "700"));
        stream.push(sp(3));
        stream.push(tkHi(sign, altStr(f.alt), C.alt, px - 2, "600"));
        stream.push(sp(8));
        stream.push(tkHi(sign, f.gs + "KT", C.speed, px - 2, "600"));
        stream.push(sp(8));
        stream.push(tkHi(sign, f.trk + "\u00B0", C.track, px - 2, "600"));
        stream.push(sp(8));
        stream.push(tkHi(sign, f.dist, C.dist, px - 2, "600"));
        stream.push(sp(14));
        stream.push(tkHi(sign, "\u2022", C.label, px, "700"));
        stream.push(sp(14));
      }
      var yTop = Math.round((sign.physH - stream[0].h) / 2);
      ticker(sign, stream, yTop, t, ctx.speed, 60, 0, {
        vAlign: "top"
      });
      livePulse(sign, t);
    },
    // ---- LONGBOI C: two-up stacked rows -------------------------------
    longC: function (sign, ctx) {
      var fl = ctx.flights,
        t = ctx.t,
        px = 8;
      // rotate the *pair* shown
      var pairStart = Math.floor(t / (5000 / ctx.speed)) % fl.length;
      for (var r = 0; r < 2; r++) {
        var f = fl[(pairStart + r) % fl.length];
        var y = r * 8;
        var row = [tkText(sign, f.flt, C.ident, px), sp(3 * sign.scale), tkText(sign, f.type, C.type, px), sp(4 * sign.scale), tkGlyph(sign, vGlyph(f.vr), vColor(f.vr)), sp(1 * sign.scale), tkText(sign, altStr(f.alt), C.alt, px), sp(3 * sign.scale), tkText(sign, f.gs + "KT", C.speed, px), sp(3 * sign.scale), tkText(sign, "" + f.trk, C.track, px), tkGlyph(sign, "deg", C.track), sp(3 * sign.scale), tkText(sign, f.dist, C.dist, px)];
        var w = rowWidth(row);
        if (w <= sign.physW) drawRow(sign, row, 1 * sign.scale, y * sign.scale, {
          vAlign: "top"
        });else ticker(sign, row, y * sign.scale, t, ctx.speed, 40, 24 * sign.scale, {
          vAlign: "top"
        });
      }
      livePulse(sign, t);
    }
  };

  // ======================================================================
  //  BOOT
  // ======================================================================
  var SIGN_DEFS = {
    smallA: {
      logW: 160,
      logH: 16,
      scale: 1
    },
    smallB: {
      logW: 160,
      logH: 16,
      scale: 1
    },
    bigA: {
      logW: 64,
      logH: 16,
      scale: 4
    },
    bigB: {
      logW: 64,
      logH: 16,
      scale: 4
    },
    longA: {
      logW: 128,
      logH: 16,
      scale: 4
    },
    longB: {
      logW: 128,
      logH: 16,
      scale: 4
    },
    longC: {
      logW: 128,
      logH: 16,
      scale: 4
    }
  };
  var state = {
    speed: 1,
    traffic: 4,
    glow: true,
    playing: true,
    clock: 0,
    last: 0
  };
  var signs = [];
  function cellFor(physW) {
    return Math.max(2, Math.round(920 / physW));
  }
  function boot() {
    Object.keys(SIGN_DEFS).forEach(function (id) {
      var cv = document.getElementById("cv-" + id);
      if (!cv) return;
      var def = SIGN_DEFS[id];
      var s = new LED.Sign(cv, {
        logW: def.logW,
        logH: def.logH,
        scale: def.scale,
        cell: cellFor(def.logW * def.scale),
        glow: state.glow
      });
      signs.push({
        id: id,
        sign: s,
        draw: LAYOUTS[id]
      });
    });
    bindControls();
    state.last = performance.now();
    frame(); // paint immediately
    setInterval(frame, 1000 / 40);
  }
  function frame() {
    var now = performance.now();
    var dt = now - state.last;
    state.last = now;
    if (dt > 250) dt = 250; // clamp after tab throttling
    if (state.playing) state.clock += dt;
    var flights = FLIGHTS.slice(0, state.traffic);
    var empty = flights.length === 0;
    var wideMap = {
      longA: 1,
      longB: 1,
      longC: 1,
      bigA: 0,
      bigB: 0
    };
    for (var i = 0; i < signs.length; i++) {
      var S = signs[i];
      S.sign.glow = state.glow;
      S.sign.clear();
      if (empty) drawEmpty(S.sign, state.clock, S.sign.logW * S.sign.scale >= 200);else S.draw(S.sign, {
        t: state.clock,
        speed: state.speed,
        flights: flights
      });
      S.sign.render();
    }
  }
  function bindControls() {
    var traffic = document.getElementById("ctl-traffic");
    var speed = document.getElementById("ctl-speed");
    var glow = document.getElementById("ctl-glow");
    var play = document.getElementById("ctl-play");
    if (traffic) traffic.addEventListener("change", function () {
      state.traffic = +traffic.value;
    });
    if (speed) speed.addEventListener("input", function () {
      state.speed = +speed.value;
      var lbl = document.getElementById("ctl-speed-val");
      if (lbl) lbl.textContent = state.speed.toFixed(1) + "\u00D7";
    });
    if (glow) glow.addEventListener("change", function () {
      state.glow = glow.checked;
    });
    if (play) play.addEventListener("click", function () {
      state.playing = !state.playing;
      play.textContent = state.playing ? "\u2759\u2759 Pause" : "\u25B6 Play";
      play.setAttribute("aria-pressed", String(!state.playing));
    });
  }

  // wait for fonts, then boot
  function start() {
    var fonts = [document.fonts.load("8px Silkscreen"), document.fonts.load("16px Silkscreen"), document.fonts.load("700 28px Inter"), document.fonts.load("600 14px Inter")];
    Promise.all(fonts).catch(function () {}).then(function () {
      return document.fonts.ready;
    }).then(boot);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);else start();
  window.FT = {
    state: state
  };
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "app.js", error: String((e && e.message) || e) }); }

// design_handoff_led_flight_tracker/app.js
try { (() => {
/* Flight tracker LED layouts — sample data, semantic layouts, animation loop. */
(function () {
  "use strict";

  // ---- semantic palette (consistent across every sign) ----------------------
  var C = {
    ident: [255, 255, 255],
    type: [170, 90, 255],
    alt: [255, 180, 0],
    speed: [60, 220, 60],
    track: [0, 220, 255],
    dist: [255, 80, 255],
    climb: [0, 255, 0],
    descend: [255, 60, 60],
    level: [255, 180, 0],
    label: [70, 90, 130],
    idle: [0, 150, 200],
    live: [0, 255, 0]
  };

  // ---- sample flights overhead ---------------------------------------------
  var FLIGHTS = [{
    flt: "UA2341",
    type: "B738",
    alt: 34000,
    vr: 1200,
    gs: 460,
    trk: 247,
    dist: "12KM NE",
    reg: "N12345"
  }, {
    flt: "DL815",
    type: "A21N",
    alt: 28000,
    vr: -900,
    gs: 420,
    trk: 198,
    dist: "6KM S",
    reg: "N815DN"
  }, {
    flt: "WN88",
    type: "B737",
    alt: 39000,
    vr: 0,
    gs: 480,
    trk: 90,
    dist: "22KM E",
    reg: "N7088A"
  }, {
    flt: "BA49H",
    type: "B77W",
    alt: 41000,
    vr: 0,
    gs: 510,
    trk: 305,
    dist: "31KM NW",
    reg: "G-STBA"
  }];

  // ---- formatting -----------------------------------------------------------
  function altStr(a) {
    return a.toLocaleString("en-US") + "FT";
  }
  function vColor(vr) {
    return vr > 50 ? C.climb : vr < -50 ? C.descend : C.level;
  }
  function vGlyph(vr) {
    return vr > 50 ? "up" : vr < -50 ? "down" : "level";
  }

  // ---- airlines: brand-color tail-fin marks (NOT logos — trademark-safe) ----
  // Derived from the callsign alpha prefix. Colors are brand palettes, drawn as
  // a swept vertical-stabiliser silhouette with an accent stripe.
  var AIRLINES = {
    UA: {
      name: "UNITED",
      c1: [40, 95, 210],
      c2: [235, 240, 255]
    },
    DL: {
      name: "DELTA",
      c1: [220, 40, 60],
      c2: [30, 80, 150]
    },
    WN: {
      name: "SOUTHWEST",
      c1: [255, 190, 0],
      c2: [220, 45, 55]
    },
    BA: {
      name: "BRITISH",
      c1: [40, 95, 175],
      c2: [220, 45, 55]
    }
  };
  var DEFAULT_AL = {
    name: "",
    c1: [150, 160, 175],
    c2: [90, 100, 115]
  };
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
    var bandTop = Math.round(H * 0.5),
      bandH = Math.max(1, Math.round(H * 0.16));
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
  function tkCustom(w, h, fn) {
    return {
      custom: fn,
      w: w,
      h: h
    };
  }
  function tkTail(sign, al, H) {
    var W = Math.max(4, Math.round(H * 0.82));
    return tkCustom(W, H, function (s, x, yTop, opts) {
      var b = opts && opts.bright != null ? opts.bright : 1;
      var y = yTop + Math.max(0, (opts && opts.rowH || H) - H);
      if (opts && opts.vAlign === "top") y = yTop;
      drawTail(s, x, y, H, al, b);
    });
  }
  // small centred separator dot for use between fields
  function tkSep(sign, H, color) {
    var s = sign.scale,
      d = s;
    return tkCustom(d, H, function (sg, x, yTop, opts) {
      var b = opts && opts.bright != null ? opts.bright : 1;
      var cy = yTop + Math.round(H / 2) - Math.round(d / 2);
      for (var yy = 0; yy < d; yy++) for (var xx = 0; xx < d; xx++) sg.px(x + xx, cy + yy, color || C.label, 0.7 * b);
    });
  }

  // ---- token helpers (all coordinates physical) -----------------------------
  function tkText(sign, val, color, px) {
    var m = LED.rasterize(val, px, "Silkscreen", null, true);
    return {
      mask: m,
      expand: sign.scale,
      color: color,
      w: m.w * sign.scale,
      h: m.h * sign.scale
    };
  }
  function tkHi(sign, val, color, px, wt) {
    var m = sign.hiresMask(val, px, wt || "700");
    return {
      mask: m,
      expand: 1,
      color: color,
      w: m.w,
      h: m.h
    };
  }
  function tkGlyph(sign, name, color) {
    var m = LED.GLYPH[name];
    return {
      mask: m,
      expand: sign.scale,
      color: color,
      w: m.w * sign.scale,
      h: m.h * sign.scale
    };
  }
  function sp(w) {
    return {
      spacer: true,
      w: w
    };
  }
  function rowWidth(tokens) {
    var w = 0;
    for (var i = 0; i < tokens.length; i++) w += tokens[i].w;
    return w;
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
          x0: opts.x0,
          x1: opts.x1,
          y0: opts.y0,
          y1: opts.y1
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
    t.push(tkText(sign, altStr(f.alt), C.alt, px));
    t.push(sp(kern));
    t.push(tkText(sign, f.gs + "KT", C.speed, px));
    t.push(sp(kern));
    t.push(tkText(sign, "" + f.trk, C.track, px));
    t.push(tkGlyph(sign, "deg", C.track));
    t.push(sp(kern));
    t.push(tkText(sign, f.dist, C.dist, px));
    return t;
  }
  // compact metrics (short) for tight rows
  function metricsCompact(sign, f, px, kern) {
    var s = sign.scale,
      t = [];
    t.push(tkText(sign, Math.round(f.alt / 1000) + "K", C.alt, px));
    t.push(tkGlyph(sign, vGlyph(f.vr), vColor(f.vr)));
    t.push(sp(kern));
    t.push(tkText(sign, f.gs + "", C.speed, px));
    t.push(sp(kern));
    t.push(tkText(sign, "" + f.trk, C.track, px));
    t.push(tkGlyph(sign, "deg", C.track));
    t.push(sp(kern));
    t.push(tkText(sign, f.dist.replace(" ", ""), C.dist, px));
    return t;
  }
  function pagingDots(sign, n, cur, physX, physY) {
    var s = sign.scale,
      step = 2 * s;
    for (var i = 0; i < n; i++) {
      sign.blit(LED.GLYPH.dot, physX + i * step, physY, i === cur ? C.ident : C.label, s, {});
    }
  }
  function scrollOffset(t, speed, pxPerSec, period) {
    if (period <= 0) return 0;
    return t / 1000 * pxPerSec * speed % period;
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
      x += period;
      guard++;
    }
  }

  // ---- empty state ----------------------------------------------------------
  function drawEmpty(sign, t, wide) {
    // slow radar scan column
    var period = 3200;
    var sx = Math.floor(t % period / period * sign.physW);
    for (var y = 0; y < sign.physH; y++) {
      var d = Math.abs(y - sign.physH / 2) / (sign.physH / 2);
      sign.px(sx, y, C.idle, 0.10 * (1 - d));
    }
    var pulse = 0.55 + 0.45 * Math.sin(t / 600);
    var label = wide ? "NO TRAFFIC OVERHEAD" : "NO TRAFFIC";
    var px = sign.logH >= 16 ? sign.scale > 1 ? 8 : wide ? 12 : 8 : 8;
    var m = LED.rasterize(label, px, "Silkscreen", null, true);
    var wLog = m.w,
      hLog = m.h;
    var bx = Math.round((sign.logW - wLog) / 2) * sign.scale;
    var by = Math.round((sign.logH - hLog) / 2) * sign.scale;
    sign.blit(m, bx, by, C.idle, sign.scale, {
      bright: pulse
    });
  }

  // ---- refresh pulse (top-right live dot, blinks each ~10s) ------------------
  function livePulse(sign, t) {
    var phase = t % 10000 / 10000;
    var on = phase < 0.12 ? 1 : 0.18;
    sign.blit(LED.GLYPH.dot, sign.physW - sign.scale * 2, sign.scale, C.live, sign.scale, {
      bright: on
    });
  }

  // ======================================================================
  //  LAYOUT VARIANTS
  // ======================================================================
  var LAYOUTS = {
    // ---- SMALLSIGN A: two-row rotator ---------------------------------
    smallA: function (sign, ctx) {
      var fl = ctx.flights,
        t = ctx.t,
        sp8 = 8;
      var idx = Math.floor(t / (4500 / ctx.speed)) % fl.length;
      var f = fl[idx];
      // top: ident + type, held
      var top = [tkText(sign, f.flt, C.ident, sp8), sp(6), tkText(sign, f.type, C.type, sp8)];
      drawRow(sign, top, 1, 0, {
        vAlign: "top"
      });
      pagingDots(sign, fl.length, idx, sign.physW - fl.length * 2 - 3, 1);
      // bottom: metrics, scroll if overflow
      var met = metricsBDF(sign, f, sp8, 3);
      var w = rowWidth(met);
      if (w <= sign.physW) drawRow(sign, met, 1, 8, {
        vAlign: "top"
      });else ticker(sign, met, 8, t, ctx.speed, 18, 14, {
        vAlign: "top"
      });
      livePulse(sign, t);
    },
    // ---- SMALLSIGN B: single-line 6x12 ticker -------------------------
    smallB: function (sign, ctx) {
      var fl = ctx.flights,
        t = ctx.t,
        px = 12;
      var stream = [];
      for (var i = 0; i < fl.length; i++) {
        var f = fl[i];
        var al = airlineOf(f.flt);
        stream.push(tkTail(sign, al, 12));
        stream.push(sp(4));
        stream.push(tkText(sign, f.flt, C.ident, px));
        stream.push(sp(5));
        stream.push(tkSep(sign, 12));
        stream.push(sp(5));
        stream.push(tkText(sign, f.type, C.type, px));
        stream.push(sp(5));
        stream.push(tkSep(sign, 12));
        stream.push(sp(5));
        stream.push(tkGlyph(sign, vGlyph(f.vr), vColor(f.vr)));
        stream.push(sp(2));
        stream.push(tkText(sign, altStr(f.alt), C.alt, px));
        stream.push(sp(5));
        stream.push(tkSep(sign, 12));
        stream.push(sp(5));
        stream.push(tkText(sign, f.gs + "KT", C.speed, px));
        stream.push(sp(5));
        stream.push(tkSep(sign, 12));
        stream.push(sp(5));
        stream.push(tkText(sign, "" + f.trk, C.track, px));
        stream.push(tkGlyph(sign, "deg", C.track));
        stream.push(sp(5));
        stream.push(tkSep(sign, 12));
        stream.push(sp(5));
        stream.push(tkText(sign, f.dist, C.dist, px));
        stream.push(sp(8));
        stream.push(tkSep(sign, 12, C.ident));
        stream.push(sp(8));
      }
      var rowH = 0;
      for (var k = 0; k < stream.length; k++) if (stream[k].h > rowH) rowH = stream[k].h;
      var yTop = Math.round((sign.physH - rowH) / 2);
      ticker(sign, stream, yTop, t, ctx.speed, 26, 0, {
        vAlign: "top"
      });
      livePulse(sign, t);
    },
    // ---- BIGSIGN A: hi-res hero ident + hi-res metrics ----------------
    bigA: function (sign, ctx) {
      var fl = ctx.flights,
        t = ctx.t;
      var idx = Math.floor(t / (4200 / ctx.speed)) % fl.length;
      var f = fl[idx];
      var al = airlineOf(f.flt);
      // airline tail fin, left
      var finW = drawTail(sign, 4, 3, 28, al, 1);
      var lx = 4 + finW + 8;
      // ident hero
      sign.hires(f.flt, lx, 1, C.ident, 26, "700");
      // airline name + type, second line under ident
      var ny = 30,
        nx = lx;
      if (al.name) nx += sign.hires(al.name, lx, ny, al.c1, 10, "700") + 6;
      sign.hires(f.type, nx, ny, C.type, 10, "600");
      // metrics line (hi-res small, colored)
      var arrow = f.vr > 50 ? "\u25B2" : f.vr < -50 ? "\u25BC" : "\u25AC";
      var y = 45,
        x = 4,
        px = 12;
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
      var fl = ctx.flights,
        t = ctx.t,
        px = 8;
      var idx = Math.floor(t / (4200 / ctx.speed)) % fl.length;
      var f = fl[idx];
      // top: ident held (type moves to the scrolling row to respect the ~10-char budget)
      var top = [tkText(sign, f.flt, C.ident, px)];
      drawRow(sign, top, 1 * sign.scale, 0, {
        vAlign: "top"
      });
      // bottom: type + metrics scroll
      var met = [tkText(sign, f.type, C.type, px), sp(4 * sign.scale)].concat(metricsBDF(sign, f, px, 3));
      var w = rowWidth(met);
      if (w <= sign.physW) drawRow(sign, met, 1 * sign.scale, 8 * sign.scale, {
        vAlign: "top"
      });else ticker(sign, met, 8 * sign.scale, t, ctx.speed, 46, 20 * sign.scale, {
        vAlign: "top"
      });
      livePulse(sign, t);
    },
    // ---- LONGBOI A: dashboard row (Flight Wall analog) ----------------
    longA: function (sign, ctx) {
      var fl = ctx.flights,
        t = ctx.t;
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
      var uy = 40,
        ux = hx;
      if (al.name) ux += sign.hires(al.name, hx, uy, al.c1, 12, "700") + 7;
      sign.hires(f.type, ux, uy, C.type, 12, "600");
      // metric columns
      var arrow = f.vr > 50 ? "\u25B2" : f.vr < -50 ? "\u25BC" : "\u25AC";
      var cols = [{
        lab: "ALT FT",
        val: f.alt.toLocaleString("en-US"),
        c: C.alt,
        arr: arrow,
        ac: vColor(f.vr)
      }, {
        lab: "SPD KT",
        val: f.gs + "",
        c: C.speed
      }, {
        lab: "TRK",
        val: f.trk + "\u00B0",
        c: C.track
      }, {
        lab: "DIST",
        val: f.dist,
        c: C.dist
      }];
      var x = Math.max(hx + iw + 30, 190);
      var colW = Math.floor((sign.physW - x - 16) / cols.length);
      for (var i = 0; i < cols.length; i++) {
        var cx = x + i * colW;
        sign.hires(cols[i].lab, cx, 8, C.label, 10, "700");
        var vx = cx;
        if (cols[i].arr) {
          vx += sign.hires(cols[i].arr, cx, 26, cols[i].ac, 11, "700") + 3;
        }
        sign.hires(cols[i].val, vx, 24, cols[i].c, 16, "700");
      }
      pagingDots(sign, fl.length, idx, sign.physW - fl.length * (2 * sign.scale) - 6, sign.physH - sign.scale * 2 - 3);
      livePulse(sign, t);
    },
    // ---- LONGBOI B: hi-res ticker stream ------------------------------
    longB: function (sign, ctx) {
      var fl = ctx.flights,
        t = ctx.t,
        px = 20;
      var stream = [];
      for (var i = 0; i < fl.length; i++) {
        var f = fl[i];
        var arrow = f.vr > 50 ? "\u25B2" : f.vr < -50 ? "\u25BC" : "\u25AC";
        stream.push(tkHi(sign, f.flt, C.ident, px, "700"));
        stream.push(sp(6));
        stream.push(tkHi(sign, f.type, C.type, px - 4, "600"));
        stream.push(sp(8));
        stream.push(tkHi(sign, arrow, vColor(f.vr), px - 6, "700"));
        stream.push(sp(3));
        stream.push(tkHi(sign, altStr(f.alt), C.alt, px - 2, "600"));
        stream.push(sp(8));
        stream.push(tkHi(sign, f.gs + "KT", C.speed, px - 2, "600"));
        stream.push(sp(8));
        stream.push(tkHi(sign, f.trk + "\u00B0", C.track, px - 2, "600"));
        stream.push(sp(8));
        stream.push(tkHi(sign, f.dist, C.dist, px - 2, "600"));
        stream.push(sp(14));
        stream.push(tkHi(sign, "\u2022", C.label, px, "700"));
        stream.push(sp(14));
      }
      var yTop = Math.round((sign.physH - stream[0].h) / 2);
      ticker(sign, stream, yTop, t, ctx.speed, 60, 0, {
        vAlign: "top"
      });
      livePulse(sign, t);
    },
    // ---- LONGBOI C: two-up stacked rows -------------------------------
    longC: function (sign, ctx) {
      var fl = ctx.flights,
        t = ctx.t,
        px = 8;
      // rotate the *pair* shown
      var pairStart = Math.floor(t / (5000 / ctx.speed)) % fl.length;
      for (var r = 0; r < 2; r++) {
        var f = fl[(pairStart + r) % fl.length];
        var y = r * 8;
        var row = [tkText(sign, f.flt, C.ident, px), sp(3 * sign.scale), tkText(sign, f.type, C.type, px), sp(4 * sign.scale), tkGlyph(sign, vGlyph(f.vr), vColor(f.vr)), sp(1 * sign.scale), tkText(sign, altStr(f.alt), C.alt, px), sp(3 * sign.scale), tkText(sign, f.gs + "KT", C.speed, px), sp(3 * sign.scale), tkText(sign, "" + f.trk, C.track, px), tkGlyph(sign, "deg", C.track), sp(3 * sign.scale), tkText(sign, f.dist, C.dist, px)];
        var w = rowWidth(row);
        if (w <= sign.physW) drawRow(sign, row, 1 * sign.scale, y * sign.scale, {
          vAlign: "top"
        });else ticker(sign, row, y * sign.scale, t, ctx.speed, 40, 24 * sign.scale, {
          vAlign: "top"
        });
      }
      livePulse(sign, t);
    }
  };

  // ======================================================================
  //  BOOT
  // ======================================================================
  var SIGN_DEFS = {
    smallA: {
      logW: 160,
      logH: 16,
      scale: 1
    },
    smallB: {
      logW: 160,
      logH: 16,
      scale: 1
    },
    bigA: {
      logW: 64,
      logH: 16,
      scale: 4
    },
    bigB: {
      logW: 64,
      logH: 16,
      scale: 4
    },
    longA: {
      logW: 128,
      logH: 16,
      scale: 4
    },
    longB: {
      logW: 128,
      logH: 16,
      scale: 4
    },
    longC: {
      logW: 128,
      logH: 16,
      scale: 4
    }
  };
  var state = {
    speed: 1,
    traffic: 4,
    glow: true,
    playing: true,
    clock: 0,
    last: 0
  };
  var signs = [];
  function cellFor(physW) {
    return Math.max(2, Math.round(920 / physW));
  }
  function boot() {
    Object.keys(SIGN_DEFS).forEach(function (id) {
      var cv = document.getElementById("cv-" + id);
      if (!cv) return;
      var def = SIGN_DEFS[id];
      var s = new LED.Sign(cv, {
        logW: def.logW,
        logH: def.logH,
        scale: def.scale,
        cell: cellFor(def.logW * def.scale),
        glow: state.glow
      });
      signs.push({
        id: id,
        sign: s,
        draw: LAYOUTS[id]
      });
    });
    bindControls();
    state.last = performance.now();
    frame(); // paint immediately
    setInterval(frame, 1000 / 40);
  }
  function frame() {
    var now = performance.now();
    var dt = now - state.last;
    state.last = now;
    if (dt > 250) dt = 250; // clamp after tab throttling
    if (state.playing) state.clock += dt;
    var flights = FLIGHTS.slice(0, state.traffic);
    var empty = flights.length === 0;
    var wideMap = {
      longA: 1,
      longB: 1,
      longC: 1,
      bigA: 0,
      bigB: 0
    };
    for (var i = 0; i < signs.length; i++) {
      var S = signs[i];
      S.sign.glow = state.glow;
      S.sign.clear();
      if (empty) drawEmpty(S.sign, state.clock, S.sign.logW * S.sign.scale >= 200);else S.draw(S.sign, {
        t: state.clock,
        speed: state.speed,
        flights: flights
      });
      S.sign.render();
    }
  }
  function bindControls() {
    var traffic = document.getElementById("ctl-traffic");
    var speed = document.getElementById("ctl-speed");
    var glow = document.getElementById("ctl-glow");
    var play = document.getElementById("ctl-play");
    if (traffic) traffic.addEventListener("change", function () {
      state.traffic = +traffic.value;
    });
    if (speed) speed.addEventListener("input", function () {
      state.speed = +speed.value;
      var lbl = document.getElementById("ctl-speed-val");
      if (lbl) lbl.textContent = state.speed.toFixed(1) + "\u00D7";
    });
    if (glow) glow.addEventListener("change", function () {
      state.glow = glow.checked;
    });
    if (play) play.addEventListener("click", function () {
      state.playing = !state.playing;
      play.textContent = state.playing ? "\u2759\u2759 Pause" : "\u25B6 Play";
      play.setAttribute("aria-pressed", String(!state.playing));
    });
  }

  // wait for fonts, then boot
  function start() {
    var fonts = [document.fonts.load("8px Silkscreen"), document.fonts.load("16px Silkscreen"), document.fonts.load("700 28px Inter"), document.fonts.load("600 14px Inter")];
    Promise.all(fonts).catch(function () {}).then(function () {
      return document.fonts.ready;
    }).then(boot);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);else start();
  window.FT = {
    state: state
  };
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "design_handoff_led_flight_tracker/app.js", error: String((e && e.message) || e) }); }

// design_handoff_led_flight_tracker/led-engine.js
try { (() => {
/* LED sign engine — physical framebuffer rendered as lit dots on pure black.
   Matches the ground-truth engine renders: no visible off-grid, chunky BDF dots,
   fine hi-res dots. One physical pixel = one LED. */
(function (global) {
  "use strict";

  // ---- offscreen rasterizer (text -> alpha mask, cached) --------------------
  const rc = document.createElement("canvas");
  const rx = rc.getContext("2d", {
    willReadFrequently: true
  });
  const maskCache = new Map();
  function rasterize(text, px, family, weight, crisp) {
    const key = text + "|" + px + "|" + family + "|" + (weight || "") + "|" + (crisp ? 1 : 0);
    let m = maskCache.get(key);
    if (m) return m;
    const font = (weight ? weight + " " : "") + px + "px " + family;
    rx.font = font;
    const w = Math.max(1, Math.ceil(rx.measureText(text).width) + 2);
    const h = Math.ceil(px * 1.6);
    rc.width = w;
    rc.height = h;
    rx.font = font;
    rx.textBaseline = "top";
    rx.imageSmoothingEnabled = false;
    rx.clearRect(0, 0, w, h);
    rx.fillStyle = "#fff";
    rx.fillText(text, 0, 1);
    const data = rx.getImageData(0, 0, w, h).data;
    // trim to content bounds vertically & left
    let top = h,
      bot = -1,
      left = w,
      right = -1;
    const alpha = new Float32Array(w * h);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        let a = data[(y * w + x) * 4 + 3] / 255;
        if (crisp) a = a >= 0.5 ? 1 : 0;
        alpha[y * w + x] = a;
        if (a > 0) {
          if (y < top) top = y;
          if (y > bot) bot = y;
          if (x < left) left = x;
          if (x > right) right = x;
        }
      }
    }
    if (bot < 0) {
      top = 0;
      bot = 0;
      left = 0;
      right = 0;
    }
    // crop
    const cw = right - left + 1,
      ch = bot - top + 1;
    const cropped = new Float32Array(cw * ch);
    for (let y = 0; y < ch; y++) for (let x = 0; x < cw; x++) cropped[y * cw + x] = alpha[(y + top) * w + (x + left)];
    m = {
      w: cw,
      h: ch,
      alpha: cropped
    };
    maskCache.set(key, m);
    return m;
  }

  // ---- manual bitmap glyphs (things Silkscreen lacks) -----------------------
  function toGlyph(rows) {
    const h = rows.length,
      w = rows[0].length;
    const a = new Float32Array(w * h);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) a[y * w + x] = rows[y][x] === "#" ? 1 : 0;
    return {
      w,
      h,
      alpha: a
    };
  }
  const GLYPH = {
    up: toGlyph(["..#..", ".###.", "#####", "..#..", "..#..", "..#..", "..#.."]),
    down: toGlyph(["..#..", "..#..", "..#..", "..#..", "#####", ".###.", "..#.."]),
    level: toGlyph(["#####", "#####"]),
    deg: toGlyph(["###", "#.#", "###"]),
    dot: toGlyph(["#"]),
    plane: toGlyph(["....#....", "....#....", "...###...", "#########", "###########".slice(0, 9), "...###...", "...#.#..."])
  };

  // ---- Sign -----------------------------------------------------------------
  class Sign {
    constructor(canvas, opts) {
      this.logW = opts.logW;
      this.logH = opts.logH;
      this.scale = opts.scale; // physical px per logical dot
      this.physW = this.logW * this.scale;
      this.physH = this.logH * this.scale;
      this.cell = opts.cell; // screen px per physical dot
      this.glow = opts.glow !== false;
      canvas.width = this.physW * this.cell;
      canvas.height = this.physH * this.cell;
      canvas.style.width = "100%";
      canvas.style.aspectRatio = this.physW + " / " + this.physH;
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.fb = new Float32Array(this.physW * this.physH * 3); // rgb 0..1*bright
    }
    clear() {
      this.fb.fill(0);
    }
    // additive-max write of a physical pixel
    px(x, y, rgb, b) {
      x = x | 0;
      y = y | 0;
      if (x < 0 || y < 0 || x >= this.physW || y >= this.physH) return;
      const i = (y * this.physW + x) * 3;
      const r = rgb[0] * b,
        g = rgb[1] * b,
        bl = rgb[2] * b;
      if (r > this.fb[i]) this.fb[i] = r;
      if (g > this.fb[i + 1]) this.fb[i + 1] = g;
      if (bl > this.fb[i + 2]) this.fb[i + 2] = bl;
    }
    // blit a mask. baseX/baseY in physical px; expand = block size per mask px.
    // clip: {x0,x1} physical column clip (for scroll windows)
    blit(mask, baseX, baseY, rgb, expand, opts) {
      opts = opts || {};
      const bright = opts.bright == null ? 1 : opts.bright;
      const cx0 = opts.x0 == null ? 0 : opts.x0;
      const cx1 = opts.x1 == null ? this.physW : opts.x1;
      const cy0 = opts.y0 == null ? 0 : opts.y0;
      const cy1 = opts.y1 == null ? this.physH : opts.y1;
      baseX = Math.round(baseX);
      baseY = Math.round(baseY);
      for (let my = 0; my < mask.h; my++) {
        for (let mx = 0; mx < mask.w; mx++) {
          const a = mask.alpha[my * mask.w + mx];
          if (a <= 0) continue;
          const b = a * bright;
          for (let sy = 0; sy < expand; sy++) {
            const py = baseY + my * expand + sy;
            if (py < cy0 || py >= cy1) continue;
            for (let sx = 0; sx < expand; sx++) {
              const pxx = baseX + mx * expand + sx;
              if (pxx < cx0 || pxx >= cx1) continue;
              this.px(pxx, py, rgb, b);
            }
          }
        }
      }
    }
    // BDF text: logical coords, expanded by scale
    bdf(text, logX, logY, rgb, px, opts) {
      const m = rasterize(text, px, "Silkscreen", null, true);
      this.blit(m, logX * this.scale, logY * this.scale, rgb, this.scale, opts);
      return m.w; // logical advance
    }
    bdfWidth(text, px) {
      return rasterize(text, px, "Silkscreen", null, true).w;
    }
    // hi-res text: physical coords, 1:1
    hires(text, physX, physY, rgb, px, weight, opts) {
      const m = rasterize(text, px, "Inter", weight || "700", false);
      this.blit(m, physX, physY, rgb, 1, opts);
      return m.w;
    }
    hiresMask(text, px, weight) {
      return rasterize(text, px, "Inter", weight || "700", false);
    }
    glyph(name, logX, logY, rgb, opts) {
      const g = GLYPH[name];
      this.blit(g, logX * this.scale, logY * this.scale, rgb, this.scale, opts);
      return g.w;
    }
    // draw framebuffer as lit dots
    render() {
      const ctx = this.ctx,
        cell = this.cell;
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
      const gap = cell <= 2 ? 0 : Math.max(1, Math.round(cell * 0.16));
      const d = cell - gap;
      const rad = Math.min(d * 0.28, 3);
      // glow pass
      if (this.glow && cell >= 3) {
        ctx.globalCompositeOperation = "lighter";
        for (let y = 0; y < this.physH; y++) {
          for (let x = 0; x < this.physW; x++) {
            const i = (y * this.physW + x) * 3;
            const r = this.fb[i],
              g = this.fb[i + 1],
              b = this.fb[i + 2];
            if (r + g + b < 0.05) continue;
            ctx.fillStyle = "rgba(" + (r * 255 | 0) + "," + (g * 255 | 0) + "," + (b * 255 | 0) + ",0.18)";
            const cx = x * cell + cell / 2,
              cy = y * cell + cell / 2;
            ctx.beginPath();
            ctx.arc(cx, cy, d * 0.9, 0, 6.2832);
            ctx.fill();
          }
        }
        ctx.globalCompositeOperation = "source-over";
      }
      // solid dots
      for (let y = 0; y < this.physH; y++) {
        for (let x = 0; x < this.physW; x++) {
          const i = (y * this.physW + x) * 3;
          const r = this.fb[i],
            g = this.fb[i + 1],
            b = this.fb[i + 2];
          if (r + g + b < 0.02) continue;
          ctx.fillStyle = "rgb(" + Math.min(255, r * 255 | 0) + "," + Math.min(255, g * 255 | 0) + "," + Math.min(255, b * 255 | 0) + ")";
          const px = x * cell + gap / 2,
            py = y * cell + gap / 2;
          if (rad > 0.5) {
            roundRect(ctx, px, py, d, d, rad);
            ctx.fill();
          } else ctx.fillRect(px, py, d, d);
        }
      }
    }
  }
  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }
  global.LED = {
    Sign,
    rasterize,
    GLYPH
  };
})(window);
})(); } catch (e) { __ds_ns.__errors.push({ path: "design_handoff_led_flight_tracker/led-engine.js", error: String((e && e.message) || e) }); }

// design_handoff_stock_ticker/led-engine.js
try { (() => {
/* LED sign engine — physical framebuffer rendered as lit dots on pure black.
   Matches the ground-truth engine renders: no visible off-grid, chunky BDF dots,
   fine hi-res dots. One physical pixel = one LED. */
(function (global) {
  "use strict";

  // ---- offscreen rasterizer (text -> alpha mask, cached) --------------------
  const rc = document.createElement("canvas");
  const rx = rc.getContext("2d", {
    willReadFrequently: true
  });
  const maskCache = new Map();
  function rasterize(text, px, family, weight, crisp) {
    const key = text + "|" + px + "|" + family + "|" + (weight || "") + "|" + (crisp ? 1 : 0);
    let m = maskCache.get(key);
    if (m) return m;
    const font = (weight ? weight + " " : "") + px + "px " + family;
    rx.font = font;
    const w = Math.max(1, Math.ceil(rx.measureText(text).width) + 2);
    const h = Math.ceil(px * 1.6);
    rc.width = w;
    rc.height = h;
    rx.font = font;
    rx.textBaseline = "top";
    rx.imageSmoothingEnabled = false;
    rx.clearRect(0, 0, w, h);
    rx.fillStyle = "#fff";
    rx.fillText(text, 0, 1);
    const data = rx.getImageData(0, 0, w, h).data;
    // trim to content bounds vertically & left
    let top = h,
      bot = -1,
      left = w,
      right = -1;
    const alpha = new Float32Array(w * h);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        let a = data[(y * w + x) * 4 + 3] / 255;
        if (crisp) a = a >= 0.5 ? 1 : 0;
        alpha[y * w + x] = a;
        if (a > 0) {
          if (y < top) top = y;
          if (y > bot) bot = y;
          if (x < left) left = x;
          if (x > right) right = x;
        }
      }
    }
    if (bot < 0) {
      top = 0;
      bot = 0;
      left = 0;
      right = 0;
    }
    // crop
    const cw = right - left + 1,
      ch = bot - top + 1;
    const cropped = new Float32Array(cw * ch);
    for (let y = 0; y < ch; y++) for (let x = 0; x < cw; x++) cropped[y * cw + x] = alpha[(y + top) * w + (x + left)];
    m = {
      w: cw,
      h: ch,
      alpha: cropped
    };
    maskCache.set(key, m);
    return m;
  }

  // ---- manual bitmap glyphs (things Silkscreen lacks) -----------------------
  function toGlyph(rows) {
    const h = rows.length,
      w = rows[0].length;
    const a = new Float32Array(w * h);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) a[y * w + x] = rows[y][x] === "#" ? 1 : 0;
    return {
      w,
      h,
      alpha: a
    };
  }
  const GLYPH = {
    up: toGlyph(["..#..", ".###.", "#####", "..#..", "..#..", "..#..", "..#.."]),
    down: toGlyph(["..#..", "..#..", "..#..", "..#..", "#####", ".###.", "..#.."]),
    level: toGlyph(["#####", "#####"]),
    deg: toGlyph(["###", "#.#", "###"]),
    dot: toGlyph(["#"]),
    plane: toGlyph(["....#....", "....#....", "...###...", "#########", "###########".slice(0, 9), "...###...", "...#.#..."])
  };

  // ---- Sign -----------------------------------------------------------------
  class Sign {
    constructor(canvas, opts) {
      this.logW = opts.logW;
      this.logH = opts.logH;
      this.scale = opts.scale; // physical px per logical dot
      this.physW = this.logW * this.scale;
      this.physH = this.logH * this.scale;
      this.cell = opts.cell; // screen px per physical dot
      this.glow = opts.glow !== false;
      canvas.width = this.physW * this.cell;
      canvas.height = this.physH * this.cell;
      canvas.style.width = "100%";
      canvas.style.aspectRatio = this.physW + " / " + this.physH;
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.fb = new Float32Array(this.physW * this.physH * 3); // rgb 0..1*bright
    }
    clear() {
      this.fb.fill(0);
    }
    // additive-max write of a physical pixel
    px(x, y, rgb, b) {
      x = x | 0;
      y = y | 0;
      if (x < 0 || y < 0 || x >= this.physW || y >= this.physH) return;
      const i = (y * this.physW + x) * 3;
      const r = rgb[0] * b,
        g = rgb[1] * b,
        bl = rgb[2] * b;
      if (r > this.fb[i]) this.fb[i] = r;
      if (g > this.fb[i + 1]) this.fb[i + 1] = g;
      if (bl > this.fb[i + 2]) this.fb[i + 2] = bl;
    }
    // blit a mask. baseX/baseY in physical px; expand = block size per mask px.
    // clip: {x0,x1} physical column clip (for scroll windows)
    blit(mask, baseX, baseY, rgb, expand, opts) {
      opts = opts || {};
      const bright = opts.bright == null ? 1 : opts.bright;
      const cx0 = opts.x0 == null ? 0 : opts.x0;
      const cx1 = opts.x1 == null ? this.physW : opts.x1;
      const cy0 = opts.y0 == null ? 0 : opts.y0;
      const cy1 = opts.y1 == null ? this.physH : opts.y1;
      baseX = Math.round(baseX);
      baseY = Math.round(baseY);
      for (let my = 0; my < mask.h; my++) {
        for (let mx = 0; mx < mask.w; mx++) {
          const a = mask.alpha[my * mask.w + mx];
          if (a <= 0) continue;
          const b = a * bright;
          for (let sy = 0; sy < expand; sy++) {
            const py = baseY + my * expand + sy;
            if (py < cy0 || py >= cy1) continue;
            for (let sx = 0; sx < expand; sx++) {
              const pxx = baseX + mx * expand + sx;
              if (pxx < cx0 || pxx >= cx1) continue;
              this.px(pxx, py, rgb, b);
            }
          }
        }
      }
    }
    // BDF text: logical coords, expanded by scale
    bdf(text, logX, logY, rgb, px, opts) {
      const m = rasterize(text, px, "Silkscreen", null, true);
      this.blit(m, logX * this.scale, logY * this.scale, rgb, this.scale, opts);
      return m.w; // logical advance
    }
    bdfWidth(text, px) {
      return rasterize(text, px, "Silkscreen", null, true).w;
    }
    // hi-res text: physical coords, 1:1
    hires(text, physX, physY, rgb, px, weight, opts) {
      const m = rasterize(text, px, "Inter", weight || "700", false);
      this.blit(m, physX, physY, rgb, 1, opts);
      return m.w;
    }
    hiresMask(text, px, weight) {
      return rasterize(text, px, "Inter", weight || "700", false);
    }
    glyph(name, logX, logY, rgb, opts) {
      const g = GLYPH[name];
      this.blit(g, logX * this.scale, logY * this.scale, rgb, this.scale, opts);
      return g.w;
    }
    // draw framebuffer as lit dots
    render() {
      const ctx = this.ctx,
        cell = this.cell;
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
      const gap = cell <= 2 ? 0 : Math.max(1, Math.round(cell * 0.16));
      const d = cell - gap;
      const rad = Math.min(d * 0.28, 3);
      // glow pass
      if (this.glow && cell >= 3) {
        ctx.globalCompositeOperation = "lighter";
        for (let y = 0; y < this.physH; y++) {
          for (let x = 0; x < this.physW; x++) {
            const i = (y * this.physW + x) * 3;
            const r = this.fb[i],
              g = this.fb[i + 1],
              b = this.fb[i + 2];
            if (r + g + b < 0.05) continue;
            ctx.fillStyle = "rgba(" + (r * 255 | 0) + "," + (g * 255 | 0) + "," + (b * 255 | 0) + ",0.18)";
            const cx = x * cell + cell / 2,
              cy = y * cell + cell / 2;
            ctx.beginPath();
            ctx.arc(cx, cy, d * 0.9, 0, 6.2832);
            ctx.fill();
          }
        }
        ctx.globalCompositeOperation = "source-over";
      }
      // solid dots
      for (let y = 0; y < this.physH; y++) {
        for (let x = 0; x < this.physW; x++) {
          const i = (y * this.physW + x) * 3;
          const r = this.fb[i],
            g = this.fb[i + 1],
            b = this.fb[i + 2];
          if (r + g + b < 0.02) continue;
          ctx.fillStyle = "rgb(" + Math.min(255, r * 255 | 0) + "," + Math.min(255, g * 255 | 0) + "," + Math.min(255, b * 255 | 0) + ")";
          const px = x * cell + gap / 2,
            py = y * cell + gap / 2;
          if (rad > 0.5) {
            roundRect(ctx, px, py, d, d, rad);
            ctx.fill();
          } else ctx.fillRect(px, py, d, d);
        }
      }
    }
  }
  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }
  global.LED = {
    Sign,
    rasterize,
    GLYPH
  };
})(window);
})(); } catch (e) { __ds_ns.__errors.push({ path: "design_handoff_stock_ticker/led-engine.js", error: String((e && e.message) || e) }); }

// design_handoff_stock_ticker/stocks.js
try { (() => {
/* Stock ticker LED layouts — sample market data, live tick simulation,
   market state machine, semantic layouts. Reuses led-engine.js. */
(function () {
  "use strict";

  // ---- semantic palette ------------------------------------------------------
  var C = {
    sym: [255, 255, 255],
    price: [255, 180, 0],
    up: [60, 220, 60],
    down: [255, 60, 60],
    flat: [255, 180, 0],
    idx: [0, 220, 255],
    fx: [170, 90, 255],
    label: [70, 90, 130],
    white: [255, 255, 255]
  };

  // ---- market states ---------------------------------------------------------
  var STATES = {
    pre: {
      label: "PRE",
      c: [255, 180, 0],
      dim: 0.85,
      tick: 2600
    },
    open: {
      label: "LIVE",
      c: [0, 255, 0],
      dim: 1.0,
      tick: 700
    },
    after: {
      label: "AH",
      c: [170, 90, 255],
      dim: 0.85,
      tick: 2600
    },
    closed: {
      label: "CLSD",
      c: [255, 60, 60],
      dim: 0.45,
      tick: 0
    }
  };

  // ---- watchlist (brand chips are abstract two-tone marks, NOT logos) --------
  var WATCH = [{
    sym: "AAPL",
    name: "APPLE",
    kind: "eq",
    base: 227.52,
    pct0: 0.62,
    c1: [205, 210, 220],
    c2: [125, 132, 145]
  }, {
    sym: "NVDA",
    name: "NVIDIA",
    kind: "eq",
    base: 172.40,
    pct0: 2.41,
    c1: [118, 185, 0],
    c2: [235, 250, 225]
  }, {
    sym: "MSFT",
    name: "MICROSOFT",
    kind: "eq",
    base: 468.35,
    pct0: -0.38,
    c1: [0, 120, 215],
    c2: [240, 245, 255]
  }, {
    sym: "TSLA",
    name: "TESLA",
    kind: "eq",
    base: 312.80,
    pct0: 3.05,
    c1: [232, 33, 39],
    c2: [248, 248, 248]
  }, {
    sym: "AMZN",
    name: "AMAZON",
    kind: "eq",
    base: 223.10,
    pct0: 0.18,
    c1: [255, 153, 0],
    c2: [90, 115, 145]
  }, {
    sym: "META",
    name: "META",
    kind: "eq",
    base: 731.20,
    pct0: -1.12,
    c1: [0, 129, 255],
    c2: [215, 232, 255]
  }, {
    sym: "SPX",
    name: "S&P 500",
    kind: "ix",
    base: 6412.30,
    pct0: 0.44
  }, {
    sym: "NDX",
    name: "NASDAQ 100",
    kind: "ix",
    base: 23415.75,
    pct0: 0.71
  }, {
    sym: "DJI",
    name: "DOW JONES",
    kind: "ix",
    base: 44733.20,
    pct0: -0.12
  }, {
    sym: "EUR/USD",
    name: "EURO",
    kind: "fx",
    base: 1.0864,
    pct0: 0.21,
    dp: 4
  }, {
    sym: "USD/JPY",
    name: "YEN",
    kind: "fx",
    base: 156.42,
    pct0: -0.33,
    dp: 2
  }];

  // ---- seeded rng + spark generation ----------------------------------------
  function hash(s) {
    var h = 2166136261;
    for (var i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }
  function rng(seed) {
    var a = seed;
    return function () {
      a |= 0;
      a = a + 0x6D2B79F5 | 0;
      var t = Math.imul(a ^ a >>> 15, 1 | a);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  var SPARK_N = 64;
  WATCH.forEach(function (f) {
    f.dp = f.dp != null ? f.dp : 2;
    f.prev = f.base / (1 + f.pct0 / 100);
    var r = rng(hash(f.sym));
    var open = f.prev * (1 + (r() - 0.5) * 0.006);
    var d = [open],
      v = open;
    for (var i = 1; i < SPARK_N; i++) {
      v += v * (r() - 0.5) * 0.0045;
      d.push(v);
    }
    // blend so the walk lands on the current price
    var end = d[SPARK_N - 1];
    for (i = 0; i < SPARK_N; i++) d[i] += (f.base - end) * (i / (SPARK_N - 1));
    f.spark = d;
    f.price = f.base;
    f.flashT = -1e9;
    f.tickDir = 1;
  });
  var EQ = WATCH.filter(function (f) {
    return f.kind === "eq";
  });
  var IX = WATCH.filter(function (f) {
    return f.kind !== "eq";
  });
  var CARDS = WATCH.filter(function (f) {
    return f.kind !== "fx";
  }); // rotator decks

  // ---- formatting ------------------------------------------------------------
  function fmt(v, dp) {
    return v.toLocaleString("en-US", {
      minimumFractionDigits: dp,
      maximumFractionDigits: dp
    });
  }
  function chgOf(f) {
    return f.price - f.prev;
  }
  function pctOf(f) {
    return (f.price - f.prev) / f.prev * 100;
  }
  function chgColor(f) {
    var c = chgOf(f);
    return c > 0 ? C.up : c < 0 ? C.down : C.flat;
  }
  function pctStr(f) {
    var p = pctOf(f);
    return (p >= 0 ? "+" : "") + p.toFixed(2) + "%";
  }
  function chgStr(f) {
    var c = chgOf(f);
    return (c >= 0 ? "+" : "") + fmt(Math.abs(c) < 10 ? c : c, f.kind === "fx" ? f.dp : 2).replace("-", "-");
  }
  function symColor(f) {
    return f.kind === "ix" ? C.idx : f.kind === "fx" ? C.fx : C.sym;
  }
  function priceStr(f) {
    return fmt(f.price, f.dp);
  }
  function lerp(a, b, k) {
    return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k];
  }
  // Bloomberg-style flash: price lerps to white right after a tick
  function priceColor(f, t) {
    var k = Math.max(0, 1 - (t - f.flashT) / 420);
    return k > 0 ? lerp(C.price, C.white, k * 0.95) : C.price;
  }
  function arrowGlyph(f) {
    var c = chgOf(f);
    return c > 0 ? "up" : c < 0 ? "down" : "level";
  }
  function arrowChar(f) {
    var c = chgOf(f);
    return c > 0 ? "\u25B2" : c < 0 ? "\u25BC" : "\u25AC";
  }

  // ---- clipped pixel write (custom tokens must respect scroll windows) -------
  function cpx(sign, x, y, col, b, o) {
    if (o) {
      if (o.x0 != null && x < o.x0) return;
      if (o.x1 != null && x >= o.x1) return;
      if (o.y0 != null && y < o.y0) return;
      if (o.y1 != null && y >= o.y1) return;
    }
    sign.px(x, y, col, b);
  }

  // ---- brand chip: rounded two-tone diagonal mark (trademark-safe) -----------
  function drawChip(sign, x, y, H, f, bright, o) {
    if (!f.c1) return 0;
    var W = H;
    var rd = H >= 10 ? 2 : H >= 6 ? 1 : 0;
    for (var r = 0; r < H; r++) {
      for (var c = 0; c < W; c++) {
        var ex = Math.min(c, W - 1 - c),
          ey = Math.min(r, H - 1 - r);
        if (ex + ey < rd) continue; // knock corners
        var col = c - r > 0 ? f.c2 : f.c1;
        cpx(sign, x + c, y + r, col, bright, o);
      }
    }
    return W;
  }
  function tkCustom(w, h, fn) {
    return {
      custom: fn,
      w: w,
      h: h
    };
  }
  function tkChip(sign, f, H) {
    if (!f.c1) return {
      spacer: true,
      w: 0
    };
    return tkCustom(H, H, function (s, x, yTop, o) {
      var b = o && o.bright != null ? o.bright : 1;
      var y = yTop + Math.max(0, (o && o.rowH || H) - H) / 2;
      drawChip(s, x, Math.round(y), H, f, b, o);
    });
  }

  // ---- sparkline (physical px) with prev-close reference line ----------------
  function sparkRange(f) {
    var lo = f.prev,
      hi = f.prev;
    for (var i = 0; i < f.spark.length; i++) {
      var v = f.spark[i];
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    if (hi - lo < 1e-9) hi = lo + 1;
    return [lo, hi];
  }
  function drawSpark(sign, x, y, w, h, f, t, bright, o) {
    var lohi = sparkRange(f),
      lo = lohi[0],
      span = lohi[1] - lo;
    var n = f.spark.length;
    function Y(v) {
      return y + (h - 1) - Math.round((v - lo) / span * (h - 1));
    }
    // prev-close dotted reference
    var pcY = Y(f.prev);
    for (var xx = x; xx < x + w; xx += 3) cpx(sign, xx, pcY, C.label, 0.55 * bright, o);
    var prevY = null;
    for (var i = 0; i < w; i++) {
      var v = f.spark[Math.round(i / (w - 1) * (n - 1))];
      var yy = Y(v);
      var col = v >= f.prev ? C.up : C.down;
      cpx(sign, x + i, yy, col, bright, o);
      if (prevY !== null && Math.abs(yy - prevY) > 1) {
        var s0 = Math.min(yy, prevY) + 1,
          s1 = Math.max(yy, prevY);
        for (var sy = s0; sy < s1; sy++) cpx(sign, x + i, sy, col, 0.55 * bright, o);
      }
      prevY = yy;
    }
    // live endpoint pulse
    var pulse = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(t / 260));
    cpx(sign, x + w - 1, Y(f.price), C.white, pulse * bright, o);
  }
  function tkSpark(sign, f, w, h, t) {
    return tkCustom(w, h, function (s, x, yTop, o) {
      var b = o && o.bright != null ? o.bright : 1;
      var y = yTop + Math.max(0, (o && o.rowH || h) - h) / 2;
      drawSpark(s, x, Math.round(y), w, h, f, t, b, o);
    });
  }

  // ---- day range bar ----------------------------------------------------------
  function drawRange(sign, x, y, w, f, bright, o) {
    var lohi = sparkRange(f),
      lo = lohi[0],
      span = lohi[1] - lo;
    for (var i = 0; i < w; i++) cpx(sign, x + i, y + 1, C.label, 0.4 * bright, o);
    var mx = x + Math.round((f.price - lo) / span * (w - 1));
    var col = chgColor(f);
    for (var yy = 0; yy < 3; yy++) cpx(sign, mx, y + yy, col, bright, o);
    var px2 = x + Math.round((f.prev - lo) / span * (w - 1));
    cpx(sign, px2, y + 1, C.white, 0.7 * bright, o);
  }

  // ---- token helpers (from app.js conventions) --------------------------------
  function tkText(sign, val, color, px) {
    var m = LED.rasterize(val, px, "Silkscreen", null, true);
    return {
      mask: m,
      expand: sign.scale,
      color: color,
      w: m.w * sign.scale,
      h: m.h * sign.scale
    };
  }
  function tkHi(sign, val, color, px, wt) {
    var m = sign.hiresMask(val, px, wt || "700");
    return {
      mask: m,
      expand: 1,
      color: color,
      w: m.w,
      h: m.h
    };
  }
  function tkGlyph(sign, name, color) {
    var m = LED.GLYPH[name];
    return {
      mask: m,
      expand: sign.scale,
      color: color,
      w: m.w * sign.scale,
      h: m.h * sign.scale
    };
  }
  function sp(w) {
    return {
      spacer: true,
      w: w
    };
  }
  function tkSep(sign, H, color) {
    var s = sign.scale,
      d = s;
    return tkCustom(d, H, function (sg, x, yTop, o) {
      var b = o && o.bright != null ? o.bright : 1;
      var cy = yTop + Math.round(H / 2) - Math.round(d / 2);
      for (var yy = 0; yy < d; yy++) for (var xx = 0; xx < d; xx++) cpx(sg, x + xx, cy + yy, color || C.label, 0.7 * b, o);
    });
  }
  function rowWidth(tokens) {
    var w = 0;
    for (var i = 0; i < tokens.length; i++) w += tokens[i].w;
    return w;
  }
  function drawRow(sign, tokens, x, yTop, opts) {
    opts = opts || {};
    for (var i = 0; i < tokens.length; i++) {
      var t = tokens[i];
      if (t.custom) t.custom(sign, x, yTop, opts);else if (!t.spacer) {
        var yy = yTop;
        if (opts.vAlign !== "top") yy = yTop + Math.max(0, (opts.rowH || t.h) - t.h);
        sign.blit(t.mask, x, yy, t.color, t.expand, {
          bright: opts.bright == null ? 1 : opts.bright,
          x0: opts.x0,
          x1: opts.x1,
          y0: opts.y0,
          y1: opts.y1
        });
      }
      x += t.w;
    }
    return x;
  }
  function ticker(sign, tokens, yTop, t, speed, pxPerSec, gapBetween, rowOpts) {
    var content = rowWidth(tokens);
    var period = content + gapBetween;
    if (period <= 0) return;
    var off = t / 1000 * pxPerSec * speed % period;
    var xEnd = rowOpts && rowOpts.x1 != null ? rowOpts.x1 : sign.physW;
    var x = xEnd - off;
    var guard = 0;
    while (x < xEnd && guard < 8) {
      if (x + content > 0) drawRow(sign, tokens, x, yTop, rowOpts);
      x += period;
      guard++;
    }
  }
  function pagingDots(sign, n, cur, physX, physY) {
    var s = sign.scale,
      step = 2 * s;
    for (var i = 0; i < n; i++) {
      sign.blit(LED.GLYPH.dot, physX + i * step, physY, i === cur ? C.sym : C.label, s, {});
    }
  }

  // ---- market-state chips ------------------------------------------------------
  function stateInfo() {
    return STATES[state.market];
  }
  // held right-hand zone for crawls (BDF). Returns clip x1 for the crawl.
  function stateZoneBDF(sign, px) {
    var st = stateInfo();
    var m = LED.rasterize(st.label, px, "Silkscreen", null, true);
    var w = m.w * sign.scale;
    var zx = sign.physW - w - 2 * sign.scale;
    // separator: dotted column
    var sepX = zx - 3 * sign.scale;
    for (var y = 0; y < sign.physH; y += 2 * sign.scale) for (var k = 0; k < sign.scale; k++) for (var j = 0; j < sign.scale; j++) sign.px(sepX + k, y + j, C.label, 0.5);
    var pulse = state.market === "open" ? 0.55 + 0.45 * Math.sin(state.clock / 350) : 1;
    var by = Math.round((sign.physH - m.h * sign.scale) / 2);
    sign.blit(m, zx, by, st.c, sign.scale, {
      bright: 0.9 * pulse
    });
    return sepX - 2 * sign.scale;
  }
  // hi-res state chip: pulsing dot + label. Returns width.
  function stateHi(sign, x, y, px) {
    var st = stateInfo();
    var s = 3;
    var pulse = state.market === "open" ? 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(state.clock / 350)) : 1;
    for (var yy = 0; yy < s; yy++) for (var xx = 0; xx < s; xx++) sign.px(x + xx, y + Math.round(px / 2) - 1 + yy - 1, st.c, pulse);
    return s + 3 + sign.hires(st.label, x + s + 3, y, st.c, px, "700");
  }

  // ---- crawl streams -----------------------------------------------------------
  function quoteBDF(sign, f, px, t) {
    var s = sign.scale,
      tk = [];
    if (f.c1) {
      tk.push(tkChip(sign, f, Math.min(10, px) * s > 10 ? 10 : Math.round(px * 0.83 * s)));
      tk.push(sp(3 * s));
    }
    tk.push(tkText(sign, f.sym, symColor(f), px));
    tk.push(sp(4 * s));
    tk.push(tkText(sign, priceStr(f), priceColor(f, t), px));
    tk.push(sp(3 * s));
    tk.push(tkGlyph(sign, arrowGlyph(f), chgColor(f)));
    tk.push(sp(1 * s));
    tk.push(tkText(sign, pctStr(f), chgColor(f), px));
    return tk;
  }
  function streamBDF(sign, list, px, t) {
    var s = sign.scale,
      out = [];
    for (var i = 0; i < list.length; i++) {
      out = out.concat(quoteBDF(sign, list[i], px, t));
      out.push(sp(6 * s));
      out.push(tkSep(sign, px * s));
      out.push(sp(6 * s));
    }
    return out;
  }

  // ======================================================================
  //  LAYOUT VARIANTS
  // ======================================================================
  var LAYOUTS = {
    // ---- SMALLSIGN A: single-line NYSE crawl + held state zone ---------
    smallA: function (sign, ctx) {
      var clipX = stateZoneBDF(sign, 8);
      var stream = streamBDF(sign, WATCH, 12, ctx.t);
      var rowH = 12;
      var yTop = Math.round((sign.physH - rowH) / 2) - 1;
      ticker(sign, stream, yTop, ctx.t, ctx.speed, 26, 0, {
        vAlign: "top",
        x1: clipX,
        rowH: rowH
      });
    },
    // ---- SMALLSIGN B: two-row quote pages ------------------------------
    smallB: function (sign, ctx) {
      var t = ctx.t,
        px = 8;
      var idx = Math.floor(t / (3800 / ctx.speed)) % CARDS.length;
      var f = CARDS[idx];
      // top: chip + sym + price (flash), held
      var top = [];
      if (f.c1) {
        top.push(tkChip(sign, f, 7));
        top.push(sp(3));
      }
      top.push(tkText(sign, f.sym, symColor(f), px));
      top.push(sp(5));
      top.push(tkText(sign, priceStr(f), priceColor(f, t), px));
      drawRow(sign, top, 1, 0, {
        vAlign: "top"
      });
      pagingDots(sign, CARDS.length, idx, sign.physW - CARDS.length * 2 - 2, 1);
      // bottom: change + range bar + state
      var st = stateInfo();
      var bot = [tkGlyph(sign, arrowGlyph(f), chgColor(f)), sp(2), tkText(sign, chgStr(f), chgColor(f), px), sp(4), tkText(sign, pctStr(f), chgColor(f), px), sp(6)];
      var x = drawRow(sign, bot, 1, 9, {
        vAlign: "top"
      });
      drawRange(sign, x + 2, 11, 26, f, 1, null);
      var sm = LED.rasterize(st.label, px, "Silkscreen", null, true);
      var pulse = state.market === "open" ? 0.5 + 0.5 * Math.sin(t / 350) : 1;
      sign.blit(sm, sign.physW - sm.w - 1, 8, st.c, 1, {
        bright: 0.9 * pulse
      });
    },
    // ---- BIGSIGN A: held quote card with sparkline ----------------------
    bigA: function (sign, ctx) {
      var t = ctx.t;
      var idx = Math.floor(t / (5200 / ctx.speed)) % CARDS.length;
      var f = CARDS[idx];
      // chip + hero symbol
      var x = 4;
      if (f.c1) {
        drawChip(sign, x, 4, 16, f, 1, null);
        x += 20;
      }
      sign.hires(f.sym, x, 1, symColor(f), 22, "700");
      sign.hires(f.name, x, 26, C.label, 9, "700");
      // price right-aligned, flash on tick
      var ps = priceStr(f);
      var pm = sign.hiresMask(ps, 22, "700");
      sign.hires(ps, sign.physW - pm.w - 4, 1, priceColor(f, t), 22, "700");
      // change line under price
      var cs = arrowChar(f) + " " + chgStr(f) + "  " + pctStr(f);
      var cm = sign.hiresMask(cs, 11, "600");
      sign.hires(cs, sign.physW - cm.w - 4, 26, chgColor(f), 11, "600");
      // sparkline strip
      drawSpark(sign, 4, 41, 178, 19, f, t, 1, null);
      // state + paging bottom-right
      stateHi(sign, 192, 42, 9);
      pagingDots(sign, CARDS.length, idx, sign.physW - CARDS.length * 8 - 4, sign.physH - 6);
      if (state.market === "closed") sign.hires("AT CLOSE", 192, 53, C.label, 8, "600");
    },
    // ---- BIGSIGN B: dual crawl — indices top, equities bottom ----------
    bigB: function (sign, ctx) {
      var t = ctx.t,
        px = 8,
        s = sign.scale;
      var clipX = stateZoneBDF(sign, 8);
      var top = streamBDF(sign, IX, px, t);
      var bot = streamBDF(sign, EQ, px, t);
      ticker(sign, top, 0, t, ctx.speed, 34, 0, {
        vAlign: "top",
        x1: clipX,
        rowH: 8 * s
      });
      ticker(sign, bot, 8 * s + 2, t, ctx.speed, 52, 0, {
        vAlign: "top",
        x1: clipX,
        rowH: 8 * s
      });
    },
    // ---- LONGBOI A: trading dashboard -----------------------------------
    longA: function (sign, ctx) {
      var t = ctx.t;
      var idx = Math.floor(t / (5200 / ctx.speed)) % CARDS.length;
      var f = CARDS[idx];
      // hero: chip + sym + name
      var x = 6;
      if (f.c1) {
        drawChip(sign, x, 6, 20, f, 1, null);
        x += 26;
      }
      sign.hires(f.sym, x, 2, symColor(f), 26, "700");
      sign.hires(f.name, x, 32, C.label, 10, "700");
      stateHi(sign, x, 48, 9);
      // price + change block
      var px2 = 150;
      sign.hires(priceStr(f), px2, 4, priceColor(f, t), 24, "700");
      var cs = arrowChar(f) + " " + chgStr(f) + "  " + pctStr(f);
      sign.hires(cs, px2, 34, chgColor(f), 13, "600");
      sign.hires("PREV " + fmt(f.prev, f.dp), px2, 51, C.label, 8, "600");
      // sparkline center-right
      drawSpark(sign, 288, 8, 132, 48, f, t, 1, null);
      // mini watch column (next three)
      var mx = 434;
      for (var r = 0; r < 3; r++) {
        var g = CARDS[(idx + 1 + r) % CARDS.length];
        var y = 6 + r * 18;
        sign.hires(g.sym, mx, y, symColor(g), 10, "700");
        var pv = pctStr(g);
        var pvm = sign.hiresMask(pv, 10, "600");
        sign.hires(pv, sign.physW - pvm.w - 6, y, chgColor(g), 10, "600");
      }
      pagingDots(sign, CARDS.length, idx, mx, 58);
    },
    // ---- LONGBOI B: hi-res crawl with inline sparklines ------------------
    longB: function (sign, ctx) {
      var t = ctx.t,
        px = 20;
      var st = stateInfo();
      // held state zone right
      var lm = sign.hiresMask(st.label, 10, "700");
      var zoneW = lm.w + 14;
      var clipX = sign.physW - zoneW - 8;
      for (var y = 4; y < sign.physH - 4; y += 4) sign.px(clipX + 3, y, C.label, 0.5);
      stateHi(sign, clipX + 8, Math.round((sign.physH - 10) / 2), 10);
      var stream = [];
      for (var i = 0; i < WATCH.length; i++) {
        var f = WATCH[i];
        if (f.c1) {
          stream.push(tkChip(sign, f, 16));
          stream.push(sp(6));
        }
        stream.push(tkHi(sign, f.sym, symColor(f), px, "700"));
        stream.push(sp(7));
        stream.push(tkHi(sign, priceStr(f), priceColor(f, t), px, "600"));
        stream.push(sp(6));
        stream.push(tkHi(sign, arrowChar(f), chgColor(f), px - 6, "700"));
        stream.push(sp(3));
        stream.push(tkHi(sign, pctStr(f), chgColor(f), px - 4, "600"));
        stream.push(sp(8));
        stream.push(tkSpark(sign, f, 42, 22, t));
        stream.push(sp(12));
        stream.push(tkHi(sign, "\u2022", C.label, px, "700"));
        stream.push(sp(12));
      }
      var rowH = 26;
      var yTop = Math.round((sign.physH - rowH) / 2);
      ticker(sign, stream, yTop, t, ctx.speed, 58, 0, {
        vAlign: "top",
        x1: clipX,
        rowH: rowH
      });
    },
    // ---- LONGBOI C: index board -------------------------------------------
    longC: function (sign, ctx) {
      var t = ctx.t;
      var idxs = [WATCH[6], WATCH[7], WATCH[8]]; // SPX NDX DJI
      var colW = 146,
        x0 = 6;
      for (var i = 0; i < idxs.length; i++) {
        var f = idxs[i],
          cx = x0 + i * colW;
        sign.hires(f.name, cx, 2, C.label, 9, "700");
        sign.hires(priceStr(f), cx, 14, priceColor(f, t), 19, "700");
        var cs = arrowChar(f) + " " + pctStr(f);
        sign.hires(cs, cx, 37, chgColor(f), 11, "600");
        drawSpark(sign, cx, 52, colW - 24, 11, f, t, 1, null);
        if (i < idxs.length) {
          // divider
          var dx = cx + colW - 12;
          for (var y = 4; y < sign.physH - 4; y += 4) sign.px(dx, y, C.label, 0.5);
        }
      }
      // right zone: FX pair + state
      var rx = x0 + 3 * colW + 4;
      stateHi(sign, rx, 3, 9);
      for (var r = 0; r < 2; r++) {
        var g = WATCH[9 + r],
          y2 = 22 + r * 16;
        sign.hires(g.sym, rx, y2, C.fx, 8, "700");
        var v = pctStr(g);
        sign.hires(fmt(g.price, g.dp), rx, y2 + 9, priceColor(g, t), 8, "600");
        var vm = sign.hiresMask(v, 8, "600");
        sign.hires(v, sign.physW - vm.w - 4, y2 + 9, chgColor(g), 8, "600");
      }
    }
  };

  // ======================================================================
  //  BOOT + SIMULATION
  // ======================================================================
  var SIGN_DEFS = {
    smallA: {
      logW: 160,
      logH: 16,
      scale: 1
    },
    smallB: {
      logW: 160,
      logH: 16,
      scale: 1
    },
    bigA: {
      logW: 64,
      logH: 16,
      scale: 4
    },
    bigB: {
      logW: 64,
      logH: 16,
      scale: 4
    },
    longA: {
      logW: 128,
      logH: 16,
      scale: 4
    },
    longB: {
      logW: 128,
      logH: 16,
      scale: 4
    },
    longC: {
      logW: 128,
      logH: 16,
      scale: 4
    }
  };
  var state = {
    speed: 1,
    market: "open",
    glow: true,
    playing: true,
    clock: 0,
    last: 0,
    lastTick: 0
  };
  var signs = [];
  var tickR = rng(0xC0FFEE);
  function simTick() {
    var f = WATCH[Math.floor(tickR() * WATCH.length)];
    var delta = f.price * (tickR() - 0.48) * 0.0016;
    f.price = Math.max(f.price + delta, f.prev * 0.9);
    f.tickDir = delta >= 0 ? 1 : -1;
    f.flashT = state.clock;
    f.spark[f.spark.length - 1] = f.price;
    // occasionally advance the intraday walk
    if (tickR() < 0.14) {
      f.spark.shift();
      f.spark.push(f.price);
    }
  }
  function cellFor(physW) {
    return Math.max(2, Math.round(920 / physW));
  }
  function boot() {
    Object.keys(SIGN_DEFS).forEach(function (id) {
      var cv = document.getElementById("cv-" + id);
      if (!cv) return;
      var def = SIGN_DEFS[id];
      var s = new LED.Sign(cv, {
        logW: def.logW,
        logH: def.logH,
        scale: def.scale,
        cell: cellFor(def.logW * def.scale),
        glow: state.glow
      });
      signs.push({
        id: id,
        sign: s,
        draw: LAYOUTS[id]
      });
    });
    bindControls();
    state.last = performance.now();
    frame();
    setInterval(frame, 1000 / 40);
  }
  function frame() {
    var now = performance.now();
    var dt = now - state.last;
    state.last = now;
    if (dt > 250) dt = 250;
    if (state.playing) state.clock += dt;
    var st = STATES[state.market];
    if (state.playing && st.tick > 0 && state.clock - state.lastTick > st.tick / state.speed) {
      state.lastTick = state.clock;
      simTick();
    }
    for (var i = 0; i < signs.length; i++) {
      var S = signs[i];
      S.sign.glow = state.glow;
      S.sign.clear();
      S.draw(S.sign, {
        t: state.clock,
        speed: state.speed
      });
      // market-state global dimming (closed = 45%)
      if (st.dim < 1) {
        var fb = S.sign.fb;
        for (var k = 0; k < fb.length; k++) fb[k] *= st.dim;
      }
      S.sign.render();
    }
  }
  function bindControls() {
    var market = document.getElementById("ctl-market");
    var speed = document.getElementById("ctl-speed");
    var glow = document.getElementById("ctl-glow");
    var play = document.getElementById("ctl-play");
    if (market) market.addEventListener("change", function () {
      state.market = market.value;
    });
    if (speed) speed.addEventListener("input", function () {
      state.speed = +speed.value;
      var lbl = document.getElementById("ctl-speed-val");
      if (lbl) lbl.textContent = state.speed.toFixed(1) + "\u00D7";
    });
    if (glow) glow.addEventListener("change", function () {
      state.glow = glow.checked;
    });
    if (play) play.addEventListener("click", function () {
      state.playing = !state.playing;
      play.textContent = state.playing ? "\u2759\u2759 Pause" : "\u25B6 Play";
      play.setAttribute("aria-pressed", String(!state.playing));
    });
  }
  function start() {
    var fonts = [document.fonts.load("8px Silkscreen"), document.fonts.load("12px Silkscreen"), document.fonts.load("700 28px Inter"), document.fonts.load("600 14px Inter")];
    Promise.all(fonts).catch(function () {}).then(function () {
      return document.fonts.ready;
    }).then(boot);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);else start();
  window.ST = {
    state: state,
    watch: WATCH
  };
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "design_handoff_stock_ticker/stocks.js", error: String((e && e.message) || e) }); }

// led-engine.js
try { (() => {
/* LED sign engine — physical framebuffer rendered as lit dots on pure black.
   Matches the ground-truth engine renders: no visible off-grid, chunky BDF dots,
   fine hi-res dots. One physical pixel = one LED. */
(function (global) {
  "use strict";

  // ---- offscreen rasterizer (text -> alpha mask, cached) --------------------
  const rc = document.createElement("canvas");
  const rx = rc.getContext("2d", {
    willReadFrequently: true
  });
  const maskCache = new Map();
  function rasterize(text, px, family, weight, crisp) {
    const key = text + "|" + px + "|" + family + "|" + (weight || "") + "|" + (crisp ? 1 : 0);
    let m = maskCache.get(key);
    if (m) return m;
    const font = (weight ? weight + " " : "") + px + "px " + family;
    rx.font = font;
    const w = Math.max(1, Math.ceil(rx.measureText(text).width) + 2);
    const h = Math.ceil(px * 1.6);
    rc.width = w;
    rc.height = h;
    rx.font = font;
    rx.textBaseline = "top";
    rx.imageSmoothingEnabled = false;
    rx.clearRect(0, 0, w, h);
    rx.fillStyle = "#fff";
    rx.fillText(text, 0, 1);
    const data = rx.getImageData(0, 0, w, h).data;
    // trim to content bounds vertically & left
    let top = h,
      bot = -1,
      left = w,
      right = -1;
    const alpha = new Float32Array(w * h);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        let a = data[(y * w + x) * 4 + 3] / 255;
        if (crisp) a = a >= 0.5 ? 1 : 0;
        alpha[y * w + x] = a;
        if (a > 0) {
          if (y < top) top = y;
          if (y > bot) bot = y;
          if (x < left) left = x;
          if (x > right) right = x;
        }
      }
    }
    if (bot < 0) {
      top = 0;
      bot = 0;
      left = 0;
      right = 0;
    }
    // crop
    const cw = right - left + 1,
      ch = bot - top + 1;
    const cropped = new Float32Array(cw * ch);
    for (let y = 0; y < ch; y++) for (let x = 0; x < cw; x++) cropped[y * cw + x] = alpha[(y + top) * w + (x + left)];
    m = {
      w: cw,
      h: ch,
      alpha: cropped
    };
    maskCache.set(key, m);
    return m;
  }

  // ---- manual bitmap glyphs (things Silkscreen lacks) -----------------------
  function toGlyph(rows) {
    const h = rows.length,
      w = rows[0].length;
    const a = new Float32Array(w * h);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) a[y * w + x] = rows[y][x] === "#" ? 1 : 0;
    return {
      w,
      h,
      alpha: a
    };
  }
  const GLYPH = {
    up: toGlyph(["..#..", ".###.", "#####", "..#..", "..#..", "..#..", "..#.."]),
    down: toGlyph(["..#..", "..#..", "..#..", "..#..", "#####", ".###.", "..#.."]),
    level: toGlyph(["#####", "#####"]),
    deg: toGlyph(["###", "#.#", "###"]),
    dot: toGlyph(["#"]),
    plane: toGlyph(["....#....", "....#....", "...###...", "#########", "###########".slice(0, 9), "...###...", "...#.#..."])
  };

  // ---- Sign -----------------------------------------------------------------
  class Sign {
    constructor(canvas, opts) {
      this.logW = opts.logW;
      this.logH = opts.logH;
      this.scale = opts.scale; // physical px per logical dot
      this.physW = this.logW * this.scale;
      this.physH = this.logH * this.scale;
      this.cell = opts.cell; // screen px per physical dot
      this.glow = opts.glow !== false;
      canvas.width = this.physW * this.cell;
      canvas.height = this.physH * this.cell;
      canvas.style.width = "100%";
      canvas.style.aspectRatio = this.physW + " / " + this.physH;
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.fb = new Float32Array(this.physW * this.physH * 3); // rgb 0..1*bright
    }
    clear() {
      this.fb.fill(0);
    }
    // additive-max write of a physical pixel
    px(x, y, rgb, b) {
      x = x | 0;
      y = y | 0;
      if (x < 0 || y < 0 || x >= this.physW || y >= this.physH) return;
      const i = (y * this.physW + x) * 3;
      const r = rgb[0] * b,
        g = rgb[1] * b,
        bl = rgb[2] * b;
      if (r > this.fb[i]) this.fb[i] = r;
      if (g > this.fb[i + 1]) this.fb[i + 1] = g;
      if (bl > this.fb[i + 2]) this.fb[i + 2] = bl;
    }
    // blit a mask. baseX/baseY in physical px; expand = block size per mask px.
    // clip: {x0,x1} physical column clip (for scroll windows)
    blit(mask, baseX, baseY, rgb, expand, opts) {
      opts = opts || {};
      const bright = opts.bright == null ? 1 : opts.bright;
      const cx0 = opts.x0 == null ? 0 : opts.x0;
      const cx1 = opts.x1 == null ? this.physW : opts.x1;
      const cy0 = opts.y0 == null ? 0 : opts.y0;
      const cy1 = opts.y1 == null ? this.physH : opts.y1;
      baseX = Math.round(baseX);
      baseY = Math.round(baseY);
      for (let my = 0; my < mask.h; my++) {
        for (let mx = 0; mx < mask.w; mx++) {
          const a = mask.alpha[my * mask.w + mx];
          if (a <= 0) continue;
          const b = a * bright;
          for (let sy = 0; sy < expand; sy++) {
            const py = baseY + my * expand + sy;
            if (py < cy0 || py >= cy1) continue;
            for (let sx = 0; sx < expand; sx++) {
              const pxx = baseX + mx * expand + sx;
              if (pxx < cx0 || pxx >= cx1) continue;
              this.px(pxx, py, rgb, b);
            }
          }
        }
      }
    }
    // BDF text: logical coords, expanded by scale
    bdf(text, logX, logY, rgb, px, opts) {
      const m = rasterize(text, px, "Silkscreen", null, true);
      this.blit(m, logX * this.scale, logY * this.scale, rgb, this.scale, opts);
      return m.w; // logical advance
    }
    bdfWidth(text, px) {
      return rasterize(text, px, "Silkscreen", null, true).w;
    }
    // hi-res text: physical coords, 1:1
    hires(text, physX, physY, rgb, px, weight, opts) {
      const m = rasterize(text, px, "Inter", weight || "700", false);
      this.blit(m, physX, physY, rgb, 1, opts);
      return m.w;
    }
    hiresMask(text, px, weight) {
      return rasterize(text, px, "Inter", weight || "700", false);
    }
    glyph(name, logX, logY, rgb, opts) {
      const g = GLYPH[name];
      this.blit(g, logX * this.scale, logY * this.scale, rgb, this.scale, opts);
      return g.w;
    }
    // draw framebuffer as lit dots
    render() {
      const ctx = this.ctx,
        cell = this.cell;
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
      const gap = cell <= 2 ? 0 : Math.max(1, Math.round(cell * 0.16));
      const d = cell - gap;
      const rad = Math.min(d * 0.28, 3);
      // glow pass
      if (this.glow && cell >= 3) {
        ctx.globalCompositeOperation = "lighter";
        for (let y = 0; y < this.physH; y++) {
          for (let x = 0; x < this.physW; x++) {
            const i = (y * this.physW + x) * 3;
            const r = this.fb[i],
              g = this.fb[i + 1],
              b = this.fb[i + 2];
            if (r + g + b < 0.05) continue;
            ctx.fillStyle = "rgba(" + (r * 255 | 0) + "," + (g * 255 | 0) + "," + (b * 255 | 0) + ",0.18)";
            const cx = x * cell + cell / 2,
              cy = y * cell + cell / 2;
            ctx.beginPath();
            ctx.arc(cx, cy, d * 0.9, 0, 6.2832);
            ctx.fill();
          }
        }
        ctx.globalCompositeOperation = "source-over";
      }
      // solid dots
      for (let y = 0; y < this.physH; y++) {
        for (let x = 0; x < this.physW; x++) {
          const i = (y * this.physW + x) * 3;
          const r = this.fb[i],
            g = this.fb[i + 1],
            b = this.fb[i + 2];
          if (r + g + b < 0.02) continue;
          ctx.fillStyle = "rgb(" + Math.min(255, r * 255 | 0) + "," + Math.min(255, g * 255 | 0) + "," + Math.min(255, b * 255 | 0) + ")";
          const px = x * cell + gap / 2,
            py = y * cell + gap / 2;
          if (rad > 0.5) {
            roundRect(ctx, px, py, d, d, rad);
            ctx.fill();
          } else ctx.fillRect(px, py, d, d);
        }
      }
    }
  }
  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }
  global.LED = {
    Sign,
    rasterize,
    GLYPH
  };
})(window);
})(); } catch (e) { __ds_ns.__errors.push({ path: "led-engine.js", error: String((e && e.message) || e) }); }

// stocks.js
try { (() => {
/* Stock ticker LED layouts — sample market data, live tick simulation,
   market state machine, semantic layouts. Reuses led-engine.js. */
(function () {
  "use strict";

  // ---- semantic palette ------------------------------------------------------
  var C = {
    sym: [255, 255, 255],
    price: [255, 180, 0],
    up: [60, 220, 60],
    down: [255, 60, 60],
    flat: [255, 180, 0],
    idx: [0, 220, 255],
    fx: [170, 90, 255],
    label: [70, 90, 130],
    white: [255, 255, 255]
  };

  // ---- market states ---------------------------------------------------------
  var STATES = {
    pre: {
      label: "PRE",
      c: [255, 180, 0],
      dim: 0.85,
      tick: 2600
    },
    open: {
      label: "LIVE",
      c: [0, 255, 0],
      dim: 1.0,
      tick: 700
    },
    after: {
      label: "AH",
      c: [170, 90, 255],
      dim: 0.85,
      tick: 2600
    },
    closed: {
      label: "CLSD",
      c: [255, 60, 60],
      dim: 0.45,
      tick: 0
    }
  };

  // ---- watchlist (brand chips are abstract two-tone marks, NOT logos) --------
  var WATCH = [{
    sym: "AAPL",
    name: "APPLE",
    kind: "eq",
    base: 227.52,
    pct0: 0.62,
    c1: [205, 210, 220],
    c2: [125, 132, 145]
  }, {
    sym: "NVDA",
    name: "NVIDIA",
    kind: "eq",
    base: 172.40,
    pct0: 2.41,
    c1: [118, 185, 0],
    c2: [235, 250, 225]
  }, {
    sym: "MSFT",
    name: "MICROSOFT",
    kind: "eq",
    base: 468.35,
    pct0: -0.38,
    c1: [0, 120, 215],
    c2: [240, 245, 255]
  }, {
    sym: "TSLA",
    name: "TESLA",
    kind: "eq",
    base: 312.80,
    pct0: 3.05,
    c1: [232, 33, 39],
    c2: [248, 248, 248]
  }, {
    sym: "AMZN",
    name: "AMAZON",
    kind: "eq",
    base: 223.10,
    pct0: 0.18,
    c1: [255, 153, 0],
    c2: [90, 115, 145]
  }, {
    sym: "META",
    name: "META",
    kind: "eq",
    base: 731.20,
    pct0: -1.12,
    c1: [0, 129, 255],
    c2: [215, 232, 255]
  }, {
    sym: "SPX",
    name: "S&P 500",
    kind: "ix",
    base: 6412.30,
    pct0: 0.44
  }, {
    sym: "NDX",
    name: "NASDAQ 100",
    kind: "ix",
    base: 23415.75,
    pct0: 0.71
  }, {
    sym: "DJI",
    name: "DOW JONES",
    kind: "ix",
    base: 44733.20,
    pct0: -0.12
  }, {
    sym: "EUR/USD",
    name: "EURO",
    kind: "fx",
    base: 1.0864,
    pct0: 0.21,
    dp: 4
  }, {
    sym: "USD/JPY",
    name: "YEN",
    kind: "fx",
    base: 156.42,
    pct0: -0.33,
    dp: 2
  }];

  // ---- seeded rng + spark generation ----------------------------------------
  function hash(s) {
    var h = 2166136261;
    for (var i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }
  function rng(seed) {
    var a = seed;
    return function () {
      a |= 0;
      a = a + 0x6D2B79F5 | 0;
      var t = Math.imul(a ^ a >>> 15, 1 | a);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  var SPARK_N = 64;
  WATCH.forEach(function (f) {
    f.dp = f.dp != null ? f.dp : 2;
    f.prev = f.base / (1 + f.pct0 / 100);
    var r = rng(hash(f.sym));
    var open = f.prev * (1 + (r() - 0.5) * 0.006);
    var d = [open],
      v = open;
    for (var i = 1; i < SPARK_N; i++) {
      v += v * (r() - 0.5) * 0.0045;
      d.push(v);
    }
    // blend so the walk lands on the current price
    var end = d[SPARK_N - 1];
    for (i = 0; i < SPARK_N; i++) d[i] += (f.base - end) * (i / (SPARK_N - 1));
    f.spark = d;
    f.price = f.base;
    f.flashT = -1e9;
    f.tickDir = 1;
  });
  var EQ = WATCH.filter(function (f) {
    return f.kind === "eq";
  });
  var IX = WATCH.filter(function (f) {
    return f.kind !== "eq";
  });
  var CARDS = WATCH.filter(function (f) {
    return f.kind !== "fx";
  }); // rotator decks

  // ---- formatting ------------------------------------------------------------
  function fmt(v, dp) {
    return v.toLocaleString("en-US", {
      minimumFractionDigits: dp,
      maximumFractionDigits: dp
    });
  }
  function chgOf(f) {
    return f.price - f.prev;
  }
  function pctOf(f) {
    return (f.price - f.prev) / f.prev * 100;
  }
  function chgColor(f) {
    var c = chgOf(f);
    return c > 0 ? C.up : c < 0 ? C.down : C.flat;
  }
  function pctStr(f) {
    var p = pctOf(f);
    return (p >= 0 ? "+" : "") + p.toFixed(2) + "%";
  }
  function chgStr(f) {
    var c = chgOf(f);
    return (c >= 0 ? "+" : "") + fmt(Math.abs(c) < 10 ? c : c, f.kind === "fx" ? f.dp : 2).replace("-", "-");
  }
  function symColor(f) {
    return f.kind === "ix" ? C.idx : f.kind === "fx" ? C.fx : C.sym;
  }
  function priceStr(f) {
    return fmt(f.price, f.dp);
  }
  function lerp(a, b, k) {
    return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k];
  }
  // Bloomberg-style flash: price lerps to white right after a tick
  function priceColor(f, t) {
    var k = Math.max(0, 1 - (t - f.flashT) / 420);
    return k > 0 ? lerp(C.price, C.white, k * 0.95) : C.price;
  }
  function arrowGlyph(f) {
    var c = chgOf(f);
    return c > 0 ? "up" : c < 0 ? "down" : "level";
  }
  function arrowChar(f) {
    var c = chgOf(f);
    return c > 0 ? "\u25B2" : c < 0 ? "\u25BC" : "\u25AC";
  }

  // ---- clipped pixel write (custom tokens must respect scroll windows) -------
  function cpx(sign, x, y, col, b, o) {
    if (o) {
      if (o.x0 != null && x < o.x0) return;
      if (o.x1 != null && x >= o.x1) return;
      if (o.y0 != null && y < o.y0) return;
      if (o.y1 != null && y >= o.y1) return;
    }
    sign.px(x, y, col, b);
  }

  // ---- brand chip: rounded two-tone diagonal mark (trademark-safe) -----------
  function drawChip(sign, x, y, H, f, bright, o) {
    if (!f.c1) return 0;
    var W = H;
    var rd = H >= 10 ? 2 : H >= 6 ? 1 : 0;
    for (var r = 0; r < H; r++) {
      for (var c = 0; c < W; c++) {
        var ex = Math.min(c, W - 1 - c),
          ey = Math.min(r, H - 1 - r);
        if (ex + ey < rd) continue; // knock corners
        var col = c - r > 0 ? f.c2 : f.c1;
        cpx(sign, x + c, y + r, col, bright, o);
      }
    }
    return W;
  }
  function tkCustom(w, h, fn) {
    return {
      custom: fn,
      w: w,
      h: h
    };
  }
  function tkChip(sign, f, H) {
    if (!f.c1) return {
      spacer: true,
      w: 0
    };
    return tkCustom(H, H, function (s, x, yTop, o) {
      var b = o && o.bright != null ? o.bright : 1;
      var y = yTop + Math.max(0, (o && o.rowH || H) - H) / 2;
      drawChip(s, x, Math.round(y), H, f, b, o);
    });
  }

  // ---- sparkline (physical px) with prev-close reference line ----------------
  function sparkRange(f) {
    var lo = f.prev,
      hi = f.prev;
    for (var i = 0; i < f.spark.length; i++) {
      var v = f.spark[i];
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    if (hi - lo < 1e-9) hi = lo + 1;
    return [lo, hi];
  }
  function drawSpark(sign, x, y, w, h, f, t, bright, o) {
    var lohi = sparkRange(f),
      lo = lohi[0],
      span = lohi[1] - lo;
    var n = f.spark.length;
    function Y(v) {
      return y + (h - 1) - Math.round((v - lo) / span * (h - 1));
    }
    // prev-close dotted reference
    var pcY = Y(f.prev);
    for (var xx = x; xx < x + w; xx += 3) cpx(sign, xx, pcY, C.label, 0.55 * bright, o);
    var prevY = null;
    for (var i = 0; i < w; i++) {
      var v = f.spark[Math.round(i / (w - 1) * (n - 1))];
      var yy = Y(v);
      var col = v >= f.prev ? C.up : C.down;
      cpx(sign, x + i, yy, col, bright, o);
      if (prevY !== null && Math.abs(yy - prevY) > 1) {
        var s0 = Math.min(yy, prevY) + 1,
          s1 = Math.max(yy, prevY);
        for (var sy = s0; sy < s1; sy++) cpx(sign, x + i, sy, col, 0.55 * bright, o);
      }
      prevY = yy;
    }
    // live endpoint pulse
    var pulse = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(t / 260));
    cpx(sign, x + w - 1, Y(f.price), C.white, pulse * bright, o);
  }
  function tkSpark(sign, f, w, h, t) {
    return tkCustom(w, h, function (s, x, yTop, o) {
      var b = o && o.bright != null ? o.bright : 1;
      var y = yTop + Math.max(0, (o && o.rowH || h) - h) / 2;
      drawSpark(s, x, Math.round(y), w, h, f, t, b, o);
    });
  }

  // ---- day range bar ----------------------------------------------------------
  function drawRange(sign, x, y, w, f, bright, o) {
    var lohi = sparkRange(f),
      lo = lohi[0],
      span = lohi[1] - lo;
    for (var i = 0; i < w; i++) cpx(sign, x + i, y + 1, C.label, 0.4 * bright, o);
    var mx = x + Math.round((f.price - lo) / span * (w - 1));
    var col = chgColor(f);
    for (var yy = 0; yy < 3; yy++) cpx(sign, mx, y + yy, col, bright, o);
    var px2 = x + Math.round((f.prev - lo) / span * (w - 1));
    cpx(sign, px2, y + 1, C.white, 0.7 * bright, o);
  }

  // ---- token helpers (from app.js conventions) --------------------------------
  function tkText(sign, val, color, px) {
    var m = LED.rasterize(val, px, "Silkscreen", null, true);
    return {
      mask: m,
      expand: sign.scale,
      color: color,
      w: m.w * sign.scale,
      h: m.h * sign.scale
    };
  }
  function tkHi(sign, val, color, px, wt) {
    var m = sign.hiresMask(val, px, wt || "700");
    return {
      mask: m,
      expand: 1,
      color: color,
      w: m.w,
      h: m.h
    };
  }
  function tkGlyph(sign, name, color) {
    var m = LED.GLYPH[name];
    return {
      mask: m,
      expand: sign.scale,
      color: color,
      w: m.w * sign.scale,
      h: m.h * sign.scale
    };
  }
  function sp(w) {
    return {
      spacer: true,
      w: w
    };
  }
  function tkSep(sign, H, color) {
    var s = sign.scale,
      d = s;
    return tkCustom(d, H, function (sg, x, yTop, o) {
      var b = o && o.bright != null ? o.bright : 1;
      var cy = yTop + Math.round(H / 2) - Math.round(d / 2);
      for (var yy = 0; yy < d; yy++) for (var xx = 0; xx < d; xx++) cpx(sg, x + xx, cy + yy, color || C.label, 0.7 * b, o);
    });
  }
  function rowWidth(tokens) {
    var w = 0;
    for (var i = 0; i < tokens.length; i++) w += tokens[i].w;
    return w;
  }
  function drawRow(sign, tokens, x, yTop, opts) {
    opts = opts || {};
    for (var i = 0; i < tokens.length; i++) {
      var t = tokens[i];
      if (t.custom) t.custom(sign, x, yTop, opts);else if (!t.spacer) {
        var yy = yTop;
        if (opts.vAlign !== "top") yy = yTop + Math.max(0, (opts.rowH || t.h) - t.h);
        sign.blit(t.mask, x, yy, t.color, t.expand, {
          bright: opts.bright == null ? 1 : opts.bright,
          x0: opts.x0,
          x1: opts.x1,
          y0: opts.y0,
          y1: opts.y1
        });
      }
      x += t.w;
    }
    return x;
  }
  function ticker(sign, tokens, yTop, t, speed, pxPerSec, gapBetween, rowOpts) {
    var content = rowWidth(tokens);
    var period = content + gapBetween;
    if (period <= 0) return;
    var off = t / 1000 * pxPerSec * speed % period;
    var xEnd = rowOpts && rowOpts.x1 != null ? rowOpts.x1 : sign.physW;
    var x = xEnd - off;
    var guard = 0;
    while (x < xEnd && guard < 8) {
      if (x + content > 0) drawRow(sign, tokens, x, yTop, rowOpts);
      x += period;
      guard++;
    }
  }
  function pagingDots(sign, n, cur, physX, physY) {
    var s = sign.scale,
      step = 2 * s;
    for (var i = 0; i < n; i++) {
      sign.blit(LED.GLYPH.dot, physX + i * step, physY, i === cur ? C.sym : C.label, s, {});
    }
  }

  // ---- market-state chips ------------------------------------------------------
  function stateInfo() {
    return STATES[state.market];
  }
  // held right-hand zone for crawls (BDF). Returns clip x1 for the crawl.
  function stateZoneBDF(sign, px) {
    var st = stateInfo();
    var m = LED.rasterize(st.label, px, "Silkscreen", null, true);
    var w = m.w * sign.scale;
    var zx = sign.physW - w - 2 * sign.scale;
    // separator: dotted column
    var sepX = zx - 3 * sign.scale;
    for (var y = 0; y < sign.physH; y += 2 * sign.scale) for (var k = 0; k < sign.scale; k++) for (var j = 0; j < sign.scale; j++) sign.px(sepX + k, y + j, C.label, 0.5);
    var pulse = state.market === "open" ? 0.55 + 0.45 * Math.sin(state.clock / 350) : 1;
    var by = Math.round((sign.physH - m.h * sign.scale) / 2);
    sign.blit(m, zx, by, st.c, sign.scale, {
      bright: 0.9 * pulse
    });
    return sepX - 2 * sign.scale;
  }
  // hi-res state chip: pulsing dot + label. Returns width.
  function stateHi(sign, x, y, px) {
    var st = stateInfo();
    var s = 3;
    var pulse = state.market === "open" ? 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(state.clock / 350)) : 1;
    for (var yy = 0; yy < s; yy++) for (var xx = 0; xx < s; xx++) sign.px(x + xx, y + Math.round(px / 2) - 1 + yy - 1, st.c, pulse);
    return s + 3 + sign.hires(st.label, x + s + 3, y, st.c, px, "700");
  }

  // ---- crawl streams -----------------------------------------------------------
  function quoteBDF(sign, f, px, t) {
    var s = sign.scale,
      tk = [];
    if (f.c1) {
      tk.push(tkChip(sign, f, Math.min(10, px) * s > 10 ? 10 : Math.round(px * 0.83 * s)));
      tk.push(sp(3 * s));
    }
    tk.push(tkText(sign, f.sym, symColor(f), px));
    tk.push(sp(4 * s));
    tk.push(tkText(sign, priceStr(f), priceColor(f, t), px));
    tk.push(sp(3 * s));
    tk.push(tkGlyph(sign, arrowGlyph(f), chgColor(f)));
    tk.push(sp(1 * s));
    tk.push(tkText(sign, pctStr(f), chgColor(f), px));
    return tk;
  }
  function streamBDF(sign, list, px, t) {
    var s = sign.scale,
      out = [];
    for (var i = 0; i < list.length; i++) {
      out = out.concat(quoteBDF(sign, list[i], px, t));
      out.push(sp(6 * s));
      out.push(tkSep(sign, px * s));
      out.push(sp(6 * s));
    }
    return out;
  }

  // ======================================================================
  //  LAYOUT VARIANTS
  // ======================================================================
  var LAYOUTS = {
    // ---- SMALLSIGN A: single-line NYSE crawl + held state zone ---------
    smallA: function (sign, ctx) {
      var clipX = stateZoneBDF(sign, 8);
      var stream = streamBDF(sign, WATCH, 12, ctx.t);
      var rowH = 12;
      var yTop = Math.round((sign.physH - rowH) / 2) - 1;
      ticker(sign, stream, yTop, ctx.t, ctx.speed, 26, 0, {
        vAlign: "top",
        x1: clipX,
        rowH: rowH
      });
    },
    // ---- SMALLSIGN B: two-row quote pages ------------------------------
    smallB: function (sign, ctx) {
      var t = ctx.t,
        px = 8;
      var idx = Math.floor(t / (3800 / ctx.speed)) % CARDS.length;
      var f = CARDS[idx];
      // top: chip + sym + price (flash), held
      var top = [];
      if (f.c1) {
        top.push(tkChip(sign, f, 7));
        top.push(sp(3));
      }
      top.push(tkText(sign, f.sym, symColor(f), px));
      top.push(sp(5));
      top.push(tkText(sign, priceStr(f), priceColor(f, t), px));
      drawRow(sign, top, 1, 0, {
        vAlign: "top"
      });
      pagingDots(sign, CARDS.length, idx, sign.physW - CARDS.length * 2 - 2, 1);
      // bottom: change + range bar + state
      var st = stateInfo();
      var bot = [tkGlyph(sign, arrowGlyph(f), chgColor(f)), sp(2), tkText(sign, chgStr(f), chgColor(f), px), sp(4), tkText(sign, pctStr(f), chgColor(f), px), sp(6)];
      var x = drawRow(sign, bot, 1, 9, {
        vAlign: "top"
      });
      drawRange(sign, x + 2, 11, 26, f, 1, null);
      var sm = LED.rasterize(st.label, px, "Silkscreen", null, true);
      var pulse = state.market === "open" ? 0.5 + 0.5 * Math.sin(t / 350) : 1;
      sign.blit(sm, sign.physW - sm.w - 1, 8, st.c, 1, {
        bright: 0.9 * pulse
      });
    },
    // ---- BIGSIGN A: held quote card with sparkline ----------------------
    bigA: function (sign, ctx) {
      var t = ctx.t;
      var idx = Math.floor(t / (5200 / ctx.speed)) % CARDS.length;
      var f = CARDS[idx];
      // chip + hero symbol
      var x = 4;
      if (f.c1) {
        drawChip(sign, x, 4, 16, f, 1, null);
        x += 20;
      }
      sign.hires(f.sym, x, 1, symColor(f), 22, "700");
      sign.hires(f.name, x, 26, C.label, 9, "700");
      // price right-aligned, flash on tick
      var ps = priceStr(f);
      var pm = sign.hiresMask(ps, 22, "700");
      sign.hires(ps, sign.physW - pm.w - 4, 1, priceColor(f, t), 22, "700");
      // change line under price
      var cs = arrowChar(f) + " " + chgStr(f) + "  " + pctStr(f);
      var cm = sign.hiresMask(cs, 11, "600");
      sign.hires(cs, sign.physW - cm.w - 4, 26, chgColor(f), 11, "600");
      // sparkline strip
      drawSpark(sign, 4, 41, 178, 19, f, t, 1, null);
      // state + paging bottom-right
      stateHi(sign, 192, 42, 9);
      pagingDots(sign, CARDS.length, idx, sign.physW - CARDS.length * 8 - 4, sign.physH - 6);
      if (state.market === "closed") sign.hires("AT CLOSE", 192, 53, C.label, 8, "600");
    },
    // ---- BIGSIGN B: dual crawl — indices top, equities bottom ----------
    bigB: function (sign, ctx) {
      var t = ctx.t,
        px = 8,
        s = sign.scale;
      var clipX = stateZoneBDF(sign, 8);
      var top = streamBDF(sign, IX, px, t);
      var bot = streamBDF(sign, EQ, px, t);
      ticker(sign, top, 0, t, ctx.speed, 34, 0, {
        vAlign: "top",
        x1: clipX,
        rowH: 8 * s
      });
      ticker(sign, bot, 8 * s + 2, t, ctx.speed, 52, 0, {
        vAlign: "top",
        x1: clipX,
        rowH: 8 * s
      });
    },
    // ---- LONGBOI A: trading dashboard -----------------------------------
    longA: function (sign, ctx) {
      var t = ctx.t;
      var idx = Math.floor(t / (5200 / ctx.speed)) % CARDS.length;
      var f = CARDS[idx];
      // hero: chip + sym + name
      var x = 6;
      if (f.c1) {
        drawChip(sign, x, 6, 20, f, 1, null);
        x += 26;
      }
      sign.hires(f.sym, x, 2, symColor(f), 26, "700");
      sign.hires(f.name, x, 32, C.label, 10, "700");
      stateHi(sign, x, 48, 9);
      // price + change block
      var px2 = 150;
      sign.hires(priceStr(f), px2, 4, priceColor(f, t), 24, "700");
      var cs = arrowChar(f) + " " + chgStr(f) + "  " + pctStr(f);
      sign.hires(cs, px2, 34, chgColor(f), 13, "600");
      sign.hires("PREV " + fmt(f.prev, f.dp), px2, 51, C.label, 8, "600");
      // sparkline center-right
      drawSpark(sign, 288, 8, 132, 48, f, t, 1, null);
      // mini watch column (next three)
      var mx = 434;
      for (var r = 0; r < 3; r++) {
        var g = CARDS[(idx + 1 + r) % CARDS.length];
        var y = 6 + r * 18;
        sign.hires(g.sym, mx, y, symColor(g), 10, "700");
        var pv = pctStr(g);
        var pvm = sign.hiresMask(pv, 10, "600");
        sign.hires(pv, sign.physW - pvm.w - 6, y, chgColor(g), 10, "600");
      }
      pagingDots(sign, CARDS.length, idx, mx, 58);
    },
    // ---- LONGBOI B: hi-res crawl with inline sparklines ------------------
    longB: function (sign, ctx) {
      var t = ctx.t,
        px = 20;
      var st = stateInfo();
      // held state zone right
      var lm = sign.hiresMask(st.label, 10, "700");
      var zoneW = lm.w + 14;
      var clipX = sign.physW - zoneW - 8;
      for (var y = 4; y < sign.physH - 4; y += 4) sign.px(clipX + 3, y, C.label, 0.5);
      stateHi(sign, clipX + 8, Math.round((sign.physH - 10) / 2), 10);
      var stream = [];
      for (var i = 0; i < WATCH.length; i++) {
        var f = WATCH[i];
        if (f.c1) {
          stream.push(tkChip(sign, f, 16));
          stream.push(sp(6));
        }
        stream.push(tkHi(sign, f.sym, symColor(f), px, "700"));
        stream.push(sp(7));
        stream.push(tkHi(sign, priceStr(f), priceColor(f, t), px, "600"));
        stream.push(sp(6));
        stream.push(tkHi(sign, arrowChar(f), chgColor(f), px - 6, "700"));
        stream.push(sp(3));
        stream.push(tkHi(sign, pctStr(f), chgColor(f), px - 4, "600"));
        stream.push(sp(8));
        stream.push(tkSpark(sign, f, 42, 22, t));
        stream.push(sp(12));
        stream.push(tkHi(sign, "\u2022", C.label, px, "700"));
        stream.push(sp(12));
      }
      var rowH = 26;
      var yTop = Math.round((sign.physH - rowH) / 2);
      ticker(sign, stream, yTop, t, ctx.speed, 58, 0, {
        vAlign: "top",
        x1: clipX,
        rowH: rowH
      });
    },
    // ---- LONGBOI C: index board -------------------------------------------
    longC: function (sign, ctx) {
      var t = ctx.t;
      var idxs = [WATCH[6], WATCH[7], WATCH[8]]; // SPX NDX DJI
      var colW = 146,
        x0 = 6;
      for (var i = 0; i < idxs.length; i++) {
        var f = idxs[i],
          cx = x0 + i * colW;
        sign.hires(f.name, cx, 2, C.label, 9, "700");
        sign.hires(priceStr(f), cx, 14, priceColor(f, t), 19, "700");
        var cs = arrowChar(f) + " " + pctStr(f);
        sign.hires(cs, cx, 37, chgColor(f), 11, "600");
        drawSpark(sign, cx, 52, colW - 24, 11, f, t, 1, null);
        if (i < idxs.length) {
          // divider
          var dx = cx + colW - 12;
          for (var y = 4; y < sign.physH - 4; y += 4) sign.px(dx, y, C.label, 0.5);
        }
      }
      // right zone: FX pair + state
      var rx = x0 + 3 * colW + 4;
      stateHi(sign, rx, 3, 9);
      for (var r = 0; r < 2; r++) {
        var g = WATCH[9 + r],
          y2 = 22 + r * 16;
        sign.hires(g.sym, rx, y2, C.fx, 8, "700");
        var v = pctStr(g);
        sign.hires(fmt(g.price, g.dp), rx, y2 + 9, priceColor(g, t), 8, "600");
        var vm = sign.hiresMask(v, 8, "600");
        sign.hires(v, sign.physW - vm.w - 4, y2 + 9, chgColor(g), 8, "600");
      }
    }
  };

  // ======================================================================
  //  BOOT + SIMULATION
  // ======================================================================
  var SIGN_DEFS = {
    smallA: {
      logW: 160,
      logH: 16,
      scale: 1
    },
    smallB: {
      logW: 160,
      logH: 16,
      scale: 1
    },
    bigA: {
      logW: 64,
      logH: 16,
      scale: 4
    },
    bigB: {
      logW: 64,
      logH: 16,
      scale: 4
    },
    longA: {
      logW: 128,
      logH: 16,
      scale: 4
    },
    longB: {
      logW: 128,
      logH: 16,
      scale: 4
    },
    longC: {
      logW: 128,
      logH: 16,
      scale: 4
    }
  };
  var state = {
    speed: 1,
    market: "open",
    glow: true,
    playing: true,
    clock: 0,
    last: 0,
    lastTick: 0
  };
  var signs = [];
  var tickR = rng(0xC0FFEE);
  function simTick() {
    var f = WATCH[Math.floor(tickR() * WATCH.length)];
    var delta = f.price * (tickR() - 0.48) * 0.0016;
    f.price = Math.max(f.price + delta, f.prev * 0.9);
    f.tickDir = delta >= 0 ? 1 : -1;
    f.flashT = state.clock;
    f.spark[f.spark.length - 1] = f.price;
    // occasionally advance the intraday walk
    if (tickR() < 0.14) {
      f.spark.shift();
      f.spark.push(f.price);
    }
  }
  function cellFor(physW) {
    return Math.max(2, Math.round(920 / physW));
  }
  function boot() {
    Object.keys(SIGN_DEFS).forEach(function (id) {
      var cv = document.getElementById("cv-" + id);
      if (!cv) return;
      var def = SIGN_DEFS[id];
      var s = new LED.Sign(cv, {
        logW: def.logW,
        logH: def.logH,
        scale: def.scale,
        cell: cellFor(def.logW * def.scale),
        glow: state.glow
      });
      signs.push({
        id: id,
        sign: s,
        draw: LAYOUTS[id]
      });
    });
    bindControls();
    state.last = performance.now();
    frame();
    setInterval(frame, 1000 / 40);
  }
  function frame() {
    var now = performance.now();
    var dt = now - state.last;
    state.last = now;
    if (dt > 250) dt = 250;
    if (state.playing) state.clock += dt;
    var st = STATES[state.market];
    if (state.playing && st.tick > 0 && state.clock - state.lastTick > st.tick / state.speed) {
      state.lastTick = state.clock;
      simTick();
    }
    for (var i = 0; i < signs.length; i++) {
      var S = signs[i];
      S.sign.glow = state.glow;
      S.sign.clear();
      S.draw(S.sign, {
        t: state.clock,
        speed: state.speed
      });
      // market-state global dimming (closed = 45%)
      if (st.dim < 1) {
        var fb = S.sign.fb;
        for (var k = 0; k < fb.length; k++) fb[k] *= st.dim;
      }
      S.sign.render();
    }
  }
  function bindControls() {
    var market = document.getElementById("ctl-market");
    var speed = document.getElementById("ctl-speed");
    var glow = document.getElementById("ctl-glow");
    var play = document.getElementById("ctl-play");
    if (market) market.addEventListener("change", function () {
      state.market = market.value;
    });
    if (speed) speed.addEventListener("input", function () {
      state.speed = +speed.value;
      var lbl = document.getElementById("ctl-speed-val");
      if (lbl) lbl.textContent = state.speed.toFixed(1) + "\u00D7";
    });
    if (glow) glow.addEventListener("change", function () {
      state.glow = glow.checked;
    });
    if (play) play.addEventListener("click", function () {
      state.playing = !state.playing;
      play.textContent = state.playing ? "\u2759\u2759 Pause" : "\u25B6 Play";
      play.setAttribute("aria-pressed", String(!state.playing));
    });
  }
  function start() {
    var fonts = [document.fonts.load("8px Silkscreen"), document.fonts.load("12px Silkscreen"), document.fonts.load("700 28px Inter"), document.fonts.load("600 14px Inter")];
    Promise.all(fonts).catch(function () {}).then(function () {
      return document.fonts.ready;
    }).then(boot);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);else start();
  window.ST = {
    state: state,
    watch: WATCH
  };
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "stocks.js", error: String((e && e.message) || e) }); }

})();
