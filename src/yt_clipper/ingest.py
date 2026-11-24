"""
Ingestion module for YouTube videos:
- Extracts video ID & metadata (title, duration, channel, etc.)
- Fetches accurate timed transcripts via youtube-transcript-api (no video download required)
- Handles downloading video files via yt-dlp when cutting is requested.
"""

import re
import os
from typing import Dict, List, Any, Optional
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound


def extract_video_id(url_or_id: str) -> str:
    """Extract 11-character YouTube video ID from various URL formats."""
    url_or_id = url_or_id.strip()
    if len(url_or_id) == 11 and re.match(r"^[A-Za-z0-9_-]{11}$", url_or_id):
        return url_or_id

    patterns = [
        r"(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/|\/live\/)([A-Za-z0-9_-]{11})",
        r"^([A-Za-z0-9_-]{11})$",
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract a valid YouTube video ID from: {url_or_id}")


def format_timestamp(seconds: float) -> str:
    """Convert seconds into HH:MM:SS format."""
    total_sec = int(round(seconds))
    hrs = total_sec // 3600
    mins = (total_sec % 3600) // 60
    secs = total_sec % 60
    return f"{hrs:02d}:{mins:02d}:{secs:02d}"


def parse_timestamp(timestamp_str: str) -> float:
    """Convert HH:MM:SS or MM:SS to float seconds."""
    parts = timestamp_str.strip().split(":")
    if len(parts) == 3:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 1:
        return float(parts[0])
    raise ValueError(f"Invalid timestamp format: {timestamp_str}")


def get_video_metadata(url_or_id: str) -> Dict[str, Any]:
    """Fetch video metadata using yt-dlp without downloading media."""
    video_id = extract_video_id(url_or_id)
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return {
            "id": video_id,
            "url": url,
            "title": info.get("title", "Unknown Title"),
            "duration": info.get("duration", 0),
            "duration_str": format_timestamp(info.get("duration", 0)),
            "uploader": info.get("uploader", "Unknown Channel"),
            "description": info.get("description", "")[:500],
            "view_count": info.get("view_count", 0),
        }


def fetch_transcript(url_or_id: str, preferred_languages: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Fetch timed transcript segments without downloading video.
    Returns list of dicts: [{'start': float, 'end': float, 'start_str': str, 'end_str': str, 'text': str}, ...]
    """
    if preferred_languages is None:
        preferred_languages = ["en", "en-US", "en-GB"]

    video_id = extract_video_id(url_or_id)
    api = YouTubeTranscriptApi()

    snippets = None

    # 1. Try fetching directly with preferred languages
    try:
        snippets = api.fetch(video_id, languages=preferred_languages)
    except Exception:
        pass

    # 2. If direct fetch fails, list available transcripts and pick best or translate
    if not snippets:
        try:
            transcript_list = api.list(video_id)
            try:
                transcript = transcript_list.find_transcript(preferred_languages)
                snippets = transcript.fetch()
            except Exception:
                available = list(transcript_list)
                if available:
                    first = available[0]
                    if first.is_translatable:
                        snippets = first.translate("en").fetch()
                    else:
                        snippets = first.fetch()
        except (TranscriptsDisabled, NoTranscriptFound) as e:
            raise RuntimeError(f"No transcripts/captions are available on YouTube for video ID: {video_id}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to fetch transcript: {e}") from e

    if not snippets:
        raise RuntimeError(f"Could not retrieve any transcript for video ID: {video_id}")

    formatted_transcript = []
    for item in snippets:
        start_sec = getattr(item, "start", 0.0)
        dur_sec = getattr(item, "duration", 0.0)
        text = getattr(item, "text", "").strip()
        end_sec = start_sec + dur_sec

        if not text:
            continue

        formatted_transcript.append({
            "start": round(start_sec, 2),
            "end": round(end_sec, 2),
            "start_str": format_timestamp(start_sec),
            "end_str": format_timestamp(end_sec),
            "text": text,
        })

    return formatted_transcript


def download_source_video(url_or_id: str, output_dir: str = "downloads", max_height: int = 1080) -> str:
    """
    Download source video file using yt-dlp to output_dir.
    Returns the absolute path to the downloaded video file.
    """
    video_id = extract_video_id(url_or_id)
    url = f"https://www.youtube.com/watch?v={video_id}"
    os.makedirs(output_dir, exist_ok=True)
    out_tmpl = os.path.join(output_dir, f"{video_id}.%(ext)s")

    ydl_opts = {
        "format": f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": out_tmpl,
        "merge_output_format": "mp4",
        "quiet": False,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        base, _ = os.path.splitext(filename)
        mp4_path = f"{base}.mp4"
        if os.path.exists(mp4_path):
            return os.path.abspath(mp4_path)
        return os.path.abspath(filename)
