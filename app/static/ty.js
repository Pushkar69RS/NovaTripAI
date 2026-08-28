/* Travel Yantra — the pages' behaviour. Vanilla JS, no build step.
   Data arrives through #page-data. Every number drawn here was computed by
   the API; this file only formats and draws. */
(function () {
  'use strict';

  var DATA = {};
  try { DATA = JSON.parse(document.getElementById('page-data').textContent || '{}') || {}; } catch (e) { DATA = {}; }
  var PAGE = document.body.dataset.page || '';

  // ------------------------------------------------------------------ helpers
  var CITY_KN = DATA.city_kn || {Mysuru: 'ಮೈಸೂರು', Hampi: 'ಹಂಪಿ', Bengaluru: 'ಬೆಂಗಳೂರು', Chikmagalur: 'ಚಿಕ್ಕಮಗಳೂರು', Coorg: 'ಕೊಡಗು'};
  var KN_DIGITS = '೦೧೨೩೪೫೬೭೮೯';
  var LABEL_SKIP = {hotel: 1, sri: 1, the: 1, of: 1, and: 1, st: 1, 'st.': 1, hills: 1, hill: 1};
  var LANG_TAG = {en: 'en-IN', kn: 'kn-IN', hi: 'hi-IN'};

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function h(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]; }); }
  function inr(n) { return '₹' + Math.round(Number(n) || 0).toLocaleString('en-IN'); }
  function hm(t) { return String(t || '').slice(0, 5); }
  function clock12(t) { var p = hm(t).split(':'); var H = +p[0] || 0; return (H % 12 || 12) + ':' + (p[1] || '00') + ' ' + (H >= 12 ? 'pm' : 'am'); }
  function hour12(t) { var p = hm(t).split(':'); var H = +p[0] || 0; return (H % 12 || 12) + (p[1] && p[1] !== '00' ? ':' + p[1] : '') + ' ' + (H >= 12 ? 'pm' : 'am'); }
  function dur(m) { m = Math.round(+m || 0); if (m < 60) return m + ' min'; var H = Math.floor(m / 60), R = m % 60; return R ? H + ' h ' + (R < 10 ? '0' + R : R) : H + ' h'; }
  function knNum(n) { return String(n).replace(/\d/g, function (d) { return KN_DIGITS[+d]; }); }
  function dateLong(iso) { return new Date(iso + 'T00:00:00').toLocaleDateString('en-GB', {weekday: 'long', day: 'numeric', month: 'long'}); }
  function cap(s) { s = String(s || ''); return s.charAt(0).toUpperCase() + s.slice(1); }
  function shortName(name) { var s = String(name || '').split('(')[0].split(',')[0].trim(); return s || String(name || ''); }
  function pinLabel(name) {
    var words = shortName(name).split(/\s+/);
    var pick = words.filter(function (w) { return !LABEL_SKIP[w.toLowerCase()] && w.length <= 11; })[0] || words[0] || '';
    return pick.toUpperCase().replace(/[^A-Z0-9'\-]/g, '');
  }
  function plural(n, w, ws) { return n + ' ' + (n === 1 ? w : (ws || w + 's')); }
  function dateShort(iso) { var d = new Date(iso + 'T00:00:00'); return isNaN(d) ? iso : d.toLocaleDateString('en-GB', {weekday: 'short', day: 'numeric', month: 'short'}); }
  // "2 adults (one over 60), 1 child" from travellers; "N people" for a trip stored before them.
  function partyText(req) {
    var t = req.travellers || [];
    if (!t.length) return (req.party_size || 1) + ' people';
    var adults = t.filter(function (x) { return x.kind === 'adult'; }), kids = t.filter(function (x) { return x.kind === 'child'; });
    var elders = adults.filter(function (x) { return x.age_band === '60+'; }).length;
    var s = plural(adults.length, 'adult') + (elders ? ' (' + (elders === 1 ? 'one' : elders) + ' over 60)' : '');
    return kids.length ? s + ', ' + plural(kids.length, 'child', 'children') : s;
  }
  function listJoin(xs) { xs = xs.map(String); return xs.length < 2 ? xs.join('') : xs.slice(0, -1).join(', ') + ' and ' + xs[xs.length - 1]; }
  function round1(x) { return Math.round(x * 10) / 10; }
  function fmt(n) { return Math.round(n * 10) / 10; }
  function stopsOf(day) { return (day.items || []).filter(function (it) { return it.kind === 'stop'; }); }
  function transferOf(day) { var f = (day.items || [])[0]; return f && f.kind === 'move' ? f : null; }
  function localMoves(day) { var t = transferOf(day); return (day.items || []).filter(function (it) { return it.kind === 'move' && it !== t; }); }
  // Day.route_km is measured exactly like Day.naive_km; plans stored before it
  // existed fall back to the hops, rounded to match.
  function routedKm(day) { return day.route_km != null && day.naive_order && day.naive_order.length ? day.route_km : round1(localMoves(day).reduce(function (a, m) { return a + (+m.km || 0); }, 0)); }
  function listedKm(day) { return day.route_km != null && day.naive_order && day.naive_order.length ? day.naive_km : round1(day.naive_km || 0); }
  function api(method, url, body) {
    return fetch(url, {method: method, headers: body ? {'Content-Type': 'application/json'} : {}, body: body ? JSON.stringify(body) : undefined})
      .then(function (r) {
        if (r.status === 204) return null;
        return r.json().catch(function () { return {}; }).then(function (j) {
          if (!r.ok) throw new Error((j && (typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail))) || r.statusText);
          return j;
        });
      });
  }
  function el(html) { var t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstChild; }

  // --------------------------------------------------------------------- maps
  var CONTOURS = '<g class="mapcontour"><path d="M14 244q84-42 156-22t216-42"/><path d="M14 210q92-40 166-18t206-44"/><path d="M14 176q90-34 164-14t208-40"/><path d="M14 142q88-30 160-10t212-38"/></g>';
  // Karnataka's outline, from the mockup. The projection is the one the mockup's
  // own city dots were placed with (fitted from Hampi, Bengaluru, Mysuru, Belur, Coorg).
  var LAND = 'M40 100 L60 70 L105 55 L150 45 L200 20 L232 8 L240 40 L222 70 L235 120 L218 150 L226 185 L250 215 L262 255 L278 300 L262 318 L235 330 L215 362 L196 384 L178 368 L160 350 L132 352 L100 340 L66 318 L44 270 L26 215 L20 175 L30 135 Z';
  function kxy(lat, lng) { return [163 + (lng - 76.46) * 63, 182 + (15.335 - lat) * 55.4]; }

  // Equirectangular: longitude scaled by cos(latitude), the bounding box
  // fitted into the frame with padding, aspect preserved, centred.
  function projector(points, W, H, pad) {
    var lats = points.map(function (p) { return p[0]; }), lngs = points.map(function (p) { return p[1]; });
    var minLat = Math.min.apply(null, lats), maxLat = Math.max.apply(null, lats);
    var minLng = Math.min.apply(null, lngs), maxLng = Math.max.apply(null, lngs);
    var k = Math.cos((minLat + maxLat) / 2 * Math.PI / 180);
    var dx = (maxLng - minLng) * k, dy = maxLat - minLat;
    var s = Math.min(dx > 1e-9 ? (W - 2 * pad) / dx : Infinity, dy > 1e-9 ? (H - 2 * pad) / dy : Infinity);
    if (!isFinite(s)) s = 1;
    var cx = (minLng + maxLng) / 2 * k, cy = (minLat + maxLat) / 2;
    return function (lat, lng) { return [W / 2 + (lng * k - cx) * s, H / 2 - (lat - cy) * s]; };
  }
  // Where the segment from (x1,y1) towards (x2,y2) leaves the rect [l,t,r,b].
  function exitPoint(x1, y1, x2, y2, rect) {
    var l = rect[0], t = rect[1], r = rect[2], b = rect[3];
    if (x2 >= l && x2 <= r && y2 >= t && y2 <= b) return [x2, y2];
    var dx = x2 - x1, dy = y2 - y1, best = 1;
    [[l, 'x'], [r, 'x'], [t, 'y'], [b, 'y']].forEach(function (edge) {
      var tt = edge[1] === 'x' ? (dx ? (edge[0] - x1) / dx : Infinity) : (dy ? (edge[0] - y1) / dy : Infinity);
      if (tt > 0 && tt < best) {
        var px = x1 + dx * tt, py = y1 + dy * tt;
        if (px >= l - 0.01 && px <= r + 0.01 && py >= t - 0.01 && py <= b + 0.01) best = tt;
      }
    });
    return [x1 + dx * best, y1 + dy * best];
  }
  // Pins closer than minDist are nudged apart so numbers stay legible; a
  // stop 400 m from the next one moves a few pixels, not to another street.
  function spread(pts, minDist) {
    var out = pts.map(function (p) { return [p[0], p[1]]; });
    for (var it = 0; it < 30; it++) {
      var moved = false;
      for (var i = 0; i < out.length; i++) {
        for (var j = i + 1; j < out.length; j++) {
          var dx = out[j][0] - out[i][0], dy = out[j][1] - out[i][1], d = Math.sqrt(dx * dx + dy * dy);
          if (d >= minDist) continue;
          var ux = d < 0.01 ? 1 : dx / d, uy = d < 0.01 ? 0 : dy / d, push = (minDist - d) / 2;
          out[i][0] -= ux * push; out[i][1] -= uy * push; out[j][0] += ux * push; out[j][1] += uy * push; moved = true;
        }
      }
      if (!moved) break;
    }
    return out;
  }
  function dayMapSvg(day, opts) {
    opts = opts || {};
    var W = 400, H = opts.height || 300, pad = 46;
    var stops = stopsOf(day);
    var out = ['<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + h('Day ' + day.index + ' on the map, stops in visit order') + '">', CONTOURS];
    if (!stops.length) { out.push('<text x="200" y="' + (H / 2) + '" class="dotlabel">NO STOPS THIS DAY</text></svg>'); return out.join(''); }
    var proj = projector(stops.map(function (s) { return [s.lat, s.lng]; }), W, H, pad);
    var pts = spread(stops.map(function (s) { return proj(s.lat, s.lng); }), 30);
    var labelAbove = {};
    stops.map(function (_, i) { return i; }).sort(function (a, b) { return pts[a][0] - pts[b][0]; })
      .forEach(function (idx, k) { labelAbove[idx] = k % 2 === 1; });
    var byId = {}; stops.forEach(function (s, i) { byId[s.poi_id] = pts[i]; });
    var listed = (day.naive_order || []).map(function (id) { return byId[id]; }).filter(Boolean);
    var transfer = transferOf(day);
    if (transfer && opts.origin) {
      var o = proj(opts.origin[0], opts.origin[1]);
      var e = exitPoint(pts[0][0], pts[0][1], o[0], o[1], [8, 8, W - 8, H - 8]);
      out.push('<line class="transfer" x1="' + fmt(pts[0][0]) + '" y1="' + fmt(pts[0][1]) + '" x2="' + fmt(e[0]) + '" y2="' + fmt(e[1]) + '"/>');
      var mx = (pts[0][0] + e[0]) / 2, my = (pts[0][1] + e[1]) / 2;
      out.push('<text class="dotlabel" x="' + fmt(mx) + '" y="' + fmt(my - 6) + '">' + h(('from ' + transfer.from_name + ' · ' + transfer.mode + ' · ' + dur(transfer.minutes)).toUpperCase()) + '</text>');
    }
    var mode = opts.mode || 'routed';
    var pl = function (ps) { return ps.map(function (p) { return fmt(p[0]) + ',' + fmt(p[1]); }).join(' '); };
    out.push('<polyline class="route route--before" data-route="listed" points="' + pl(listed) + '"' + (mode === 'listed' ? '' : ' style="display:none"') + '/>');
    out.push('<polyline class="route route--after" data-route="routed" points="' + pl(pts) + '"' + (mode === 'routed' ? '' : ' style="display:none"') + '/>');
    stops.forEach(function (s, i) {
      var p = pts[i], hard = s.leg_type === 'hard';
      out.push('<g class="pin' + (hard ? ' is-hard' : '') + '" data-stop="' + (i + 1) + '"><circle cx="' + fmt(p[0]) + '" cy="' + fmt(p[1]) + '" r="' + (hard ? 12 : 11) + '"/><text x="' + fmt(p[0]) + '" y="' + fmt(p[1]) + '">' + (i + 1) + '</text></g>');
      var above = p[1] > H - 30 || (labelAbove[i] && p[1] > 30);
      var ly = above ? p[1] - 18 : p[1] + 23;
      out.push('<text class="pin__label" x="' + fmt(p[0]) + '" y="' + fmt(ly) + '">' + h(pinLabel(s.name)) + '</text>');
    });
    out.push('</svg>');
    return out.join('');
  }
  function karnatakaSvg(o) {
    var out = ['<svg viewBox="0 0 300 400" role="img" aria-label="' + h(o.label || 'Karnataka') + '">', '<path class="mapland" d="' + LAND + '"/>'];
    (o.lines || []).forEach(function (ln) {
      var a = kxy(ln[0][0], ln[0][1]), b = kxy(ln[1][0], ln[1][1]);
      out.push('<path d="M' + fmt(a[0]) + ' ' + fmt(a[1]) + ' L' + fmt(b[0]) + ' ' + fmt(b[1]) + '" style="stroke:var(--laterite)" stroke-width="2" stroke-dasharray="6 5" fill="none"/>');
      if (ln[2]) out.push('<text x="' + fmt((a[0] + b[0]) / 2 + 9) + '" y="' + fmt((a[1] + b[1]) / 2) + '" class="dotlabel" style="font-size:9px;fill:var(--laterite);text-anchor:start">' + h(ln[2]) + '</text>');
    });
    (o.dots || []).forEach(function (d) {
      var p = kxy(d.lat, d.lng), r = d.r || 6, fill = d.laterite ? ' style="fill:var(--laterite)"' : '';
      out.push('<circle class="dot' + (d.dim ? ' is-off' : '') + '" cx="' + fmt(p[0]) + '" cy="' + fmt(p[1]) + '" r="' + r + '"' + fill + ' data-city="' + h(d.name) + '"><title>' + h(d.title || d.name) + '</title></circle>');
      var above = p[1] < 200;
      out.push('<text x="' + fmt(p[0]) + '" y="' + fmt(above ? p[1] - r - 7 : p[1] + r + 12) + '" class="dotlabel"' + (d.laterite ? ' style="fill:var(--laterite)"' : '') + '>' + h(String(d.name).toUpperCase()) + '</text>');
    });
    out.push('<text x="150" y="398" class="dotlabel" style="font-size:8.5px;letter-spacing:.18em">KARNATAKA</text></svg>');
    return out.join('');
  }
  function originOf(day) { var t = transferOf(day), c = DATA.centroids || {}; return t && c[t.from_name] ? c[t.from_name] : null; }

  // ---------------------------------------------------------- shared widgets
  function kathaFor(scope, extra, button) {
    var body = Object.assign({scope: scope, duration_min: 5, depth: 'quick', language: 'en'}, extra || {});
    if (button) { button.disabled = true; button.dataset.label = button.textContent; button.textContent = 'Building…'; }
    return api('POST', '/api/katha', body)
      .then(function (k) { location.href = '/katha/' + k.id; })
      .catch(function (err) { if (button) { button.disabled = false; button.textContent = button.dataset.label; } alert(err.message); });
  }


  // ---------------------------------------------------------------- real maps
  // Leaflet over CARTO Positron tiles (no key, no account), the library served
  // from /static/leaflet. The SVG sketch is drawn first and stays underneath:
  // the tiles fade in on the first tile that loads, and if none has loaded
  // within four seconds (dead WiFi) the map is removed and the sketch remains.
  var TILES = 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';
  var TILE_ATTR = '&copy; OpenStreetMap contributors &copy; CARTO';
  var KARNATAKA = [[11.5, 74.0], [18.5, 78.6]];
  var TILE_WAIT_MS = 4000;
  function mapInto(container, opts) {
    // opts: height, svg (the sketch), pins [{lat, lng, label, hard, dim, on, laterite, tooltip, permanent, key, onClick}],
    //       lines [{key, points, dashed, cls, tooltip}], bounds ([[lat,lng],[lat,lng]] or absent: fit the pins)
    if (!container) return null;
    container.innerHTML = opts.svg || '';
    var pins = opts.pins || [];
    if (!window.L || !pins.length) { console.log('[map] sketch (' + (window.L ? 'no pins' : 'no Leaflet') + ')'); return null; }
    var box = document.createElement('div');
    box.className = 'lmap'; box.style.height = opts.height + 'px';
    container.appendChild(box);
    var map = L.map(box, {zoomControl: false, scrollWheelZoom: false, dragging: true});
    map.attributionControl.setPrefix(false);
    var tiles = L.tileLayer(TILES, {attribution: TILE_ATTR, subdomains: 'abcd', maxZoom: 19}).addTo(map);
    var live = {map: map, markers: {}, layers: {}, dead: false};
    pins.forEach(function (p) {
      var cls = 'lpin' + (p.hard ? ' lpin--hard' : '') + (p.dim ? ' lpin--dim' : '') + (p.on ? ' lpin--on' : '') + (p.laterite ? ' lpin--lat' : '');
      var icon = L.divIcon({className: cls, html: '<span>' + h(p.label == null ? '' : String(p.label)) + '</span>', iconSize: [24, 24], iconAnchor: [12, 12], tooltipAnchor: [0, -14]});
      var m = L.marker([p.lat, p.lng], {icon: icon, keyboard: false}).addTo(map);
      if (p.tooltip) m.bindTooltip(p.tooltip, {permanent: !!p.permanent, direction: 'top', className: 'ltip', opacity: 1});
      if (p.onClick) m.on('click', p.onClick);
      if (p.key != null) live.markers[p.key] = m;
    });
    (opts.lines || []).forEach(function (ln) {
      var pl = L.polyline(ln.points, {className: 'lroute ' + (ln.cls || ''), dashArray: ln.dashed ? '7 6' : null, weight: 2.5, interactive: false});
      if (ln.show !== false) pl.addTo(map);
      if (ln.tooltip) {
        var a = ln.points[0], b = ln.points[ln.points.length - 1];
        L.tooltip({permanent: true, direction: 'top', className: 'ltip', opacity: 1}).setLatLng([(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]).setContent(h(ln.tooltip)).addTo(map);
      }
      if (ln.key) live.layers[ln.key] = pl;
    });
    var pts = pins.map(function (p) { return [p.lat, p.lng]; });
    if (opts.bounds) map.fitBounds(opts.bounds, {padding: [28, 28]});
    else if (pts.length === 1) map.setView(pts[0], 15);
    else map.fitBounds(pts, {padding: [28, 28]});
    var shown = false;
    var timer = setTimeout(function () {
      if (shown) return;
      live.dead = true; map.remove(); box.remove();
      console.log('[map] sketch fallback: no tile loaded within ' + TILE_WAIT_MS + ' ms');
    }, TILE_WAIT_MS);
    tiles.once('tileload', function () { shown = true; clearTimeout(timer); box.classList.add('is-on'); console.log('[map] tiles'); });
    live.focus = function (key) {
      Object.keys(live.markers).forEach(function (k) { var el = live.markers[k].getElement(); if (el) el.classList.toggle('lpin--on', String(k) === String(key)); });
    };
    live.show = function (key, on) { var l = live.layers[key]; if (!l || live.dead) return; if (on) { if (!map.hasLayer(l)) l.addTo(map); } else if (map.hasLayer(l)) map.removeLayer(l); };
    live.destroy = function () { clearTimeout(timer); if (!live.dead) { map.remove(); box.remove(); } live.dead = true; };
    setTimeout(function () { if (!live.dead) map.invalidateSize(); }, 0);
    return live;
  }

  // -------------------------------------------------------------------- pages
  var MODE_LABEL = {cab: 'cabs', own_car: 'own car', auto_public: 'autos and public transport'};
  var init = {};

  init.landing = function () {
    if (DATA.day) $('#landing-map').innerHTML = dayMapSvg(DATA.day, {origin: originOf(DATA.day), height: 250});
  };

  init.trip_new = function () {
    var page = $('#form-page');
    var ADULT_BANDS = ['18-39', '40-59', '60+'], CHILD_BANDS = ['under 3', '3-5', '6-12', '13-17'];
    var TRIP_TAGS = {pilgrimage: ['spiritual'], heritage: ['heritage'], nature: ['nature', 'waterfall'], food: ['food'], family: ['heritage', 'food'], adventure: ['nature', 'trek'], couple: ['quiet', 'nature'], friends: ['food', 'photography']};
    var TRIP_LABEL = {family: 'Family holiday', pilgrimage: 'Pilgrimage', heritage: 'Heritage & history', nature: 'Nature & hills', food: 'Food trail', adventure: 'Adventure', couple: 'Couple', friends: 'Friends'};
    var AROUND = {cab: 'cabs', own_car: 'your own car', auto_public: 'autos and public transport', suggest: 'whatever we suggest'};
    var THERE = {train: 'Train', bus: 'Bus', flight: 'Flight', car: 'Own car', any: 'Any way'};
    var touched = {pace: false, endby: false, interests: false};
    var fillNote = '';

    function showStep(id) {
      $$('.fstep').forEach(function (p) { p.classList.toggle('is-on', p.id === id); });
      $$('.steps button').forEach(function (b) { b.setAttribute('aria-current', String(b.dataset.fstep === id)); });
      window.scrollTo({top: 0});
    }
    function current(sel) { var b = $(sel + ' [aria-current="true"]'); return b ? (b.dataset.value !== undefined ? b.dataset.value : b.textContent.trim()) : ''; }
    function single(sel) { var b = $(sel + ' [aria-pressed="true"]'); return b ? (b.dataset.value !== undefined ? b.dataset.value : b.textContent.trim()) : ''; }
    function setSingle(sel, value) { $$(sel + ' .tag').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.value === value)); }); }
    function setSeg(sel, value) { $$(sel + ' button').forEach(function (b) { b.setAttribute('aria-current', String(b.dataset.value === value)); }); }
    function num(id) { return parseInt($('#' + id).textContent, 10) || 0; }
    function val(id) { return $('#' + id).value.trim(); }
    function list(id) { return val(id).split(/[,;/]/).map(function (s) { return s.trim(); }).filter(Boolean); }

    // ---- who's going: one row per traveller, bands kept when the count changes
    function row(kind, i, options, value) {
      return '<div class="field"><label>' + cap(kind) + ' ' + (i + 1) + ' · age</label><select data-kind="' + kind + '" data-index="' + i + '">' +
        options.map(function (b) { return '<option value="' + b + '"' + (b === value ? ' selected' : '') + '>' + b + '</option>'; }).join('') + '</select></div>';
    }
    function renderTravellers(preset) {
      var prev = {};
      $$('#travellers select').forEach(function (s) { prev[s.dataset.kind + s.dataset.index] = s.value; });
      (preset || []).forEach(function (t, i) { prev[t.kind + t.index] = t.age_band; });
      var html = '', a = num('adults'), c = num('children');
      for (var i = 0; i < a; i++) html += row('adult', i, ADULT_BANDS, prev['adult' + i] || '40-59');
      for (var j = 0; j < c; j++) html += row('child', j, CHILD_BANDS, prev['child' + j] || '6-12');
      $('#travellers').innerHTML = html;
    }
    function travellers() { return $$('#travellers select').map(function (s) { return {kind: s.dataset.kind, age_band: s.value}; }); }
    function facts() {
      var t = travellers();
      var elders = t.filter(function (x) { return x.kind === 'adult' && x.age_band === '60+'; }).length;
      var toddler = t.some(function (x) { return x.kind === 'child' && (x.age_band === 'under 3' || x.age_band === '3-5'); });
      return {list: t, adults: t.filter(function (x) { return x.kind === 'adult'; }).length, children: t.filter(function (x) { return x.kind === 'child'; }).length, elders: elders, toddler: toddler, gentle: elders > 0 || toddler};
    }
    // Derived defaults: relaxed and 7 pm for an elder or a child under six,
    // packed greyed for a toddler, interests seeded from the trip type. A
    // control the traveller touched is left alone.
    function derive() {
      var f = facts();
      $('#pace [data-value="packed"]').disabled = f.toddler;
      if (!touched.pace) setSeg('#pace', f.gentle ? 'relaxed' : 'comfortable');
      else if (f.toddler && current('#pace') === 'packed') setSeg('#pace', 'comfortable');
      if (!touched.endby) $('#endby').value = f.gentle ? '19:00' : '20:00';
      if (!touched.interests) {
        var tags = TRIP_TAGS[single('#triptype')] || [];
        $$('#interests .tag').forEach(function (b) { b.setAttribute('aria-pressed', String(tags.indexOf(b.dataset.tag) >= 0)); });
      }
    }
    function money() {
      var figure = parseInt(val('m1').replace(/[^\d]/g, ''), 10) || 0, basis = current('#basis') || 'total';
      var party = Math.max(1, facts().list.length);
      var total = basis === 'per_person' ? figure * party : figure;
      var head = Math.round(total / party);
      $('#budget-line').textContent = inr(total) + ' total · ' + inr(head) + ' a head for ' + party;
      $$('#budget-chips .tag').forEach(function (t) { t.setAttribute('aria-pressed', String(+t.dataset.budget === figure)); });
      return {total: total, basis: basis, head: head, party: party};
    }
    function request() {
      var transport = val('w6'); if (transport === 'flight') transport = 'any';
      var m = money();
      return {
        origin_city: val('w1'),
        destination_cities: list('w2'),
        start_date: val('w3'),
        days: parseInt(val('w4'), 10) || 1,
        travellers: travellers(),
        trip_type: single('#triptype') || null,
        pace: current('#pace') || 'comfortable',
        budget_inr: m.total,
        budget_basis: m.basis,
        transport: transport,
        getting_around: single('#around') || 'suggest',
        food: single('#food') || null,
        interest_tags: $$('#interests [aria-pressed="true"]').map(function (b) { return b.dataset.tag; }),
        must_see: list('m2'),
        skip: list('m3'),
        notes: val('free') || null,
        // "Whenever" is an honest 23:00, not the silent 8 pm default.
        day_end: val('endby') || '23:00'
      };
    }
    // ---- the live summary: one sentence, then up to three lines that are true
    function summary() {
      var f = facts(), m = money(), req = request();
      var who = plural(f.adults, 'adult') + (f.elders ? ' (' + (f.elders === 1 ? 'one' : f.elders) + ' over 60)' : '');
      if (f.children) who += ', ' + plural(f.children, 'child', 'children') + ' (' + f.list.filter(function (x) { return x.kind === 'child'; }).map(function (x) { return x.age_band; }).join(', ') + ')';
      var end = req.day_end === '23:00' ? 'No evening limit' : 'Evenings end by ' + hour12(req.day_end);
      var bits = [
        (req.origin_city || '…') + ' → ' + (req.destination_cities.join(' & ') || '…'),
        plural(req.days, 'day') + (req.start_date ? ' from ' + dateShort(req.start_date) : ''),
        who,
        TRIP_LABEL[req.trip_type] || 'Trip type not set',
        inr(m.total) + ' total, ' + inr(m.head) + ' a head',
        THERE[req.transport === 'any' && val('w6') === 'flight' ? 'flight' : req.transport] + ' there, ' + AROUND[req.getting_around] + ' around',
        req.interest_tags.length ? req.interest_tags.map(cap).join(', ') : 'No interests ticked',
        end
      ];
      $('#sum-line').textContent = bits.join(' · ');
      var rules = [];
      if (f.elders) rules.push('Days end by ' + hour12(req.day_end) + ' and climbs stay short because someone is over 60.');
      else if (f.toddler) rules.push('Days end by ' + hour12(req.day_end) + ' and the easy places win because a child is under 6.');
      else if (req.day_end === '23:00') rules.push('No end-of-day limit: days run as late as the places stay open.');
      if (req.skip.length) rules.push('Skipping ' + listJoin(req.skip) + '.');
      rules.push('One lunch stop is reserved every day.');
      rules.push('Getting around is costed per day, estimated.');
      $('#sum-rules').innerHTML = rules.slice(0, 3).map(function (r) { return '<li>' + h(r) + '</li>'; }).join('');
      var fillEl = $('#sum-fill'); fillEl.hidden = !fillNote; fillEl.textContent = fillNote;
    }
    function refresh() { summary(); }

    page.addEventListener('click', function (e) {
      var fs = e.target.closest('[data-fstep]');
      if (fs) { showStep(fs.dataset.fstep); return; }
      var st = e.target.closest('.stepper button');
      if (st) {
        var out = st.parentElement.querySelector('output'), min = +(st.parentElement.dataset.min || 0);
        out.textContent = Math.max(min, Math.min(12, parseInt(out.textContent, 10) + parseInt(st.dataset.step, 10)));
        renderTravellers(); derive(); refresh();
        return;
      }
      var tag = e.target.closest('.tag');
      if (tag && !tag.disabled) {
        var group = tag.parentElement, on = tag.getAttribute('aria-pressed') === 'true';
        if (group.hasAttribute('data-single')) {
          $$('.tag', group).forEach(function (t) { t.setAttribute('aria-pressed', 'false'); });
          tag.setAttribute('aria-pressed', 'true');
        } else {
          tag.setAttribute('aria-pressed', String(!on));
        }
        if (group.id === 'interests') touched.interests = true;
        if (tag.dataset.budget) $('#m1').value = inr(tag.dataset.budget);
        if (group.id === 'triptype') derive();
        refresh();
        return;
      }
      var seg = e.target.closest('.seg3 button');
      if (seg && !seg.disabled) {
        $$('button', seg.parentElement).forEach(function (b) { b.setAttribute('aria-current', 'false'); }); seg.setAttribute('aria-current', 'true');
        if (seg.parentElement.id === 'pace') touched.pace = true;
        refresh();
      }
    });
    page.addEventListener('input', refresh);
    page.addEventListener('change', function (e) {
      if (e.target.id === 'endby') touched.endby = true;
      if (e.target.closest('#travellers')) derive();
      refresh();
    });

    // ---- "Fill the form from this": the AI reads, the traveller checks
    var fillBtn = $('#fill'), fillNoteEl = $('#fill-note');
    fillBtn.addEventListener('click', function () {
      var text = val('free');
      if (!text) { fillNoteEl.textContent = 'Write a line or two first.'; return; }
      fillBtn.disabled = true; fillBtn.textContent = 'Reading…'; fillNoteEl.textContent = 'The model is reading what you wrote…';
      api('POST', '/api/trips/parse', {text: text}).then(function (out) {
        var f = out.filled || {}, n = Object.keys(f).length;
        if (f.origin_city) $('#w1').value = f.origin_city;
        if (f.destination_cities) $('#w2').value = f.destination_cities.join(', ');
        if (f.start_date) $('#w3').value = f.start_date;
        if (f.days) $('#w4').value = f.days;
        if (f.travellers) {
          var ad = f.travellers.filter(function (t) { return t.kind === 'adult'; }), ch = f.travellers.filter(function (t) { return t.kind === 'child'; });
          $('#adults').textContent = Math.max(1, ad.length); $('#children').textContent = ch.length;
          renderTravellers(ad.map(function (t, i) { return {kind: 'adult', index: i, age_band: t.age_band}; }).concat(ch.map(function (t, i) { return {kind: 'child', index: i, age_band: t.age_band}; })));
        }
        if (f.trip_type) setSingle('#triptype', f.trip_type);
        if (f.budget_basis) setSeg('#basis', f.budget_basis);
        if (f.budget_inr) $('#m1').value = inr(f.budget_inr);
        if (f.transport) $('#w6').value = f.transport;
        if (f.getting_around) setSingle('#around', f.getting_around);
        if (f.interest_tags) { touched.interests = true; $$('#interests .tag').forEach(function (b) { b.setAttribute('aria-pressed', String(f.interest_tags.indexOf(b.dataset.tag) >= 0)); }); }
        if (f.must_see) $('#m2').value = f.must_see.join(', ');
        if (f.skip) $('#m3').value = f.skip.join(', ');
        if (f.food) setSingle('#food', f.food);
        fillNote = out.note || ('Filled ' + n + ' fields from what you wrote — check them');
        fillNoteEl.textContent = fillNote;
        derive(); refresh();
      }).catch(function (err) {
        fillNote = "Couldn't read that — fill it in by hand"; fillNoteEl.textContent = fillNote + ' (' + err.message + ')'; refresh();
      }).then(function () { fillBtn.disabled = false; fillBtn.textContent = 'Fill the form from this'; });
    });

    // ---- submit: warn about a city we have never seen, then post
    var btn = $('#make-plan'), hint = $('#make-hint');
    btn.addEventListener('click', function () {
      var req = request();
      if (!req.destination_cities.length || !req.origin_city || !req.start_date) {
        hint.textContent = 'Where from, where to, and when — we need all three.'; hint.classList.add('err'); return;
      }
      btn.disabled = true; btn.textContent = 'Making your plan…'; hint.textContent = 'Reading your answers…'; hint.classList.remove('err');
      api('GET', '/api/places/coverage?cities=' + encodeURIComponent(req.destination_cities.join(',')))
        .catch(function () { return {}; })
        .then(function (cov) {
          var unknown = req.destination_cities.filter(function (c) { return (cov[c] || 0) < 8; });
          if (unknown.length) {
            hint.textContent = "We haven't been to " + listJoin(unknown) + ' yet — learning about it first, about 20 seconds';
            btn.textContent = 'Learning about ' + unknown[0] + '…';
          }
          return api('POST', '/api/trips', req);
        })
        .then(function (out) {
          if (out.status !== 'planned') { location.href = '/trips/' + out.id; return; }
          showBuild(out, req);
        })
        .catch(function (err) {
          btn.disabled = false; btn.textContent = 'Make my plan →'; hint.textContent = err.message; hint.classList.add('err');
        });
    });
    function showBuild(out, req) {
      var m = out.plan.metrics, days = out.plan.days.length;
      $('#st-read').textContent = plural(req.destination_cities.length, 'place') + ' · ' + partyText(req) + ' · ' + inr(req.budget_inr);
      var learned = (out.cold_start || []).filter(function (r) { return r.drafted_places > 0; });
      var st = $('#st-learn');
      if (learned.length) {
        st.hidden = false;
        $('span', st).textContent = 'Learning about ' + listJoin(learned.map(function (r) { return r.city; }));
        $('small', st).textContent = learned.map(function (r) { return plural(r.drafted_places, 'place') + ' drafted, unverified'; }).join(' · ') + ' · ' + Math.round(learned.reduce(function (a, r) { return a + r.seconds; }, 0)) + ' s';
      }
      $('#st-pick').textContent = m.candidates_considered + ' candidates from ' + (DATA.poi_total || '?');
      $('#st-sort').textContent = plural(days, 'cluster') + ', one per day';
      $('#st-order').textContent = m.route_km_naive + ' km as listed → ' + m.route_km_after + ' km as routed';
      $('#st-check').textContent = m.constraint_checks_passed + ' of ' + m.constraint_checks_total + ' checks · ' + plural(m.repair_iterations, 'fix', 'fixes') + ' made';
      $('#build-total').textContent = 'Total: ' + m.build_ms + ' ms. The plan is computed, not guessed.';
      $('#see-plans').href = '/trips/' + out.id + '?pick';
      page.hidden = true;
      var build = $('#build'); build.hidden = false; build.classList.add('is-on');
      window.scrollTo({top: 0});
    }

    // first paint: the demo defaults, with the bands the page-data carries
    var preset = ((DATA.defaults || {}).travellers || []);
    var ai = 0, ci = 0;
    renderTravellers(preset.map(function (t) { return {kind: t.kind, index: t.kind === 'adult' ? ai++ : ci++, age_band: t.age_band}; }));
    if (DATA.defaults && DATA.defaults.pace) { setSeg('#pace', DATA.defaults.pace); touched.pace = true; }
    if (DATA.defaults && DATA.defaults.day_end) { $('#endby').value = DATA.defaults.day_end.slice(0, 5); touched.endby = true; }
    if ($$('#interests [aria-pressed="true"]').length) touched.interests = true;
    derive(); refresh();
  };

  init.choose = function () {
    document.addEventListener('click', function (e) {
      var card = e.target.closest('[data-choose]'); if (!card) return;
      var i = +card.dataset.choose;
      if (i === 0) { location.href = '/trips/' + DATA.trip_id; return; }
      card.disabled = true;
      api('POST', '/api/trips/' + DATA.trip_id + '/choose', {index: i})
        .then(function () { location.href = '/trips/' + DATA.trip_id; })
        .catch(function (err) { card.disabled = false; alert(err.message); });
    });
  };

  init.nofit = function () {
    var cities = DATA.cities || {}, route = DATA.route || [], legs = DATA.legs || [];
    var dots = route.filter(function (c) { return cities[c]; }).map(function (c) { return {name: c, lat: cities[c][0], lng: cities[c][1], r: 7, laterite: true}; });
    var lines = legs.filter(function (m) { return cities[m.from_name] && cities[m.to_name]; })
      .map(function (m) { return [cities[m.from_name], cities[m.to_name], dur(m.minutes).toUpperCase()]; });
    var fitBox = $('#fit-map');  // absent when a city could not be placed
    if (fitBox) {
      mapInto(fitBox, {
        height: 260,
        svg: karnatakaSvg({dots: dots, lines: lines, label: route.join(' and ') + ' on the map'}),
        pins: dots.map(function (d) { return {lat: d.lat, lng: d.lng, laterite: true, tooltip: d.name, permanent: true}; }),
        lines: legs.filter(function (m) { return cities[m.from_name] && cities[m.to_name]; })
          .map(function (m) { return {points: [cities[m.from_name], cities[m.to_name]], dashed: true, cls: 'lroute--transfer', tooltip: m.mode + ' · ' + dur(m.minutes)}; })
      });
    }
    document.addEventListener('click', function (e) {
      var b = e.target.closest('[data-alt]'); if (!b) return;
      var alt = (DATA.alternatives || [])[+b.dataset.alt]; if (!alt) return;
      var body = Object.assign({}, DATA.request, alt.request_override);
      if (alt.request_override.destination_cities) body.places = alt.request_override.destination_cities;
      b.disabled = true; b.textContent = 'Building…';
      api('POST', '/api/trips', body)
        .then(function (out) { location.href = '/trips/' + out.id + (out.status === 'planned' ? '?pick' : ''); })
        .catch(function (err) { b.disabled = false; b.textContent = 'Build this'; var er = $('#alt-error'); er.hidden = false; er.textContent = err.message; });
    });
  };

  init.trip = function () {
    var trip = DATA.trip, plan = trip.plan, req = trip.request;
    var current = parseInt(new URLSearchParams(location.search).get('day'), 10) || 1;
    var mode = 'routed', lang = 'en', live = null;
    function dayOf(n) { return plan.days.filter(function (d) { return d.index === n; })[0] || plan.days[0]; }
    function dayLines(day, stops) {
      var byId = {}; stops.forEach(function (s) { byId[s.poi_id] = [s.lat, s.lng]; });
      var routed = stops.map(function (s) { return [s.lat, s.lng]; });
      var listed = (day.naive_order || []).map(function (id) { return byId[id]; }).filter(Boolean);
      var lines = [
        {key: 'routed', points: routed, cls: 'lroute--routed', show: mode === 'routed'},
        {key: 'listed', points: listed, dashed: true, cls: 'lroute--listed', show: mode === 'listed'}
      ];
      var transfer = transferOf(day), origin = originOf(day);
      if (transfer && origin && stops.length) {
        lines.push({points: [origin, [stops[0].lat, stops[0].lng]], dashed: true, cls: 'lroute--transfer', tooltip: 'from ' + transfer.from_name + ' · ' + transfer.mode + ' · ' + dur(transfer.minutes)});
      }
      return lines;
    }
    var limit = DATA.day_limit ? hour12(DATA.day_limit) : '';

    function railHtml(day) {
      var out = [], n = 0, transfer = transferOf(day);
      (day.items || []).forEach(function (it) {
        if (it.kind === 'move') {
          var line = (it === transfer ? 'from ' + it.from_name + ' · ' : '') + it.mode + ' · ' + it.minutes + ' min · ' + it.km + ' km · ' + (it.is_estimated ? 'estimated' : 'from our table');
          out.push('<div class="leg leg--move"><div class="leg__time"></div><div class="leg__node"></div><div class="leg__body"><div class="move">' + h(line) + '</div></div></div>');
          return;
        }
        n++;
        var hard = it.leg_type === 'hard';
        var chips = [hard ? '<span class="chip chip--river">Must be on time</span>' : '<span class="chip">Flexible</span>']
          .concat(it.trust === 'ai_generated' ? ['<span class="chip chip--lat">AI-drafted · unverified</span>'] : [])
          .concat((it.tags || []).slice(0, 2).map(function (t) { return '<span class="chip">' + h(cap(t)) + '</span>'; }));
        out.push('<div class="leg"><div class="leg__time">' + h(hm(it.arrive)) + '</div><div class="leg__node"><span class="node node--' + (hard ? 'hard' : 'soft') + '"></span></div>' +
          '<div class="leg__body"><div class="stop" data-stop="' + n + '"><div class="stop__top"><span class="stop__name">' + n + ' · ' + h(it.name) + '</span><span class="stop__meta">' + h(dur(it.dwell_min)) + ' · ' + (it.cost_inr ? inr(it.cost_inr) : 'free') + '</span></div>' +
          '<p class="stop__note">' + h(it.why + (it.note ? ' ' + it.note : '')) + '</p>' +
          '<div class="stop__foot"><div class="stop__tags">' + chips.join('') + '</div><button class="btn btn--sm btn--ghost" data-katha-place="' + it.poi_id + '">Katha</button></div></div></div></div>');
      });
      out.push('<div class="leg"><div class="leg__time">' + h(hm(day.ends_at)) + '</div><div class="leg__node"><span class="node node--soft"></span></div><div class="leg__body"><div class="stop" style="border-style:dashed"><div class="stop__top"><span class="stop__name">' + (n + 1) + ' · Back at the hotel</span><span class="stop__meta">' + (limit ? 'before ' + h(limit) : '') + '</span></div>' +
        '<p class="stop__note">' + (limit ? 'As promised: the day ends ' + h(clock12(day.ends_at)) + ', inside your ' + h(limit) + '.' : 'The day ends ' + h(clock12(day.ends_at)) + '.') + '</p></div></div></div>');
      return out.join('');
    }
    function traceHtml(day) {
      var m = plan.metrics, fixes = m.repair_iterations;
      return [
        'candidates from your tags · <b>' + m.candidates_considered + ' of ' + (DATA.poi_total || '?') + '</b>',
        'grouped by geography · <b>' + plural(plan.days.length, 'cluster') + ', one per day</b>',
        'this day as listed, no routing · <b>' + listedKm(day) + ' km</b>',
        'this day nearest-next, then untangled · <b>' + routedKm(day) + ' km</b>',
        'whole trip · <b>' + m.route_km_naive + ' km listed → ' + m.route_km_before + ' km nearest-next → ' + m.route_km_after + ' km routed</b>',
        'rules checked · <b>' + m.constraint_checks_passed + ' of ' + m.constraint_checks_total + ' · opening hours, budget, meals' + (limit ? ', your ' + h(limit) : '') + '</b>',
        'fixes · <b>' + (fixes ? fixes + ' · ' + (fixes === 1 ? 'one stop dropped so a day would hold' : 'stops dropped so the days would hold') : 'none needed') + '</b>',
        'time to build · <b>' + m.build_ms + ' ms · no AI in this part</b>'
      ].join('<br>');
    }
    function routeLabel(day) {
      $('#routeLabel').textContent = mode === 'listed' ? listedKm(day) + ' km · as listed, no routing' : routedKm(day) + ' km · as routed';
      $('#btnListed').setAttribute('aria-pressed', String(mode === 'listed'));
      $('#btnRouted').setAttribute('aria-pressed', String(mode === 'routed'));
      $$('#day-map [data-route]').forEach(function (p) { p.style.display = p.dataset.route === mode ? '' : 'none'; });
      if (live) { live.show('listed', mode === 'listed'); live.show('routed', mode === 'routed'); }
    }
    function renderQuick() {
      $('#quick').innerHTML = '<button data-quick="lighter">Make Day ' + current + ' lighter</button><button data-quick="food">One more food stop</button><button data-quick="kn">ಕನ್ನಡದಲ್ಲಿ ಹೇಳಿ</button>';
    }
    function renderDay(n) {
      var day = dayOf(n); current = day.index;
      $$('#daytabs button').forEach(function (b) { b.setAttribute('aria-current', String(+b.dataset.day === current)); });
      var stops = stopsOf(day);
      $('#map-title').textContent = 'Day ' + day.index + ' · ' + day.city;
      $('#map-stops').textContent = plural(stops.length, 'stop');
      if (live) { live.destroy(); live = null; }
      live = mapInto($('#day-map'), {
        height: 300,
        svg: dayMapSvg(day, {origin: originOf(day), mode: mode}),
        pins: stops.map(function (s, i) {
          return {lat: s.lat, lng: s.lng, label: i + 1, hard: s.leg_type === 'hard', key: i + 1, tooltip: shortName(s.name),
            onClick: function () { focusStop(i + 1, true); }};
        }),
        lines: dayLines(day, stops)
      });
      routeLabel(day);
      var g = day.getting_around;
      var around = g ? '<p class="dayhead__around">Getting around: ' + h(MODE_LABEL[g.mode] || g.mode) + ' · about ' + inr(g.est_cost_inr) + ' for ' + g.km + ' km · estimated</p>' : '';
      $('#dayhead').innerHTML = '<h3>' + h(dateLong(day.date)) + '</h3><span class="kn">ದಿನ ' + knNum(day.index) + ' · ' + h(CITY_KN[day.city] || day.city) + '</span><span class="chip">Ends ' + h(clock12(day.ends_at)) + '</span>' + around;
      $('#rail').innerHTML = railHtml(day);
      $('#summary').innerHTML = '<div><span>On foot</span><b>' + day.walk_km + ' km</b></div><div><span>By road</span><b>' + day.road_km + ' km</b></div><div><span>Spend today</span><b>' + inr(day.spend_inr) + '</b></div><div><span>Ends</span><b>' + h(clock12(day.ends_at)) + '</b></div>' +
        (g ? '<div><span>Not in the total</span><b>+ ' + inr(g.est_cost_inr) + ' getting around, estimated</b></div>' : '');
      $('#trace').innerHTML = traceHtml(day);
      $('#chat-day').textContent = 'Day ' + day.index;
      renderQuick();
    }
    function focusStop(n, scroll) {
      $$('#rail .stop').forEach(function (s) { s.classList.toggle('is-focus', s.dataset.stop === String(n)); });
      $$('#day-map .pin').forEach(function (p) { p.classList.toggle('is-focus', p.dataset.stop === String(n)); });
      if (live && !live.dead) live.focus(n);
      if (scroll) { var card = $('#rail .stop[data-stop="' + n + '"]'); if (card) card.scrollIntoView({block: 'nearest', behavior: 'smooth'}); }
    }
    // "In a few words": the model writes it from the finished plan, checked
    // against it; nothing else waits on it, and a failure hides the block.
    function showNarration(text) {
      var box = $('#narr');
      if (!box) {
        box = el('<section class="narr" id="narr"><p class="eyebrow">In a few words</p><p id="narr-text"></p><p class="hint">Written by the model from the computed plan, and checked against it.</p></section>');
        $('#daytabs').parentNode.insertBefore(box, $('#daytabs'));
      }
      $('#narr-text').textContent = text;
      box.hidden = false;
    }
    function fetchNarration() {
      api('POST', '/api/trips/' + trip.id + '/narrate')
        .then(function (out) { if (out && out.narration) { trip.narration = out.narration; showNarration(out.narration); } })
        .catch(function () { var box = $('#narr'); if (box) box.hidden = true; });
    }
    if (!trip.narration) fetchNarration();
    $('#btnListed').addEventListener('click', function () { mode = 'listed'; routeLabel(dayOf(current)); });
    $('#btnRouted').addEventListener('click', function () { mode = 'routed'; routeLabel(dayOf(current)); });
    document.addEventListener('click', function (e) {
      var pin = e.target.closest('.pin[data-stop]');
      if (pin) { focusStop(pin.dataset.stop, true); return; }
      var kb = e.target.closest('[data-katha-place]');
      if (kb) { kathaFor({kind: 'place', id: +kb.dataset.kathaPlace}, {trip_id: trip.id, language: lang}, kb); return; }
      var card = e.target.closest('.stop[data-stop]');
      if (card) { focusStop(card.dataset.stop, false); return; }
      var tab = e.target.closest('#daytabs button');
      if (tab) renderDay(+tab.dataset.day);
    });
    $('#katha-day').addEventListener('click', function () { kathaFor({kind: 'day', id: current}, {trip_id: trip.id, language: lang}, this); });

    // chat
    var log = $('#chat-log'), input = $('#chat-in');
    function msg(cls, text, cite) {
      var m = el('<div class="msg' + (cls ? ' ' + cls : '') + '"></div>');
      m.textContent = text;
      if (cite) { var c = document.createElement('cite'); c.textContent = cite; m.appendChild(c); }
      log.appendChild(m); log.scrollTop = log.scrollHeight; return m;
    }
    msg('msg--sys', 'Ask about any stop, or ask for a change. An edit rebuilds one day and leaves the rest alone.');
    $('#quick').addEventListener('click', function (e) {
      var b = e.target.closest('[data-quick]'); if (!b) return;
      if (b.dataset.quick === 'lighter') send('Make Day ' + current + ' lighter');
      else if (b.dataset.quick === 'food') send('Add one more food stop to day ' + current);
      else {
        lang = lang === 'kn' ? 'en' : 'kn';
        input.placeholder = lang === 'kn' ? 'ಕೇಳಿ, ಅಥವಾ ಬದಲಾವಣೆ ಕೇಳಿ…' : 'Ask, or ask for a change…';
        msg('msg--sys', lang === 'kn' ? 'ಇನ್ನು ಮುಂದೆ ಕನ್ನಡದಲ್ಲಿ · replies in Kannada from here' : 'Back to English');
      }
    });
    function send(text) {
      text = (text || input.value).trim(); if (!text) return;
      input.value = ''; msg('msg--me', text);
      var wait = msg('msg--sys msg--wait', 'Thinking…');
      api('POST', '/api/trips/' + trip.id + '/chat', {message: text, language: lang, current_day: current}).then(function (out) {
        wait.remove();
        if (out.kind === 'edit') applyEdit(out);
        else if (out.kind === 'clarify') msg('', out.question);
        else { var src = (out.sources || [])[0]; msg('', out.text, out.refused ? 'nothing reliable in the library' : (src ? (src.name || src.title || '') : '')); }
      }).catch(function (err) { wait.remove(); msg('msg--sys', 'That did not go through: ' + err.message); });
    }
    $('#chat-send').addEventListener('click', function () { send(); });
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); send(); } });
    function applyEdit(out) {
      plan = out.plan; trip.plan = plan;
      // the paragraph described a plan that no longer exists
      trip.narration = null; var narr = $('#narr'); if (narr) narr.hidden = true; fetchNarration();
      var changed = out.changed_day, others = plan.days.map(function (d) { return d.index; }).filter(function (i) { return i !== changed; });
      msg('msg--sys', 'Day ' + changed + ' rebuilt' + (others.length ? ' · Day' + (others.length > 1 ? 's ' : ' ') + listJoin(others) + ' untouched' : ''));
      var s = out.change_summary, day = dayOf(changed), bits = [];
      if (s.removed.length) bits.push(listJoin(s.removed.map(shortName)) + ' out');
      if (s.added.length) bits.push(listJoin(s.added.map(shortName)) + ' in');
      var text = bits.length || s.times_shifted
        ? 'Done. ' + (bits.length ? bits.join('; ') + '. ' : '') + 'Day ' + changed + ' now ends at ' + clock12(day.ends_at) + '.'
        : 'No change: nothing of that kind fits day ' + changed + ' as it stands, so it was left alone.';
      if (out.violations && out.violations.length) text += ' Still not clean: ' + out.violations[0];
      msg('', text, s.removed.length + ' removed · ' + s.added.length + ' added · ' + s.times_shifted + ' times shifted');
      $('#chip-spend').textContent = inr(plan.total_spend) + ' of ' + inr(req.budget_inr);
      var cc = $('#chip-comfort'); cc.textContent = cap(plan.comfort); cc.className = 'chip ' + (plan.comfort === 'tight' ? 'chip--lat' : 'chip--river');
      renderDay(changed); // one day is on screen at a time; only the rebuilt one is redrawn
    }
    renderDay(current);
  };

  init.katha_home = function () {
    function row(r) {
      if (r.kind === 'city') {
        return '<div class="kitem"><span class="kitem__kind">City</span><div><b>' + h(r.name) + '</b><span>' + h(plural(r.places, 'place') + ' · ' + r.minutes + ' min of material') + '</span></div><button class="btn btn--sm btn--ghost" data-listen-kind="city" data-listen-id="' + h(r.id) + '">Listen</button></div>';
      }
      var sub = [r.city, r.name_kn, r.minutes ? r.minutes + ' min of material' : 'city material only'].filter(Boolean).join(' · ');
      return '<div class="kitem"><span class="kitem__kind is-place">Place</span><div><b>' + h(r.name) + '</b><span>' + h(sub) + '</span></div><button class="btn btn--sm btn--ghost" data-listen-kind="place" data-listen-id="' + r.id + '">Listen</button></div>';
    }
    function renderResults(q, results) {
      $('#results-count').textContent = q ? plural(results.length, 'result') + ' for “' + q + '”' : plural(results.length, 'place') + ' to start with';
      $('#results').innerHTML = results.map(row).join('');
    }
    renderResults(DATA.q || '', DATA.results || []);
    $('#search').addEventListener('submit', function (e) {
      e.preventDefault();
      var q = $('#search input').value.trim();
      api('GET', '/api/places/search?q=' + encodeURIComponent(q)).then(function (out) {
        renderResults(q, out.results); history.replaceState(null, '', q ? '/katha?q=' + encodeURIComponent(q) : '/katha');
      });
    });
    var cov = DATA.coverage || [];
    mapInto($('#coverage-map'), {
      height: 400,
      bounds: KARNATAKA,
      svg: karnatakaSvg({
        label: 'Karnataka, with dots where Katha material exists',
        dots: cov.map(function (c) { return {name: c.city, lat: c.lat, lng: c.lng, r: 3 + c.places / 5, title: c.city + ' — ' + plural(c.places, 'place') + ' · ' + plural(c.paragraphs, 'paragraph')}; })
      }),
      pins: cov.map(function (c) {
        return {lat: c.lat, lng: c.lng, label: c.places, tooltip: c.city + ' · ' + plural(c.places, 'place'), permanent: true,
          onClick: function () { kathaFor({kind: 'city', id: c.city}); }};
      })
    });
    document.addEventListener('click', function (e) {
      var dot = e.target.closest('.dot[data-city]');
      if (dot) { kathaFor({kind: 'city', id: dot.dataset.city}); return; }
      var b = e.target.closest('[data-listen-kind]');
      if (b) kathaFor({kind: b.dataset.listenKind, id: b.dataset.listenKind === 'place' ? +b.dataset.listenId : b.dataset.listenId}, {}, b);
    });
  };

  init.katha = function () {
    var K = DATA.katha, segs = K.segments, places = DATA.places || {}, order = (DATA.order || []).filter(function (n) { return places[n]; });
    var segEls = $$('.seg');
    $$('.pick').forEach(function (pick) {
      pick.addEventListener('click', function (e) {
        var b = e.target.closest('button'); if (!b || b.getAttribute('aria-current') === 'true') return;
        var body = {scope: K.scope, duration_min: K.duration_min, depth: K.depth, language: K.language, trip_id: DATA.trip_id};
        var key = pick.dataset.pick; body[key] = key === 'duration_min' ? +b.dataset.value : b.dataset.value;
        $$('button', pick).forEach(function (x) { x.setAttribute('aria-current', 'false'); }); b.setAttribute('aria-current', 'true');
        var status = $('#pick-status'); status.hidden = false; status.classList.remove('err');
        status.textContent = 'Building a ' + body.duration_min + '-minute ' + body.depth + ' Katha…';
        api('POST', '/api/katha', body).then(function (k) { location.href = '/katha/' + k.id; })
          .catch(function (err) { status.textContent = err.message; status.classList.add('err'); });
      });
    });
    document.addEventListener('click', function (e) {
      var d = e.target.closest('[data-deeper]');
      if (d) kathaFor({kind: 'place', id: +d.dataset.deeper}, {trip_id: DATA.trip_id, language: K.language, depth: 'deep'}, d);
    });

    function placeAt(i) { var name = segEls[i] ? segEls[i].dataset.place : ''; return places[name] ? name : null; }
    var locLive = null, locAt = null;
    function locatorTiles(box, now) {
      // rebuilt only when the lit place changes, so the map does not flicker
      if (locLive && locAt === now && !locLive.dead) return;
      if (locLive) locLive.destroy();
      locAt = now;
      var pinsOf = K.scope.kind === 'place' ? [order[0] || Object.keys(places)[0]].filter(Boolean) : order;
      var seen = true;
      locLive = mapInto(box, {
        height: 240,
        svg: box.innerHTML,
        pins: pinsOf.map(function (n, i) {
          var p = places[n], isNow = n === now;
          if (isNow) seen = false;
          var dim = K.scope.kind !== 'place' && !isNow && !seen;
          return {lat: p.lat, lng: p.lng, label: K.scope.kind === 'place' ? '' : i + 1, on: isNow, dim: dim, tooltip: shortName(p.name), permanent: isNow};
        })
      });
    }
    function locator(i) {
      var box = $('#locator'), now = placeAt(i);
      if (locLive && !locLive.dead && locAt === now) return;  // same place lit: nothing to redraw
      locatorSvg(i);
      if (locLive && locLive.dead) return;  // tiles never came: the sketch is the map from here on
      locatorTiles(box, now);
    }
    function locatorSvg(i) {
      var box = $('#locator'), now = placeAt(i);
      if (K.scope.kind === 'place') {
        var p = places[order[0]] || places[Object.keys(places)[0]];
        if (!p) { box.innerHTML = ''; return; }
        box.innerHTML = '<svg viewBox="0 0 300 200" role="img" aria-label="' + h('Locator map for ' + p.name) + '"><g class="mapcontour"><path d="M10 160q66-24 118-12t162-24"/><path d="M10 132q70-22 124-10t156-24"/><path d="M10 104q68-20 122-8t158-22"/></g>' +
          '<rect x="118" y="78" width="64" height="44" fill="none" stroke="#17211E" stroke-width="1" opacity=".55"/><circle cx="150" cy="100" r="7" class="dot"/><circle cx="150" cy="100" r="16" fill="none" stroke="#1F5C6B" stroke-width="1" opacity=".55"/><circle cx="150" cy="100" r="27" fill="none" stroke="#1F5C6B" stroke-width="1" opacity=".3"/>' +
          '<text x="150" y="140" class="dotlabel">' + h(shortName(p.name).toUpperCase()) + '</text><text x="150" y="152" class="dotlabel" style="font-size:7px">' + h(p.lat.toFixed(4) + '° N · ' + p.lng.toFixed(4) + '° E') + '</text></svg>';
        $('#loc-chip').textContent = p.lat.toFixed(4) + '° N';
        var today = ((new Date().getDay() + 6) % 7) + 1;
        $('#loc-foot').textContent = (p.closed_on || []).indexOf(today) >= 0 ? 'Closed today' : (p.closes ? 'Open today · closes ' + p.closes : 'Open today · hours not listed');
        return;
      }
      if (!order.length) { box.innerHTML = ''; $('#loc-foot').textContent = 'No pins for this Katha'; return; }
      var proj = projector(order.map(function (n) { return [places[n].lat, places[n].lng]; }), 300, 220, 40);
      var out = ['<svg viewBox="0 0 300 220" role="img" aria-label="' + h('Locator map for ' + (DATA.scope_title || '')) + '"><g class="mapcontour"><path d="M10 174q66-30 118-16t162-30"/><path d="M10 146q70-28 124-14t156-30"/></g>'];
      order.forEach(function (n) {
        var p = proj(places[n].lat, places[n].lng), isNow = n === now;
        out.push('<circle class="dot' + (isNow ? '' : ' is-off') + '" cx="' + fmt(p[0]) + '" cy="' + fmt(p[1]) + '" r="' + (isNow ? 7 : 4.5) + '"/>');
        if (isNow) out.push('<circle cx="' + fmt(p[0]) + '" cy="' + fmt(p[1]) + '" r="13" fill="none" stroke="#1F5C6B" stroke-width="1" opacity=".5"/>');
        out.push('<text x="' + fmt(p[0]) + '" y="' + fmt(p[1] - (isNow ? 18 : 13)) + '" class="dotlabel">' + h(pinLabel(places[n].name)) + '</text>');
      });
      out.push('</svg>');
      box.innerHTML = out.join('');
      $('#loc-chip').textContent = plural(order.length, 'stop');
      $('#loc-foot').textContent = 'Now at · ' + (now ? shortName(now) : (DATA.city || ''));
    }

    // the player: one WAV for the whole Katha, segment boundaries by word share (estimated)
    var btn = $('#ttsBtn'), label = $('#ttsLabel'), title = $('#ttsTitle'), bar = $('#ttsBar'), chip = $('#ttsChip');
    var audio = new Audio(), state = 'idle', source = 'none', cur = 0;
    function words(s) { return (s.narration || s.text).split(/\s+/).length; }
    function bounds() { var total = segs.reduce(function (a, s) { return a + words(s); }, 0) || 1, acc = 0; return segs.map(function (s) { acc += words(s); return acc / total; }); }
    function setSeg(i) { cur = i; $$('#progress span').forEach(function (s, k) { s.classList.toggle('on', k <= i); }); title.textContent = segs[i] ? segs[i].title : ''; locator(i); }
    function setLabel(prefix) { label.textContent = prefix + 'SEGMENT ' + (cur + 1) + ' OF ' + segs.length + (state === 'idle' ? ' · TAP TO LISTEN' : ''); }
    var langWord = K.language === 'kn' ? 'ಕನ್ನಡ · ' : K.language === 'hi' ? 'हिन्दी · ' : '';
    setSeg(0); setLabel('');
    audio.addEventListener('timeupdate', function () {
      if (!audio.duration) return;
      var f = audio.currentTime / audio.duration; bar.style.width = (f * 100).toFixed(1) + '%';
      var i = bounds().findIndex(function (b) { return f < b; }); if (i < 0) i = segs.length - 1;
      if (i !== cur) setSeg(i);
      setLabel('PLAYING · ' + langWord);
    });
    audio.addEventListener('ended', function () { state = 'idle'; setLabel(''); });
    function speakBrowser() {
      if (!('speechSynthesis' in window)) { label.textContent = 'NO VOICE AVAILABLE RIGHT NOW · READ ALONG'; state = 'idle'; return; }
      chip.textContent = 'Voice · browser'; source = 'browser'; state = 'playing';
      speechSynthesis.cancel();
      segs.forEach(function (s, i) {
        var u = new SpeechSynthesisUtterance(s.narration || s.text);
        u.lang = LANG_TAG[K.language] || 'en-IN';
        u.onstart = function () { setSeg(i); setLabel('PLAYING · ' + langWord); bar.style.width = ((i + 0.5) / segs.length * 100) + '%'; };
        if (i === segs.length - 1) u.onend = function () { state = 'idle'; setLabel(''); bar.style.width = '100%'; };
        speechSynthesis.speak(u);
      });
    }
    btn.addEventListener('click', function () {
      if (state === 'playing') { if (source === 'browser') speechSynthesis.pause(); else audio.pause(); state = 'paused'; setLabel('PAUSED · '); return; }
      if (state === 'paused') { if (source === 'browser') speechSynthesis.resume(); else audio.play(); state = 'playing'; setLabel('PLAYING · ' + langWord); return; }
      if (state === 'loading') return;
      state = 'loading'; label.textContent = 'PREPARING THE VOICE…'; chip.textContent = 'Sarvam · asking';
      fetch('/api/katha/' + K.id + '/audio', {method: 'POST'}).then(function (r) {
        if (r.status === 204 || !r.ok) { speakBrowser(); return null; }
        chip.textContent = r.headers.get('X-Voice') === 'cached' ? 'Sarvam · cached' : 'Sarvam · live';
        return r.blob().then(function (b) {
          audio.src = URL.createObjectURL(b); source = 'sarvam'; state = 'playing'; setLabel('PLAYING · ' + langWord);
          return audio.play();
        });
      }).catch(function () { speakBrowser(); });
    });

    // narration in the chosen language, when the page came without it
    if (K.language !== 'en' && segs.some(function (s) { return !s.narration; })) {
      var status = $('#pick-status'); status.hidden = false;
      status.textContent = K.language === 'kn' ? 'ಕನ್ನಡದಲ್ಲಿ ಬರೆಯಲಾಗುತ್ತಿದೆ… the narrator is writing this in Kannada; the library\'s English stays until then.' : 'हिन्दी में लिखा जा रहा है… the narrator is writing this in Hindi; the library\'s English stays until then.';
      api('POST', '/api/katha/' + K.id + '/narrate').then(function (k) {
        K.segments = segs = k.segments;
        segs.forEach(function (s, i) {
          var body = segEls[i] && $('.seg__body', segEls[i]); if (!body) return;
          body.classList.remove('narr-pending');
          $$('p:not(.seg__src)', body).forEach(function (p) { p.remove(); });
          var src = $('.seg__src', body);
          (s.narration || s.text).split(/\n\n+/).forEach(function (para) { var p = document.createElement('p'); p.textContent = para; body.insertBefore(p, src); });
        });
        status.textContent = k.narration_source === 'demo' ? 'Narration from the cached demo, fact-checked when it was made.' : 'Narrated and fact-checked against the paragraphs.';
      }).catch(function (err) { status.textContent = 'Could not narrate right now: ' + err.message; status.classList.add('err'); });
    }
  };

  if (init[PAGE]) init[PAGE]();
})();
