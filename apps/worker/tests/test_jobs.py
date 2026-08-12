from app.jobs import noop_job


def test_noop_job() -> None:
    assert noop_job() == "ok"
