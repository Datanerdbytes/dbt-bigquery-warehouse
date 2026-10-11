// Product storytelling is independent of session initialization and data loading.
function initializeShowcase() {
  const showcase = document.getElementById("auth-showcase");
  if (!showcase) return;
  const slides = [...showcase.querySelectorAll(".auth-slide")];
  const selectors = [...document.querySelectorAll("[data-slide]")];
  const rotation = showcase.querySelector('[data-carousel="rotation"]');
  const landing = document.body.classList.contains("landing-page");
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let active = 0;
  let timer = null;
  let hovered = false;
  function show(index) {
    const moveFocus = slides[active].contains(document.activeElement);
    active = (index + slides.length) % slides.length;
    slides.forEach((slide, i) => {
      slide.hidden = i !== active;
      slide.inert = i !== active;
      slide.setAttribute("aria-hidden", String(i !== active));
      slide.classList.toggle("auth-slide-enter", i === active);
    });
    selectors.forEach((button) => {
      if (Number(button.dataset.slide) === active)
        button.setAttribute("aria-current", "true");
      else button.removeAttribute("aria-current");
    });
    if (moveFocus) {
      showcase
        .querySelector(`.auth-carousel-tabs [data-slide="${active}"]`)
        .focus({ preventScroll: true });
    }
  }
  function stop() {
    window.clearInterval(timer);
    timer = null;
    if (rotation) {
      rotation.textContent = "Play";
      rotation.setAttribute("aria-label", "Play slideshow");
    }
    showcase.querySelector(".auth-slides").setAttribute("aria-live", "polite");
  }
  function play() {
    stop();
    if (
      motion.matches ||
      document.hidden ||
      (landing && (hovered || showcase.querySelector(":focus-visible")))
    )
      return;
    showcase.querySelector(".auth-slides").setAttribute("aria-live", "off");
    if (rotation) {
      rotation.textContent = "Pause";
      rotation.setAttribute("aria-label", "Pause slideshow");
    }
    timer = window.setInterval(() => show(active + 1), landing ? 6000 : 9000);
  }
  selectors.forEach((button) =>
    button.addEventListener("click", () => {
      stop();
      show(Number(button.dataset.slide));
      if (landing) play();
    }),
  );
  for (const [action, delta] of [
    ["previous", -1],
    ["next", 1],
  ]) {
    showcase
      .querySelector(`[data-carousel="${action}"]`)
      ?.addEventListener("click", () => {
        stop();
        show(active + delta);
      });
  }
  rotation?.addEventListener("click", () => (timer === null ? play() : stop()));
  const hoverTargets = landing
    ? [...showcase.querySelectorAll(".auth-preview")]
    : [showcase];
  hoverTargets.forEach((target) => {
    target.addEventListener("pointerenter", () => {
      hovered = true;
      stop();
    });
    target.addEventListener("pointerleave", () => {
      hovered = false;
      if (landing) play();
    });
  });
  document.addEventListener("focusin", (event) => {
    if (landing) play();
    else if (event.target !== rotation) stop();
  });
  if (landing) {
    document.addEventListener("focusout", () => window.setTimeout(play, 0));
  }
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stop();
    else if (landing) play();
  });
  window.addEventListener("pagehide", stop);
  if (landing) window.addEventListener("pageshow", play);
  motion.addEventListener("change", () => {
    if (landing) play();
    else if (motion.matches) stop();
    if (rotation) rotation.hidden = motion.matches;
  });
  show(0);
  if (rotation) rotation.hidden = motion.matches;
  showcase.querySelector(".auth-carousel-controls").hidden = false;
  play();
}
initializeShowcase();
