"""Live local transcription: whisper.cpp's `whisper-stream` on the mic.

Runs `whisper-stream` in voice-activity mode (`--step 0`): it listens
until a pause, transcribes the utterance, prints it, and listens again.
Nothing is uploaded; the model file is on disk. The parser is tolerant
of the banner lines the binary prints while starting, of blank-audio
markers, and of the two output shapes the VAD mode has used
(`### Transcription N START/END` fences, or bare lines).

The capture device defaults to the first one whose name says
"microphone", because a virtual loopback device (BlackHole and the
like) is often the system default and hears nothing.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from collections.abc import Iterator
from pathlib import Path
from queue import Queue

DEFAULT_MODEL = Path(
    os.environ.get(
        "PROSAIC_WHISPER_MODEL",
        Path.home() / ".local" / "share" / "whisper-models" / "ggml-medium.en.bin",
    )
)

# [BLANK_AUDIO], (silence), *music*
_NOISE_RE = re.compile(r"^\s*(\[[^\]]*\]|\([^)]*\)|\*[^*]*\*)\s*$")
_FENCE_RE = re.compile(r"^###\s+Transcription\s+\d+\s+(START|END)")
_BANNER_PREFIXES = (
    "main:",
    "init:",
    "whisper_",
    "ggml_",
    "load_backend",
    "system_info",
    "[Start speaking]",
    "processing",
    "audio_ctx",
)


def list_devices(binary: str = "whisper-stream") -> list[str]:
    """Device names, index-ordered, from the binary's startup banner."""
    try:
        proc = subprocess.run([binary, "--help"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return re.findall(r"Capture device #\d+: '([^']+)'", proc.stderr + proc.stdout)


def pick_device(names: list[str]) -> int | None:
    for i, n in enumerate(names):
        if "microphone" in n.lower() or " mic" in n.lower():
            return i
    return None


def clean(line: str) -> str:
    line = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line)  # ANSI clears
    line = line.replace("\r", "").strip()
    if not line or _FENCE_RE.match(line) or line.startswith(_BANNER_PREFIXES):
        return ""
    if _NOISE_RE.match(line):
        return ""
    # Timestamps whisper prints with -pt: [00:00:00.000 --> 00:00:02.000]
    line = re.sub(r"^\[\d\d:\d\d:\d\d\.\d+\s*-->\s*\d\d:\d\d:\d\d\.\d+\]\s*", "", line)
    return line.strip()


def utterances_from_lines(lines: Iterator[str]) -> Iterator[str]:
    """Group the binary's lines into utterances: everything between START
    and END fences is one utterance; outside fences, each non-empty
    line is one."""
    buf: list[str] = []
    fenced = False
    for raw in lines:
        stripped = raw.replace("\r", "").strip()
        m = _FENCE_RE.match(stripped)
        if m:
            if m.group(1) == "START":
                fenced, buf = True, []
            else:
                fenced = False
                text = " ".join(x for x in buf if x)
                buf = []
                if text:
                    yield text
            continue
        text = clean(raw)
        if not text:
            continue
        if fenced:
            buf.append(text)
        else:
            yield text
    if buf:
        text = " ".join(buf)
        if text:
            yield text


class WhisperStream:
    """`whisper-stream` as a background process feeding a queue of utterances."""

    def __init__(
        self,
        model: Path = DEFAULT_MODEL,
        device: int | None = None,
        threads: int = 8,
        vad_threshold: float = 0.6,
        length_ms: int = 30000,
        binary: str = "whisper-stream",
    ):
        if not shutil.which(binary):
            raise SystemExit(
                f"listen: {binary} not found; install whisper-cpp (brew install whisper-cpp)"
            )
        if not Path(model).exists():
            raise SystemExit(f"listen: whisper model not found at {model}; see docs/stt.md")
        self.cmd = [
            binary,
            "-m",
            str(model),
            "--step",
            "0",
            "--length",
            str(length_ms),
            "-vth",
            str(vad_threshold),
            "-t",
            str(threads),
        ]
        if device is None:
            device = pick_device(list_devices(binary))
        if device is not None:
            self.cmd += ["-c", str(device)]
        self.device = device
        self.queue: Queue[str | None] = Queue()
        self.proc: subprocess.Popen[str] | None = None

    def start(self) -> None:
        self.proc = subprocess.Popen(
            self.cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1
        )
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        assert self.proc and self.proc.stdout
        try:
            for utt in utterances_from_lines(iter(self.proc.stdout.readline, "")):
                self.queue.put(utt)
        finally:
            self.queue.put(None)

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
