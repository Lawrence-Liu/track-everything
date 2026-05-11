import subprocess
import sys
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = BackgroundScheduler()


def run_script(script_path: str):
    """Execute a tracking script using the uv-managed Python."""
    python = sys.executable
    result = subprocess.run(
        [python, script_path],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        print(f"[scheduler] script {script_path} failed:\n{result.stderr}")
    else:
        print(f"[scheduler] script {script_path} ok:\n{result.stdout}")


def add_job(job_id: str, script_path: str, cron_expression: str):
    """Schedule a job with a cron expression like '*/30 * * * *'."""
    parts = cron_expression.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {cron_expression}")
    minute, hour, day, month, day_of_week = parts
    trigger = CronTrigger(
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
    )
    scheduler.add_job(
        run_script,
        trigger=trigger,
        args=[script_path],
        id=job_id,
        replace_existing=True,
    )


def remove_job(job_id: str):
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)


def get_jobs() -> list[dict]:
    jobs = []
    for job in scheduler.get_jobs():
        next_run = job.next_run_time.isoformat() if job.next_run_time else None
        jobs.append({"id": job.id, "next_run": next_run, "trigger": str(job.trigger)})
    return jobs
