import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from app.jobs import noop_job

logging.basicConfig(level=logging.INFO)


def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler()
    scheduler.add_job(noop_job, "interval", minutes=15, id="noop_job")
    return scheduler


if __name__ == "__main__":
    build_scheduler().start()
