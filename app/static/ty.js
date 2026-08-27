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

  // -------------------------------------------------------------------- pages
  var init = {};

  init.landing = function () {
    if (DATA.day) $('#landing-map').innerHTML = dayMapSvg(DATA.day, {origin: originOf(DATA.day), height: 250});
  };

  init.trip_new = function () {
    var page = $('#form-page');
    function showStep(id) {
      $$('.fstep').forEach(function (p) { p.classList.toggle('is-on', p.id === id); });
      $$('.steps button').forEach(function (b) { b.setAttribute('aria-current', String(b.dataset.fstep === id)); });
      window.scrollTo({top: 0});
    }
    page.addEventListener('click', function (e) {
      var fs = e.target.closest('[data-fstep]');
      if (fs) { showStep(fs.dataset.fstep); return; }
      var st = e.target.closest('.stepper button');
      if (st) {
        var out = st.parentElement.querySelector('output'), min = +(st.parentElement.dataset.min || 0);
        out.textContent = Math.max(min, Math.min(12, parseInt(out.textContent, 10) + parseInt(st.dataset.step, 10)));
        return;
      }
      var tag = e.target.closest('.tag, .check');
      if (tag) {
        var group = tag.parentElement, on = tag.getAttribute('aria-pressed') === 'true';
        if (group.hasAttribute('data-single')) {
          $$('.tag, .check', group).forEach(function (t) { t.setAttribute('aria-pressed', 'false'); });
          tag.setAttribute('aria-pressed', 'true');
        } else {
          tag.setAttribute('aria-pressed', String(!on));
        }
        if (tag.dataset.budget) $('#m1').value = inr(tag.dataset.budget);
        return;
      }
      var seg = e.target.closest('.seg3 button');
      if (seg) { $$('button', seg.parentElement).forEach(function (b) { b.setAttribute('aria-current', 'false'); }); seg.setAttribute('aria-current', 'true'); }
    });
    $('#m1').addEventListener('input', function () {
      var v = parseInt($('#m1').value.replace(/[^\d]/g, ''), 10);
      $$('#budget-chips .tag').forEach(function (t) { t.setAttribute('aria-pressed', String(+t.dataset.budget === v)); });
    });

    function pressed(sel) { return $$(sel + ' [aria-pressed="true"]').map(function (b) { return b.textContent.trim(); }); }
    function current(sel) { var b = $(sel + ' [aria-current="true"]'); return b ? (b.dataset.value || b.textContent.trim()) : ''; }
    function num(id) { return parseInt($('#' + id).textContent, 10) || 0; }
    function val(id) { return $('#' + id).value.trim(); }
    function request() {
      var adults = num('adults'), elders = num('elders'), children = num('children');
      var transport = val('w6'); if (transport === 'flight') transport = 'any';
      return {
        origin_city: val('w1'),
        destination_cities: val('w2').split(/[,;/]/).map(function (s) { return s.trim(); }).filter(Boolean),
        start_date: val('w3'),
        days: parseInt(val('w4'), 10) || 1,
        party_size: Math.max(1, adults + elders + children),
        has_elderly: elders > 0,
        has_children: children > 0,
        pace: current('#pace') || 'comfortable',
        budget_inr: parseInt(val('m1').replace(/[^\d]/g, ''), 10) || 0,
        transport: transport,
        interest_tags: $$('#interests [aria-pressed="true"]').map(function (b) { return b.dataset.tag; }),
        notes: val('m4') || null,
        day_one_start: val('w5'),
        day_end: val('endby') || null,
        preferences: {
          adults: String(adults), elders: String(elders), children: String(children),
          children_ages: pressed('#ages').join(', '), walking: pressed('#walking').join(', '),
          mornings: val('mornings'), food: pressed('#food').join(', '), budget_covers: pressed('#covers').join(', '),
          stay: current('#stay'), getting_around: pressed('#around').join(', '),
          getting_there: $('#w6').selectedOptions[0].textContent, must_see: val('m2'), skip: val('m3')
        }
      };
    }
    var btn = $('#make-plan'), hint = $('#make-hint');
    btn.addEventListener('click', function () {
      var req = request();
      if (!req.destination_cities.length || !req.origin_city || !req.start_date) {
        hint.textContent = 'Where from, where to, and when — we need all three.'; hint.classList.add('err'); return;
      }
      btn.disabled = true; btn.textContent = 'Making your plan…'; hint.textContent = 'Reading your answers…'; hint.classList.remove('err');
      api('POST', '/api/trips', req).then(function (out) {
        if (out.status !== 'planned') { location.href = '/trips/' + out.id; return; }
        showBuild(out, req);
      }).catch(function (err) {
        btn.disabled = false; btn.textContent = 'Make my plan →'; hint.textContent = err.message; hint.classList.add('err');
      });
    });
    function showBuild(out, req) {
      var m = out.plan.metrics, days = out.plan.days.length;
      $('#st-read').textContent = plural(req.destination_cities.length, 'place') + ' · ' + req.party_size + ' people · ' + inr(req.budget_inr);
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
    $('#fit-map').innerHTML = karnatakaSvg({dots: dots, lines: lines, label: route.join(' and ') + ' on the map'});
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
    var mode = 'routed', lang = 'en';
    function dayOf(n) { return plan.days.filter(function (d) { return d.index === n; })[0] || plan.days[0]; }
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
      $('#day-map').innerHTML = dayMapSvg(day, {origin: originOf(day), mode: mode});
      routeLabel(day);
      $('#dayhead').innerHTML = '<h3>' + h(dateLong(day.date)) + '</h3><span class="kn">ದಿನ ' + knNum(day.index) + ' · ' + h(CITY_KN[day.city] || day.city) + '</span><span class="chip">Ends ' + h(clock12(day.ends_at)) + '</span>';
      $('#rail').innerHTML = railHtml(day);
      $('#summary').innerHTML = '<div><span>On foot</span><b>' + day.walk_km + ' km</b></div><div><span>By road</span><b>' + day.road_km + ' km</b></div><div><span>Spend today</span><b>' + inr(day.spend_inr) + '</b></div><div><span>Ends</span><b>' + h(clock12(day.ends_at)) + '</b></div>';
      $('#trace').innerHTML = traceHtml(day);
      $('#chat-day').textContent = 'Day ' + day.index;
      renderQuick();
    }
    function focusStop(n, scroll) {
      $$('#rail .stop').forEach(function (s) { s.classList.toggle('is-focus', s.dataset.stop === String(n)); });
      $$('#day-map .pin').forEach(function (p) { p.classList.toggle('is-focus', p.dataset.stop === String(n)); });
      if (scroll) { var card = $('#rail .stop[data-stop="' + n + '"]'); if (card) card.scrollIntoView({block: 'nearest', behavior: 'smooth'}); }
    }
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
    $('#coverage-map').innerHTML = karnatakaSvg({
      label: 'Karnataka, with dots where Katha material exists',
      dots: cov.map(function (c) { return {name: c.city, lat: c.lat, lng: c.lng, r: 3 + c.places / 5, title: c.city + ' — ' + plural(c.places, 'place') + ' · ' + plural(c.paragraphs, 'paragraph')}; })
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
    function locator(i) {
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
