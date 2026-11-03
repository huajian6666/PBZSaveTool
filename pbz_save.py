"""PBZS 存档读写：AES-256-GCM 容器 + Oodle 解压 + JSON 编辑 + 重新打包。

块布局
    header  b"PBZS" + <BBHI> version=3, flags=1, count, directory_size
    dir     seal(header + rows)                       # 行首 12 字节必须等于 header
    rows    <H name_len> name <BBIII> algo, 1, raw_size, offset, block_size
    block   b"PBZS\\x01\\x01\\x00\\x00" + nonce(12) + tag(16) + cipher

压缩算法：0 原样 / 1 zlib / 2 Oodle。写回时统一用 2 + Oodle 存储块（\\xcc\\x06 分段），
不需要专有编码器，游戏自带的解码器认这种块。
"""

from __future__ import annotations

import ctypes
import json
import os
import struct
from dataclasses import dataclass, field

from Crypto.Cipher import AES

MAGIC = b"PBZS"
BLOCK_HDR = b"PBZS\x01\x01\x00\x00"
NONCE_LEN = 12
TAG_LEN = 16
OVERHEAD = len(BLOCK_HDR) + NONCE_LEN + TAG_LEN  # 36
CHUNK = 0x40000
MAX_SLOT = 64 * 1024 * 1024


class SaveError(Exception):
    pass


# --------------------------------------------------------------------------- #
# Oodle 解码
# --------------------------------------------------------------------------- #


class OodleCodec:
    """基于开源解码器 oozextract 编译的 pbz_codec.dll（见 native/NOTICE）。"""

    def __init__(self, path: str | None = None):
        base = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            path,
            os.path.join(base, "native", "pbz_codec.dll"),
            os.path.join(getattr(os.sys, "_MEIPASS", base), "native", "pbz_codec.dll"),
        ]
        for cand in candidates:
            if cand and os.path.isfile(cand):
                self.dll = ctypes.CDLL(cand)
                break
        else:
            raise SaveError("找不到 pbz_codec.dll，无法解压存档。")
        self.dll.pbz_codec_version.restype = ctypes.c_uint32
        if self.dll.pbz_codec_version() != 1:
            raise SaveError("pbz_codec.dll 版本不匹配。")
        self._fn = self.dll.pbz_decode
        self._fn.restype = ctypes.c_size_t
        self._fn.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]

    def decompress(self, data: bytes, size: int) -> bytes:
        if not 0 <= size <= MAX_SLOT:
            raise SaveError("解压尺寸超出范围。")
        out = ctypes.create_string_buffer(max(1, size))
        n = self._fn(data, len(data), out, size)
        if n != size:
            raise SaveError("Oodle 解压失败，文件可能损坏。")
        return out.raw[:size]


_CODEC: OodleCodec | None = None


def codec() -> OodleCodec:
    global _CODEC
    if _CODEC is None:
        _CODEC = OodleCodec()
    return _CODEC


def oodle_store(data: bytes) -> bytes:
    """把明文切成 256KB 的 Oodle 存储块（不压缩，但格式合法）。"""
    if not data:
        return b"\xcc\x06"
    return b"".join(b"\xcc\x06" + data[p : p + CHUNK] for p in range(0, len(data), CHUNK))


# --------------------------------------------------------------------------- #
# 容器
# --------------------------------------------------------------------------- #


@dataclass
class Slot:
    name: str
    algo: int
    size: int
    offset: int
    block_size: int
    block: bytes = field(repr=False, default=b"")
    original: bytes = field(repr=False, default=b"")
    _raw: bytes | None = field(repr=False, default=None)
    dirty: bool = False

    @property
    def label(self) -> str:
        return "手动" if self.name.startswith("ManualSave") else ("自动" if self.name.startswith("AutoSave") else "系统")


def _seal(key: bytes, plain: bytes) -> bytes:
    nonce = os.urandom(NONCE_LEN)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce, mac_len=TAG_LEN)
    ct, tag = cipher.encrypt_and_digest(plain)
    return BLOCK_HDR + nonce + tag + ct


def _unseal(key: bytes, block: bytes) -> bytes:
    if len(block) < OVERHEAD or block[:8] != BLOCK_HDR:
        raise SaveError("加密块头无效。")
    nonce = block[8:20]
    tag = block[20:36]
    ct = block[36:]
    try:
        return AES.new(key, AES.MODE_GCM, nonce=nonce, mac_len=TAG_LEN).decrypt_and_verify(ct, tag)
    except ValueError as exc:
        raise SaveError("完整性校验失败：文件损坏或密钥不对。") from exc


class Save:
    def __init__(self, path: str, key: bytes):
        self.path = os.path.abspath(path)
        self.key = key
        with open(self.path, "rb") as fh:
            self.source = fh.read()
        self.slots: list[Slot] = []
        self._parse()

    # -- 读 --------------------------------------------------------------- #

    def _parse(self) -> None:
        data = self.source
        if data[:4] != MAGIC:
            raise SaveError("不是 PBZS 存档。")
        version, flags, count, dir_size = struct.unpack_from("<BBHI", data, 4)
        if version != 3 or flags != 1:
            raise SaveError(f"不支持的容器版本 {version}/{flags}。")
        self.header = data[:12]
        self.dir_size = dir_size
        directory = _unseal(self.key, data[12 : 12 + dir_size])
        if directory[:12] != self.header:
            raise SaveError("目录头副本校验失败。")
        base = 12 + dir_size
        cursor = 12
        for _ in range(count):
            nlen = struct.unpack_from("<H", directory, cursor)[0]
            cursor += 2
            name = directory[cursor : cursor + nlen].decode("utf-8")
            cursor += nlen
            algo, flag, size, offset, bsize = struct.unpack_from("<BBIII", directory, cursor)
            cursor += 14
            block = data[base + offset : base + offset + bsize]
            self.slots.append(Slot(name, algo, size, offset, bsize, block, block))

    def slot(self, name: str) -> Slot:
        for s in self.slots:
            if s.name == name:
                return s
        raise SaveError(f"没有槽位 {name}")

    def raw(self, slot: Slot) -> bytes:
        if slot._raw is None:
            plain = _unseal(self.key, slot.block)
            if slot.algo == 0:
                out = plain
            elif slot.algo == 1:
                import zlib

                out = zlib.decompress(plain)
            elif slot.algo == 2:
                out = codec().decompress(plain, slot.size)
            else:
                raise SaveError(f"未知压缩算法 {slot.algo}")
            if len(out) != slot.size:
                raise SaveError(f"{slot.name} 尺寸与目录不符。")
            slot._raw = out
        return slot._raw

    def text(self, slot: Slot) -> str:
        return self.raw(slot).decode("utf-8")

    def obj(self, slot: Slot) -> dict:
        return json.loads(self.raw(slot))

    # -- 写 --------------------------------------------------------------- #

    def set_raw(self, slot: Slot, raw: bytes) -> None:
        json.loads(raw)  # 必须是合法 JSON
        slot._raw = raw
        slot.size = len(raw)
        slot.dirty = True

    def build(self) -> bytes:
        rows = bytearray()
        chunks = bytearray()
        offset = 0
        for s in self.slots:
            if s.dirty:
                raw = self.raw(s)
                plain = oodle_store(raw)
                s.algo = 2
                s.block = _seal(self.key, plain)
                s.size = len(raw)
            block = s.block
            name = s.name.encode("utf-8")
            rows += struct.pack("<H", len(name)) + name
            rows += struct.pack("<BBIII", s.algo, 1, s.size, offset, len(block))
            chunks += block
            offset += len(block)
        dir_plain = self.header + bytes(rows)
        self.dir_size = len(dir_plain) + OVERHEAD
        header = MAGIC + struct.pack("<BBHI", 3, 1, len(self.slots), self.dir_size)
        # 目录明文前 12 字节必须与最终文件头一致，所以用新 header 重新封一次
        dir_plain = header + bytes(rows)
        return header + _seal(self.key, dir_plain) + bytes(chunks)

    def save(self, backup: bool = True) -> str | None:
        data = self.build()
        bak = None
        if backup:
            import shutil
            from datetime import datetime

            bak = f"{self.path}.bak-{datetime.now():%Y%m%d-%H%M%S}"
            shutil.copy2(self.path, bak)
        tmp = self.path + ".tmp-write"
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)
        self.source = data
        for s in self.slots:
            s.dirty = False
            s.original = s.block
        return bak

    # -- JSON 辅助 -------------------------------------------------------- #

    def find(self, value: str, slot: Slot | None = None) -> list[tuple[Slot, str, str]]:
        """在 JSON 里按值搜索，返回值所在的路径。"""
        hits: list[tuple[Slot, str, str]] = []
        for s in [slot] if slot else self.slots:
            try:
                obj = self.obj(s)
            except Exception:
                continue
            hits.extend((s, path, json.dumps(v, ensure_ascii=False)) for path, v in _walk(obj, "") if _match(v, value))
        return hits


def _match(v, needle: str) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return str(v) == needle
    if isinstance(v, str):
        return needle in v
    return False


def _walk(node, path: str):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")
    else:
        yield path, node


def get_path(obj, path: str):
    cur = obj
    for part in _split_path(path):
        if isinstance(part, int):
            cur = cur[part]
        else:
            cur = cur[part]
    return cur


def _split_path(path: str):
    out = []
    for chunk in path.split("."):
        if "[" in chunk:
            name, rest = chunk.split("[", 1)
            if name:
                out.append(name)
            for idx in rest.rstrip("]").split("]["):
                out.append(int(idx))
        elif chunk:
            out.append(chunk)
    return out


def set_path(obj, path: str, value) -> None:
    parts = _split_path(path)
    cur = obj
    for part in parts[:-1]:
        cur = cur[part]
    cur[parts[-1]] = value
