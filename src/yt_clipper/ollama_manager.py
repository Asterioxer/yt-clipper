"""
Ollama Manager Module:
- Ensures Ollama background service is running
- Discovers installed local models
- Automatically downloads/pulls a local model if missing (with streaming progress bar)
"""

import sys
import time
import json
import subprocess
import requests
from typing import List, Optional
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
)

console = Console()
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_FALLBACK_MODEL = "llama3.2:3b"


def is_ollama_running(base_url: str = DEFAULT_OLLAMA_URL) -> bool:
    """Check if the Ollama API server is responding."""
    try:
        r = requests.get(f"{base_url}/api/tags", timeout=1.5)
        return r.status_code == 200
    except Exception:
        return False


def ensure_ollama_running(base_url: str = DEFAULT_OLLAMA_URL) -> bool:
    """Check if Ollama server is running; attempt to launch if not."""
    if is_ollama_running(base_url):
        return True

    console.print("[yellow]⚠️  Ollama server is not active at localhost:11434.[/yellow]")
    console.print("[cyan]Starting Ollama background process...[/cyan]")

    try:
        # On Windows, start detached process
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        subprocess.Popen(
            ["ollama", "serve"],
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            close_fds=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        for _ in range(12):
            time.sleep(1)
            if is_ollama_running(base_url):
                console.print("[green]✓ Ollama daemon started successfully![/green]")
                return True
    except FileNotFoundError:
        console.print("[bold red]Error:[/bold red] Ollama is not installed or not in your system PATH.")
        console.print("Please install Ollama from [bold cyan]https://ollama.com[/bold cyan] and retry.")
        return False
    except Exception as e:
        console.print(f"[red]Could not auto-start Ollama: {e}[/red]")

    return False


def get_installed_models(base_url: str = DEFAULT_OLLAMA_URL) -> List[str]:
    """Return a list of all model names currently available in local Ollama."""
    try:
        res = requests.get(f"{base_url}/api/tags", timeout=3)
        if res.status_code == 200:
            return [m["name"] for m in res.json().get("models", [])]
    except Exception:
        pass
    return []


def pull_model_with_progress(model_name: str, base_url: str = DEFAULT_OLLAMA_URL) -> bool:
    """
    Pulls a model from Ollama registry with a live Rich progress bar.
    """
    console.print(f"\n[bold cyan]📦 Downloading local model:[/bold cyan] [bold magenta]{model_name}[/bold magenta]")
    console.print("[dim]This is a one-time download and will run 100% locally on your machine afterwards.[/dim]\n")

    url = f"{base_url}/api/pull"
    payload = {"name": model_name, "stream": True}

    try:
        with requests.post(url, json=payload, stream=True, timeout=1200) as response:
            if response.status_code != 200:
                console.print(f"[red]Failed to pull {model_name}: HTTP {response.status_code}[/red]")
                return False

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console
            ) as progress:
                tasks = {}

                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line.decode("utf-8"))
                        status = data.get("status", "")
                        digest = data.get("digest", "default")
                        total = data.get("total", 0)
                        completed = data.get("completed", 0)

                        if total > 0:
                            if digest not in tasks:
                                tasks[digest] = progress.add_task(
                                    f"[cyan]{status}",
                                    total=total,
                                    completed=completed
                                )
                            else:
                                progress.update(
                                    tasks[digest],
                                    description=f"[cyan]{status}",
                                    completed=completed,
                                    total=total
                                )
                        else:
                            if status:
                                console.print(f"  [dim]• {status}[/dim]")
                    except Exception:
                        continue

        console.print(f"\n[bold green]✓ Successfully downloaded and loaded {model_name}![/bold green]\n")
        return True

    except Exception as e:
        console.print(f"[red]Error downloading model via Ollama API: {e}[/red]")
        console.print(f"[yellow]Attempting CLI fallback: 'ollama pull {model_name}'...[/yellow]")
        try:
            subprocess.run(["ollama", "pull", model_name], check=True)
            return True
        except Exception as cli_err:
            console.print(f"[bold red]Failed to download model: {cli_err}[/bold red]")
            return False


def prepare_model(requested_model: Optional[str] = None, base_url: str = DEFAULT_OLLAMA_URL) -> str:
    """
    Validates that a usable local model exists.
    If none exists or the requested model is missing, automatically downloads it.
    """
    if not ensure_ollama_running(base_url):
        sys.exit(1)

    installed = get_installed_models(base_url)

    # 1. User requested a specific model
    if requested_model:
        # Check if already installed
        for m in installed:
            if requested_model.lower() in m.lower():
                return m

        # Not installed -> auto-pull it!
        console.print(f"[yellow]Model '{requested_model}' not found locally.[/yellow]")
        success = pull_model_with_progress(requested_model, base_url)
        if success:
            return requested_model
        sys.exit(1)

    # 2. User did not specify a model: check existing models in priority order
    priority_order = [
        "llama3.2-3b",
        "llama3.2",
        "qwen3.5:4b",
        "qwen2.5:7b",
        "qwen2.5:3b",
        "qwen3.5",
        "qwen",
        "mistral",
        "llama",
    ]
    for prio in priority_order:
        for m in installed:
            if prio in m.lower():
                return m

    # If any other model is installed, use that
    if installed:
        return installed[0]

    # 3. No models installed at all: auto-download default lightweight model!
    console.print(f"\n[bold yellow]No local models found in your Ollama installation.[/bold yellow]")
    console.print(f"[cyan]Automatically setting up recommended fast model: [bold]{DEFAULT_FALLBACK_MODEL}[/bold]...[/cyan]")
    success = pull_model_with_progress(DEFAULT_FALLBACK_MODEL, base_url)
    if success:
        return DEFAULT_FALLBACK_MODEL

    console.print("[red]Could not setup a local model. Please run `ollama pull llama3.2:3b` manually.[/red]")
    sys.exit(1)
