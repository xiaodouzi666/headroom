"""Plot measured allocator event history, without interpolating wall-clock time."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def render_timeline(timeline, output_path, oom_events=None, step_boundaries=None):
    """Render event-index curves; unknown step positions are not invented."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
    points = sorted(timeline, key=lambda point: point["event_index"])
    if points:
        x = [point["event_index"] for point in points]
        allocated = [point["allocated_bytes"] / 1e9 for point in points]
        reserved = [point["reserved_bytes"] / 1e9 for point in points]
        axis.plot(x, allocated, color="#1769aa", linewidth=1.8, label="Allocated")
        axis.plot(x, reserved, color="#595959", linewidth=1.5, linestyle="--", label="Reserved")
        span = max(1, max(x) - min(x))
        axis.set_xlim(min(x), max(x) + 0.025 * span)
    else:
        axis.text(
            0.5, 0.5, "Allocation event history unavailable", ha="center", transform=axis.transAxes
        )
    marked = set()
    for event in oom_events or []:
        index = event.get("event_index") if isinstance(event, dict) else event
        if index is None or index in marked:
            continue
        axis.axvline(
            index,
            color="#bf3434",
            linewidth=1.5,
            zorder=5,
            label="OOM" if not marked else None,
        )
        axis.annotate(
            "OOM",
            xy=(index, 0.98),
            xycoords=("data", "axes fraction"),
            xytext=(-5, 0),
            textcoords="offset points",
            ha="right",
            va="top",
            color="#bf3434",
            fontsize=9,
            zorder=6,
        )
        marked.add(index)
    steps_marked = 0
    for boundary in step_boundaries or []:
        index = boundary.get("event_index") if isinstance(boundary, dict) else boundary
        if index is None:
            continue
        axis.axvline(
            index,
            color="#8b6c25",
            alpha=0.35,
            linewidth=0.7,
            label="Optimizer step" if not steps_marked else None,
        )
        steps_marked += 1
    axis.set_xlabel("Allocator event index (not wall-clock time)")
    axis.set_ylabel("GPU memory (GB, decimal)")
    axis.set_ylim(bottom=0)
    axis.set_title("CUDA allocator history")
    axis.grid(axis="y", alpha=0.18)
    if points or marked or steps_marked:
        axis.legend(loc="best", frameon=False)
    figure.savefig(output, dpi=150, metadata={"Software": "Headroom"})
    plt.close(figure)
    return str(output)
