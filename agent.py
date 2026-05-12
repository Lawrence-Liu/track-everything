import json
import subprocess

PROMPT_TEMPLATE = """You are an expert Python web scraping engineer. Your task is to create a VERIFIED working tracking script. Follow these steps exactly:

**Step 1:** Use WebFetch to fetch this URL and analyze its actual HTML structure:
URL: {url}

**Step 2:** Write a Python script to /tmp/track_{job_id}.py that:
- Uses httpx (sync, not async) and BeautifulSoup4 + lxml
- Tracks: {what_to_track}
- Appends each result as a JSON line to /tmp/track_{job_id}.jsonl
- Includes "timestamp" (ISO 8601) and "url" fields in every result
- Has a realistic User-Agent header
- Has try/except error handling

**Step 3:** Run the script with Bash: `python /tmp/track_{job_id}.py`
- If it errors, fix the script and run again
- Try up to 3 times until it works

**Step 4:** Once the script runs successfully, output ONLY this JSON object (no markdown, no extra text):
{{"script": "<the verified script, but replace /tmp/track_{job_id}.jsonl with {data_file}>", "description": "<one sentence describing what is tracked>", "suggested_schedule": "<cron expression like '*/30 * * * *'>"}}"""


def generate_tracking_script_stream(url: str, what_to_track: str, job_id: str):
    """Yields SSE-compatible dicts. Final event is {type: done, result: {...}}."""
    data_file = f"/home/lawrence/tracking-everything/tracked_data/{job_id}.jsonl"
    prompt = PROMPT_TEMPLATE.format(
        url=url,
        what_to_track=what_to_track,
        job_id=job_id,
        data_file=data_file,
    )

    try:
        proc = subprocess.Popen(
            ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose",
             "--allowedTools", "WebFetch,Bash"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        yield {"type": "error", "text": "'claude' CLI not found. Is Claude Code installed?"}
        return

    final_text = None

    for raw_line in proc.stdout:
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        etype = event.get("type")

        if etype == "assistant":
            for block in event.get("message", {}).get("content", []):
                btype = block.get("type")
                if btype == "text":
                    text = block["text"].strip()
                    if text:
                        yield {"type": "text", "text": text}
                elif btype == "tool_use":
                    name = block.get("name", "")
                    inp = block.get("input", {})
                    if name == "WebFetch":
                        yield {"type": "tool", "tool": "WebFetch",
                               "text": f"Fetching {inp.get('url', url)}..."}
                    elif name == "Bash":
                        yield {"type": "tool", "tool": "Bash",
                               "text": f"$ {inp.get('command', '')}"}

        elif etype == "user":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_result":
                    content = block.get("content", "")
                    if isinstance(content, list):
                        text = "\n".join(c.get("text", "") for c in content if c.get("type") == "text")
                    else:
                        text = str(content)
                    if text.strip():
                        yield {"type": "output", "text": text[:1000]}

        elif etype == "result":
            final_text = event.get("result", "").strip()

    proc.wait()

    stderr_out = proc.stderr.read()
    if proc.returncode != 0:
        yield {"type": "error", "text": f"claude exited {proc.returncode}: {stderr_out}"}
        return

    if not final_text:
        yield {"type": "error", "text": "Claude returned no result."}
        return

    # Strip markdown fences if present
    if "```" in final_text:
        import re
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', final_text, re.DOTALL)
        if m:
            final_text = m.group(1)

    # If there's preamble text before the JSON object, extract the JSON
    if not final_text.startswith("{"):
        import re
        m = re.search(r'\{.*\}', final_text, re.DOTALL)
        if m:
            final_text = m.group()

    try:
        result = json.loads(final_text)
        yield {"type": "done", "result": result}
    except json.JSONDecodeError as e:
        yield {"type": "error", "text": f"Could not parse final JSON: {e}\n\n{final_text}"}
