"""Render a saved per-agent topological graph."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx

COLORS = {
    "room": "#b8c0cc",
    "junction": "#f2b84b",
    "frontier": "#4aa8e0",
    "survivor_suspected": "#ee8a3b",
    "survivor_confirmed": "#e43f4f",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("graph", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = json.loads(args.graph.read_text())
    graph = nx.node_link_graph(data, edges="edges")
    positions = {
        node: (values["position"][0], -values["position"][1])
        for node, values in graph.nodes(data=True)
    }
    colors = [COLORS.get(values["kind"], "#dddddd") for _, values in graph.nodes(data=True)]
    labels = {
        node: values["kind"].replace("survivor_", "S:")[:8]
        for node, values in graph.nodes(data=True)
    }
    plt.figure(figsize=(9, 7))
    nx.draw_networkx(
        graph,
        positions,
        labels=labels,
        node_color=colors,
        node_size=700,
        font_size=7,
        width=1.2,
    )
    plt.title(f"Topological map: {graph.graph.get('owner', args.graph.stem)}")
    plt.axis("equal")
    plt.axis("off")
    plt.tight_layout()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(args.output, dpi=150, bbox_inches="tight")
        print(args.output)
    else:
        plt.show()


if __name__ == "__main__":
    main()
