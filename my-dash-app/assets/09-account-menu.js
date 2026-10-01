// Native details supplies click, Enter/Space, and expanded-state semantics.
(() => {
  const account = () => document.getElementById("sidebar-account");
  document.addEventListener("click", (event) => {
    const menu = account();
    if (menu?.open && !menu.contains(event.target)) menu.open = false;
  });
  document.addEventListener("keydown", (event) => {
    const menu = account();
    if (event.key === "Escape" && menu?.open) {
      menu.open = false;
      menu.querySelector("summary").focus();
      event.preventDefault();
    }
  });
  document.addEventListener("focusin", (event) => {
    const menu = account();
    if (menu?.open && !menu.contains(event.target)) menu.open = false;
  });
})();
