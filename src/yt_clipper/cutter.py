"""
FFmpeg Video Slicer:
- Losslessly or frame-accurately extracts highlight clips using ffmpeg.
- Sanitizes clip names and outputs organized MP4 files.
- Generates JSON and Markdown summary reports for editors.
"""

import os
import re
import subprocess
from typing import List, Dict, Any, Optional


def sanitize_filename(name: str) -> str:
    """Sanitize title into a safe file name."""
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:60]


def cut_clip(
    source_video_path: str,
    start_time: str,
    end_time: str,
    output_path: str,
    accurate: bool = True
) -> bool:
    """
    Cut a video clip from source_video_path between start_time and end_time.
    If accurate=True, re-encodes with fast x264 for exact keyframe boundaries.
    If accurate=False, uses stream copy (-c copy) for instantaneous cuts.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    if accurate:
        cmd = [
            "ffmpeg",
            "-y",
            "-ss", start_time,
            "-to", end_time,
            "-i", source_video_path,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "128k",
            output_path
        ]
    else:
        cmd = [
            "ffmpeg",
            "-y",
            "-ss", start_time,
            "-to", end_time,
            "-i", source_video_path,
            "-c", "copy",
            output_path
        ]

    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except subprocess.CalledProcessError as e:
        print(f"  [Error cutting clip {output_path}]: {e.stderr.decode('utf-8', errors='ignore')[:300]}")
        return False


def cut_all_highlights(
    source_video_path: str,
    highlights: List[Dict[str, Any]],
    output_dir: str = "clips",
    accurate: bool = True
) -> List[Dict[str, Any]]:
    """
    Cut all highlight segments into MP4 files and save summary metadata.
    """
    os.makedirs(output_dir, exist_ok=True)
    results = []

    for idx, h in enumerate(highlights, 1):
        safe_title = sanitize_filename(h["title"])
        start_clean = h["start_time"].replace(":", "-")
        end_clean = h["end_time"].replace(":", "-")
        filename = f"clip_{idx:02d}_[{start_clean}_to_{end_clean}]_{safe_title}.mp4"
        out_path = os.path.join(output_dir, filename)

        success = cut_clip(
            source_video_path=source_video_path,
            start_time=h["start_time"],
            end_time=h["end_time"],
            output_path=out_path,
            accurate=accurate
        )

        if success:
            file_size_mb = round(os.path.getsize(out_path) / (1024 * 1024), 2)
            results.append({
                **h,
                "clip_number": idx,
                "file_path": os.path.abspath(out_path),
                "filename": filename,
                "file_size_mb": file_size_mb,
            })

    return results
