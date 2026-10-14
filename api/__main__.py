"""python -m api [--port 8000] [--reload]"""
import argparse

import uvicorn

from common.config import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m api")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    setup_logging()
    uvicorn.run("api.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
