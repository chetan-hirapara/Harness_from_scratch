"""Render the orchestrator's tool DAG to an image.

Instantiates the real SupportAgentOrchestrator so the drawn graph exactly matches
what runs (same depends_on edges and computed execution levels). Viz-only; not
required by the agent at runtime.

Usage:
    python draw_dag.py            # writes dag.png
    python draw_dag.py out.png    # custom output path
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: render straight to file
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import networkx as nx

from support_agent_tools import TOOLS
from support_agent_orchestrator import SupportAgentOrchestrator

BASE = Path(__file__).parent
SPEC = BASE / "support_agent_spec.yaml"

# One color per pipeline stage.
STAGE_COLORS = {
    "intake": "#4C9AFF",
    "lookup": "#57D9A3",
    "validation": "#FFC400",
    "assessment": "#FF8B00",
    "calculation": "#B39DDB",
    "decision": "#F76707",
    "execution": "#00B8D9",
    "response": "#FF5C93",
}


def build_graph(orch: SupportAgentOrchestrator) -> nx.DiGraph:
    g = nx.DiGraph()
    for tool, tool_def in orch.tool_defs.items():
        g.add_node(
            tool,
            layer=orch.execution_levels.get(tool, 0),
            stage=tool_def.get("stage", "other"),
        )
    for tool, deps in orch.dag.items():
        for dep in deps:
            g.add_edge(dep, tool)
    return g


def main(out_path: str) -> None:
    orch = SupportAgentOrchestrator(str(SPEC), TOOLS)
    g = build_graph(orch)

    # Columns = execution levels (left -> right), matching parallel run order.
    pos = nx.multipartite_layout(g, subset_key="layer", align="vertical")
    max_level = max(orch.execution_levels.values(), default=0)

    fig, ax = plt.subplots(figsize=(2.4 * (max_level + 1) + 3, 11))

    node_colors = [STAGE_COLORS.get(g.nodes[n]["stage"], "#B0BEC5") for n in g.nodes]

    nx.draw_networkx_edges(
        g, pos, ax=ax, edge_color="#8A94A6", arrows=True,
        arrowsize=16, width=1.4, node_size=2600,
        connectionstyle="arc3,rad=0.04",
    )
    nx.draw_networkx_nodes(
        g, pos, ax=ax, node_color=node_colors, node_size=2600,
        edgecolors="#2B2B2B", linewidths=1.0,
    )
    nx.draw_networkx_labels(
        g, pos, ax=ax,
        labels={n: n.replace("_", "\n") for n in g.nodes},
        font_size=7, font_color="#101418",
    )

    # Level headers along the top.
    for lvl in range(max_level + 1):
        xs = [p[0] for n, p in pos.items() if orch.execution_levels.get(n) == lvl]
        if xs:
            ax.text(sum(xs) / len(xs), 1.12, f"Level {lvl}",
                    ha="center", va="bottom", fontsize=10, fontweight="bold",
                    color="#4B5563")

    legend = [mpatches.Patch(color=c, label=s) for s, c in STAGE_COLORS.items()]
    ax.legend(handles=legend, title="stage", loc="lower center",
              ncol=len(STAGE_COLORS), bbox_to_anchor=(0.5, -0.08), frameon=False, fontsize=8)

    ax.set_title("Customer Support Refund Agent — Tool Execution DAG "
                 f"({g.number_of_nodes()} tools, {max_level + 1} levels)",
                 fontsize=13, fontweight="bold")
    ax.margins(0.12)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    print(f"\u2713 DAG image written to {out_path}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else str(BASE / "dag.png")
    main(out)
