import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web.fixtures import snapshot
from web.server import serve


def main():
    port = int(os.environ.get("WEB_PORT", "8765"))
    print(f"http://127.0.0.1:{port}", flush=True)
    serve(port, lambda _view: snapshot("single"))


if __name__ == "__main__":
    main()
