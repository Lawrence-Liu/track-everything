import json
import os
import httpx

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = """You are an expert Python web scraping engineer. When given a website URL and a description of what information to track, you generate a clean, self-contained Python script that:

1. Fetches the webpage using httpx (sync, not async)
2. Parses HTML with BeautifulSoup4
3. Extracts the requested information
4. Appends results as a JSON line to DATA_FILE
5. Prints a summary of what was found

Requirements:
- The script must be completely self-contained and runnable with `python script.py`
- Use only these libraries: httpx, beautifulsoup4, lxml (they are pre-installed)
- Store results by appending a JSON object (one per line) to DATA_FILE
- Each result must include a "timestamp" field (ISO 8601 format) and a "url" field
- Handle errors gracefully (network errors, missing elements) with try/except
- Set a realistic User-Agent header

Respond with ONLY a JSON object (no markdown fences) in this exact format:
{"script": "<the complete python script>", "description": "<one sentence describing what is tracked>", "suggested_schedule": "<cron expression like '*/30 * * * *' for every 30 min>"}"""


def generate_tracking_script(url: str, what_to_track: str, job_id: str) -> dict:
    data_file = f"/home/lawrence/tracking-everything/tracked_data/{job_id}.jsonl"
    user_msg = f"URL: {url}\nWhat to track: {what_to_track}\nDATA_FILE = \"{data_file}\""

    response = httpx.post(
        API_URL,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 4096,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_msg}],
        },
        timeout=60,
    )
    response.raise_for_status()

    text = response.json()["content"][0]["text"].strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        end = -1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end])

    return json.loads(text)
