#!/usr/bin/env python3
import os
import signal
import sys
from pathlib import Path
from typing import IO

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import util
from core.config import load_review_config
from core.engine import ReviewEngine
from core.protocol import JsonLineTransport


def run(reader: IO[str], writer: IO[str]) -> int:
    transport = JsonLineTransport(reader, writer)
    util.init_runtime_context(os.getcwd())
    if not util._RUNTIME_CONTEXT.repo_root_path:
        transport.send({"type": "notice", "level": "error", "text": "Not inside a git repository."})
        return 1

    if not os.path.exists(util._RUNTIME_CONTEXT.index_path):
        transport.send({"type": "notice", "level": "info", "text": "Missing index"})
        return 1

    config = load_review_config()
    engine = ReviewEngine(transport=transport, scheduler=config.build_scheduler())
    return engine.run()


def main() -> int:
    for signum in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, signal.default_int_handler)
    try:
        return run(sys.stdin, sys.stdout)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
