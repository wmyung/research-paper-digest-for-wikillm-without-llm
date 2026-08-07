from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paper-digest-web",
        description="Run the private, local WikiLLM Paper Digest web app.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: localhost only).")
    parser.add_argument("--port", type=int, default=8088, help="HTTP port (default: 8088).")
    parser.add_argument("--open", action="store_true", help="Open the local app in the default browser.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    url = f"http://127.0.0.1:{args.port}/"
    if args.open:
        threading.Timer(0.8, webbrowser.open, args=(url,)).start()
    uvicorn.run("paper_digest.api:app", host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
