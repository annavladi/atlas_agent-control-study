"""Load ~/study-keys/.env (KEY=value lines) into os.environ.

The API key lives next to the wallet keys, outside the study folder, so an AI
session with access to the study folder can never read it.
"""
import os
from pathlib import Path

ENV_PATH = Path("~/study-keys/.env").expanduser()


def load_env(path=ENV_PATH):
    if not Path(path).exists():
        return
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
