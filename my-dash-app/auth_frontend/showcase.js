// Product storytelling is independent of session initialization and data loading.
function initializeShowcase() {
  const showcase = document.getElementById("auth-showcase");
  if (!showcase) return;
  const slides = [...showcase.querySelectorAll(".auth-slide")];
  const selectors = [...document.querySelectorAll("[data-slide]")];
  const rotation = showcase.querySelector('[data-carousel="rotation"]');
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let active = 0;
  let timer = null;
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
    rotation.textContent = "Play";
    rotation.setAttribute("aria-label", "Play slideshow");
    showcase.querySelector(".auth-slides").setAttribute("aria-live", "polite");
  }
  function play() {
    stop();
    if (motion.matches || document.hidden) return;
    showcase.querySelector(".auth-slides").setAttribute("aria-live", "off");
    rotation.textContent = "Pause";
    rotation.setAttribute("aria-label", "Pause slideshow");
    timer = window.setInterval(() => show(active + 1), 9000);
  }
  selectors.forEach((button) =>
    button.addEventListener("click", () => {
      stop();
      show(Number(button.dataset.slide));
    }),
  );
  for (const [action, delta] of [
    ["previous", -1],
    ["next", 1],
  ]) {
    showcase
      .querySelector(`[data-carousel="${action}"]`)
      .addEventListener("click", () => {
        stop();
        show(active + delta);
      });
  }
  rotation.addEventListener("click", () => (timer === null ? play() : stop()));
  showcase.addEventListener("pointerenter", stop);
  document.addEventListener("focusin", (event) => {
    if (event.target !== rotation) stop();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stop();
  });
  window.addEventListener("pagehide", stop);
  motion.addEventListener("change", () => {
    if (motion.matches) stop();
    rotation.hidden = motion.matches;
  });
  show(0);
  rotation.hidden = motion.matches;
  showcase.querySelector(".auth-carousel-controls").hidden = false;
  play();
}
initializeShowcase();
