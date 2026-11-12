"""Start StarLinks on this PC and open the warehouse in the browser.

The Windows build places node\\node.exe and web\\server.js beside this program.
The database and uploaded files stay in data\\ next to the program.
"""

from __future__ import annotations

import multiprocessing
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path


def install_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return install_dir() / "backend"


def lan_ip() -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        address = sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()
    if address.startswith("127."):
        return None
    return address


def prepare() -> None:
    root = install_dir()
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "storage").mkdir(parents=True, exist_ok=True)
    database = (data / "wms.db").resolve().as_posix()
    os.environ["DATABASE_URL"] = f"sqlite:///{database}"
    os.environ["LOCAL_STORAGE_PATH"] = str((data / "storage").resolve())
    os.environ["STORAGE_BACKEND"] = "local"
    os.environ["REDIS_URL"] = ""
    os.environ["RATE_LIMIT_STORAGE"] = "memory://"
    os.environ["CORS_ORIGINS"] = "http://127.0.0.1:3000,http://localhost:3000"
    stock = bundle_dir() / "data" / "iSpring_SKU_List.xlsx"
    if stock.exists():
        os.environ["WMS_STOCK_FILE"] = str(stock)

    from alembic import command
    from alembic.config import Config

    ini = bundle_dir() / "alembic.ini"
    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(bundle_dir() / "alembic"))
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"].replace("%", "%%"))
    command.upgrade(cfg, "head")

    from app.seed import run

    run()


def wait_for(port: int, timeout: float = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.4):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def serve_api() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_level="info")


def node_command() -> list[str]:
    root = install_dir()
    windows = root / "node" / "node.exe"
    if windows.exists():
        return [str(windows), "server.js"]
    return ["node", "server.js"]


def main() -> None:
    multiprocessing.freeze_support()
    web = install_dir() / "web"
    if not (web / "server.js").exists():
        print("The web folder is missing next to StarLinks.exe.")
        print("On the Windows PC run packaging\\windows\\build.ps1, then start release\\StarLinks\\StarLinks.exe.")
        raise SystemExit(1)
    print("Preparing the warehouse database…")
    prepare()
    threading.Thread(target=serve_api, name="starlinks-api", daemon=True).start()
    if not wait_for(8000):
        print("The API did not start on port 8000.")
        raise SystemExit(1)
    env = os.environ.copy()
    env["HOSTNAME"] = "0.0.0.0"
    env["PORT"] = "3000"
    env["NODE_ENV"] = "production"
    site = subprocess.Popen(node_command(), cwd=web, env=env)
    try:
        if not wait_for(3000):
            print("The site did not start on port 3000.")
            raise SystemExit(1)
        local = "http://127.0.0.1:3000"
        print()
        print("StarLinks is running.")
        print(f"This PC: {local}")
        address = lan_ip()
        if address:
            print(f"Phones on this network: http://{address}:3000")
        print("Close this window to stop.")
        print()
        webbrowser.open(local + "/login")
        site.wait()
    finally:
        if site.poll() is None:
            site.terminate()


if __name__ == "__main__":
    main()
