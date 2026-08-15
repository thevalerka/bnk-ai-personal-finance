"""Event scoring and exponential decay (docs/PLAN.md section 4.3).

Scores are decayed lazily on read/write rather than recomputed from full
event history: ``s_n(t) = Σ w_i · 2^(-(t - t_i)/half_life)`` collapses to an
incremental update because exponential decay is time-homogeneous — a stored
``(score, last_updated)`` pair decayed forward to "now" and summed with a
new event's weight is exactly equal to re-summing the whole series. That's
the whole trick: no history replay, no background decay job.

DAG propagation (docs/PLAN.md section 4.2 decay factors): an event on a leaf
node contributes to that node at full weight, its bucket at 0.6x, and its
asset class at 0.3x — a click on "technology" is also weak evidence of
interest in "equities" generally, just less so.
"""

from datetime import timedelta
from enum import StrEnum

from app.attention.taxonomy import Taxonomy

HALF_LIFE = timedelta(days=7)

# child (the event's own node) 1.0, parent (bucket) 0.6, grandparent
# (asset_class) 0.3 — docs/PLAN.md section 4.2.
PROPAGATION_FACTORS = (1.0, 0.6, 0.3)


class EventKind(StrEnum):
    IMPRESSION = "impression"
    DWELL = "dwell"
    HOVER = "hover"
    CLICK = "click"
    CHART_INTERACTION = "chart_interaction"
    SEARCH = "search"
    AGENT_MENTION = "agent_mention"
    PIN = "pin"
    MUTE = "mute"


# docs/PLAN.md section 4.3.
EVENT_WEIGHTS: dict[EventKind, float] = {
    EventKind.IMPRESSION: 0.2,
    EventKind.DWELL: 0.3,  # per additional 5s visible — caller multiplies by increments
    EventKind.HOVER: 0.5,
    EventKind.CLICK: 2.0,
    EventKind.CHART_INTERACTION: 2.5,
    EventKind.SEARCH: 3.0,
    EventKind.AGENT_MENTION: 4.0,
    EventKind.PIN: 8.0,
    EventKind.MUTE: -10.0,
}

# MUTE additionally caps the node's effective score (docs/PLAN.md: "set a
# floor override") so continued ambient engagement (impressions, dwell)
# can't quietly out-accumulate an explicit mute — only an explicit PIN lifts
# it. Enforced by the interest-vector service, not this module; the value
# lives here because it's part of the same weight table.
MUTE_CEILING = -5.0


def decay_factor(elapsed: timedelta) -> float:
    if elapsed <= timedelta(0):
        return 1.0
    half_lives: float = elapsed / HALF_LIFE
    return float(2.0**-half_lives)


def decayed_score(stored_score: float, elapsed: timedelta) -> float:
    """Score as of "now", given the score last written at `elapsed` ago."""
    return stored_score * decay_factor(elapsed)


def apply_event(stored_score: float, elapsed_since_last_update: timedelta, weight: float) -> float:
    """New stored score after an event of `weight` lands `elapsed_since_last_update`
    after the previous write. Decay-then-add, per the module docstring."""
    return decayed_score(stored_score, elapsed_since_last_update) + weight


def propagate(taxonomy: Taxonomy, node_id: str, weight: float) -> dict[str, float]:
    """Weight contribution to `node_id` and each of its DAG ancestors."""
    contributions: dict[str, float] = {}
    current: str | None = node_id
    for factor in PROPAGATION_FACTORS:
        if current is None:
            break
        contributions[current] = weight * factor
        current = taxonomy.parent(current)
    return contributions
