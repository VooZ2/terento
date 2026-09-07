/* Reusable country coverage renderer. No network, authentication or telemetry.
 * Input: trusted Natural Earth SVG and aggregated {code, count, name} rows.
 * Hosts own data policy, fetching, provider details and surrounding UI.
 */
(function (global) {
  'use strict';
  global.TerentoCoverageMap = function (container, options) {
    container.classList.add('terento-coverage-map');
    const svg = new DOMParser().parseFromString(options.svg, 'image/svg+xml').documentElement;
    const [, , width, height] = svg.getAttribute('viewBox').split(/\s+/).map(Number);
    const bounds = L.latLngBounds([0, 0], [height, width]);
    const map = L.map(container, {
      crs: L.CRS.Simple, minZoom: -4, maxZoom: 4, zoomSnap: .25,
      scrollWheelZoom: true, attributionControl: true, zoomControl: false,
      maxBounds: bounds.pad(.3), maxBoundsViscosity: .8
    });
    L.svgOverlay(svg, bounds, {interactive: true}).addTo(map);
    map.attributionControl.setPrefix(false);
    map.attributionControl.addAttribution('Boundaries: Natural Earth (public domain) · Leaflet');
    const paths = new Map([...svg.querySelectorAll('path[id]')].map(path => [path.id, path]));
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
        map.fitBounds([[height - box.y - box.height, box.x], [height - box.y, box.x + box.width]], {padding: [40, 40], maxZoom: 3});
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
    const reset = () => { map.invalidateSize(); map.fitBounds(bounds); highlight(null); };
    const resize = new ResizeObserver(() => map.invalidateSize({pan: false}));
    resize.observe(container);
    map.on('zoomend', () => options.onZoom?.(map.getZoom(), map.getBoundsZoom(bounds)));
    reset();
    return {
      codes: new Set(paths.keys()),
      update(rows) {
        data = new Map(rows.map(row => [row.code, row]));
        const maximum = Math.max(0, ...rows.map(row => row.count));
        paths.forEach((path, code) => {
          const row = data.get(code);
          const count = row?.count || 0;
          path.style.fill = count && maximum ? `hsl(198 25% ${97 - Math.pow(count / maximum, .58) * 48}%)` : 'var(--surface, #fff)';
          path.setAttribute('aria-label', `${row?.name || options.names?.[code] || code.toUpperCase()}: ${count} completed installs`);
        });
      },
      highlight,
      zoom(action) { if (action === 'reset') reset(); else action === 'in' ? map.zoomIn() : map.zoomOut(); },
      destroy() { resize.disconnect(); map.remove(); }
    };
  };
})(window);
