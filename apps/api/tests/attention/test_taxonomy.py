from app.attention.taxonomy import load_taxonomy


def test_default_weights_sum_to_one() -> None:
    taxonomy = load_taxonomy()
    weights = taxonomy.default_weights()
    # derivatives/fx-with-no-instruments carry a real (possibly zero)
    # default_weight, but only the six cold-start asset classes from
    # docs/PLAN.md section 4.4 are meant to sum to 1.0.
    cold_start = {"equities", "fixed_income", "macro", "crypto", "commodities", "fx"}
    assert sum(w for ac, w in weights.items() if ac in cold_start) == 1.0


def test_node_ids_are_three_level_dotted_paths() -> None:
    taxonomy = load_taxonomy()
    node_ids = taxonomy.node_ids()
    assert len(node_ids) > 0
    for node_id in node_ids:
        assert len(node_id.split(".")) == 3


def test_parent_walks_up_the_dag() -> None:
    taxonomy = load_taxonomy()
    node_id = "equities.us_large_cap.technology"
    assert taxonomy.parent(node_id) == "equities.us_large_cap"
    assert taxonomy.parent("equities.us_large_cap") == "equities"
    assert taxonomy.parent("equities") is None


def test_instrument_reverse_lookup() -> None:
    taxonomy = load_taxonomy()
    assert "equities.us_large_cap.technology" in taxonomy.nodes_for_instrument("XLK")
    # DGS10 legitimately tags two different lenses on the same instrument.
    dgs10_nodes = taxonomy.nodes_for_instrument("DGS10")
    assert "fixed_income.rates_ust.long_end" in dgs10_nodes
    assert "macro.cross_asset.fed_policy" in dgs10_nodes


def test_fx_has_no_fabricated_instruments() -> None:
    taxonomy = load_taxonomy()
    fx_nodes = [n for n in taxonomy.node_ids() if n.startswith("fx.")]
    assert fx_nodes == []
