"""Contribution decomposition / attribution analysis.

Source: GSCPI contribution methodology.
Formula: % by Factor = SUM(signals_factor × weight) / SUM(all_weighted_signals)

Attribution dimensions:
    - By Source Layer: Primary % | Logistics % | Market % | Industry %
    - By Impact Pathway: Cost % | Time % | Compliance % | Availability %
    - By Jurisdiction: India % | UK % | Bilateral %
"""

from collections import defaultdict


def compute_attribution(
    events: list[dict],
) -> dict[str, dict[str, float]]:
    """Compute attribution percentages across three dimensions.

    Args:
        events: List of dicts with keys: weighted_score, source_layer,
                impact_pathway (semicolon-separated), jurisdiction

    Returns:
        {
            "source_layer": {"Primary": 0.72, "Industry": 0.28, ...},
            "impact_pathway": {"Compliance": 0.85, "Cost": 0.15, ...},
            "jurisdiction": {"India": 0.60, "UK": 0.40, ...},
        }
    """
    total_abs = sum(abs(e["weighted_score"]) for e in events)
    if total_abs == 0:
        return {"source_layer": {}, "impact_pathway": {}, "jurisdiction": {}}

    by_source: dict[str, float] = defaultdict(float)
    by_pathway: dict[str, float] = defaultdict(float)
    by_jurisdiction: dict[str, float] = defaultdict(float)

    for e in events:
        abs_score = abs(e["weighted_score"])

        by_source[e["source_layer"]] += abs_score

        # Impact pathway can be multi-valued: "Compliance;Time"
        pathways = [p.strip() for p in e["impact_pathway"].split(";")]
        per_pathway = abs_score / len(pathways)
        for p in pathways:
            by_pathway[p] += per_pathway

        by_jurisdiction[e["jurisdiction"]] += abs_score

    return {
        "source_layer": {k: v / total_abs for k, v in by_source.items()},
        "impact_pathway": {k: v / total_abs for k, v in by_pathway.items()},
        "jurisdiction": {k: v / total_abs for k, v in by_jurisdiction.items()},
    }
