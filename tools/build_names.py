"""从本机游戏资源生成 物品ID -> 中文名 映射。"""

import json
import sys
from pathlib import Path

ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[1])
sys.path[:0] = [ROOT, ROOT + "/vendor", ROOT + "/refpak"]

import pbz_save as ps
from refpak.catalog_builder import build_catalog
from refpak.resources_reader import IoStore, localization

def find_game() -> Path:
    import os
    for drive in ("E:", "D:", "F:", "C:"):
        p = Path(drive) / "SteamLibrary/steamapps/common/PBZ"
        if (p / "ProjectPBZ/Content/Paks").is_dir():
            return p
    return Path(r"C:/Program Files (x86)/Steam/steamapps/common/PBZ")


GAME = find_game()
PAKS = GAME / "ProjectPBZ/Content/Paks"

codec = ps.codec()
print("打开 IoStore ...")
store = IoStore(PAKS / "ProjectPBZ-Windows.utoc", codec)
print("  文件", len(store.files))

from refpak.pak_reader import PakReader
pak = PakReader(PAKS / "ProjectPBZ-Windows.pak", codec)
zh = localization(pak.read_file("projectpbz/content/localization/game/zh-hans/game.locres"))
en = localization(pak.read_file("projectpbz/content/localization/game/en-us/game.locres"))
print("  本地化条目 zh", len(zh), "en", len(en))

profile = json.loads((Path(__file__).parent / "profile.json").read_text(encoding="utf8"))
print("  profile resources", len(profile.get("resources", {})))

catalog = build_catalog(
    store, zh, en, profile["resources"], profile.get("item_property_schemas"), tolerant=True
)
items = catalog.get("items", [])
print("物品", len(items), "不可用类别", catalog.get("unavailable_categories"))
for it in items[:5]:
    print("  ", it.get("id"), "->", it.get("name"), "|", it.get("category"))
out = Path(ROOT, "names.json")
out.write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf8")
print("写出", out)
