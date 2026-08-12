import logging

logger = logging.getLogger(__name__)


def noop_job() -> str:
    """Placeholder job so the scheduler has something to run in P0.

    Real jobs (ingestion, briefing generation, decay) land in P1/P3/P5.
    """
    logger.info("noop_job tick")
    return "ok"
