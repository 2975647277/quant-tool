import argparse
import os
import signal
import threading
import time

import uvicorn

from .main import app, configure_session_token


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local quant service")
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--parent-pid", required=True, type=int)
    return parser.parse_args()


def stop_when_parent_exits(parent_pid: int) -> None:
    while os.getppid() == parent_pid:
        time.sleep(0.5)
    os.kill(os.getpid(), signal.SIGTERM)


def main() -> None:
    args = parse_args()
    token = os.environ.get("QUANT_SESSION_TOKEN")
    if not token:
        raise SystemExit("QUANT_SESSION_TOKEN is required")
    configure_session_token(token)
    threading.Thread(
        target=stop_when_parent_exits,
        args=(args.parent_pid,),
        daemon=True,
    ).start()
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=args.port,
        access_log=False,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
