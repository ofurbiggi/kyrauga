const initSiteNavigation = () => {
  const navRoot = document.querySelector("[data-site-nav]");

  if (!navRoot) {
    return;
  }

  const openButton = navRoot.querySelector("[data-nav-open]");
  const closeButton = navRoot.querySelector("[data-nav-close]");
  const overlay = navRoot.querySelector("[data-nav-overlay]");
  const panel = navRoot.querySelector("[data-nav-panel]");
  const focusTarget = navRoot.querySelector("[data-nav-focus]");
  let lastFocusedElement = null;

  if (!openButton || !closeButton || !overlay || !panel) {
    return;
  }

  const syncExpandedState = (isOpen) => {
    openButton.setAttribute("aria-expanded", String(isOpen));
    closeButton.setAttribute("aria-expanded", String(isOpen));
  };

  const openMenu = () => {
    lastFocusedElement = document.activeElement instanceof HTMLElement ? document.activeElement : openButton;
    overlay.classList.remove("pointer-events-none", "opacity-0");
    panel.classList.remove("translate-y-6", "opacity-0");
    document.body.classList.add("overflow-hidden");
    syncExpandedState(true);
    window.setTimeout(() => {
      (focusTarget || closeButton).focus();
    }, 120);
  };

  const closeMenu = () => {
    overlay.classList.add("pointer-events-none", "opacity-0");
    panel.classList.add("translate-y-6", "opacity-0");
    document.body.classList.remove("overflow-hidden");
    syncExpandedState(false);
    if (lastFocusedElement instanceof HTMLElement) {
      lastFocusedElement.focus();
    } else {
      openButton.focus();
    }
  };

  openButton.addEventListener("click", openMenu);
  closeButton.addEventListener("click", closeMenu);

  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) {
      closeMenu();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && openButton.getAttribute("aria-expanded") === "true") {
      closeMenu();
    }
  });
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initSiteNavigation, { once: true });
} else {
  initSiteNavigation();
}
