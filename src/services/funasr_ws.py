"""
Utilities for interacting with FunASR WebSocket speech recognition service.

Provides functions to stream audio data to FunASR over WebSocket and collect
transcription results. Designed for reuse by both CLI tools and web handlers.
"""

from __future__ import annotations

import asyncio
import audioop
import json
import os
import ssl
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

import websockets


class FunASRClientError(Exception):
    """Custom exception for FunASR client errors."""


def parse_chunk_sizes(value: str) -> Sequence[int]:
    """Parse chunk size argument formatted as '5,10,5'."""
    parts = [v.strip() for v in value.split(",")]
    if len(parts) != 3:
        raise ValueError("chunk_size expects exactly 3 integers, e.g. '5,10,5'")
    try:
        return [int(p) for p in parts]
    except ValueError as exc:
        raise ValueError(f"Invalid chunk_size value: {value}") from exc


def load_hotwords(path: Optional[str]) -> str:
    """Load hotword definitions from file."""
    if not path:
        return ""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Hotword file not found: {path}")

    hotwords = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2 or not parts[-1].isdigit():
                raise ValueError(f"Invalid hotword line: {line}")
            hotwords[" ".join(parts[:-1])] = int(parts[-1])
    return json.dumps(hotwords, ensure_ascii=False)


def _ensure_mono_16k_pcm(data: bytes, sample_rate: int, sample_width: int, channels: int) -> Tuple[bytes, int]:
    """Convert arbitrary PCM data to mono 16k 16-bit PCM."""

    target_rate = 16000
    target_width = 2
    target_channels = 1

    processed = data

    if channels > 1:
        processed = audioop.tomono(processed, sample_width, 0.5, 0.5)
        channels = 1

    if sample_width != target_width:
        processed = audioop.lin2lin(processed, sample_width, target_width)
        sample_width = target_width

    if sample_rate != target_rate:
        processed, _ = audioop.ratecv(processed, target_width, target_channels, sample_rate, target_rate, None)
        sample_rate = target_rate

    return processed, sample_rate


def load_audio_bytes(path: str) -> Tuple[bytes, int, str]:
    """Load PCM/WAV audio file and normalize to mono 16k PCM."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Audio file not found: {path}")

    ext = os.path.splitext(path)[1].lower()
    if ext == ".pcm":
        with open(path, "rb") as f:
            data = f.read()
        normalized, sample_rate = _ensure_mono_16k_pcm(data, 16000, 2, 1)
        return normalized, sample_rate, "pcm"

    if ext == ".wav":
        import wave

        with wave.open(path, "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            sample_width = wav_file.getsampwidth()
            channels = wav_file.getnchannels()
            frames = wav_file.readframes(wav_file.getnframes())
        normalized, sample_rate = _ensure_mono_16k_pcm(bytes(frames), sample_rate, sample_width, channels)
        return normalized, sample_rate, "pcm"

    raise ValueError(f"Unsupported audio format: {ext}. Only .wav and .pcm are supported.")


@dataclass
class TranscriptionResult:
    """Represents a transcription message from FunASR."""

    text: str
    mode: str
    is_final: bool
    timestamp: Optional[str] = None


async def _stream_audio(
    websocket: websockets.WebSocketClientProtocol,
    audio_bytes: bytes,
    sample_rate: int,
    chunk_size: Sequence[int],
    chunk_interval: int,
    mode: str,
    hotwords_json: str,
    use_itn: bool,
    audio_path: str,
    send_without_sleep: bool,
) -> None:
    """Stream audio bytes to FunASR server."""

    frame_ms = 60 * chunk_size[1] / chunk_interval
    stride = int(sample_rate * 2 * frame_ms / 1000)
    if stride <= 0:
        raise FunASRClientError("Invalid chunk configuration, stride computed to zero.")

    total_chunks = (len(audio_bytes) - 1) // stride + 1

    init_payload = {
        "mode": mode,
        "chunk_size": list(chunk_size),
        "chunk_interval": chunk_interval,
        "audio_fs": sample_rate,
        "wav_name": os.path.basename(audio_path),
        "wav_format": "pcm",
        "is_speaking": True,
        "hotwords": hotwords_json,
        "itn": use_itn,
    }
    await websocket.send(json.dumps(init_payload, ensure_ascii=False))

    sleep_per_chunk = 0.0 if send_without_sleep else frame_ms / 1000.0

    for idx in range(total_chunks):
        start = idx * stride
        chunk = audio_bytes[start : start + stride]
        if not chunk:
            break
        await websocket.send(chunk)
        if sleep_per_chunk:
            await asyncio.sleep(sleep_per_chunk)

    await websocket.send(json.dumps({"is_speaking": False}))


async def _receive_results(
    websocket: websockets.WebSocketClientProtocol,
    callback: Callable[[TranscriptionResult], None],
) -> None:
    """Receive transcription results and invoke callback."""

    async for message in websocket:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            raise FunASRClientError("Received non-JSON message from FunASR server.")

        result = TranscriptionResult(
            text=payload.get("text", ""),
            mode=payload.get("mode", "unknown"),
            is_final=bool(payload.get("is_final", False)),
            timestamp=payload.get("timestamp"),
        )
        callback(result)
        if result.is_final:
            await websocket.close(code=1000)
            break


async def transcribe_async(
    host: str,
    port: int,
    audio_path: str,
    chunk_size: Sequence[int],
    chunk_interval: int,
    mode: str = "2pass",
    hotword_path: Optional[str] = None,
    use_itn: bool = True,
    send_without_sleep: bool = False,
    use_ssl: bool = False,
    ssl_verify: bool = False,
) -> List[TranscriptionResult]:
    """Asynchronously transcribe audio via FunASR WebSocket."""

    audio_bytes, sample_rate, _ = load_audio_bytes(audio_path)
    hotwords_json = load_hotwords(hotword_path)

    ssl_context = None
    scheme = "wss" if use_ssl else "ws"
    if use_ssl:
        ssl_context = ssl.create_default_context()
        if not ssl_verify:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

    uri = f"{scheme}://{host}:{port}"
    results: List[TranscriptionResult] = []

    async with websockets.connect(
        uri,
        subprotocols=["binary"],
        ssl=ssl_context,
        ping_interval=None,
    ) as websocket:
        sender = asyncio.create_task(
            _stream_audio(
                websocket,
                audio_bytes,
                sample_rate,
                chunk_size,
                chunk_interval,
                mode,
                hotwords_json,
                use_itn,
                audio_path,
                send_without_sleep,
            )
        )

        def collect(result: TranscriptionResult) -> None:
            results.append(result)

        receiver = asyncio.create_task(_receive_results(websocket, collect))

        try:
            await asyncio.gather(sender, receiver)
        except Exception:
            sender.cancel()
            receiver.cancel()
            raise

    return results


def transcribe_audio(
    host: str,
    port: int,
    audio_path: str,
    chunk_size: Sequence[int],
    chunk_interval: int,
    mode: str = "2pass",
    hotword_path: Optional[str] = None,
    use_itn: bool = True,
    send_without_sleep: bool = False,
    use_ssl: bool = False,
    ssl_verify: bool = False,
) -> List[TranscriptionResult]:
    """Blocking transcription helper."""

    return asyncio.run(
        transcribe_async(
            host=host,
            port=port,
            audio_path=audio_path,
            chunk_size=chunk_size,
            chunk_interval=chunk_interval,
            mode=mode,
            hotword_path=hotword_path,
            use_itn=use_itn,
            send_without_sleep=send_without_sleep,
            use_ssl=use_ssl,
            ssl_verify=ssl_verify,
        )
    )


