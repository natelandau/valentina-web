/**
 * Dice tumble animation — rapidly cycles random numbers on each die chip
 * before settling on the final value. Triggered after HTMX swaps in results.
 */
function initDiceTumble() {
    document.querySelectorAll(".dice-tumble").forEach(function (el) {
        var finalValue = el.dataset.value;
        var delay = parseInt(el.dataset.delay, 10);
        var result = el.dataset.result;
        var tumbleDuration = 800;
        var tumbleInterval = 50;

        setTimeout(function () {
            var start = Date.now();
            var timer = setInterval(function () {
                if (Date.now() - start >= tumbleDuration) {
                    el.textContent = finalValue;
                    clearInterval(timer);

                    el.classList.remove("die-neutral");
                    el.classList.add(result === "success" ? "die-success" : "die-failure");

                    var num = parseInt(finalValue, 10);
                    if (num === 10 || num === 1) {
                        el.classList.remove("opacity-0");
                        el.style.opacity = "1";
                        el.style.transform = "none";
                        el.style.animation = "none";
                        // Force reflow before applying glow
                        void el.offsetWidth;
                        el.style.animation = "";
                        el.classList.add(num === 10 ? "die-glow-success" : "die-glow-error");
                    }
                    return;
                }
                el.textContent = Math.floor(Math.random() * 10) + 1;
            }, tumbleInterval);
        }, delay);
    });
}

document.body.addEventListener("htmx:afterSwap", function (event) {
    if (event.detail.target.id === "roll-results") {
        initDiceTumble();
    }
});
