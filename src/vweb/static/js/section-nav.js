/**
 * Priority+ section navigation.
 *
 * Measures the actual rendered width of each tab (and the "More" button)
 * against the container width, then decides how many tabs fit inline and
 * how many spill into the overflow dropdown. Runs on mount, on container
 * resize, and after web fonts settle.
 */
document.addEventListener("alpine:init", () => {
    Alpine.data("priorityNav", ({ items, active }) => ({
        items,
        active,
        visibleCount: 0,
        open: false,
        ready: false,
        tabWidths: [],
        moreWidth: 0,
        resizeObserver: null,

        init() {
            // Initial measurement after first paint — $refs are populated here.
            this.$nextTick(() => {
                this.captureWidths();
                this.computeFit();
                this.ready = true;
                this.resizeObserver = new ResizeObserver(() => this.computeFit());
                this.resizeObserver.observe(this.$refs.bar);
            });

            // Re-measure once web fonts load — label widths can shift when
            // fallback fonts are swapped for the real ones.
            if (document.fonts && document.fonts.ready) {
                document.fonts.ready.then(() => {
                    this.captureWidths();
                    this.computeFit();
                });
            }
        },

        destroy() {
            if (this.resizeObserver) {
                this.resizeObserver.disconnect();
            }
        },

        captureWidths() {
            const measureRow = this.$refs.measure;
            if (!measureRow) return;
            const tabs = measureRow.querySelectorAll("[data-measure-tab]");
            this.tabWidths = Array.from(tabs, (el) => el.getBoundingClientRect().width);
            const more = measureRow.querySelector("[data-measure-more]");
            this.moreWidth = more ? more.getBoundingClientRect().width : 0;
        },

        computeFit() {
            const bar = this.$refs.bar;
            if (!bar || this.tabWidths.length === 0) return;
            const available = bar.clientWidth;

            const total = this.tabWidths.reduce((sum, width) => sum + width, 0);
            if (total <= available) {
                this.visibleCount = this.items.length;
                return;
            }

            // Overflow needed — reserve room for the More button.
            const cap = available - this.moreWidth;
            let used = 0;
            let count = 0;
            for (const width of this.tabWidths) {
                if (used + width > cap) break;
                used += width;
                count++;
            }
            // Always keep at least one tab inline so the bar isn't just "More".
            this.visibleCount = Math.max(count, 1);
        },

        isOverflow(index) {
            return index >= this.visibleCount;
        },

        activeInOverflow() {
            const activeIndex = this.items.findIndex((item) => item.key === this.active);
            return activeIndex >= 0 && activeIndex >= this.visibleCount;
        },
    }));
});
