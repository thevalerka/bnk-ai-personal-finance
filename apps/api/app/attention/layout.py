"""Interest vector -> LayoutPlan (docs/PLAN.md section 4.4).

**Scoping note** (see docs/DECISIONS.md ADR-0012): the plan's full vision is
a fully dynamic set of blocks, one per taxonomy node, arranged by a
squarified treemap. This phase reallocates space between the three P2
blocks that map cleanly onto a distinct, disjoint set of taxonomy nodes —
Quotes, Yield Curve, Sector Heatmap — rather than also generating new block
types per node. News/Calendar are cross-cutting list UIs (their value isn't
"bigger = more of what I want" the way a stat-tile or chart's is) and keep
a fixed span, outside the competition below.

Because the competing set is always exactly these three blocks, the
plan's "top-K nodes" step is a no-op here (K=3=len(BLOCK_NODES) always) and
"exploration: reserve ε=10% for an unengaged adjacent node" has no unused
adjacent node to sample from a fixed 3-block set — the min-area clamp below
substitutes for it: a block with zero engagement still keeps MIN_COLUMNS,
so the page never fully closes a door on an asset class the user hasn't
touched yet. Revisit both simplifications if/when the frontend grows
per-node dynamic blocks.
"""

import math

from pydantic import BaseModel

TAU = 1.5
MIN_AREA = 0.06
MAX_AREA = 0.40

GRID_COLUMNS = 12
# The plan's 6%/40% area clamps assume a treemap with many simultaneous
# blocks, where 6% of the page is still a legible size. Translated onto a
# single 12-column row shared by exactly 3 blocks, that fraction rounds to
# under one column — a block that thin can't render a tile grid or a chart.
# MIN/MAX_COLUMNS is the same policy (never fully starve a block, never let
# one dominate) re-scaled to stay legible at this row's actual denominator.
MIN_COLUMNS = 2
MAX_COLUMNS = 8

# Every leaf taxonomy node each P2 block visually represents (see the module
# docstring's scoping note). Disjoint by construction so a node's score
# never double-counts toward two blocks.
BLOCK_NODES: dict[str, list[str]] = {
    "quotes": ["equities.us_large_cap.broad_market", "crypto.majors.btc"],
    "yield_curve": [
        "fixed_income.rates_ust.short_end",
        "fixed_income.rates_ust.belly",
        "fixed_income.rates_ust.long_end",
    ],
    "heatmap": [
        "equities.us_large_cap.technology",
        "equities.us_large_cap.financials",
        "equities.us_large_cap.healthcare",
        "equities.us_large_cap.discretionary",
        "equities.us_large_cap.staples",
        "equities.us_large_cap.energy_sector",
        "equities.us_large_cap.industrials",
        "equities.us_large_cap.materials",
        "equities.us_large_cap.real_estate",
        "equities.us_large_cap.utilities",
        "equities.us_large_cap.communications",
    ],
}


class BlockPlan(BaseModel):
    block_type: str
    nodes: list[str]
    raw_score: float
    area_weight: float
    columns: int
    priority: int


class LayoutPlan(BaseModel):
    blocks: list[BlockPlan]


def block_scores(node_scores: dict[str, float]) -> dict[str, float]:
    """Sum each block's mapped nodes' current (already-decayed) scores."""
    return {
        block_type: sum(node_scores.get(node_id, 0.0) for node_id in nodes)
        for block_type, nodes in BLOCK_NODES.items()
    }


def softmax(scores: dict[str, float], tau: float = TAU) -> dict[str, float]:
    if not scores:
        return {}
    top = max(scores.values())  # subtract max for numerical stability
    exps = {k: math.exp((v - top) / tau) for k, v in scores.items()}
    total = sum(exps.values())
    return {k: v / total for k, v in exps.items()}


def clamp_and_renormalize(
    weights: dict[str, float], min_area: float = MIN_AREA, max_area: float = MAX_AREA
) -> dict[str, float]:
    clamped = {k: min(max(v, min_area), max_area) for k, v in weights.items()}
    total = sum(clamped.values())
    return {k: v / total for k, v in clamped.items()}


def area_weights_to_columns(
    weights: dict[str, float],
    total_columns: int = GRID_COLUMNS,
    min_columns: int = MIN_COLUMNS,
    max_columns: int = MAX_COLUMNS,
) -> dict[str, int]:
    """Largest-remainder apportionment: fractional area weights (summing to
    1) -> integer grid-column spans that always sum to exactly
    `total_columns` — a CSS Grid whose spans don't sum to the template's
    column count either overflows or leaves a gap, so this must be exact,
    not just "close"."""
    keys = list(weights)
    raw = {k: weights[k] * total_columns for k in keys}
    columns = {k: min(max_columns, max(min_columns, round(raw[k]))) for k in keys}

    diff = total_columns - sum(columns.values())
    # Give (or take) columns one at a time, largest-remainder-first, to
    # whichever block has the most room to absorb it without breaching a
    # clamp — guaranteed to terminate since every key becomes ineligible
    # once it hits its clamp.
    while diff != 0:
        eligible = [
            k
            for k in keys
            if (diff > 0 and columns[k] < max_columns) or (diff < 0 and columns[k] > min_columns)
        ]
        if not eligible:
            break
        remainders = {k: raw[k] - columns[k] for k in eligible}
        pick = max if diff > 0 else min
        target = pick(remainders, key=lambda k: remainders[k])
        step = 1 if diff > 0 else -1
        columns[target] += step
        diff -= step

    return columns


def compute_layout(node_scores: dict[str, float]) -> LayoutPlan:
    scores = block_scores(node_scores)
    weights = clamp_and_renormalize(softmax(scores))
    columns = area_weights_to_columns(weights)

    blocks = [
        BlockPlan(
            block_type=block_type,
            nodes=BLOCK_NODES[block_type],
            raw_score=scores[block_type],
            area_weight=weights[block_type],
            columns=columns[block_type],
            priority=0,
        )
        for block_type in BLOCK_NODES
    ]
    blocks.sort(key=lambda b: b.area_weight, reverse=True)
    for priority, block in enumerate(blocks, start=1):
        block.priority = priority
    return LayoutPlan(blocks=blocks)
