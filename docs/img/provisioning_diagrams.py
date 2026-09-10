#!/usr/bin/env python3
"""Draw the diagrams for docs/design/remote-provisioning.md.

Regenerate all four with:  python3 docs/img/provisioning_diagrams.py
"""
from _flowlib import (INK, LANE_A, LANE_B, MUTED, FONT,
                      arrow, box, diamond, figure, lane, legend, save)


# ---------------------------------------------------------------------------
def before_after():
    """What a worker actually ends up running, before and after."""
    fig, ax = figure(15, 8.5)

    lane(ax, 1, 6, 47, 80, "BEFORE", LANE_B)
    lane(ax, 52, 6, 47, 80, "AFTER   (--remote_mlc_scripts=1.2.0a4)", LANE_A)

    lx, rx = 24.5, 75.5

    for x in (lx, rx):
        box(ax, x, 78, 42, 8, [
            "Head node",
            "pip install mlc-scripts==1.2.0a4",
            "mlcflow 1.4.0a3  +  scripts 1.2.0a4"], kind="good")

    arrow(ax, (lx, 73), (lx, 66.5), label="ssh")
    arrow(ax, (rx, 73), (rx, 66.5), label="ssh")

    box(ax, lx, 61, 42, 8, [
        "Worker: install mlcflow",
        "pip install mlcflow",
        "->  whatever PyPI calls latest"], kind="bad")

    box(ax, rx, 61, 42, 8, [
        "Worker: install mlcflow",
        "pip install mlcflow",
        "->  whatever PyPI calls latest"])

    arrow(ax, (lx, 56.5), (lx, 50))
    arrow(ax, (rx, 56.5), (rx, 50))

    box(ax, lx, 44, 42, 9, [
        "Worker: where do scripts come from?",
        "nothing installed them, so mlcflow",
        "falls back to cloning  dev", ], kind="bad")

    box(ax, rx, 44, 42, 9, [
        "Worker: where do scripts come from?",
        "pip install mlc-scripts==1.2.0a4",
        "the fallback never fires"], kind="new")

    arrow(ax, (lx, 39), (lx, 32.5))
    arrow(ax, (rx, 39), (rx, 32.5))

    box(ax, lx, 27, 42, 8, [
        "Worker ends up running",
        "mlcflow latest  +  scripts @ dev",
        "neither is what you asked for"], kind="bad")

    box(ax, rx, 27, 42, 8, [
        "Worker ends up running",
        "mlcflow >=1.4.0a3  +  scripts 1.2.0a4",
        "pulled in as the package's dependency"], kind="good")

    arrow(ax, (lx, 22.5), (lx, 17))
    arrow(ax, (rx, 22.5), (rx, 17))

    box(ax, lx, 12, 42, 7, [
        "Aggregated output",
        "mlc_scripts_version  absent entirely"], kind="bad")

    box(ax, rx, 12, 42, 7, [
        "Aggregated output",
        "mlc_scripts_version.consistent = true"], kind="good")

    save(fig, "provisioning-before-after.png")


# ---------------------------------------------------------------------------
def modes():
    """How provision.resolve() picks a mode and what it emits."""
    fig, ax = figure(16, 12)

    ax.text(50, 96, "provision.resolve()   -   all of this runs on the head "
            "node, before any ssh", ha="center", va="center", fontsize=13,
            fontweight="bold", color=MUTED, **FONT)

    sx = 38  # the spine

    box(ax, sx, 89, 60, 9, [
        "inputs",
        "--remote_provision    --remote_mlc_scripts    --remote_repo",
        "--remote_repo_ref    --remote_mlcflow"])
    arrow(ax, (sx, 84.5), (sx, 80.5))

    diamond(ax, sx, 76, 32, 8, ["do the flags contradict?"])

    arrow(ax, (54, 76), (68.5, 76), label="yes")
    box(ax, 84, 74, 30, 18, [
        "REFUSED, before any ssh",
        "--remote_mlcflow  with a package pin",
        "--remote_mlcflow  with mirror",
        "mirror  with any explicit pin",
        "both kinds of pin at once",
        "package with no version",
        "repo with no ref"], kind="bad", step=2.7)

    arrow(ax, (sx, 72), (sx, 67), label="no")

    box(ax, sx, 61, 64, 10, [
        "pick the mode",
        "named by --remote_provision, otherwise inferred from the pin:",
        "--remote_mlc_scripts -> package     --remote_repo_ref -> repo",
        "neither -> default"], step=2.8)

    # fan out to the four modes
    arrow(ax, (sx, 56), (sx, 52.6))
    xs = [12.5, 37.5, 62.5, 87.5]
    ax.plot([xs[0], xs[-1]], [52, 52], color=MUTED, linewidth=1.4, zorder=1)
    for x in xs:
        arrow(ax, (x, 52), (x, 48.6))

    box(ax, xs[0], 44, 22, 7.5, ["default", "nothing was asked for"])
    box(ax, xs[1], 44, 22, 7.5, ["package",
        "a version was pinned"], kind="new")
    box(ax, xs[2], 44, 22, 7.5, ["repo", "a ref was pinned"], kind="new")
    box(ax, xs[3], 44, 22, 9.5, [
        "mirror", "match this machine",
        "-> becomes package or repo"], kind="new")

    for x in xs[:3]:
        arrow(ax, (x, 39.8), (x, 36.5))

    box(ax, xs[0], 31, 22, 6.5, ["emits", "(nothing)"], kind="note")
    box(ax, xs[1], 31, 22, 8.5, [
        "emits", "pip install", "\"mlc-scripts==1.2.0a4\""], kind="note")
    box(ax, xs[2], 31, 22, 8.5, [
        "emits", "mlc pull repo <repo>", "--checkout=<ref>"], kind="note")

    arrow(ax, (xs[1], 26.3), (44, 22.5))
    arrow(ax, (xs[2], 26.3), (56, 22.5))

    box(ax, 50, 17.5, 64, 7, [
        "each emitted command aborts the node if it fails",
        "<cmd> || { echo \"MLC_PROVISION_FAILED: ...\"; exit 1; }"],
        kind="new")

    arrow(ax, (50, 13.6), (50, 9.5))
    box(ax, 50, 6, 64, 5.5, [
        "", "inserted after  . mlcflow/bin/activate,  before the mlcr line"],
        mono_from=0)

    save(fig, "provisioning-modes.png")


# ---------------------------------------------------------------------------
def mirror():
    """What --remote_provision=mirror reads off the head node."""
    fig, ax = figure(16, 11)

    ax.text(50, 97, "--remote_provision=mirror   -   reading the head node",
            ha="center", va="center", fontsize=13, fontweight="bold",
            color=MUTED, **FONT)

    box(ax, 50, 90, 46, 7.5, [
        "which repo did this script come from?",
        "longest matching path  -  never alias or uid"])
    arrow(ax, (50, 86), (50, 84.5))

    diamond(ax, 50, 79, 30, 9, ["does it have a .git?", "checked FIRST"])

    box(ax, 87, 88, 24, 11, [
        "why .git is checked first",
        "an editable install is both",
        "a checkout and a package;",
        "only the checkout says what",
        "is really running here"], kind="note", step=2.4)
    arrow(ax, (75, 85), (62, 81.5), dashed=True)

    arrow(ax, (38, 77), (21, 73.2), label="yes")
    arrow(ax, (62, 77), (66, 73.5), label="no", label_dx=3)

    # ---- left column: a git checkout ----
    diamond(ax, 18, 68, 24, 9, ["uncommitted changes?", "tracked files only"])
    arrow(ax, (30, 68), (32, 68), label="yes", label_dx=-1)
    box(ax, 40, 68, 15, 10, [
        "REFUSED", "those edits", "cannot reach", "the nodes"],
        kind="bad", step=2.4)

    arrow(ax, (18, 63.5), (18, 57), label="no")
    diamond(
        ax, 18, 52, 24, 9, [
            "is the commit pushed?", "on any remote branch"])
    arrow(ax, (30, 52), (32, 52), label="no", label_dx=-1)
    box(ax, 40, 52, 15, 9, [
        "REFUSED", "the nodes", "cannot fetch it"], kind="bad", step=2.4)

    arrow(ax, (18, 47.5), (18, 42.5), label="yes")
    box(ax, 18, 36, 30, 12, [
        "send: repo mode",
        "mlc pull repo <origin>",
        "--checkout=<commit>",
        "+ this machine's mlcflow"], kind="new", step=2.7)

    # ---- right column: a packaged install ----
    diamond(ax, 68, 68, 26, 10,
            ["is it the installed", "mlc-scripts package?"])
    arrow(ax, (81, 68), (83.5, 68), label="no", label_dx=-1)
    box(ax, 91, 68, 14, 11, [
        "REFUSED", "not a checkout", "and not a", "package  -  no",
        "version to send"], kind="bad", step=2.3)

    arrow(ax, (68, 63), (68, 56.5), label="yes")
    box(ax, 68, 50, 30, 10, [
        "send: package mode",
        "pip install",
        "\"mlc-scripts==<version>\""], kind="new")

    box(ax, 68, 32, 46, 8, [
        "the package brings its own mlcflow",
        "which is why --remote_mlcflow is refused here"], kind="note")
    arrow(ax, (68, 44.5), (68, 36.5))

    box(ax, 50, 18, 72, 7.5, [
        "every refusal names a way forward",
        "commit and push   |   --remote_repo_ref=<ref>   |   "
        "--remote_copy_mlc_repos"], kind="note")

    legend(ax, 3, 9, [("new", "what gets sent to the nodes"),
                      ("bad", "refused on the head node, before any ssh")])

    save(fig, "provisioning-mirror.png")


# ---------------------------------------------------------------------------
def failures():
    """The four places a silent failure now stops the run."""
    fig, ax = figure(14, 9)

    ax.text(50, 95, "Where a lost node used to disappear quietly",
            ha="center", va="center", fontsize=13, fontweight="bold",
            color=MUTED, **FONT)

    rows = [
        (78, "1.  provisioning fails on the node",
         "pip install / mlc pull repo returns non-zero",
         "was: the script ran anyway on whatever was there",
         "now: the node's shell exits 1",
         "mlcflow  provision.py"),
        (58, "2.  a node cannot be reached or run",
         "mlc.access(remote_run) returns non-zero, or raises",
         "was: logger.error, loop continues",
         "now: every failed host named, run fails",
         "mpa  get-mlperf-multi-node-system-info/customize.py"),
        (38, "3.  the result file cannot be copied back",
         "rsync missing or the copy fails",
         "was: return value discarded",
         "now: the copy failure is returned",
         "mpa  remote-run-commands/customize.py"),
        (18, "4.  a node's file never arrives",
         "expected JSON not on disk at aggregation time",
         "was: logger.warning, node silently absent",
         "now: every missing node named, run fails",
         "mpa  get-mlperf-multi-node-system-info/customize.py"),
    ]

    for y, title, detail, was, now, where in rows:
        box(ax, 30, y, 54, 13, [title, detail, was, now],
            kind="new", step=2.9)
        ax.text(60, y, where, ha="left", va="center", fontsize=9,
                color=MUTED, **FONT)

    for y in (78, 58, 38):
        arrow(ax, (30, y - 7), (30, y - 13))

    box(ax, 45, 5, 76, 7, [
        "the point of all four",
        "a run that reports success now means every node reported  -  "
        "the count can no longer shrink in silence"], kind="note")

    save(fig, "provisioning-failures.png")


if __name__ == "__main__":
    before_after()
    modes()
    mirror()
    failures()
