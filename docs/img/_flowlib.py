"""Shared drawing helpers for the diagrams in this directory.

Kept deliberately small: boxes, diamonds, arrows and lanes on a 0-100 grid.
Every diagram here is generated, so it can be corrected rather than redrawn.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                  # noqa: E402
from matplotlib.patches import (FancyArrowPatch, FancyBboxPatch,  # noqa: E402
                                Polygon)

INK = "#1f2933"
MUTED = "#6b7480"
LANE_A = "#eef2f7"
LANE_B = "#f6f1ea"

# Box styles: (fill, border, linewidth)
STYLES = {
    "plain": ("#ffffff", "#9aa5b1", 1.2),
    "new": ("#dff3e3", "#2f8f4e", 2.0),
    "bad": ("#fdecea", "#c0392b", 1.8),
    "good": ("#e8f0fb", "#2f6fb0", 1.8),
    "note": ("#f4f4f5", "#c9ced6", 1.0),
}

FONT = {"family": "DejaVu Sans"}
MONO = {"family": "DejaVu Sans Mono"}


def figure(width=15, height=11):
    fig, ax = plt.subplots(figsize=(width, height))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    return fig, ax


def lane(ax, x, y, w, h, label, colour, label_dy=1.8):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.6,rounding_size=1.2",
        facecolor=colour, edgecolor="none", zorder=0))
    if label:
        ax.text(x + w / 2, y + h + label_dy, label, ha="center", va="center",
                fontsize=13, fontweight="bold", color=MUTED, **FONT)


def box(ax, cx, cy, w, h, lines, kind="plain", mono_from=1, step=3.0):
    """One step. lines[:mono_from] are headings, the rest monospace detail."""
    fill, border, lw = STYLES[kind]
    ax.add_patch(FancyBboxPatch(
        (cx - w / 2, cy - h / 2), w, h,
        boxstyle="round,pad=0.4,rounding_size=0.8",
        facecolor=fill, edgecolor=border, linewidth=lw, zorder=2))
    top = cy + (len(lines) - 1) * step / 2
    for n, text in enumerate(lines):
        head = n < mono_from
        ax.text(cx, top - n * step, text, ha="center", va="center",
                fontsize=10.5 if head else 9.2,
                fontweight="bold" if head else "normal",
                color=INK if head else MUTED, zorder=3,
                **(FONT if head else MONO))


def diamond(ax, cx, cy, w, h, lines, step=2.7):
    ax.add_patch(Polygon(
        [(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2),
         (cx - w / 2, cy)],
        closed=True, facecolor="#fff8e6", edgecolor="#c99a2e",
        linewidth=1.6, zorder=2))
    top = cy + (len(lines) - 1) * step / 2
    for n, text in enumerate(lines):
        ax.text(cx, top - n * step, text, ha="center", va="center",
                fontsize=9.6 if n == 0 else 8.8,
                fontweight="bold" if n == 0 else "normal",
                color=INK, zorder=3, **(FONT if n == 0 else MONO))


def arrow(ax, xy_from, xy_to, label=None, dashed=False, rad=0.0,
          colour=None, label_side="above", label_dx=0.0):
    ax.add_patch(FancyArrowPatch(
        xy_from, xy_to, arrowstyle="-|>", mutation_scale=15, linewidth=1.4,
        color=colour or MUTED, zorder=1,
        linestyle="--" if dashed else "-",
        connectionstyle=f"arc3,rad={rad}"))
    if label:
        mx = (xy_from[0] + xy_to[0]) / 2 + label_dx
        my = (xy_from[1] + xy_to[1]) / 2
        dy, va = (1.3, "bottom") if label_side == "above" else (-1.3, "top")
        ax.text(mx, my + dy, label, ha="center", va=va, fontsize=9,
                color=colour or MUTED, style="italic", **FONT)


def legend(ax, x, y, entries, gap=3.4):
    """entries: list of (kind, text)."""
    for n, (kind, text) in enumerate(entries):
        fill, border, lw = STYLES[kind]
        cy = y - n * gap
        ax.add_patch(FancyBboxPatch(
            (x, cy - 1.0), 3.2, 2.0,
            boxstyle="round,pad=0.2,rounding_size=0.4",
            facecolor=fill, edgecolor=border, linewidth=lw))
        ax.text(x + 4.6, cy, text, ha="left", va="center", fontsize=10,
                color=INK, **FONT)


def save(fig, name):
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    fig.savefig(out, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(out)
    return out
