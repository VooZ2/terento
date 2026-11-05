(() => {
  document.querySelectorAll("[data-map-switch]").forEach((root) => {
    const image = root.querySelector("[data-map-image]");
    const buttons = [...root.querySelectorAll("[data-map-style]")];
    if (!image || buttons.length < 2) return;

    const source = (style) => image.src.replace(/(hero|edge)-[a-z-]+\.webp/, (_, scene) => `${scene}-${style}.webp`);
    // Warm the cache so switching styles does not flash an empty screen.
    buttons.forEach((button) => { new Image().src = source(button.dataset.mapStyle); });

    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        buttons.forEach((other) => other.setAttribute("aria-pressed", String(other === button)));
        image.src = source(button.dataset.mapStyle);
        image.alt = button.dataset.mapAlt;
      });
    });
  });
})();
