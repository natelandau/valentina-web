/**
 * Priority+ section navigation with pinned active tab.
 *
 * Measures the actual rendered width of each tab (and the "More" button) and
 * decides which items fit inline vs. overflow. The active item is always
 * promoted into the visible set; the item it displaces drops into the More
 * dropdown. Re-runs on mount, container resize, and after web fonts settle.
 */
document.addEventListener("alpine:init", () => {
    Alpine.data("priorityNav", ({ items, active }) => ({
        items,
        active,
        open: false,
        ready: false,
        tabWidths: [],
        moreWidth: 0,
        barWidth: 0,
        layout: { visible: [], hidden: [] },
        resizeObserver: null,

        init() {
            this.$nextTick(() => {
                this.captureItemWidths();
                this.updateBarWidth();
                this.recompute();
                this.ready = true;
                this.resizeObserver = new ResizeObserver(() => {
                    this.updateBarWidth();
                    this.recompute();
                });
                this.resizeObserver.observe(this.$refs.bar);
            });

            // Item widths can shift when fallback fonts are swapped for the
            // real ones — re-capture after font load, then recompute.
            if (document.fonts && document.fonts.ready) {
                document.fonts.ready.then(() => {
                    this.captureItemWidths();
                    this.recompute();
                });
            }
        },

        destroy() {
            if (this.resizeObserver) {
                this.resizeObserver.disconnect();
            }
        },

        captureItemWidths() {
            const measureRow = this.$refs.measure;
            if (!measureRow) return;
            const tabs = measureRow.querySelectorAll("[data-measure-tab]");
            this.tabWidths = Array.from(tabs, (el) => el.getBoundingClientRect().width);
            const more = measureRow.querySelector("[data-measure-more]");
            this.moreWidth = more ? more.getBoundingClientRect().width : 0;
        },

        updateBarWidth() {
            const bar = this.$refs.bar;
            if (bar) {
                this.barWidth = bar.clientWidth;
            }
        },

        recompute() {
            const next = this._computeLayout();

            // Skip reassignment when the visible/hidden arrays are identical
            // to the current layout — no-op resizes shouldn't thrash Alpine's
            // reactive consumers (x-for templates re-render on every change).
            if (sameLayout(next, this.layout)) return;
            this.layout = next;
        },

        _computeLayout() {
            if (this.tabWidths.length === 0 || this.barWidth === 0) {
                return { visible: [...this.items], hidden: [] };
            }

            const total = this.tabWidths.reduce((sum, width) => sum + width, 0);
            if (total <= this.barWidth) {
                return { visible: [...this.items], hidden: [] };
            }

            // Overflow mode — reserve space for the More button.
            const cap = this.barWidth - this.moreWidth;
            const activeIndex = this.active
                ? this.items.findIndex((item) => item.key === this.active)
                : -1;
            const visibleSet = new Set();
            let used = 0;

            // Pin the active item into the visible set first so it's always
            // shown regardless of position in the original order.
            if (activeIndex >= 0) {
                visibleSet.add(activeIndex);
                used = this.tabWidths[activeIndex];
            }

            // Fill remaining slots with items in original order until the cap.
            for (let index = 0; index < this.items.length; index++) {
                if (index === activeIndex) continue;
                const width = this.tabWidths[index];
                if (used + width > cap) break;
                used += width;
                visibleSet.add(index);
            }

            // Fallback: always keep at least one item inline.
            if (visibleSet.size === 0 && this.items.length > 0) {
                visibleSet.add(0);
            }

            const visible = [];
            const hidden = [];
            for (let index = 0; index < this.items.length; index++) {
                if (visibleSet.has(index)) {
                    visible.push(this.items[index]);
                } else {
                    hidden.push(this.items[index]);
                }
            }
            return { visible, hidden };
        },
    }));
});

function sameLayout(a, b) {
    return sameItems(a.visible, b.visible) && sameItems(a.hidden, b.hidden);
}

function sameItems(a, b) {
    if (a.length !== b.length) return false;
    for (let index = 0; index < a.length; index++) {
        if (a[index] !== b[index]) return false;
    }
    return true;
}
