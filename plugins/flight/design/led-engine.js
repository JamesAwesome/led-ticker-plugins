/* LED sign engine — physical framebuffer rendered as lit dots on pure black.
   Matches the ground-truth engine renders: no visible off-grid, chunky BDF dots,
   fine hi-res dots. One physical pixel = one LED. */
(function (global) {
  "use strict";

  // ---- offscreen rasterizer (text -> alpha mask, cached) --------------------
  const rc = document.createElement("canvas");
  const rx = rc.getContext("2d", { willReadFrequently: true });
  const maskCache = new Map();

  function rasterize(text, px, family, weight, crisp) {
    const key = text + "|" + px + "|" + family + "|" + (weight || "") + "|" + (crisp ? 1 : 0);
    let m = maskCache.get(key);
    if (m) return m;
    const font = (weight ? weight + " " : "") + px + "px " + family;
    rx.font = font;
    const w = Math.max(1, Math.ceil(rx.measureText(text).width) + 2);
    const h = Math.ceil(px * 1.6);
    rc.width = w; rc.height = h;
    rx.font = font;
    rx.textBaseline = "top";
    rx.imageSmoothingEnabled = false;
    rx.clearRect(0, 0, w, h);
    rx.fillStyle = "#fff";
    rx.fillText(text, 0, 1);
    const data = rx.getImageData(0, 0, w, h).data;
    // trim to content bounds vertically & left
    let top = h, bot = -1, left = w, right = -1;
    const alpha = new Float32Array(w * h);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        let a = data[(y * w + x) * 4 + 3] / 255;
        if (crisp) a = a >= 0.5 ? 1 : 0;
        alpha[y * w + x] = a;
        if (a > 0) {
          if (y < top) top = y; if (y > bot) bot = y;
          if (x < left) left = x; if (x > right) right = x;
        }
      }
    }
    if (bot < 0) { top = 0; bot = 0; left = 0; right = 0; }
    // crop
    const cw = right - left + 1, ch = bot - top + 1;
    const cropped = new Float32Array(cw * ch);
    for (let y = 0; y < ch; y++)
      for (let x = 0; x < cw; x++)
        cropped[y * cw + x] = alpha[(y + top) * w + (x + left)];
    m = { w: cw, h: ch, alpha: cropped };
    maskCache.set(key, m);
    return m;
  }

  // ---- manual bitmap glyphs (things Silkscreen lacks) -----------------------
  function toGlyph(rows) {
    const h = rows.length, w = rows[0].length;
    const a = new Float32Array(w * h);
    for (let y = 0; y < h; y++)
      for (let x = 0; x < w; x++)
        a[y * w + x] = rows[y][x] === "#" ? 1 : 0;
    return { w, h, alpha: a };
  }
  const GLYPH = {
    up: toGlyph(["..#..", ".###.", "#####", "..#..", "..#..", "..#..", "..#.."]),
    down: toGlyph(["..#..", "..#..", "..#..", "..#..", "#####", ".###.", "..#.."]),
    level: toGlyph(["#####", "#####"]),
    deg: toGlyph(["###", "#.#", "###"]),
    dot: toGlyph(["#"]),
    plane: toGlyph([
      "....#....",
      "....#....",
      "...###...",
      "#########",
      "###########".slice(0, 9),
      "...###...",
      "...#.#...",
    ]),
  };

  // ---- Sign -----------------------------------------------------------------
  class Sign {
    constructor(canvas, opts) {
      this.logW = opts.logW; this.logH = opts.logH;
      this.scale = opts.scale;                 // physical px per logical dot
      this.physW = this.logW * this.scale;
      this.physH = this.logH * this.scale;
      this.cell = opts.cell;                   // screen px per physical dot
      this.glow = opts.glow !== false;
      canvas.width = this.physW * this.cell;
      canvas.height = this.physH * this.cell;
      canvas.style.width = "100%";
      canvas.style.aspectRatio = this.physW + " / " + this.physH;
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.fb = new Float32Array(this.physW * this.physH * 3); // rgb 0..1*bright
    }
    clear() { this.fb.fill(0); }
    // additive-max write of a physical pixel
    px(x, y, rgb, b) {
      x = x | 0; y = y | 0;
      if (x < 0 || y < 0 || x >= this.physW || y >= this.physH) return;
      const i = (y * this.physW + x) * 3;
      const r = rgb[0] * b, g = rgb[1] * b, bl = rgb[2] * b;
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
      baseX = Math.round(baseX); baseY = Math.round(baseY);
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
    bdfWidth(text, px) { return rasterize(text, px, "Silkscreen", null, true).w; }
    // hi-res text: physical coords, 1:1
    hires(text, physX, physY, rgb, px, weight, opts) {
      const m = rasterize(text, px, "Inter", weight || "700", false);
      this.blit(m, physX, physY, rgb, 1, opts);
      return m.w;
    }
    hiresMask(text, px, weight) { return rasterize(text, px, "Inter", weight || "700", false); }
    glyph(name, logX, logY, rgb, opts) {
      const g = GLYPH[name];
      this.blit(g, logX * this.scale, logY * this.scale, rgb, this.scale, opts);
      return g.w;
    }
    // draw framebuffer as lit dots
    render() {
      const ctx = this.ctx, cell = this.cell;
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
            const r = this.fb[i], g = this.fb[i + 1], b = this.fb[i + 2];
            if (r + g + b < 0.05) continue;
            ctx.fillStyle = "rgba(" + (r * 255 | 0) + "," + (g * 255 | 0) + "," + (b * 255 | 0) + ",0.18)";
            const cx = x * cell + cell / 2, cy = y * cell + cell / 2;
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
          const r = this.fb[i], g = this.fb[i + 1], b = this.fb[i + 2];
          if (r + g + b < 0.02) continue;
          ctx.fillStyle = "rgb(" + Math.min(255, r * 255 | 0) + "," + Math.min(255, g * 255 | 0) + "," + Math.min(255, b * 255 | 0) + ")";
          const px = x * cell + gap / 2, py = y * cell + gap / 2;
          if (rad > 0.5) { roundRect(ctx, px, py, d, d, rad); ctx.fill(); }
          else ctx.fillRect(px, py, d, d);
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

  global.LED = { Sign, rasterize, GLYPH };
})(window);
