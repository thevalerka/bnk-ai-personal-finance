"""Attention-engine taxonomy DAG loader (docs/PLAN.md section 4.2).

Node identity is a dotted path: ``asset_class.bucket.node`` (leaf) or
``asset_class.bucket`` / ``asset_class`` for the two ancestor levels. Events
always target a leaf node; decay.py walks `parent()` to propagate score
upward at the child/parent/grandparent factors from the plan.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel

CONFIG_DIR = Path(__file__).resolve().parents[4] / "config"


class Node(BaseModel):
    instruments: list[str] = []


class Bucket(BaseModel):
    nodes: dict[str, Node] = {}


class AssetClass(BaseModel):
    default_weight: float = 0.0
    buckets: dict[str, Bucket] = {}


class Taxonomy(BaseModel):
    asset_classes: dict[str, AssetClass]

    def asset_class_ids(self) -> list[str]:
        return list(self.asset_classes)

    def bucket_ids(self) -> list[str]:
        return [
            f"{ac_id}.{bucket_id}"
            for ac_id, ac in self.asset_classes.items()
            for bucket_id in ac.buckets
        ]

    def node_ids(self) -> list[str]:
        return [
            f"{ac_id}.{bucket_id}.{node_id}"
            for ac_id, ac in self.asset_classes.items()
            for bucket_id, bucket in ac.buckets.items()
            for node_id in bucket.nodes
        ]

    def node(self, node_id: str) -> Node | None:
        parts = node_id.split(".")
        if len(parts) != 3:
            return None
        ac_id, bucket_id, leaf_id = parts
        ac = self.asset_classes.get(ac_id)
        bucket = ac.buckets.get(bucket_id) if ac else None
        return bucket.nodes.get(leaf_id) if bucket else None

    def parent(self, dotted_id: str) -> str | None:
        """Bucket id for a node, asset-class id for a bucket, None for an
        asset class (the DAG root)."""
        parts = dotted_id.split(".")
        return ".".join(parts[:-1]) if len(parts) > 1 else None

    def nodes_for_instrument(self, symbol: str) -> list[str]:
        """Reverse lookup: every leaf node id that lists this instrument.

        A symbol may legitimately tag more than one node (e.g. DGS10 is
        both a fixed_income.rates_ust.long_end instrument and a
        macro.cross_asset.fed_policy one) — different lenses on the same
        instrument, both real.
        """
        return [nid for nid in self.node_ids() if symbol in (self.node(nid) or Node()).instruments]

    def default_weights(self) -> dict[str, float]:
        """Cold-start interest vector, keyed by asset_class id."""
        return {ac_id: ac.default_weight for ac_id, ac in self.asset_classes.items()}


def load_taxonomy() -> Taxonomy:
    with (CONFIG_DIR / "taxonomy.yaml").open() as f:
        data = yaml.safe_load(f)
    return Taxonomy.model_validate(data)
