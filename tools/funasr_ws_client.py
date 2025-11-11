"""
WebSocket client for FunASR speech recognition service.

Features:
    - Sends a WAV/PCM file to FunASR server via WebSocket.
    - Prints streaming recognition results to console.
    - Supports SSL/WSS, hotword file, configurable chunk sizes.

Usage:
    python tools/funasr_ws_client.py --audio sample.wav
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH when running as script
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.funasr_ws import parse_chunk_sizes, transcribe_audio


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FunASR WebSocket client.")
    parser.add_argument("--host", default="59.78.189.185", help="FunASR server host")
    parser.add_argument("--port", type=int, default=9999, help="FunASR server port")
    parser.add_argument("--audio", required=True, help="Path to WAV/PCM audio file")
    parser.add_argument(
        "--chunk_size",
        type=parse_chunk_sizes,
        default=parse_chunk_sizes("2,8,3"),
        help="Chunk size config, e.g. '2,8,3'",
    )
    parser.add_argument("--chunk_interval", type=int, default=8, help="Chunk interval")
    parser.add_argument(
        "--mode",
        choices=["offline", "online", "2pass"],
        default="2pass",
        help="Recognition mode",
    )
    parser.add_argument("--hotword", help="Hotword file path (optional)")
    parser.add_argument("--use_itn", type=int, choices=[0, 1], default=1, help="Enable inverse text normalization")
    parser.add_argument("--send_without_sleep", action="store_true", help="Send audio chunks without sleep")
    parser.add_argument("--ssl", action="store_true", help="Use WSS with TLS (self-signed accepted)")
    parser.add_argument("--ssl_verify", action="store_true", help="Verify TLS certificate when using --ssl")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        results = transcribe_audio(
            host=args.host,
            port=args.port,
            audio_path=args.audio,
            chunk_size=args.chunk_size,
            chunk_interval=args.chunk_interval,
            mode=args.mode,
            hotword_path=args.hotword,
            use_itn=bool(args.use_itn),
            send_without_sleep=args.send_without_sleep,
            use_ssl=args.ssl,
            ssl_verify=args.ssl_verify,
        )
        for item in results:
            line = f"[{item.mode}] {item.text}"
            if item.timestamp:
                line += f" | timestamp: {item.timestamp}"
            if item.is_final:
                line += " [FINAL]"
            print(line)
    except KeyboardInterrupt:
        print("Interrupted by user")


if __name__ == "__main__":
    main()

