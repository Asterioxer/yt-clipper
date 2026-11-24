#!/usr/bin/env python3
"""
CLI entry point for yt-clipper.
Can be executed directly or via the console script entry points (`clipper` / `yt-clipper`).
"""

import os
import sys
import json
import argparse
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .ingest import (
    get_video_metadata,
    fetch_transcript,
    download_source_video,
)
from .analyzer import (
    chunk_transcript,
    analyze_chunk_with_llm,
    deduplicate_and_rank_highlights,
)
from .cutter import cut_all_highlights
from .ollama_manager import prepare_model

console = Console()


def save_markdown_report(metadata: dict, highlights: list, output_path: str):
    """Save a clean Markdown summary for editors."""
    lines = [
        f"# Highlight Report: {metadata.get('title', 'Video Highlights')}",
        f"- **Channel:** {metadata.get('uploader', 'N/A')}",
        f"- **Source URL:** {metadata.get('url', 'N/A')}",
        f"- **Total Duration:** {metadata.get('duration_str', 'N/A')}",
        f"- **Highlights Found:** {len(highlights)}",
        "",
        "---",
        "",
        "| # | Timestamps | Duration | Score | Title | Hook / Opening | Reason |",
        "|---|---|---|---|---|---|---|",
    ]

    for idx, h in enumerate(highlights, 1):
        ts = f"`{h['start_time']} - {h['end_time']}`"
        dur = f"{int(h['duration_sec'])}s"
        score = f"⭐ **{h['score']}/10**"
        title = h['title'].replace("|", "-")
        hook = h.get('hook', '').replace("|", "-")
        reason = h.get('reason', '').replace("|", "-")
        lines.append(f"| {idx} | {ts} | {dur} | {score} | {title} | {hook} | {reason} |")

    lines.append("")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(
        prog="clipper",
        description="Extract the best highlights and viral moments from YouTube videos using Local LLMs (Ollama) & FFmpeg.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick scan for highlights (no video download):
  clipper --url "https://youtu.be/VIDEO_ID" --no-cut

  # Find highlights with minimum score 8 and cut MP4 clips:
  clipper --url "https://youtu.be/VIDEO_ID" --min-score 8

  # Specify a custom local Ollama model:
  clipper --url "https://youtu.be/VIDEO_ID" --model "qwen3.5:4b"
        """
    )
    parser.add_argument("--url", "-u", type=str, help="YouTube video URL or Video ID")
    parser.add_argument("--min-score", "-s", type=int, default=7, help="Minimum highlight score (1-10, default: 7)")
    parser.add_argument("--model", "-m", type=str, default=None, help="Local Ollama model name (default: auto-detected or auto-downloaded)")
    parser.add_argument("--output-dir", "-o", type=str, default="clips", help="Output directory (default: 'clips')")
    parser.add_argument("--quality", "-q", type=int, default=1080, help="Max video height in pixels for download (default: 1080)")
    parser.add_argument("--no-cut", action="store_true", help="Only identify timestamps and generate report; do not download or cut video")
    parser.add_argument("--fast-cut", action="store_true", help="Use instant stream copy (-c copy) instead of frame-accurate re-encode")
    parser.add_argument("--chunk-size", type=int, default=240, help="Transcript chunk size in seconds (default: 240)")
    parser.add_argument("--max-chunks", type=int, default=None, help="Limit number of chunks to analyze (useful for long 2h+ videos)")

    args = parser.parse_args()

    console.print(Panel.fit(
        "[bold cyan]🎬 Local AI YouTube Clipper[/bold cyan]\n"
        "[dim]100% Free • Zero Subscriptions • Auto-Managed Local LLM (Ollama) & FFmpeg[/dim]",
        border_style="cyan"
    ))

    # 1. Prompt for URL if not provided via CLI
    video_input = args.url
    if not video_input:
        video_input = console.input("\n[bold yellow]Enter YouTube URL or Video ID:[/bold yellow] ").strip()
        if not video_input:
            console.print("[red]No URL provided. Exiting.[/red]")
            sys.exit(1)

    # 2. Check and prepare Ollama model (auto-pulls if needed!)
    chosen_model = prepare_model(args.model)
    console.print(f"[green]✓[/green] Active Local LLM: [bold magenta]{chosen_model}[/bold magenta]")

    # 3. Ingest Video Metadata & Subtitles
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console
    ) as progress:
        task1 = progress.add_task("[cyan]Fetching video metadata...", total=None)
        try:
            metadata = get_video_metadata(video_input)
            progress.update(task1, completed=True)
        except Exception as e:
            console.print(f"[red]Failed to fetch video metadata: {e}[/red]")
            sys.exit(1)

        task2 = progress.add_task("[cyan]Fetching timestamped transcript...", total=None)
        try:
            transcript = fetch_transcript(video_input)
            progress.update(task2, completed=True)
        except Exception as e:
            console.print(f"[red]Transcript error: {e}[/red]")
            sys.exit(1)

    console.print(f"\n[bold]Title:[/bold] {metadata['title']}")
    console.print(f"[bold]Channel:[/bold] {metadata['uploader']} | [bold]Duration:[/bold] {metadata['duration_str']}")
    console.print(f"[bold]Transcript:[/bold] {len(transcript)} timed snippets loaded successfully.\n")

    # 4. Semantic Chunking
    chunks = chunk_transcript(transcript, chunk_duration_sec=args.chunk_size, overlap_sec=40)
    if args.max_chunks and len(chunks) > args.max_chunks:
        console.print(f"[yellow]Limiting analysis to first {args.max_chunks} of {len(chunks)} chunks (--max-chunks).[/yellow]")
        chunks = chunks[:args.max_chunks]
    else:
        console.print(f"[cyan]Analyzing content across {len(chunks)} contextual chunk(s)...[/cyan]")

    # 5. Analyze with Local LLM
    all_raw_highlights = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        llm_task = progress.add_task(f"[magenta]Running {chosen_model} highlight analysis...", total=len(chunks))
        for idx, chunk in enumerate(chunks, 1):
            progress.update(llm_task, description=f"[magenta]Analyzing segment {idx}/{len(chunks)} ({chunk['start_str']} - {chunk['end_str']})...")
            found = analyze_chunk_with_llm(chunk, model=chosen_model)
            if found:
                all_raw_highlights.extend(found)
            progress.advance(llm_task)

    # 6. Deduplicate and Rank
    highlights = deduplicate_and_rank_highlights(all_raw_highlights, min_score=args.min_score)

    if not highlights:
        console.print(f"\n[yellow]No highlights met the score threshold of {args.min_score}/10.[/yellow]")
        console.print("[dim]Tip: Try running again with `--min-score 5` or `--min-score 6`.[/dim]")
        sys.exit(0)

    # 7. Render Results Table
    table = Table(title=f"\n🌟 Top Highlights Identified ({len(highlights)})", border_style="green", header_style="bold green")
    table.add_column("#", justify="center", style="cyan", width=3)
    table.add_column("Timestamps", justify="center", style="yellow", width=19)
    table.add_column("Length", justify="center", width=7)
    table.add_column("Score", justify="center", style="bold magenta", width=8)
    table.add_column("Title & Reason", justify="left")

    for idx, h in enumerate(highlights, 1):
        ts = f"{h['start_time']} ➔ {h['end_time']}"
        dur = f"{int(h['duration_sec'])}s"
        score = f"{h['score']}/10"
        desc = f"[bold]{h['title']}[/bold]\n[dim]Hook: \"{h.get('hook', 'N/A')}\"[/dim]\n[italic dim]{h.get('reason', '')}[/italic dim]"
        table.add_row(str(idx), ts, dur, score, desc)

    console.print(table)

    # 8. Save Metadata Reports
    os.makedirs(args.output_dir, exist_ok=True)
    summary_json = os.path.join(args.output_dir, "highlights_summary.json")
    summary_md = os.path.join(args.output_dir, "highlights_summary.md")

    with open(summary_json, "w", encoding="utf-8") as f:
        json.dump({"metadata": metadata, "highlights": highlights}, f, indent=2)
    save_markdown_report(metadata, highlights, summary_md)

    console.print(f"\n[green]✓[/green] Reports saved:")
    console.print(f"   • JSON: [bold]{summary_json}[/bold]")
    console.print(f"   • Markdown: [bold]{summary_md}[/bold]")

    # 9. Cut Video Clips if requested
    if args.no_cut:
        console.print("\n[dim](Skipped video download and slicing due to --no-cut flag)[/dim]")
        return

    console.print("\n[bold cyan]Downloading source video to slice clips...[/bold cyan]")
    try:
        video_file = download_source_video(
            metadata["url"],
            output_dir=os.path.join(args.output_dir, "source"),
            max_height=args.quality
        )
        console.print(f"[green]✓[/green] Source video downloaded: [bold]{video_file}[/bold]")
    except Exception as e:
        console.print(f"[red]Failed to download source video: {e}[/red]")
        sys.exit(1)

    console.print(f"\n[cyan]Slicing {len(highlights)} highlight clip(s) with FFmpeg...[/cyan]")
    accurate = not args.fast_cut
    sliced_clips = cut_all_highlights(
        source_video_path=video_file,
        highlights=highlights,
        output_dir=os.path.join(args.output_dir, "clips"),
        accurate=accurate
    )

    console.print(f"\n[bold green]🎉 Done! {len(sliced_clips)} clip(s) extracted successfully into:[/bold green]")
    console.print(f"[bold cyan]{os.path.abspath(os.path.join(args.output_dir, 'clips'))}[/bold cyan]\n")
    for clip in sliced_clips:
        console.print(f"  • [yellow]{clip['filename']}[/yellow] ({clip['file_size_mb']} MB) - Score: {clip['score']}/10")


if __name__ == "__main__":
    main()
