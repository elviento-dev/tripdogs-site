(function () {
  "use strict";

  // Console greeting
  console.log(
    "%c  /\\_/\\\n ( o.o )\n  > ^ <\nTripDogs says hello.",
    "font-family: monospace; color: #82AFF5;"
  );

  // Triple-click on the TripDogs logo: short glitch effect.
  // A single click still navigates to Home after a short pause.
  var logo = document.querySelector("[data-logo]");
  if (!logo) return;

  var clicks = 0;
  var timer = null;

  function glitch() {
    logo.classList.remove("glitch");
    void logo.offsetWidth; // restart animation
    logo.classList.add("glitch");
    setTimeout(function () { logo.classList.remove("glitch"); }, 800);
  }

  logo.addEventListener("click", function (e) {
    e.preventDefault();
    clicks += 1;
    clearTimeout(timer);

    if (clicks >= 3) {
      clicks = 0;
      glitch();
      return;
    }

    timer = setTimeout(function () {
      var count = clicks;
      clicks = 0;
      if (count < 3) {
        window.location.href = logo.getAttribute("href");
      }
    }, 350);
  });
})();
