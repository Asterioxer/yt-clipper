# 🎬 yt-clipper

> **100% Free, Local AI YouTube Video Highlight Finder & Clipper**  
> *Zero subscriptions • Zero paid API keys • Auto-managed local models via Ollama & FFmpeg*

An open-source Python tool that ingests YouTube videos/podcasts/streams, identifies the best viral/highlight moments using a **Local LLM**, and automatically slices them into MP4 clips.

---

## ⚡ Key Highlights

- **Zero Setup Required:** If you don't have a model yet, `yt-clipper` automatically downloads a fast, high-quality model (e.g. `llama3.2:3b`) directly into Ollama with a live progress bar.
- **Fast Transcript Extraction:** Pulls accurate millisecond captions via `youtube-transcript-api` in seconds without downloading gigabytes of video.
- **Local AI Analysis:** Evaluates hooks, punchlines, debates, and emotional climaxes locally on your GPU/CPU via Ollama.
- **Instant Video Slicing:** Uses FFmpeg to cut MP4 clips (both fast stream-copy mode and frame-accurate mode).
- **Automated Metadata & Reports:** Saves `highlights_summary.json` and a clean Markdown table for editors.

---

## 📦 Installation

### From Source (Local Development)
```bash
git clone https://github.com/your-username/yt-clipper.git
cd yt-clipper
pip install -e .
```

### From Wheel / Tarball
```bash
pip install dist/yt_clipper-0.1.0-py3-none-any.whl
```

### Prerequisites
1. **Ollama:** Download and install from [ollama.com](https://ollama.com). (The tool will automatically start the background server and pull a model if you don't have one).
2. **FFmpeg:** Ensure `ffmpeg` is installed on your system PATH.

---

## 🚀 Quick Usage

Once installed, you can run `clipper` or `yt-clipper` from anywhere in your terminal:

### 1. Scan Highlights in Seconds (No Video Download)
Perfect for quickly checking if a 2-hour podcast has good moments before downloading:
```bash
clipper --url "https://www.youtube.com/watch?v=VIDEO_ID" --no-cut
```

### 2. Extract and Automatically Cut MP4 Clips
Analyzes the video and automatically saves sliced MP4 video files into `clips/`:
```bash
clipper --url "https://www.youtube.com/watch?v=VIDEO_ID" --min-score 8
```

### 3. Specify a Custom Model
```bash
clipper --url "https://youtu.be/..." --model "qwen3.5:4b"
```
*(If the specified model is not downloaded yet, `yt-clipper` will automatically pull it for you!)*

---

## ⚙️ Options & Arguments

| Flag | Shorthand | Default | Description |
| :--- | :---: | :---: | :--- |
| `--url` | `-u` | *(Prompt)* | YouTube URL or 11-char Video ID |
| `--min-score` | `-s` | `7` | Minimum highlight quality score (1–10) |
| `--model` | `-m` | Auto | Ollama model name (auto-selects or auto-downloads) |
| `--no-cut` | | `False` | Only extract timestamps and save reports; skip video download |
| `--fast-cut` | | `False` | Instant lossless stream copy (`-c copy`) without re-encoding |
| `--output-dir` | `-o` | `clips` | Directory to save clips and summaries |
| `--quality` | `-q` | `1080` | Max video height for downloaded video (e.g. 720, 1080) |
| `--chunk-size` | | `240` | Transcript context window size in seconds |

---

## 📂 Output Folder Structure

When processing with clipping enabled:
```
clips/
├── highlights_summary.json           # Structured JSON metadata
├── highlights_summary.md             # Markdown table of timestamps & hooks
├── source/
│   └── [video_id].mp4                # Downloaded source video
└── clips/
    ├── clip_01_sample_highlight.mp4
    ├── clip_02_sample_highlight.mp4
    └── ...
```

---

## 📄 License
MIT License. Free for personal and commercial use.
