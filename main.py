import json
import uuid
from pathlib import Path

from flask import Flask, Response, render_template, request, jsonify, stream_with_context

from agent import generate_tracking_script_stream
from scheduler import scheduler, add_job, remove_job, get_jobs, run_script

SCRIPTS_DIR = Path(__file__).parent / "scripts"
DATA_DIR = Path(__file__).parent / "tracked_data"
JOBS_FILE = Path(__file__).parent / "jobs.json"

app = Flask(__name__)


def load_jobs_meta() -> dict:
    if JOBS_FILE.exists():
        return json.loads(JOBS_FILE.read_text())
    return {}


def save_jobs_meta(meta: dict):
    JOBS_FILE.write_text(json.dumps(meta, indent=2))


@app.route("/")
def index():
    meta = load_jobs_meta()
    scheduler_jobs = {j["id"]: j for j in get_jobs()}
    jobs = []
    for job_id, info in meta.items():
        data_file = DATA_DIR / f"{job_id}.jsonl"
        records = []
        if data_file.exists():
            for line in data_file.read_text().splitlines():
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        jobs.append({
            "id": job_id,
            "url": info["url"],
            "what": info["what"],
            "description": info["description"],
            "cron": info["cron"],
            "next_run": scheduler_jobs.get(job_id, {}).get("next_run"),
            "records": records[-10:],
        })
    return render_template("index.html", jobs=jobs)


@app.post("/create")
def create_job():
    url = request.form.get("url", "").strip()
    what = request.form.get("what", "").strip()
    if not url or not what:
        return jsonify({"detail": "url and what are required"}), 400

    job_id = str(uuid.uuid4())[:8]

    def generate():
        try:
            for event in generate_tracking_script_stream(url, what, job_id):
                yield f"data: {json.dumps(event)}\n\n"

                if event["type"] == "done":
                    result = event["result"]
                    script_path = SCRIPTS_DIR / f"{job_id}.py"
                    script_path.write_text(result["script"])

                    cron = result.get("suggested_schedule", "0 * * * *")
                    try:
                        add_job(job_id, str(script_path), cron)
                    except ValueError as e:
                        yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"
                        return

                    meta = load_jobs_meta()
                    meta[job_id] = {
                        "url": url,
                        "what": what,
                        "description": result["description"],
                        "cron": cron,
                        "script": str(script_path),
                    }
                    save_jobs_meta(meta)

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@app.post("/run/<job_id>")
def run_now(job_id: str):
    meta = load_jobs_meta()
    if job_id not in meta:
        return jsonify({"detail": "Job not found"}), 404
    script_path = SCRIPTS_DIR / f"{job_id}.py"
    if not script_path.exists():
        return jsonify({"detail": "Script not found"}), 404
    run_script(str(script_path))
    return jsonify({"status": "ok"})


@app.delete("/job/<job_id>")
def delete_job(job_id: str):
    meta = load_jobs_meta()
    if job_id not in meta:
        return jsonify({"detail": "Job not found"}), 404
    remove_job(job_id)
    del meta[job_id]
    save_jobs_meta(meta)
    (SCRIPTS_DIR / f"{job_id}.py").unlink(missing_ok=True)
    (DATA_DIR / f"{job_id}.jsonl").unlink(missing_ok=True)
    return jsonify({"status": "deleted"})


@app.get("/data/<job_id>")
def get_data(job_id: str):
    data_file = DATA_DIR / f"{job_id}.jsonl"
    if not data_file.exists():
        return jsonify({"records": []})
    records = []
    for line in data_file.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return jsonify({"records": records})


@app.get("/script/<job_id>")
def get_script(job_id: str):
    script_path = SCRIPTS_DIR / f"{job_id}.py"
    if not script_path.exists():
        return jsonify({"detail": "Script not found"}), 404
    return jsonify({"script": script_path.read_text()})


if __name__ == "__main__":
    scheduler.start()
    meta = load_jobs_meta()
    for job_id, info in meta.items():
        script_path = SCRIPTS_DIR / f"{job_id}.py"
        if script_path.exists():
            try:
                add_job(job_id, str(script_path), info["cron"])
            except Exception as e:
                print(f"[startup] could not restore job {job_id}: {e}")

    try:
        app.run(host="0.0.0.0", port=7070, debug=False, use_reloader=False)
    finally:
        scheduler.shutdown()
