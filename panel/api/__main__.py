from __future__ import annotations

import threading
import webbrowser

import uvicorn

from .app import create_app


def main() -> None:
    threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:8000")).start()
    uvicorn.run(create_app(), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
