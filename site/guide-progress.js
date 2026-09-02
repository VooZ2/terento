(() => {
  const navigation = document.querySelector("[data-guide-progress]");
  if (!navigation) return;
  const links = [...navigation.querySelectorAll("a[href^='#']")];
  const sections = links
    .map((link) => document.getElementById(link.getAttribute("href").slice(1)))
    .filter(Boolean);
  if (!sections.length) return;

  const setCurrent = (section) => {
    links.forEach((link) => {
      const current = link.getAttribute("href") === `#${section.id}`;
      if (current) link.setAttribute("aria-current", "location");
      else link.removeAttribute("aria-current");
    });
  };

  const update = () => {
    const offset = Math.max(96, Math.round(window.innerHeight * 0.2));
    const visible = sections.filter((section) => section.getBoundingClientRect().top <= offset);
    setCurrent((visible.at(-1) || sections[0]));
  };

  let frame = 0;
  const schedule = () => {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      update();
    });
  };
  window.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", schedule, { passive: true });
  update();
})();
