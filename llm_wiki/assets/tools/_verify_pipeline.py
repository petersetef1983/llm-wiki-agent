"""Verify full Graphify pipeline: detect -> extract_python -> build -> cluster."""
import sys
from pathlib import Path, WindowsPath

if not hasattr(WindowsPath, "__len__"):
    WindowsPath.__len__ = lambda self: len(str(self))

from graphify.detect import detect
from graphify.extract import extract_python
from graphify.build import build
from graphify.cluster import cluster

root = Path(r"d:\project\codex\llm-wiki-v1.3\kb\tools")
result = detect(root)
py_files = [Path(f) for f in result["files"].get("code", []) if f.endswith(".py")]
print(f"Python files: {len(py_files)}")

extractions = []
for p in py_files:
    try:
        ext_result = extract_python(p)
        nodes = ext_result.get("nodes", []) if ext_result else []
        edges = ext_result.get("edges", []) if ext_result else []
        if nodes or edges:
            extractions.append(ext_result)
            print(f"  + {p.name}: {len(nodes)} nodes, {len(edges)} edges")
    except Exception as e:
        print(f"  x {p.name}: {type(e).__name__}: {e}")

if extractions:
    G = build(extractions)
    print(f"\n=== Graph Built ===")
    print(f"Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")

    communities = cluster(G)
    print(f"\n=== Communities: {len(communities)} ===")

    for cid, node_ids in sorted(communities.items(), key=lambda x: -len(x[1])):
        labels = []
        for nid in node_ids[:5]:
            if nid in G.nodes:
                labels.append(G.nodes[nid].get("label", nid))
            else:
                labels.append(nid)
        print(f"  Community {cid} ({len(node_ids)} nodes): {', '.join(labels)}")

    top = sorted(G.nodes(), key=lambda n: G.degree(n), reverse=True)[:15]
    print("\n=== Top 15 God Nodes ===")
    for n in top:
        d = G.nodes[n]
        label = d.get("label", n)
        degree = G.degree(n)
        src = d.get("source_file", "")
        src_short = Path(src).name if src else ""
        print(f"  {label} ({degree} connections) [{src_short}]")

    # Edge confidence breakdown
    conf_counts = {}
    for u, v, edata in G.edges(data=True):
        conf = edata.get("confidence", "EXTRACTED")
        conf_counts[conf] = conf_counts.get(conf, 0) + 1
    print(f"\n=== Edge Confidence ===")
    for conf, count in sorted(conf_counts.items()):
        print(f"  {conf}: {count} ({count * 100 // G.number_of_edges()}%)")
else:
    print("No extractions produced")
