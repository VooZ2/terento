/* Reusable country coverage renderer. No network, authentication or telemetry.
 * Input: trusted OpenStreetMap-derived SVG and aggregated {code, count, name} rows.
 * Hosts own data policy, fetching, provider details and surrounding UI.
 * options.unavailable lists country codes where maps are not offered; they get
 * a grey hatched fill and options.unavailableLabel in their accessible name.
 */
(function (global) {
  'use strict';
  global.TerentoCoverageMap = function (container, options) {
    container.classList.add('terento-coverage-map');
    const svg = new DOMParser().parseFromString(options.svg, 'image/svg+xml').documentElement;
    const [, , width, height] = svg.getAttribute('viewBox').split(/\s+/).map(Number);
    const bounds = L.latLngBounds([0, 0], [height, width]);
    const map = L.map(container, {
      crs: L.CRS.Simple, minZoom: -4, maxZoom: 4, zoomSnap: 0,
      scrollWheelZoom: true, attributionControl: true, zoomControl: false,
      maxBounds: bounds.pad(.3), maxBoundsViscosity: .8
    });
    L.svgOverlay(svg, bounds, {interactive: true}).addTo(map);
    map.attributionControl.setPrefix(false);
    map.attributionControl.addAttribution('Boundaries: <a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a> (ODbL) · Leaflet');
    const paths = new Map([...svg.querySelectorAll('path[id]')].map(path => [path.id, path]));
    const unavailable = new Set(options.unavailable || []);
    // Hatch stripes keep a fixed 5 px on-screen size: CRS.Simple draws 2^zoom px per SVG unit.
    let hatch = null;
    if (unavailable.size) {
      const ns = 'http://www.w3.org/2000/svg';
      const make = (tag, attributes) => {
        const element = svg.ownerDocument.createElementNS(ns, tag);
        Object.entries(attributes).forEach(([name, value]) => element.setAttribute(name, value));
        return element;
      };
      const defs = make('defs', {});
      hatch = make('pattern', {id: 'coverage-map-unavailable', patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)'});
      hatch.appendChild(make('rect', {style: 'fill:color-mix(in srgb,var(--secondary,#6d706f) 16%,var(--surface,#fff))'}));
      hatch.appendChild(make('path', {style: 'stroke:var(--secondary,#6d706f);stroke-opacity:.55'}));
      defs.appendChild(hatch);
      svg.insertBefore(defs, svg.firstChild);
    }
    const scaleHatch = () => {
      if (!hatch) return;
      const size = 5 * Math.pow(2, -map.getZoom());
      [hatch, hatch.children[0]].forEach(element => { element.setAttribute('width', size); element.setAttribute('height', size); });
      hatch.children[1].setAttribute('d', `M0 0V${size}`);
      hatch.children[1].setAttribute('stroke-width', size * .32);
    };
    let data = new Map();
    const notify = code => options.onCountry?.(code ? data.get(code) : null, code);
    const highlight = (code, focus = false) => {
      paths.forEach(path => path.classList.remove('is-region-highlight'));
      const path = paths.get(code);
      if (!path) { notify(null); return; }
      path.classList.add('is-region-highlight');
      notify(code);
      if (focus) {
        const box = path.getBBox();
        map.fitBounds([[height - box.y - box.height, box.x], [height - box.y, box.x + box.width]], {padding: [40, 40], maxZoom: 3, animate: false});
      }
    };
    paths.forEach((path, code) => {
      path.classList.add('world-map-country');
      path.setAttribute('tabindex', '0');
      path.setAttribute('role', 'img');
      ['mouseenter', 'focus'].forEach(event => path.addEventListener(event, () => highlight(code)));
      ['mouseleave', 'blur'].forEach(event => path.addEventListener(event, () => highlight(null)));
      path.addEventListener('click', () => highlight(code, true));
      path.addEventListener('keydown', event => {
        if (event.key === 'Enter') { event.preventDefault(); highlight(code, true); }
        if (event.key === 'Escape') { highlight(null); container.focus(); }
      });
    });
    // 100% fits the complete world with a small inset at every viewport size.
    const initialZoom = () => map.getBoundsZoom(bounds, false, [12, 12]);
    let overviewZoom;
    // Zoom out stops at 100%: the whole world is the smallest view.
    const reset = () => {
      map.invalidateSize();
      overviewZoom = initialZoom();
      map.setMinZoom(overviewZoom);
      map.setView(bounds.getCenter(), overviewZoom, {animate: false});
      scaleHatch();
      highlight(null);
    };
    const resize = new ResizeObserver(() => {
      const atOverview = map.getZoom() === overviewZoom && map.getCenter().equals(bounds.getCenter());
      map.invalidateSize({pan: false});
      if (atOverview) reset();
      else { map.setMinZoom(initialZoom()); options.onZoom?.(map.getZoom(), initialZoom()); }
    });
    resize.observe(container);
    map.on('zoomend', () => { scaleHatch(); options.onZoom?.(map.getZoom(), initialZoom()); });
    reset();
    return {
      codes: new Set(paths.keys()),
      update(rows) {
        data = new Map(rows.map(row => [row.code, row]));
        const maximum = Math.max(0, ...rows.map(row => row.count));
        paths.forEach((path, code) => {
          const row = data.get(code);
          const count = row?.count || 0;
          const name = row?.name || options.names?.[code] || code.toUpperCase();
          if (unavailable.has(code)) {
            path.classList.add('is-unavailable');
            path.style.fill = 'url(#coverage-map-unavailable)';
            path.setAttribute('aria-label', `${name}: ${options.unavailableLabel || 'maps are not offered'}`);
            return;
          }
          path.style.fill = count && maximum ? `hsl(198 25% ${97 - Math.pow(count / maximum, .58) * 48}%)` : 'var(--surface, #fff)';
          path.setAttribute('aria-label', `${name}: ${count} completed installs`);
        });
      },
      highlight,
      zoom(action) { if (action === 'reset') reset(); else action === 'in' ? map.zoomIn() : map.zoomOut(); },
      destroy() { resize.disconnect(); map.remove(); }
    };
  };
})(window);
