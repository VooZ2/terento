(() => {
  const tablist = document.querySelector("[data-map-feature-tabs]");
  if (!tablist) return;

  const tabs = [...tablist.querySelectorAll('[role="tab"]')];
  const panels = tabs
    .map((tab) => document.getElementById(tab.getAttribute("aria-controls")))
    .filter(Boolean);
  if (tabs.length < 2 || panels.length !== tabs.length) return;

  const activate = (nextTab, moveFocus = false) => {
    tabs.forEach((tab) => {
      const selected = tab === nextTab;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
    panels.forEach((panel) => {
      panel.hidden = panel.getAttribute("aria-labelledby") !== nextTab.id;
    });
    if (moveFocus) nextTab.focus();
  };

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activate(tab));
    tab.addEventListener("keydown", (event) => {
      const direction = event.key === "ArrowRight" || event.key === "ArrowDown"
        ? 1
        : event.key === "ArrowLeft" || event.key === "ArrowUp"
          ? -1
          : 0;
      if (direction) {
        event.preventDefault();
        activate(tabs[(index + direction + tabs.length) % tabs.length], true);
      } else if (event.key === "Home" || event.key === "End") {
        event.preventDefault();
        activate(tabs[event.key === "Home" ? 0 : tabs.length - 1], true);
      }
    });
  });

  activate(tabs.find((tab) => tab.getAttribute("aria-selected") === "true") || tabs[0]);
})();
