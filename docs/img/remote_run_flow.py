#!/usr/bin/env python3
"""Draw docs/img/remote-run-flow.png - how a script reaches another machine.

Regenerate with:  python3 docs/img/remote_run_flow.py
"""
from _flowlib import (LANE_A, LANE_B, MUTED, FONT,
                      arrow, box, figure, lane, legend, save)


def main():
    fig, ax = figure(15, 11)

    lane(ax, 1, 2, 47, 94, "HEAD NODE  (where you type the command)", LANE_A)
    lane(ax, 52, 2, 47, 94, "EACH REMOTE NODE  (over ssh)", LANE_B)

    hx, nx = 24.5, 75.5

    # ---- head node ----
    box(ax, hx, 90, 42, 8, [
        "You run",
        "mlcr get,mlperf,multi-node,system-info",
        "--ssh_ids=bench@node1,bench@node2"])

    box(ax, hx, 77, 42, 9, [
        "get-mlperf-multi-node-system-info / customize.py",
        "preprocess:  one mlc.access(remote_run)",
        "per ssh id  -  a node that fails now fails the run"])

    box(ax, hx, 62, 42, 8, [
        "mlcflow  automation/script/remote_run.py",
        "assembles the list of commands the node",
        "will run, then hands it to the ssh layer"])

    ax.text(hx + 2.5, 55.7, "the command list", ha="left", va="center",
            fontsize=9.5, color=MUTED, style="italic", **FONT)
    box(ax, hx, 51, 40, 4.4, [
        "", "1.  run the mlcflow installer"], mono_from=0)
    box(ax, hx, 45, 40, 4.4, ["", "2.  . mlcflow/bin/activate"], mono_from=0)
    box(ax, hx, 39, 40, 4.4,
        ["", "3.  provision.resolve()  <-  the only new step"],
        kind="new", mono_from=0)
    box(ax, hx, 33, 40, 4.4,
        ["", "4.  mlcr get,mlperf,single-node,system-info"], mono_from=0)

    box(ax, hx, 24, 42, 7.5, [
        "script/remote-run-commands",
        "ssh user@host \"cmd1 ; cmd2 ; cmd3 ; cmd4\""])

    # ---- remote node ----
    box(ax, nx, 62, 42, 9, [
        "1-2.  installer, then activate",
        "system packages  ->  python venv",
        "->  pip install mlcflow"])

    box(ax, nx, 46.5, 42, 10.5, [
        "3.  what this node should install   (NEW)",
        "pip install mlc-scripts==1.2.0a4",
        "or   mlc pull repo <repo> --checkout=<ref>",
        "unset  ->  nothing added, as before"], kind="new")

    box(ax, nx, 31, 42, 9, [
        "4.  run the single-node script",
        "writes /tmp/mlperf-system-info-single-node",
        "/mlperf-system-info-single-node-N.json"])

    box(ax, nx, 17, 42, 6, [
        "results come back",
        "rsync  -  a file that never arrives is now fatal"])

    box(ax, hx, 10, 42, 8, [
        "customize.py  postprocess",
        "aggregate  ->  system-info-multi-node.json",
        "with  mlc_scripts_version.consistent"])

    # ---- arrows ----
    arrow(ax, (hx, 86), (hx, 81.5))
    arrow(ax, (hx, 72.5), (hx, 66))
    arrow(ax, (hx, 57.6), (hx, 53.9))
    arrow(ax, (hx, 30.3), (hx, 28.4))
    arrow(ax, (45.5, 24), (nx - 21, 60), label="ssh", rad=-0.18)
    arrow(ax, (nx, 57.5), (nx, 52))
    arrow(ax, (nx, 41), (nx, 35.7))
    arrow(ax, (nx, 26.4), (nx, 20.2))
    arrow(ax, (nx - 21, 17), (45.5, 11.5), label="rsync", rad=-0.18)

    legend(ax, 54, 6.1, [("new", "everything this change adds")])
    save(fig, "remote-run-flow.png")


if __name__ == "__main__":
    main()
