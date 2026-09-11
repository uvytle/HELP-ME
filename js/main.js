document.querySelectorAll(".tab-link").forEach((link) => {
  link.addEventListener("click", () => {
    document.querySelectorAll(".tab-link").forEach((el) => el.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((el) => el.classList.remove("active"));

    link.classList.add("active");
    document.getElementById(link.dataset.tab).classList.add("active");
  });
});
