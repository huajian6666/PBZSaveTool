"""影之刃零（Phantom Blade Zero）存档工具核心。

设计前提：存档内部结构未知也能用。所有能力都建立在「字节偏移」上：

  * 结构嗅探：压缩 / 加密 / 长度前缀 / 尾部校验和
  * 数值搜索：整数、浮点、UTF-8 / UTF-16 字符串
  * 双存档对比：改一次游戏内数值，就能定位到对应偏移
  * 定点改写：自动重算校验和、自动备份、原子写回

不依赖第三方库。
"""

from __future__ import annotations

import hashlib
import math
import os
import shutil
import struct
import zlib
from dataclasses import dataclass
from datetime import datetime

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #

WIDTH_FMT = {1: "B", 2: "H", 4: "I", 8: "Q"}

ALGO_LEN = {"crc32": 4, "adler32": 4, "md5": 16, "sha1": 20, "sha256": 32}

MAGIC_SIGNS = (
    (b"\x1f\x8b\x08", "gzip 压缩"),
    (b"\x78\x9c", "zlib 压缩"),
    (b"\x78\x01", "zlib 压缩"),
    (b"\x78\xda", "zlib 压缩"),
    (b"\x04\x22\x4d\x18", "LZ4 压缩"),
    (b"\x28\xb5\x2f\xfd", "zstd 压缩"),
    (b"PK\x03\x04", "ZIP 容器"),
    (b"GVAS", "Unreal GVAS 存档"),
    (b"CON ", "Unreal 容器"),
)

SAVE_KEYWORDS = (
    "phantomblade",
    "phantom blade",
    "phantombladezero",
    "phantom_blade",
    "pbz",
    "影之刃",
    "yingzhiren",
    "s-game",
    "sgame",
    "bladezero",
)

SAVE_EXTS = (".sav", ".sav0", ".sav1", ".dat", ".bin", ".profile", ".slot", ".pbz")


class SaveError(Exception):
    """存档读写或校验失败。"""


# --------------------------------------------------------------------------- #
# 摘要
# --------------------------------------------------------------------------- #


def digest_bytes(algo: str, blob: bytes) -> bytes:
    """按算法名生成摘要字节。crc32/adler32 区分字节序，用后缀标注。"""
    if algo == "crc32le":
        return struct.pack("<I", zlib.crc32(blob) & 0xFFFFFFFF)
    if algo == "crc32be":
        return struct.pack(">I", zlib.crc32(blob) & 0xFFFFFFFF)
    if algo == "adler32le":
        return struct.pack("<I", zlib.adler32(blob) & 0xFFFFFFFF)
    if algo == "adler32be":
        return struct.pack(">I", zlib.adler32(blob) & 0xFFFFFFFF)
    return hashlib.new(algo, blob).digest()


def digest_len(algo: str) -> int:
    if algo.startswith(("crc32", "adler32")):
        return 4
    return ALGO_LEN[algo]


# --------------------------------------------------------------------------- #
# 校验和
# --------------------------------------------------------------------------- #


@dataclass
class Checksum:
    """一条校验和配方。

    style='prefix'：摘要写在 offset 处，覆盖 data[start:offset]（尾部校验，最常见）
    style='suffix'：摘要写在 offset 处，覆盖 data[offset+length:]（头部校验）
    """

    algo: str
    offset: int
    length: int
    start: int = 0
    style: str = "prefix"

    def describe(self) -> str:
        span = f"0..0x{self.offset:X}" if self.style == "prefix" else f"0x{self.offset + self.length:X}..末尾"
        return f"{self.algo} 覆盖 {span}，写在 0x{self.offset:X}"

    def recompute(self, data: bytes) -> bytes:
        if self.style == "prefix":
            blob = data[self.start : self.offset]
        else:
            blob = data[self.offset + self.length :]
        return digest_bytes(self.algo, blob)


def _is_trailing(cs: Checksum, n: int) -> bool:
    return cs.offset + cs.length >= n


def detect_checksums(data: bytes, tail_window: int = 0x200, max_start: int = 0x40) -> list[Checksum]:
    """在文件里找校验和。返回全部命中，按可信度排序。

    做法：对每个可能的摘要位置，用增量摘要（hashlib.copy）从候选起点哈希到该位置，
    所以整体是 O(文件大小 × 起点数)，几 MB 的存档在百毫秒级。
    """
    n = len(data)
    if n < 64:
        return []

    # 1) 候选摘要位置：文件末尾一片区域 + 文件头部几个常规位置
    offsets: set[int] = set()
    for alen in (4, 16, 20, 32):
        span = tail_window if alen == 4 else 0x60
        for d in range(span + 1):
            p = n - alen - d
            if p > alen:
                offsets.add(p)
    for p in (4, 8, 12, 16, 20, 24, 32, 64, 0x100):
        if p < n:
            offsets.add(p)
    offsets = sorted(offsets)

    starts = [0, 4, 8, 12, 16, 32, 64]
    found: list[Checksum] = []
    seen: set[tuple] = set()

    # 2) 尾部校验：摘要覆盖 [start, offset)
    for start in starts:
        if start >= n - 8:
            continue
        jobs = [o for o in offsets if o > start]
        if not jobs:
            continue
        big = {name: hashlib.new(name) for name in ("md5", "sha1", "sha256")}
        crc = 0
        adler = 1
        pos = start
        for off in jobs:
            if off > pos:
                chunk = data[pos:off]
                for h in big.values():
                    h.update(chunk)
                crc = zlib.crc32(chunk, crc)
                adler = zlib.adler32(chunk, adler)
                pos = off
            # 4 字节：crc32 / adler32
            if _match(data, off, struct.pack("<I", crc & 0xFFFFFFFF)):
                _add(found, seen, Checksum("crc32le", off, 4, start))
            if _match(data, off, struct.pack(">I", crc & 0xFFFFFFFF)):
                _add(found, seen, Checksum("crc32be", off, 4, start))
            if _match(data, off, struct.pack("<I", adler & 0xFFFFFFFF)):
                _add(found, seen, Checksum("adler32le", off, 4, start))
            # 16/20/32 字节
            for name, h in big.items():
                d = h.copy().digest()
                if _match(data, off, d):
                    _add(found, seen, Checksum(name, off, len(d), start))

    # 3) 头部校验：摘要覆盖 [offset+length, 末尾)
    for off in (0, 4, 8, 12, 16, 20, 32):
        if off >= n - 8:
            continue
        rest = data[off:]
        for name in ("md5", "sha1", "sha256"):
            dl = ALGO_LEN[name]
            body = rest[dl:]
            if len(body) and rest[:dl] == hashlib.new(name, body).digest():
                _add(found, seen, Checksum(name, off, dl, 0, "suffix"))
        body = rest[4:]
        for algo, pack in (("crc32le", "<I"), ("crc32be", ">I")):
            if len(body) and rest[:4] == struct.pack(pack, zlib.crc32(body) & 0xFFFFFFFF):
                _add(found, seen, Checksum(algo, off, 4, 0, "suffix"))

    found.sort(key=lambda c: (not _is_trailing(c, n), c.start != 0, c.length != 4, c.offset))
    return found


def _match(data: bytes, off: int, expect: bytes) -> bool:
    return data[off : off + len(expect)] == expect


def _add(out: list[Checksum], seen: set[tuple], cs: Checksum) -> None:
    key = (cs.algo, cs.offset, cs.start, cs.style)
    if key in seen:
        return
    seen.add(key)
    out.append(cs)


def pick_checksum(checksums: list[Checksum], n: int) -> Checksum | None:
    """挑一条最可信的配方：优先尾部、覆盖全文件、crc32。"""
    if not checksums:
        return None
    ranked = sorted(
        checksums,
        key=lambda c: (
            not _is_trailing(c, n),
            c.start != 0,
            c.style != "prefix",
            c.length != 4,
        ),
    )
    return ranked[0]


# --------------------------------------------------------------------------- #
# 结构嗅探
# --------------------------------------------------------------------------- #


def entropy(blob: bytes) -> float:
    if not blob:
        return 0.0
    counts = [0] * 256
    for b in blob:
        counts[b] += 1
    n = len(blob)
    e = 0.0
    for c in counts:
        if c:
            p = c / n
            e -= p * math.log2(p)
    return e


def printable_ratio(blob: bytes) -> float:
    if not blob:
        return 0.0
    ok = sum(1 for b in blob if 0x20 <= b < 0x7F or b in (9, 10, 13))
    return ok / len(blob)


def sniff(data: bytes) -> dict:
    """给出一份人类可读的存档画像。"""
    n = len(data)
    head = data[:16]
    magic = None
    for sig, name in MAGIC_SIGNS:
        if head.startswith(sig):
            magic = name
            break

    ent = entropy(data[: min(n, 1 << 16)])
    length_field = None
    for off, w in ((0, 4), (4, 4), (8, 4), (0, 8)):
        if n >= off + w:
            v = int.from_bytes(data[off : off + w], "little")
            if v in (n, n - off, n - off - w) and v > 64:
                length_field = {"offset": off, "width": w, "value": v}
                break

    return {
        "size": n,
        "magic": magic,
        "entropy": ent,
        "printable": printable_ratio(data[: min(n, 1 << 16)]),
        "length_field": length_field,
        "encrypted": magic is None and ent > 7.90,
        "compressed": bool(magic and ("压缩" in magic or "ZIP" in magic)),
        "head_hex": head.hex(" ").upper(),
    }


# --------------------------------------------------------------------------- #
# 搜索
# --------------------------------------------------------------------------- #


def find_int(data: bytes, value: int, width: int = 4, signed: bool = False, big_endian: bool = False) -> list[int]:
    if width not in WIDTH_FMT:
        raise ValueError(f"不支持的宽度：{width}（可选 1/2/4/8）")
    fmt = (">" if big_endian else "<") + WIDTH_FMT[width]
    try:
        needle = struct.pack(fmt, value)
    except struct.error as exc:
        raise ValueError(f"数值 {value} 放不进 {width} 字节：{exc}") from exc
    return find_bytes(data, needle)


def find_float(data: bytes, value: float, width: int = 4) -> list[int]:
    fmt = "<f" if width == 4 else "<d"
    return find_bytes(data, struct.pack(fmt, value))


def find_bytes(data: bytes, needle: bytes) -> list[int]:
    if not needle:
        return []
    out = []
    start = 0
    while True:
        i = data.find(needle, start)
        if i < 0:
            return out
        out.append(i)
        start = i + 1


def find_text(data: bytes, text: str) -> list[int]:
    """同时找 UTF-8 与 UTF-16LE 两种编码。"""
    hits = []
    for enc in ("utf-8", "utf-16-le"):
        hits += find_bytes(data, text.encode(enc))
    return sorted(set(hits))


def read_int(data: bytes, offset: int, width: int, signed: bool = False, big_endian: bool = False) -> int:
    fmt = (">" if big_endian else "<") + WIDTH_FMT[width]
    return struct.unpack_from(fmt, data, offset)[0]


def pack_int(value: int, width: int, signed: bool = False, big_endian: bool = False) -> bytes:
    fmt = (">" if big_endian else "<") + WIDTH_FMT[width]
    try:
        return struct.pack(fmt, value)
    except struct.error as exc:
        raise ValueError(f"数值 {value} 放不进 {width} 字节：{exc}") from exc


# --------------------------------------------------------------------------- #
# 对比
# --------------------------------------------------------------------------- #


@dataclass
class DiffRegion:
    start: int
    end: int
    a: bytes
    b: bytes

    @property
    def length(self) -> int:
        return self.end - self.start

    def summary(self, max_hex: int = 16) -> str:
        def brief(b: bytes) -> str:
            if len(b) <= max_hex:
                return b.hex(" ")
            return b[:max_hex].hex(" ") + f" …（共 {len(b)}B）"

        return f"0x{self.start:06X}–0x{self.end:06X}  {self.length}B  {brief(self.a)}  ->  {brief(self.b)}"


def diff_bytes(a: bytes, b: bytes, min_gap: int = 8) -> list[DiffRegion]:
    """逐字节对比，把相邻改动合并成区间。min_gap 越小越碎。"""
    n = min(len(a), len(b))
    raw = [(i, a[i], b[i]) for i in range(n) if a[i] != b[i]]
    if not raw:
        return []
    regions: list[DiffRegion] = []
    cur = [raw[0][0], raw[0][0] + 1]
    for i, _, _ in raw[1:]:
        if i - (cur[1] - 1) <= min_gap:
            cur[1] = i + 1
        else:
            regions.append(DiffRegion(cur[0], cur[1], a[cur[0] : cur[1]], b[cur[0] : cur[1]]))
            cur = [i, i + 1]
    regions.append(DiffRegion(cur[0], cur[1], a[cur[0] : cur[1]], b[cur[0] : cur[1]]))
    return regions


# --------------------------------------------------------------------------- #
# 存档对象
# --------------------------------------------------------------------------- #


class SaveFile:
    def __init__(self, path: str, data: bytes | None = None):
        self.path = os.path.abspath(path)
        self.original = bytes(data) if data is not None else read_bytes(self.path)
        self.data = bytearray(self.original)
        self.checksums: list[Checksum] = []
        self.chosen: Checksum | None = None
        self.info = sniff(self.original)

    @classmethod
    def load(cls, path: str) -> "SaveFile":
        sf = cls(path)
        sf.checksums = detect_checksums(bytes(sf.data))
        sf.chosen = pick_checksum(sf.checksums, len(sf.data))
        return sf

    # -- 状态 ------------------------------------------------------------- #

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def dirty(self) -> bool:
        return bytes(self.data) != self.original

    def sha1(self) -> str:
        return hashlib.sha1(bytes(self.data)).hexdigest()

    def hexdump(self, start: int = 0, length: int = 256, width: int = 16) -> str:
        chunk = bytes(self.data[start : start + length])
        lines = []
        for i in range(0, len(chunk), width):
            row = chunk[i : i + width]
            hexs = " ".join(f"{b:02X}" for b in row)
            ascii_ = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
            lines.append(f"{start + i:08X}  {hexs:<{width * 3}}  {ascii_}")
        return "\n".join(lines)

    # -- 改写 ------------------------------------------------------------- #

    def apply(self, offset: int, payload: bytes) -> None:
        """等长改写。长度变化会让偏移和校验和全部失效，所以直接拒绝。"""
        if offset < 0 or offset + len(payload) > len(self.data):
            raise SaveError(f"越界：0x{offset:X} + {len(payload)}B 超出文件（{self.size}B）")
        self.data[offset : offset + len(payload)] = payload

    def apply_region(self, region: DiffRegion) -> None:
        self.apply(region.start, region.b)

    def set_int(self, offset: int, value: int, width: int = 4, signed: bool = False, big_endian: bool = False) -> None:
        self.apply(offset, pack_int(value, width, signed, big_endian))

    def fix_checksums(self, all_matches: bool = False) -> list[Checksum]:
        """重算校验和。默认只改最可信的那一条，避免把碰巧长得像校验和的普通数据覆盖掉。"""
        targets = list(self.checksums) if all_matches else ([self.chosen] if self.chosen else [])
        fixed = []
        for cs in targets:
            try:
                new = cs.recompute(bytes(self.data))
            except Exception:
                continue
            if bytes(self.data[cs.offset : cs.offset + cs.length]) != new:
                self.data[cs.offset : cs.offset + cs.length] = new
                fixed.append(cs)
        return fixed

    def verify_checksums(self) -> bool:
        """当前内容是否仍与所有识别到的校验和吻合。"""
        for cs in self.checksums:
            if cs.recompute(bytes(self.data)) != bytes(self.data[cs.offset : cs.offset + cs.length]):
                return False
        return True

    # -- 落盘 ------------------------------------------------------------- #

    def backup(self) -> str:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dst = f"{self.path}.bak-{stamp}"
        shutil.copy2(self.path, dst)
        return dst

    def save(self, force: bool = False, keep_backup: bool = True) -> dict:
        if not self.dirty:
            return {"saved": False, "reason": "内容未变化"}
        if not self.checksums and not force:
            raise SaveError(
                "没识别到校验和，直接写回可能被游戏判为损坏。确认要用 force=True 写入。"
            )
        bak = self.backup() if keep_backup else None
        fixed = self.fix_checksums()
        payload = bytes(self.data)
        tmp = self.path + ".tmp-write"
        with open(tmp, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.replace(tmp, self.path)
        except OSError:
            os.unlink(tmp)
            raise
        self.original = payload
        return {
            "saved": True,
            "backup": bak,
            "checksums_fixed": [c.describe() for c in fixed],
            "size": len(payload),
        }

    # -- 分析 ------------------------------------------------------------- #

    def diff(self, other: "SaveFile", min_gap: int = 8) -> list[DiffRegion]:
        return diff_bytes(bytes(self.data), bytes(other.data), min_gap)


# --------------------------------------------------------------------------- #
# 文件与定位
# --------------------------------------------------------------------------- #


def read_bytes(path: str) -> bytes:
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as exc:
        raise SaveError(f"读取失败：{path}（{exc}）") from exc


def default_roots() -> list[str]:
    home = os.path.expanduser("~")
    cands = [
        os.environ.get("LOCALAPPDATA"),
        os.environ.get("APPDATA"),
        os.path.join(home, "AppData", "LocalLow"),
        os.path.join(home, "Saved Games"),
        os.path.join(home, "Documents"),
        os.path.join(home, "文档"),
    ]
    return [c for c in cands if c and os.path.isdir(c)]


def _looks_like_save(name: str) -> bool:
    low = name.lower()
    return low.endswith(SAVE_EXTS) or any(k in low for k in SAVE_KEYWORDS)


def auto_locate(roots: list[str] | None = None, max_depth: int = 5, limit: int = 400) -> list[str]:
    """在常规目录里找疑似存档。命中关键词的目录内部会额外放宽扩展名限制。"""
    roots = roots or default_roots()
    hits: dict[str, float] = {}
    seen_dirs = 0
    for root in roots:
        base_depth = root.rstrip("\\/").count(os.sep)
        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            seen_dirs += 1
            depth = dirpath.count(os.sep) - base_depth
            if depth >= max_depth or seen_dirs > 20000:
                dirnames[:] = []
                continue
            dirnames[:] = [
                d
                for d in dirnames
                if not d.startswith(("$", ".git", "node_modules", "Windows", "Temp"))
            ]
            dir_hit = any(k in dirpath.lower() for k in SAVE_KEYWORDS)
            for fn in filenames:
                if not (dir_hit or _looks_like_save(fn)):
                    continue
                full = os.path.join(dirpath, fn)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                if 256 <= st.st_size <= 64 << 20:
                    hits[full] = st.st_mtime
            if len(hits) > limit * 4:
                break
    ranked = sorted(hits.items(), key=lambda kv: kv[1], reverse=True)
    return [p for p, _ in ranked[:limit]]


def format_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.2f}{unit}"
        n /= 1024.0
    return f"{n}B"
