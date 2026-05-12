import json
import subprocess

PROMPT_TEMPLATE = """You are an expert Python web scraping engineer. I need you to create a tracking script.

First, fetch this URL and examine the actual HTML structure:
URL: {url}

What to track: {what_to_track}

After fetching the page and understanding its structure, write a self-contained Python script that:
1. Fetches the webpage using httpx (sync, not async)
2. Parses HTML with BeautifulSoup4
3. Extracts the requested information
4. Appends results as a JSON line to DATA_FILE = "{data_file}"
5. Prints a summary of what was found

Requirements:
- Completely self-contained, runnable with `python script.py`
- Use only: httpx, beautifulsoup4, lxml
- Each result must include "timestamp" (ISO 8601) and "url" fields
- Handle errors gracefully with try/except
- Set a realistic User-Agent header

Respond with ONLY a JSON object (no markdown fences):
{{"script": "<the complete python script>", "description": "<one sentence describing what is tracked>", "suggested_schedule": "<cron expression like '*/30 * * * *'"}}"""


def generate_tracking_script(url: str, what_to_track: str, job_id: str) -> dict:
    data_file = f"/home/lawrence/tracking-everything/tracked_data/{job_id}.jsonl"
    prompt = PROMPT_TEMPLATE.format(
        url=url,
        what_to_track=what_to_track,
        data_file=data_file,
    )

    result = subprocess.run(
        [
            "claude",
            "-p", prompt,
            "--output-format", "json",
            "--allowedTools", "WebFetch",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Claude Code exited {result.returncode}: {result.stderr}")

    output = json.loads(result.stdout)
    text = output["result"].strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        end = -1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end])

    return json.loads(text)
