"""按包名解析并安装 wheel 到 vendor/（不依赖 pip 的临时目录）。"""

from __future__ import annotations

import io
import json
import os
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.join(os.path.dirname(HERE), "vendor")
PY = f"cp{sys.version_info.major}{sys.version_info.minor}"


def pick(files: list[dict]) -> dict | None:
    """优先 cp312-win_amd64，其次 py3-none-any。"""
    order = []
    for f in files:
        name = f["filename"]
        if not name.endswith(".whl"):
            continue
        if "win_amd64" in name or "none-any" in name:
            order.append(f)
    def score(f):
        n = f["filename"]
        if f"{PY}-{PY}" in n and "win_amd64" in n:
            return 0
        if "abi3-win_amd64" in n:
            return 1
        if "none-any" in n:
            return 2
        if "win_amd64" in n:
            return 3
        return 9
    order.sort(key=score)
    return order[0] if order else None


def install(pkg: str) -> None:
    url = f"https://pypi.org/pypi/{pkg}/json"
    with urllib.request.urlopen(url, timeout=30) as r:
        meta = json.load(r)
    f = pick(meta["urls"])
    if not f:
        print(f"!! {pkg}: 没有可用 wheel")
        return
    print(f"{pkg:<24} {f['filename']}")
    with urllib.request.urlopen(f["url"], timeout=120) as r:
        blob = r.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            target = os.path.join(VENDOR, *name.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                dst.write(src.read())


if __name__ == "__main__":
    os.makedirs(VENDOR, exist_ok=True)
    for p in sys.argv[1:]:
        try:
            install(p)
        except Exception as exc:  # noqa: BLE001
            print(f"!! {p}: {exc}")
