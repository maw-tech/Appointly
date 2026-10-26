// Small progressive enhancements. Every feature also works without JavaScript.
document.addEventListener("DOMContentLoaded", function () {
  // Ask before submitting destructive forms (e.g. cancelling an appointment).
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });

  // Availability page: grey out the times of days that are switched off.
  document.querySelectorAll("[data-day-row]").forEach(function (row) {
    var toggle = row.querySelector("[data-working-toggle]");
    var status = row.querySelector("[data-day-status]");
    function update() {
      row.classList.toggle("closed", !toggle.checked);
      status.textContent = toggle.checked ? "Open" : "Closed";
    }
    toggle.addEventListener("change", update);
    update();
  });

  // Keep the selected date visible in the horizontal date strip.
  var selected = document.querySelector(".date-chip.selected");
  if (selected) {
    selected.scrollIntoView({ block: "nearest", inline: "center" });
  }
});
