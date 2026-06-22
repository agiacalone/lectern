"""Agate (Unicode block-character) chart primitives for the instructor report.

Deterministic, dependency-free, render-anywhere (Obsidian / GitHub / plain text /
print). No color, no glyphs beyond block elements.
"""


def bar_chart(rows, *, max_w: int = 24) -> str:
    """`LABEL ▏████ value`, one row per (label, value), bars scaled to the peak."""
    if not rows:
        return ""
    label_w = max(len(str(l)) for l, _ in rows)
    peak = max((v for _, v in rows), default=0) or 1
    lines = []
    for label, value in rows:
        n = round(value / peak * max_w) if value > 0 else 0
        lines.append(f"{str(label).ljust(label_w)} ▏{'█' * n} {value}")
    return "\n".join(lines)


def funnel(stages, *, max_w: int = 24) -> str:
    """Ordered bars (stage order preserved) — e.g. a ward-clear funnel."""
    return bar_chart(stages, max_w=max_w)


def histogram(values, bins, *, max_w: int = 24) -> str:
    """Bin `values` into `(label, lo, hi)` buckets (hi exclusive; last inclusive)."""
    counts = []
    for i, (label, lo, hi) in enumerate(bins):
        last = i == len(bins) - 1
        c = sum(1 for v in values if ((lo <= v <= hi) if last else (lo <= v < hi)))
        counts.append((label, c))
    return bar_chart(counts, max_w=max_w)
