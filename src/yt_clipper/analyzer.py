"""
Highlight Analyzer Module:
- Chunks transcripts into coherent time windows
- Prompts local Ollama LLMs with viral / highlight criteria
- Parses and validates JSON timestamps, viral scores, and summaries
- Deduplicates and ranks highlight segments
"""

import json
import re
import requests
from typing import List, Dict, Any, Optional
from .ingest import parse_timestamp, format_timestamp
from .ollama_manager import DEFAULT_OLLAMA_URL


def chunk_transcript(
    transcript: List[Dict[str, Any]],
    chunk_duration_sec: int = 240,  # 4 minutes
    overlap_sec: int = 40          # 40 seconds overlap
) -> List[Dict[str, Any]]:
    """
    Split timestamped transcript into overlapping chunks so highlights
    spanning segment boundaries are not missed.
    """
    if not transcript:
        return []

    chunks = []
    total_len = len(transcript)
    i = 0

    while i < total_len:
        chunk_start_sec = transcript[i]["start"]
        chunk_target_end = chunk_start_sec + chunk_duration_sec
        chunk_items = []
        next_i = -1

        for j in range(i, total_len):
            item = transcript[j]
            chunk_items.append(item)

            if item["start"] >= (chunk_target_end - overlap_sec) and next_i == -1:
                next_i = j

            if item["end"] >= chunk_target_end:
                break

        if not chunk_items:
            break

        lines = [f"[{item['start_str']}] {item['text']}" for item in chunk_items]
        chunk_end_sec = chunk_items[-1]["end"]

        chunks.append({
            "start_sec": chunk_start_sec,
            "end_sec": chunk_end_sec,
            "start_str": format_timestamp(chunk_start_sec),
            "end_str": format_timestamp(chunk_end_sec),
            "text": "\n".join(lines),
            "item_count": len(chunk_items),
        })

        if j >= total_len - 1:
            break

        if next_i != -1 and next_i > i:
            i = next_i
        else:
            i = j + 1

    return chunks


def extract_json_array(text: str) -> List[Dict[str, Any]]:
    """Robustly extract and parse a JSON array from LLM response text."""
    text = text.strip()

    # If wrapped in markdown code fence
    fence_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except Exception:
            pass

    # Search for any [ ... ] bracket block
    array_match = re.search(r"\[\s*\{.*?\}\s*\]", text, re.DOTALL)
    if array_match:
        try:
            return json.loads(array_match.group(0))
        except Exception:
            pass

    # If single object { ... } was returned, wrap it
    obj_match = re.search(r"\{[^{}]*\"start_time\"[^{}]*\}", text, re.DOTALL)
    if obj_match:
        try:
            return [json.loads(obj_match.group(0))]
        except Exception:
            pass

    return []


def analyze_chunk_with_llm(
    chunk: Dict[str, Any],
    model: str,
    base_url: str = DEFAULT_OLLAMA_URL
) -> List[Dict[str, Any]]:
    """
    Prompt Ollama model to evaluate a transcript chunk and extract top highlights.
    """
    prompt = f"""You are a professional video editor and viral clip curator.
Your task is to analyze the following timestamped transcript and identify the most engaging, viral, or insightful moments (podcasts, gaming, debates, storytelling).

Criteria for a "Good Moment":
1. STRONG HOOK: Begins with an intriguing question, bold claim, intense moment, or sudden event. Include the setup so the audience knows what is being discussed.
2. STANDALONE & COMPLETE: Makes complete sense on its own. Contains the beginning, middle, and end of the thought/story.
3. CLEAR CONCLUSION: Ends naturally after the punchline, insight, or reaction (not cut mid-sentence).
4. DURATION: Typically 20 to 120 seconds. Do NOT output tiny 5-second fragments without context.

Transcript segment:
---
{chunk['text']}
---

Output a valid JSON array of highlight candidates. If there are no good highlights in this segment, return an empty array `[]`.
Each candidate must have:
- "title": Catchy headline (max 8 words)
- "start_time": Precise start timestamp from the transcript (format HH:MM:SS)
- "end_time": Precise end timestamp from the transcript (format HH:MM:SS)
- "score": Rating from 1 to 10 (10 = incredible viral moment, 7 = solid engaging clip, <6 = skip)
- "reason": Why this moment is good (1 sentence)
- "hook": The opening sentence or hook of the clip

Respond ONLY with the JSON array:
[
  {{
    "title": "...",
    "start_time": "HH:MM:SS",
    "end_time": "HH:MM:SS",
    "score": 9,
    "reason": "...",
    "hook": "..."
  }}
]
"""

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 700,
        }
    }

    try:
        res = requests.post(f"{base_url}/api/generate", json=payload, timeout=90)
        res.raise_for_status()
        raw_text = res.json().get("response", "")
        candidates = extract_json_array(raw_text)
        return candidates
    except Exception as e:
        print(f"  [Warning] LLM analysis error on chunk {chunk['start_str']} - {chunk['end_str']}: {e}")
        return []


def deduplicate_and_rank_highlights(
    highlights: List[Dict[str, Any]],
    min_score: int = 7,
    min_duration_sec: int = 5,
    max_duration_sec: int = 180
) -> List[Dict[str, Any]]:
    """
    Validates, filters, deduplicates overlapping highlights, and sorts by score.
    """
    valid = []
    for h in highlights:
        try:
            start_str = h.get("start_time") or h.get("start")
            end_str = h.get("end_time") or h.get("end")
            score = int(h.get("score", 7))
            title = h.get("title", "Untitled Highlight").strip()
            reason = h.get("reason", "").strip()
            hook = h.get("hook", "").strip()

            if not start_str or not end_str:
                continue

            start_sec = parse_timestamp(start_str)
            end_sec = parse_timestamp(end_str)
            duration = end_sec - start_sec

            if duration < min_duration_sec or duration > max_duration_sec:
                continue
            if score < min_score:
                continue

            valid.append({
                "title": title,
                "start_time": format_timestamp(start_sec),
                "end_time": format_timestamp(end_sec),
                "start_sec": round(start_sec, 2),
                "end_sec": round(end_sec, 2),
                "duration_sec": round(duration, 2),
                "score": score,
                "reason": reason,
                "hook": hook,
            })
        except Exception:
            continue

    valid.sort(key=lambda x: (x["score"], -x["duration_sec"]), reverse=True)

    unique_highlights = []
    for candidate in valid:
        c_start, c_end = candidate["start_sec"], candidate["end_sec"]
        overlap_found = False

        for existing in unique_highlights:
            e_start, e_end = existing["start_sec"], existing["end_sec"]
            inter_start = max(c_start, e_start)
            inter_end = min(c_end, e_end)
            if inter_end > inter_start:
                inter_len = inter_end - inter_start
                c_len = c_end - c_start
                e_len = e_end - e_start
                if (inter_len / min(c_len, e_len)) > 0.4:
                    overlap_found = True
                    break

        if not overlap_found:
            unique_highlights.append(candidate)

    unique_highlights.sort(key=lambda x: x["start_sec"])
    return unique_highlights
