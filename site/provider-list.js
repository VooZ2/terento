(() => {
  const cards = [...document.querySelectorAll('[data-provider-card]')];
  if (!cards.length) return;

  const row = document.querySelector('[data-provider-cards]');
  const controls = document.querySelector('[data-provider-controls]');
  const previous = controls?.querySelector('[data-provider-previous]');
  const next = controls?.querySelector('[data-provider-next]');
  const updateControls = () => {
    if (!row || !controls) return;
    const overflow = row.scrollWidth > row.clientWidth + 2;
    controls.hidden = !overflow;
    row.tabIndex = overflow ? 0 : -1;
    previous.disabled = row.scrollLeft <= 2;
    next.disabled = row.scrollLeft + row.clientWidth >= row.scrollWidth - 2;
  };
  const move = (direction) => {
    const visible = cards.filter((card) => !card.hidden);
    const current = visible.reduce((nearest, card, index) =>
      Math.abs(card.getBoundingClientRect().left - row.getBoundingClientRect().left)
        < Math.abs(visible[nearest].getBoundingClientRect().left - row.getBoundingClientRect().left) ? index : nearest, 0);
    const target = visible[Math.max(0, Math.min(visible.length - 1, current + direction))];
    if (!target) return;
    row.scrollBy({ left: target.getBoundingClientRect().left - row.getBoundingClientRect().left,
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
  };
  if (row && controls) {
    previous.addEventListener('click', () => move(-1));
    next.addEventListener('click', () => move(1));
    row.addEventListener('scroll', updateControls, { passive: true });
    row.addEventListener('keydown', (event) => {
      if (event.target !== row || !['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
      event.preventDefault();
      move(event.key === 'ArrowLeft' ? -1 : 1);
    });
    window.addEventListener('resize', updateControls);
    if ('ResizeObserver' in window) new ResizeObserver(updateControls).observe(row);
    updateControls();
  }

  const API_URL = 'https://api.terento.app/maps/catalog-v3.json';
  const PUBLIC_PROVIDER_IDS = new Set(["freizeitkarte", "opentopomap", "maprando"]);
  const render = (providers) => {
    const activeProviders = new Map(providers
      .filter((provider) => PUBLIC_PROVIDER_IDS.has(String(provider?.id || '').trim().toLowerCase()))
      .filter((provider) => String(provider?.status || '').toUpperCase() === 'ACTIVE')
      .map((provider) => [String(provider.id).trim().toLowerCase(), provider]));
    cards.forEach((card) => {
      const provider = activeProviders.get(card.dataset.providerCard);
      card.hidden = !provider;
      if (!provider) return;
      const maps = Array.isArray(provider.maps)
        ? provider.maps.filter((map) => String(map?.availability || '').toUpperCase() === 'AVAILABLE') : [];
      const countElement = card.querySelector('[data-provider-count]');
      if (Array.isArray(provider.maps) && countElement) {
        countElement.hidden = false;
        const countries = new Set(maps.map((map) => String(map?.country || '').trim()).filter(Boolean));
        countElement.textContent = countElement.dataset.countTemplate
          .replace('{count}', String(maps.length)).replace('{countries}', String(countries.size));
      }
      const addon = card.querySelector('[data-provider-addon]');
      if (!addon) return;
      const count = maps.filter((map) => Array.isArray(map?.artifacts)
        && map.artifacts.some((artifact) => String(artifact?.kind || '').toLowerCase() === 'contours'
          && String(artifact?.validationStatus || artifact?.validationState || '').toUpperCase() === 'VALIDATED')).length;
      addon.hidden = count === 0;
      const counter = addon.querySelector('[data-contour-count]');
      if (count && counter) counter.textContent = counter.dataset.countTemplate.replace('{count}', String(count));
    });
    updateControls();
  };
  fetch(API_URL, { headers: { Accept: 'application/json' } })
    .then((response) => response.ok ? response.json() : Promise.reject(new Error('provider_catalog_unavailable')))
    .then((payload) => Array.isArray(payload?.providers) && render(payload.providers))
    .catch(() => {
      // Keep the generated content readable when the catalog is unavailable.
    });
})();
