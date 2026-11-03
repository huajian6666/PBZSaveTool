#!/usr/bin/env python3
"""影之刃零 · 存档修改器

打开存档 → 自动读出货币 / 天数 / 杀意 / 物品 / 任务 → 可视化修改 → 写回。
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pbz_core as core
import pbz_save as ps

APP_TITLE = "影之刃零 · 存档修改器"
AUTHOR = "花见 · B站 UID 169145480"
KEY = bytes.fromhex("15a1fe0f55e0eb298e7c9461548351696a2a0700ed2d17ba1f871457e8f93e2d")
def _find_save_root() -> str:
    """找 PBZ 的存档目录；找不到就返回空串，让用户手动选文件。"""
    tail = os.path.join("ProjectPBZ", "Saved", "SaveGames", "Steam")
    roots = []
    for drive in ("E:", "D:", "F:", "C:"):
        roots.append(os.path.join(drive + os.sep, "SteamLibrary", "steamapps", "common", "PBZ"))
    roots.append(os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Steam", "steamapps", "common", "PBZ"))
    roots.append(os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Steam", "steamapps", "common", "PBZ"))
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            steam = winreg.QueryValueEx(key, "SteamPath")[0]
        roots.append(os.path.join(steam, "steamapps", "common", "PBZ"))
    except Exception:
        pass
    for root in roots:
        target = os.path.join(root, tail)
        if os.path.isdir(target):
            return target
    return ""


GAME_SAVE_ROOT = _find_save_root()


# --------------------------------------------------------------------------- #
# DPI
# --------------------------------------------------------------------------- #


def _enable_dpi() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # system DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _dpi_scale() -> float:
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
        if 72 <= dpi <= 480:
            return dpi / 96.0
    except Exception:
        pass
    return 1.0


_enable_dpi()
SCALE = _dpi_scale()


def px(v: float) -> int:
    return max(1, int(round(v * SCALE)))


# --------------------------------------------------------------------------- #
# 主题
# --------------------------------------------------------------------------- #


class C:
    BG = "#F1F2F5"
    CARD = "#FFFFFF"
    BORDER = "#E2E5EA"
    TEXT = "#1B1E23"
    MUTED = "#767E8C"
    FAINT = "#A2A9B4"
    ACCENT = "#B33A2B"
    ACCENT_D = "#94301F"
    ACCENT_SOFT = "#FBEDEA"
    HEADER = "#17181C"
    HEADER_TX = "#F4F5F7"
    HEADER_MUTED = "#9AA0AA"
    OK = "#2F7A5F"
    WARN = "#B0761C"
    STRIPE = "#F7F8FA"


class F:
    title = ("Microsoft YaHei UI", 15, "bold")
    tab = ("Microsoft YaHei UI", 10)
    body = ("Microsoft YaHei UI", 10)
    small = ("Microsoft YaHei UI", 9)
    tiny = ("Microsoft YaHei UI", 8)
    bold = ("Microsoft YaHei UI", 9, "bold")
    stat = ("Microsoft YaHei UI", 18, "bold")
    mono = ("Consolas", 10)
    mono_sm = ("Consolas", 9)


def apply_theme(root: tk.Misc) -> None:
    st = ttk.Style(root)
    st.theme_use("clam")
    st.configure(".", background=C.BG, foreground=C.TEXT, font=F.body, borderwidth=0)
    st.configure("TFrame", background=C.BG)
    st.configure("TLabel", background=C.BG, foreground=C.TEXT)
    st.configure("Status.TLabel", background=C.CARD, foreground=C.MUTED, font=F.small)
    for name, base, fg in (
        ("TButton", "#F6F7F9", C.TEXT),
        ("Ghost.TButton", "#F6F7F9", C.TEXT),
        ("Primary.TButton", C.ACCENT, "#FFFFFF"),
    ):
        st.configure(
            name,
            background=base,
            foreground=fg,
            bordercolor=C.ACCENT if name == "Primary.TButton" else "#DBDFE5",
            lightcolor=base,
            darkcolor=base,
            focuscolor=base,
            padding=(px(14), px(6)) if name == "Primary.TButton" else (px(12), px(6)),
            relief="flat",
            font=F.small,
        )
    st.map("TButton", background=[("active", "#ECEEF2")], foreground=[("disabled", C.FAINT)])
    st.map("Ghost.TButton", background=[("active", "#ECEEF2")], foreground=[("disabled", C.FAINT)])
    st.map("Primary.TButton", background=[("active", C.ACCENT_D)])
    st.configure(
        "Cat.TButton",
        background="#F6F7F9",
        foreground=C.MUTED,
        bordercolor="#DBDFE5",
        lightcolor="#F6F7F9",
        darkcolor="#F6F7F9",
        focuscolor="#F6F7F9",
        padding=(px(14), px(6)),
        relief="flat",
        font=F.small,
    )
    st.configure(
        "CatActive.TButton",
        background=C.ACCENT_SOFT,
        foreground=C.ACCENT,
        bordercolor=C.ACCENT,
        lightcolor=C.ACCENT_SOFT,
        darkcolor=C.ACCENT_SOFT,
        focuscolor=C.ACCENT_SOFT,
        padding=(px(14), px(6)),
        relief="flat",
        font=F.bold,
    )
    st.map("Cat.TButton", background=[("active", "#ECEEF2")])
    st.map("CatActive.TButton", background=[("active", C.ACCENT_SOFT)])
    st.configure("TEntry", fieldbackground="#FFFFFF", background=C.CARD, bordercolor=C.BORDER, padding=(px(9), px(5)))
    st.map("TEntry", bordercolor=[("focus", C.ACCENT)])
    st.configure("TCombobox", fieldbackground="#FFFFFF", background=C.CARD, bordercolor=C.BORDER, padding=(px(7), px(4)))
    st.map("TCombobox", fieldbackground=[("readonly", "#FFFFFF")], bordercolor=[("focus", C.ACCENT)])
    st.configure(
        "Treeview",
        background=C.CARD,
        fieldbackground=C.CARD,
        foreground=C.TEXT,
        rowheight=px(27),
        borderwidth=0,
        relief="flat",
        bordercolor=C.CARD,
        lightcolor=C.CARD,
        darkcolor=C.CARD,
        font=F.small,
    )
    st.configure(
        "Treeview.Heading",
        background="#FAFBFC",
        foreground=C.MUTED,
        font=F.bold,
        relief="flat",
        borderwidth=0,
        padding=(px(10), px(8)),
    )
    st.map("Treeview", background=[("selected", C.ACCENT_SOFT)], foreground=[("selected", C.TEXT)])
    st.configure("Vertical.TScrollbar", background="#E7EAEF", troughcolor=C.CARD, bordercolor=C.CARD, arrowsize=px(12))


def card(parent: tk.Misc, title: str | None = None, note: str | None = None) -> tk.Frame:
    outer = tk.Frame(parent, bg=C.CARD, highlightthickness=1, highlightbackground=C.BORDER)
    if title:
        head = tk.Frame(outer, bg=C.CARD)
        head.pack(fill="x", padx=px(14), pady=(px(11), 0))
        tk.Label(head, text=title, bg=C.CARD, fg=C.TEXT, font=F.bold).pack(side="left")
        if note:
            tk.Label(head, text=note, bg=C.CARD, fg=C.FAINT, font=F.tiny).pack(side="left", padx=px(8))
    return outer


def table(parent: tk.Misc, specs, height: int = 10):
    wrap = tk.Frame(parent, bg=C.CARD)
    tree = ttk.Treeview(wrap, columns=[s[0] for s in specs], show="headings", height=height, selectmode="browse")
    for key, width, anchor in specs:
        tree.heading(key, text=key, anchor=anchor)
        tree.column(key, width=px(width), anchor=anchor, stretch=(key == specs[-1][0]))
    sb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y", padx=(px(6), 0))
    tree.tag_configure("odd", background=C.CARD)
    tree.tag_configure("even", background=C.STRIPE)
    return tree, wrap


def stripe(tree: ttk.Treeview) -> None:
    for i, item in enumerate(tree.get_children()):
        tree.item(item, tags=("even" if i % 2 else "odd",))


class TabBar(tk.Frame):
    def __init__(self, master, titles, on_change=None):
        super().__init__(master, bg=C.BG)
        self.on_change = on_change
        self.current = -1
        row = tk.Frame(self, bg=C.BG)
        row.pack(fill="x", padx=px(16), pady=(px(6), 0))
        self.items = []
        for i, title in enumerate(titles):
            holder = tk.Frame(row, bg=C.BG)
            holder.pack(side="left", padx=(0, px(2)))
            lbl = tk.Label(holder, text=title, bg=C.BG, fg=C.MUTED, font=F.tab, padx=px(13), pady=px(7), cursor="hand2")
            lbl.pack()
            ind = tk.Frame(holder, height=px(2), bg=C.BG)
            ind.pack(fill="x")
            lbl.bind("<Button-1>", lambda _e, i=i: self.select(i))
            self.items.append((lbl, ind))
        tk.Frame(self, height=1, bg=C.BORDER).pack(fill="x")

    def select(self, i: int) -> None:
        if i == self.current:
            return
        self.current = i
        for j, (lbl, ind) in enumerate(self.items):
            active = j == i
            lbl.configure(fg=C.ACCENT if active else C.MUTED)
            ind.configure(bg=C.ACCENT if active else C.BG)
        if self.on_change:
            self.on_change(i)


# --------------------------------------------------------------------------- #
# 字段表
# --------------------------------------------------------------------------- #

CARDS = [
    ("货币 · 尘", ["Player", "Dust"], int),
    ("剩余天数", ["Player", "RemainingDays"], int),
    ("杀意值", ["Player", "UltimateCharge"], float),
    ("杀意槽", ["Player", "UltimateChargeCount"], int),
    ("暗源", ["Player", "SpiritShadow"], int),
    ("生命饰品等级", ["Inventory", "AccessoryInfos", "AC_Health", "CurrentLevel"], int),
]

CATEGORIES = [
    ("物品", ["Inventory", "InventoryInfos"], "CurrentAmount", "MaxAmount", "数量"),
    ("影之武装", ["Inventory", "ShaChiWeaponInfo"], "ShaChiWeaponLevel", None, "等级"),
    ("饰品", ["Inventory", "AccessoryInfos"], "CurrentLevel", None, "强化等级"),
    ("药品", ["Inventory", "MedicineInfos"], "CurrentLevel", None, "等级"),
]

CATEGORY_HINT = {
    "物品": "数量 = 背包里这件东西的个数；上限来自数据的 MaxAmount，改超了可能被游戏压回去。",
    "影之武装": "等级 = 影之武装（ShaChiWeapon）的强化等级，直接对应面板上的武器等级。",
    "饰品": "强化等级：0 = 已获得但未强化，1 = 已强化；备注里会标「已装备」。",
    "药品": "等级 = 药品的强化等级；次数是当前存量 / 上限。",
}

BRANCH_TYPES = [
    "EBranchType::BranchCompleted",
    "EBranchType::BranchActivating",
    "EBranchType::BranchLocked",
    "EBranchType::None",
]

NAMES: dict[str, dict] = {}


def load_names() -> None:
    if NAMES:
        return
    bases = []
    if getattr(sys, "frozen", False):
        bases.append(getattr(sys, "_MEIPASS", ""))
        bases.append(os.path.dirname(sys.executable))
    else:
        bases.append(os.path.dirname(os.path.abspath(__file__)))
    for base in bases:
        path = os.path.join(base, "names.json")
        if base and os.path.isfile(path):
            try:
                data = json.load(open(path, encoding="utf-8"))
                for it in data.get("items", []):
                    NAMES[it["id"]] = {"name": it.get("name") or it["id"], "category": it.get("category", "")}
                return
            except Exception:
                pass


def name_of(item_id: str) -> str:
    return NAMES.get(item_id, {}).get("name", "")


def get_at(obj, path):
    cur = obj
    for p in path:
        cur = cur[p]
    return cur


def set_at(obj, path, value):
    cur = obj
    for p in path[:-1]:
        cur = cur[p]
    cur[path[-1]] = value


# --------------------------------------------------------------------------- #
# 主体
# --------------------------------------------------------------------------- #


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.tk.call("tk", "scaling", 96.0 / 72.0 * SCALE)
        self.geometry(f"{px(1220)}x{px(820)}")
        self.minsize(px(1080), px(700))
        self.configure(bg=C.BG)
        apply_theme(self)
        self._set_icon()
        load_names()

        self.save: ps.Save | None = None
        self.slot: ps.Slot | None = None
        self.data: dict | None = None
        self.rows: list[dict] = []
        self.quests: list[dict] = []
        self.quest_rows: list[dict] = []
        self.pending_acc: list[str] = []
        self.snapshots: list[tuple] = []
        self.category = tk.StringVar(value="物品")
        self.slot_name = tk.StringVar()
        self.path_var = tk.StringVar()
        self.filter_var = tk.StringVar()
        self.status = tk.StringVar(value="未打开存档")

        self._build_header()
        self._build_status()
        body = tk.Frame(self, bg=C.BG)
        body.pack(fill="both", expand=True)
        self.notebook = TabBar(body, ["面板", "任务", "未完成", "快照", "说明"], on_change=self._on_tab)
        self.notebook.pack(fill="x")
        self.host = tk.Frame(body, bg=C.BG)
        self.host.pack(fill="both", expand=True)
        self.host.rowconfigure(0, weight=1)
        self.host.columnconfigure(0, weight=1)
        self.pages = [
            self._page_panel(ttk.Frame(self.host)),
            self._page_quests(ttk.Frame(self.host)),
            self._page_pending(ttk.Frame(self.host)),
            self._page_snapshot(ttk.Frame(self.host)),
            self._page_help(ttk.Frame(self.host)),
        ]
        for pg in self.pages:
            pg.grid(row=0, column=0, sticky="nsew")
        self.notebook.select(0)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._autodetect()
        self._refresh_header()

    def _set_icon(self) -> None:
        size = px(32)
        icon = tk.PhotoImage(width=size, height=size)
        icon.put(C.HEADER, to=(0, 0, size, size))
        icon.put(C.ACCENT, to=(px(7), px(6), px(11), px(26)))
        icon.put(C.ACCENT, to=(px(15), px(6), px(25), px(10)))
        icon.put(C.ACCENT, to=(px(15), px(14), px(23), px(18)))
        icon.put(C.ACCENT, to=(px(15), px(22), px(25), px(26)))
        try:
            self.iconphoto(True, icon)
            self._icon = icon
        except Exception:
            pass

    # -- 骨架 ------------------------------------------------------------- #

    def _build_header(self) -> None:
        bar = tk.Frame(self, bg=C.HEADER, height=px(58))
        bar.pack(fill="x")
        bar.pack_propagate(False)
        left = tk.Frame(bar, bg=C.HEADER)
        left.pack(side="left", padx=px(18))
        tk.Frame(left, bg=C.ACCENT, width=px(3), height=px(26)).pack(side="left", pady=px(16))
        titles = tk.Frame(left, bg=C.HEADER)
        titles.pack(side="left", padx=(px(10), 0))
        tk.Label(titles, text="影之刃零", bg=C.HEADER, fg=C.HEADER_TX, font=F.title).pack(anchor="w")
        tk.Label(titles, text="存档修改器 · Phantom Blade Zero", bg=C.HEADER, fg=C.HEADER_MUTED, font=F.tiny).pack(anchor="w")
        tk.Label(bar, text=AUTHOR, bg=C.HEADER, fg="#8C939E", font=F.tiny).pack(side="right", padx=(0, px(18)))
        self.chip = tk.Frame(bar, bg="#24262B")
        self.chip.pack(side="right", padx=px(18), pady=px(13))
        self.chip_name = tk.Label(self.chip, text="未打开", bg="#24262B", fg=C.HEADER_TX, padx=px(12), pady=px(3), font=F.small)
        self.chip_name.pack(side="left")
        self.chip_meta = tk.Label(self.chip, text="", bg="#24262B", fg=C.HEADER_MUTED, font=F.tiny, pady=px(3))
        self.chip_meta.pack(side="left", padx=(0, px(12)))

    def _build_status(self) -> None:
        wrap = tk.Frame(self, bg=C.CARD, height=px(32))
        wrap.pack(fill="x", side="bottom")
        wrap.pack_propagate(False)
        tk.Frame(wrap, bg=C.BORDER, height=1).pack(fill="x", side="top")
        self.dot = tk.Label(wrap, text="●", bg=C.CARD, fg=C.FAINT, font=("Segoe UI", 9))
        self.dot.pack(side="left", padx=(px(16), px(6)))
        ttk.Label(wrap, textvariable=self.status, style="Status.TLabel").pack(side="left")
        tk.Label(wrap, text=AUTHOR, bg=C.CARD, fg=C.FAINT, font=F.tiny).pack(side="right", padx=px(16))

    def _on_tab(self, i: int) -> None:
        self.pages[i].tkraise()

    def _refresh_header(self) -> None:
        if not self.save:
            self.chip_name.configure(text="未打开")
            self.chip_meta.configure(text="")
            self.dot.configure(fg=C.FAINT)
            return
        dirty = any(s.dirty for s in self.save.slots)
        self.chip_name.configure(text=os.path.basename(self.save.path))
        self.chip_meta.configure(text=f"{core.format_size(os.path.getsize(self.save.path))} · {len(self.save.slots)} 槽")
        self.dot.configure(fg=C.ACCENT if dirty else C.OK)

    # -- 面板 ------------------------------------------------------------- #

    def _page_panel(self, page: ttk.Frame) -> ttk.Frame:
        bar = card(page)
        bar.pack(fill="x", padx=px(16), pady=(px(12), px(10)))
        inner = tk.Frame(bar, bg=C.CARD)
        inner.pack(fill="x", padx=px(12), pady=px(9))
        tk.Label(inner, text="存档", bg=C.CARD, fg=C.MUTED, font=F.small).pack(side="left", padx=(px(2), px(6)))
        ttk.Entry(inner, textvariable=self.path_var, width=48).pack(side="left")
        ttk.Button(inner, text="浏览", style="Ghost.TButton", command=self._browse).pack(side="left", padx=px(6))
        ttk.Button(inner, text="自动查找", style="Ghost.TButton", command=self._autodetect).pack(side="left")
        ttk.Button(inner, text="打开", style="Primary.TButton", command=self._open).pack(side="left", padx=px(6))
        tk.Label(inner, text="编辑槽位", bg=C.CARD, fg=C.MUTED, font=F.small).pack(side="left", padx=(px(18), px(6)))
        self.slot_combo = ttk.Combobox(inner, textvariable=self.slot_name, width=14, state="readonly")
        self.slot_combo.pack(side="left")
        self.slot_combo.bind("<<ComboboxSelected>>", lambda _e: self._load_slot())

        tiles = tk.Frame(page, bg=C.BG)
        tiles.pack(fill="x", padx=px(16))
        self.tiles = []
        for i, (label, path, kind) in enumerate(CARDS):
            cell = tk.Frame(tiles, bg=C.CARD, highlightthickness=1, highlightbackground=C.BORDER, cursor="hand2")
            cell.pack(side="left", fill="x", expand=True, padx=(0, px(6)) if i < len(CARDS) - 1 else 0, pady=(0, px(10)))
            lab = tk.Label(cell, text=label, bg=C.CARD, fg=C.FAINT, font=F.tiny, anchor="w")
            lab.pack(fill="x", padx=px(12), pady=(px(9), 0))
            val = tk.Label(cell, text="—", bg=C.CARD, fg=C.TEXT, font=F.stat, anchor="w")
            val.pack(fill="x", padx=px(11), pady=(0, px(2)))
            tk.Label(cell, text="点击修改", bg=C.CARD, fg=C.ACCENT, font=F.tiny, anchor="w").pack(
                fill="x", padx=px(12), pady=(0, px(7))
            )
            for w in (cell, val):
                w.bind("<Button-1>", lambda _e, p=path, k=kind, t=label: self._edit_dialog(p, k, t))
            self.tiles.append((label, path, kind, val, lab))

        bar2 = tk.Frame(page, bg=C.BG)
        bar2.pack(fill="x", padx=px(16))
        self.cat_buttons: dict[str, ttk.Button] = {}
        for name, *_ in CATEGORIES:
            b = ttk.Button(bar2, text=name, style="Cat.TButton", command=lambda n=name: self._set_category(n))
            b.pack(side="left", padx=(0, px(6)))
            self.cat_buttons[name] = b
        tk.Label(bar2, text="过滤", bg=C.BG, fg=C.FAINT, font=F.tiny).pack(side="left", padx=(px(14), px(4)))
        f = ttk.Entry(bar2, textvariable=self.filter_var, width=18)
        f.pack(side="left")
        f.bind("<KeyRelease>", lambda _e: self._fill_table())
        self.cat_label = tk.Label(bar2, text="", bg=C.BG, fg=C.FAINT, font=F.tiny)
        self.cat_label.pack(side="left", padx=px(12))

        self.hint = tk.Label(page, text="", bg=C.BG, fg=C.MUTED, font=F.tiny, anchor="w", justify="left")
        self.hint.pack(fill="x", padx=px(18), pady=(px(4), 0))

        box = card(page, "明细", "双击一行改数值")
        box.pack(fill="both", expand=True, padx=px(16), pady=(px(6), px(8)))
        self.item_tree, wrap = table(
            box, [("名称", 300, "w"), ("编号", 240, "w"), ("数值", 110, "e"), ("备注", 280, "w")], height=11
        )
        wrap.pack(fill="both", expand=True, padx=px(10), pady=px(10))
        self.item_tree.bind("<Double-1>", self._edit_row)

        foot = tk.Frame(page, bg=C.BG)
        foot.pack(fill="x", padx=px(18), pady=(0, px(12)))
        ttk.Button(foot, text="保存修改", style="Primary.TButton", command=self._save).pack(side="right")
        ttk.Button(foot, text="放弃修改", style="TButton", command=self._load_slot).pack(side="left")
        ttk.Button(foot, text="导出 JSON", style="Ghost.TButton", command=self._export).pack(side="left", padx=px(8))
        self._set_category("物品")
        return page

    # -- 任务 ------------------------------------------------------------- #

    def _page_quests(self, page: ttk.Frame) -> ttk.Frame:
        box = card(page, "任务", "双击改分支状态和进度；改任务结构有卡关风险，先备份")
        box.pack(fill="both", expand=True, padx=px(16), pady=(px(12), px(10)))
        self.quest_tree, wrap = table(
            box,
            [("任务", 400, "w"), ("分支", 70, "e"), ("已完成", 80, "e"), ("当前分支", 160, "w"),
             ("状态", 210, "w"), ("进度", 230, "w")],
            height=14,
        )
        wrap.pack(fill="both", expand=True, padx=px(10), pady=px(10))
        self.quest_tree.bind("<Double-1>", self._edit_quest)
        return page

    # -- 未完成 ----------------------------------------------------------- #

    def _page_pending(self, page: ttk.Frame) -> ttk.Frame:
        top = card(page, "未完成任务", "所有分支还没走完的任务")
        top.pack(fill="both", expand=True, padx=px(16), pady=(px(12), px(8)))
        self.pend_quest, wrap1 = table(
            top, [("任务", 440, "w"), ("分支", 70, "e"), ("已完成", 80, "e"), ("状态", 220, "w"), ("进度", 200, "w")],
            height=8,
        )
        wrap1.pack(fill="both", expand=True, padx=px(10), pady=px(10))

        bottom = card(page, "未获得饰品", "目录里有、存档里没有的饰品；选中后可以加进存档")
        bottom.pack(fill="both", expand=True, padx=px(16), pady=(0, px(12)))
        self.pend_acc, wrap2 = table(bottom, [("名称", 320, "w"), ("编号", 300, "w"), ("状态", 200, "w")], height=8)
        wrap2.pack(fill="both", expand=True, padx=px(10), pady=(px(10), px(4)))
        bar = tk.Frame(bottom, bg=C.CARD)
        bar.pack(fill="x", padx=px(10), pady=(0, px(10)))
        ttk.Button(bar, text="添加到存档（选中）", style="Primary.TButton", command=self._grant_accessory).pack(side="left")
        tk.Label(
            bar, text="双击一行也能加；加完记得「保存修改」", bg=C.CARD, fg=C.FAINT, font=F.tiny
        ).pack(side="left", padx=px(10))
        self.pend_acc.bind("<Double-1>", lambda _e: self._grant_accessory())
        return page

    # -- 快照 ------------------------------------------------------------- #

    def _page_snapshot(self, page: ttk.Frame) -> ttk.Frame:
        box = card(page, "历史快照", "1RealTime 约 15 秒一次 / 2Hourly / 3Daily")
        box.pack(fill="both", expand=True, padx=px(16), pady=(px(12), px(10)))
        self.snap_tree, wrap = table(box, [("类型", 110, "w"), ("时间", 200, "w"), ("大小", 120, "e")], height=14)
        wrap.pack(fill="both", expand=True, padx=px(10), pady=px(10))
        foot = tk.Frame(page, bg=C.BG)
        foot.pack(fill="x", padx=px(18), pady=(0, px(12)))
        ttk.Button(foot, text="用快照覆盖当前存档", style="Primary.TButton", command=self._restore).pack(side="left")
        ttk.Button(foot, text="刷新", style="Ghost.TButton", command=self._load_snapshots).pack(side="left", padx=px(8))
        tk.Label(
            foot, text="覆盖前自动备份；建议先退出游戏、关掉 Steam 云同步", bg=C.BG, fg=C.FAINT, font=F.tiny
        ).pack(side="left", padx=px(10))
        return page

    # -- 说明 ------------------------------------------------------------- #

    def _page_help(self, page: ttk.Frame) -> ttk.Frame:
        box = card(page)
        box.pack(fill="both", expand=True, padx=px(16), pady=px(12))
        text = tk.Text(box, wrap="word", relief="flat", bg=C.CARD, font=F.body, padx=px(18), pady=px(14), spacing3=px(6))
        sb = ttk.Scrollbar(box, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=sb.set)
        text.pack(side="left", fill="both", expand=True, padx=(px(6), 0), pady=px(6))
        sb.pack(side="right", fill="y", pady=px(6), padx=(0, px(6)))
        text.tag_configure("h", font=("Microsoft YaHei UI", 11, "bold"), foreground=C.ACCENT, spacing1=px(10))
        text.insert("end", f"{APP_TITLE}\n", "h")
        text.insert("end", f"作者：{AUTHOR}\n\n")
        text.insert("end", "字段含义\n", "h")
        for line in (
            "货币 · 尘 = Player.Dust（通用货币）",
            "剩余天数 = Player.RemainingDays（周目推进）",
            "杀意值 = Player.UltimateCharge（0–100 浮点）",
            "杀意槽 = Player.UltimateChargeCount",
            "暗源 = Player.SpiritShadow。官方中文叫「暗源」，和复活系统一起存档；进度 61 天时是 4，55 天时是 6，随进度涨，不是剩余复活次数",
            "生命饰品等级 = AC_Health（珍玩妖织）的强化等级；生命值本身不在存档里",
            "",
            "物品 = 背包数量（上限来自 MaxAmount）",
            "影之武装 = 等级（BrutalAxe/巨凶斧 等），游戏里叫「影之武装」",
            "饰品 = 强化等级：0 未强化、1 已强化；备注标「已装备」",
            "药品 = 强化等级 + 当前次数/上限",
        ):
            text.insert("end", line + "\n")
        text.insert("end", "\n任务\n", "h")
        for line in (
            "任务页双击一行可以改：分支 / 状态（Completed、Activating、Locked、None）/ 进度数组。",
            "「未完成」页列出所有还没走完分支的任务，以及目录里存在但存档里没有的饰品。",
            "改任务前先记下原值，出问题用 .bak 还原。",
        ):
            text.insert("end", line + "\n")
        text.insert("end", "\n刷取\n", "h")
        for line in (
            "「未完成」页下半部分选中一个未获得饰品，点「添加到存档」或双击，就会写进 Inventory.AccessoryInfos（强化等级 0）。",
            "加完回到面板「饰品」分类能看到它，再点「保存修改」写回文件。",
            "饰品是整条记录新增，不是改数值；如果游戏有校验，可能出现图标但进不了装备栏，先备份再试。",
        ):
            text.insert("end", line + "\n")
        text.configure(state="disabled")
        return page

    # -- 载入 ------------------------------------------------------------- #

    def _autodetect(self) -> None:
        if self.path_var.get().strip() and os.path.isfile(self.path_var.get().strip()):
            return
        found = []
        if os.path.isdir(GAME_SAVE_ROOT):
            for sid in os.listdir(GAME_SAVE_ROOT):
                p = os.path.join(GAME_SAVE_ROOT, sid, "PBZSaveGame.sav")
                if os.path.isfile(p):
                    found.append((os.path.getmtime(p), p))
        found.sort(reverse=True)
        if found:
            self.path_var.set(found[0][1])
            self._open()

    def _browse(self) -> None:
        path = filedialog.askopenfilename(title="选择存档", filetypes=[("存档", "*.sav"), ("全部", "*.*")])
        if path:
            self.path_var.set(path)
            self._open()

    def _open(self) -> None:
        path = self.path_var.get().strip().strip('"')
        if not path:
            return
        try:
            self.save = ps.Save(path, KEY)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"打开失败：{exc}")
            return
        names = [s.name for s in self.save.slots]
        self.slot_combo.configure(values=names)
        self.slot_name.set("AutoSave0" if "AutoSave0" in names else names[0])
        self._load_slot()
        self._load_snapshots()
        self.status.set(f"已打开 {path}")
        self._refresh_header()

    def _load_slot(self) -> None:
        if not self.save:
            return
        try:
            self.slot = self.save.slot(self.slot_name.get())
            self.data = self.save.obj(self.slot)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"读取槽位失败：{exc}")
            return
        self._fill_tiles()
        self._fill_table()
        self._fill_quests()
        self._fill_pending()
        self.status.set(f"{self.slot.name} · {self.slot.size:,} 字节明文")

    # -- 面板填充 --------------------------------------------------------- #

    def _fill_tiles(self) -> None:
        for label, path, kind, widget, lab in self.tiles:
            if path[-2:] == ["AC_Health", "CurrentLevel"]:
                zh = name_of("AC_Health")
                if zh:
                    lab.configure(text=f"生命饰品 · {zh}")
            try:
                v = get_at(self.data, path)
            except Exception:
                widget.configure(text="—", fg=C.FAINT)
                continue
            widget.configure(text=f"{v:.1f}" if kind is float else f"{v:,}" if isinstance(v, int) else str(v))

    def _set_category(self, name: str) -> None:
        self.category.set(name)
        for n, b in getattr(self, "cat_buttons", {}).items():
            b.configure(style="CatActive.TButton" if n == name else "Cat.TButton")
        self._fill_table()

    def _fill_table(self) -> None:
        self.item_tree.delete(*self.item_tree.get_children())
        self.rows.clear()
        cat = next((c for c in CATEGORIES if c[0] == self.category.get()), CATEGORIES[0])
        name, root_path, field, extra, unit = cat
        self.item_tree.heading("数值", text=unit)
        self.hint.configure(text=CATEGORY_HINT.get(name, ""))
        if not self.data:
            return
        try:
            container = get_at(self.data, root_path)
        except Exception:
            self.cat_label.configure(text="该存档没有这一类")
            return
        try:
            equipped = set(get_at(self.data, ["Inventory", "AccessoryIDs"]))
        except Exception:
            equipped = set()
        needle = self.filter_var.get().strip().lower()
        count = 0
        for key, value in container.items():
            if not isinstance(value, dict) or field not in value:
                continue
            label = name_of(key)
            if needle and needle not in key.lower() and needle not in label.lower():
                continue
            path = root_path + [key, field]
            notes = []
            if extra and extra in value:
                notes.append(f"上限 {value[extra]}")
            if name == "饰品":
                notes.append("已装备" if key in equipped else "未装备")
                notes.append("未强化" if value[field] == 0 else "已强化")
            elif name == "药品":
                notes.append(f"次数 {value.get('CurrentTime', '-')} / {value.get('MaxTime', '-')}")
            self.item_tree.insert(
                "", "end", iid=str(len(self.rows)), values=(label or key, key, value[field], "　".join(notes))
            )
            self.rows.append({"name": key, "label": label or key, "path": path, "kind": type(value[field])})
            count += 1
        stripe(self.item_tree)
        self.cat_label.configure(text=f"{name} {count} 项" + ("" if NAMES else "（未加载名称表）"))

    def _quests_src(self) -> list:
        try:
            return get_at(self.data, ["Narrative", "NarrativeSavedQuests"])
        except Exception:
            return []

    def _fill_quests(self) -> None:
        self.quest_tree.delete(*self.quest_tree.get_children())
        self.quest_rows.clear()
        if not self.data:
            return
        for q in self._quests_src():
            cls = str(q.get("QuestClass", "")).split("/")[-1].split(".")[0]
            branches = q.get("QuestBranches") or []
            done = sum(1 for b in branches if b.get("BranchType") == "EBranchType::BranchCompleted")
            b = branches[-1] if branches else {}
            prog = ",".join(str(x) for x in (b.get("TasksProgress") or []))
            self.quest_tree.insert(
                "", "end",
                values=(cls, len(branches), done, b.get("BranchID", ""), str(b.get("BranchType", "")).split("::")[-1], prog),
            )
            self.quest_rows.append({"quest": q, "name": cls})
        stripe(self.quest_tree)

    def _fill_pending(self) -> None:
        self.pend_quest.delete(*self.pend_quest.get_children())
        self.pend_acc.delete(*self.pend_acc.get_children())
        if not self.data:
            return
        for q in self._quests_src():
            branches = q.get("QuestBranches") or []
            if branches and all(b.get("BranchType") == "EBranchType::BranchCompleted" for b in branches):
                continue
            cls = str(q.get("QuestClass", "")).split("/")[-1].split(".")[0]
            done = sum(1 for b in branches if b.get("BranchType") == "EBranchType::BranchCompleted")
            b = branches[-1] if branches else {}
            prog = ",".join(str(x) for x in (b.get("TasksProgress") or []))
            self.pend_quest.insert(
                "", "end",
                values=(cls, len(branches), done, str(b.get("BranchType", "")).split("::")[-1], prog),
            )
        stripe(self.pend_quest)

        owned = set()
        try:
            owned = set(get_at(self.data, ["Inventory", "AccessoryInfos"]).keys())
        except Exception:
            pass
        missing = [(i, n) for i, n in NAMES.items() if n.get("category") == "accessory" and i not in owned]
        self.pending_acc = []
        for item_id, meta in sorted(missing, key=lambda kv: kv[0]):
            self.pend_acc.insert("", "end", values=(meta["name"], item_id, "未获得"))
            self.pending_acc.append(item_id)
        stripe(self.pend_acc)

    def _grant_accessory(self) -> None:
        if not self.data:
            return
        sel = self.pend_acc.selection()
        if not sel:
            messagebox.showinfo(APP_TITLE, "先在列表里选一个饰品。")
            return
        item_id = self.pending_acc[self.pend_acc.index(sel[0])]
        from datetime import datetime

        try:
            infos = get_at(self.data, ["Inventory", "AccessoryInfos"])
        except Exception:
            messagebox.showerror(APP_TITLE, "当前槽位没有饰品数据。")
            return
        if item_id in infos:
            messagebox.showinfo(APP_TITLE, "这个饰品已经在存档里了。")
            return
        infos[item_id] = {
            "CurrentLevel": 0,
            "HasUIRedPoint": True,
            "DirtyTime": datetime.now().strftime("%Y.%m.%d-%H.%M.%S"),
            "AcquiredCycle": 0,
            "GrantedByEntitlement": False,
        }
        self._commit()
        self.status.set(f"已添加 {name_of(item_id) or item_id}，记得保存修改")

    # -- 编辑 ------------------------------------------------------------- #

    def _edit_dialog(self, path, kind, title) -> None:
        if not self.data:
            messagebox.showinfo(APP_TITLE, "先打开存档。")
            return
        try:
            old = get_at(self.data, path)
        except Exception:
            messagebox.showerror(APP_TITLE, "这个字段在当前槽位里不存在。")
            return
        dlg = tk.Toplevel(self)
        dlg.title(f"修改 · {title}")
        dlg.configure(bg=C.CARD)
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()
        body = tk.Frame(dlg, bg=C.CARD)
        body.pack(padx=px(18), pady=px(16))
        tk.Label(body, text=title, bg=C.CARD, fg=C.MUTED, font=F.small).pack(anchor="w")
        tk.Label(body, text=f"当前值 {old}", bg=C.CARD, fg=C.TEXT, font=F.mono_sm).pack(anchor="w", pady=(px(2), px(8)))
        var = tk.StringVar(value=str(old))
        ent = ttk.Entry(body, textvariable=var, width=24)
        ent.pack(fill="x")
        ent.focus_set()
        ent.select_range(0, "end")

        def ok(_e=None):
            raw = var.get().strip()
            try:
                if kind is float:
                    value = float(raw)
                elif kind is int:
                    value = int(float(raw))
                elif kind is bool:
                    value = raw.lower() in ("1", "true", "是", "yes")
                else:
                    value = raw
            except ValueError:
                messagebox.showerror(APP_TITLE, "请输入数字。", parent=dlg)
                return
            set_at(self.data, path, value)
            self._commit()
            dlg.destroy()

        ent.bind("<Return>", ok)
        btns = tk.Frame(body, bg=C.CARD)
        btns.pack(fill="x", pady=(px(12), 0))
        ttk.Button(btns, text="确定", style="Primary.TButton", command=ok).pack(side="right")
        ttk.Button(btns, text="取消", style="TButton", command=dlg.destroy).pack(side="right", padx=px(6))

    def _edit_row(self, _evt=None) -> None:
        sel = self.item_tree.selection()
        if not sel:
            return
        row = self.rows[self.item_tree.index(sel[0])]
        self._edit_dialog(row["path"], row["kind"], row.get("label", row["name"]))

    def _edit_quest(self, _evt=None) -> None:
        sel = self.quest_tree.selection()
        if not sel:
            return
        entry = self.quest_rows[self.quest_tree.index(sel[0])]
        quest = entry["quest"]
        branches = quest.get("QuestBranches") or []
        if not branches:
            messagebox.showinfo(APP_TITLE, "这条任务没有分支数据。")
            return
        dlg = tk.Toplevel(self)
        dlg.title("修改任务 · " + entry["name"])
        dlg.configure(bg=C.CARD)
        dlg.transient(self)
        dlg.grab_set()
        body = tk.Frame(dlg, bg=C.CARD)
        body.pack(padx=px(18), pady=px(16))
        tk.Label(body, text=entry["name"], bg=C.CARD, fg=C.TEXT, font=F.bold).pack(anchor="w")
        tk.Label(body, text=quest.get("QuestClass", ""), bg=C.CARD, fg=C.FAINT, font=F.tiny, wraplength=px(360)).pack(
            anchor="w", pady=(0, px(10))
        )

        row1 = tk.Frame(body, bg=C.CARD)
        row1.pack(fill="x", pady=px(3))
        tk.Label(row1, text="分支", bg=C.CARD, fg=C.MUTED, font=F.small, width=6, anchor="w").pack(side="left")
        branch_var = tk.StringVar()
        branch_combo = ttk.Combobox(row1, textvariable=branch_var, width=20, state="readonly",
                                    values=[str(b.get("BranchID", "")) for b in branches])
        branch_combo.pack(side="left", fill="x", expand=True)

        row2 = tk.Frame(body, bg=C.CARD)
        row2.pack(fill="x", pady=px(3))
        tk.Label(row2, text="状态", bg=C.CARD, fg=C.MUTED, font=F.small, width=6, anchor="w").pack(side="left")
        type_var = tk.StringVar()
        type_combo = ttk.Combobox(row2, textvariable=type_var, width=28, state="readonly", values=BRANCH_TYPES)
        type_combo.pack(side="left", fill="x", expand=True)

        row3 = tk.Frame(body, bg=C.CARD)
        row3.pack(fill="x", pady=px(3))
        tk.Label(row3, text="进度", bg=C.CARD, fg=C.MUTED, font=F.small, width=6, anchor="w").pack(side="left")
        prog_var = tk.StringVar()
        ttk.Entry(row3, textvariable=prog_var, width=28).pack(side="left", fill="x", expand=True)

        state = {"branch": branches[-1]}

        def load_branch(_e=None):
            idx = branch_combo.current()
            if idx < 0:
                return
            b = branches[idx]
            state["branch"] = b
            type_var.set(b.get("BranchType", BRANCH_TYPES[0]))
            prog_var.set(",".join(str(x) for x in (b.get("TasksProgress") or [])))

        branch_combo.bind("<<ComboboxSelected>>", load_branch)
        branch_combo.current(len(branches) - 1)
        load_branch()

        btns = tk.Frame(body, bg=C.CARD)
        btns.pack(fill="x", pady=(px(12), 0))

        def apply(mark_done=False):
            b = state["branch"]
            if mark_done:
                b["BranchType"] = "EBranchType::BranchCompleted"
            else:
                b["BranchType"] = type_var.get() or b.get("BranchType")
            raw = prog_var.get().strip()
            if raw:
                try:
                    b["TasksProgress"] = [int(x) for x in raw.replace("，", ",").split(",") if x.strip() != ""]
                except ValueError:
                    messagebox.showerror(APP_TITLE, "进度要写成 0,0,0", parent=dlg)
                    return
            self._commit()
            dlg.destroy()

        ttk.Button(btns, text="标记该分支完成", style="TButton", command=lambda: apply(True)).pack(side="left")
        ttk.Button(btns, text="取消", style="TButton", command=dlg.destroy).pack(side="right")
        ttk.Button(btns, text="确定", style="Primary.TButton", command=apply).pack(side="right", padx=px(6))

    def _commit(self) -> None:
        if not self.slot:
            return
        raw = json.dumps(self.data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.save.set_raw(self.slot, raw)
        self._fill_tiles()
        self._fill_table()
        self._fill_quests()
        self._fill_pending()
        self.status.set("已写入内存，记得保存修改")
        self._refresh_header()

    # -- 保存 ------------------------------------------------------------- #

    def _save(self) -> None:
        if not self.save:
            return
        if not any(s.dirty for s in self.save.slots):
            messagebox.showinfo(APP_TITLE, "没有需要保存的修改。")
            return
        if not messagebox.askyesno(
            APP_TITLE,
            "写回存档？\n会先生成 .bak-时间戳 备份。\n建议先退出游戏、关掉 Steam 云同步。",
        ):
            return
        try:
            bak = self.save.save()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"保存失败：{exc}")
            return
        self.status.set("已保存")
        self._refresh_header()
        messagebox.showinfo(APP_TITLE, f"已写回。\n备份：{bak}")

    def _export(self) -> None:
        if not self.save or not self.slot:
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", initialfile=f"{self.slot.name}.json")
        if path:
            with open(path, "wb") as fh:
                fh.write(self.save.raw(self.slot))
            messagebox.showinfo(APP_TITLE, f"已导出到\n{path}")

    # -- 快照 ------------------------------------------------------------- #

    def _load_snapshots(self) -> None:
        self.snap_tree.delete(*self.snap_tree.get_children())
        if not self.save:
            return
        from datetime import datetime

        base = os.path.dirname(self.save.path)
        rows = []
        for kind in ("1RealTime", "2Hourly", "3Daily"):
            d = os.path.join(base, kind)
            if not os.path.isdir(d):
                continue
            for fn in os.listdir(d):
                if fn.lower().endswith(".sav"):
                    p = os.path.join(d, fn)
                    rows.append((os.path.getmtime(p), kind, p))
        rows.sort(reverse=True)
        self.snapshots = rows
        for mtime, kind, p in rows[:200]:
            self.snap_tree.insert(
                "",
                "end",
                values=(kind, datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"), core.format_size(os.path.getsize(p))),
            )
        stripe(self.snap_tree)

    def _restore(self) -> None:
        if not self.save:
            return
        sel = self.snap_tree.selection()
        if not sel:
            messagebox.showinfo(APP_TITLE, "先选一个快照。")
            return
        _, kind, path = self.snapshots[self.snap_tree.index(sel[0])]
        if not messagebox.askyesno(APP_TITLE, f"用这个快照覆盖？\n\n{kind}  {os.path.basename(path)}\n\n会先备份当前存档。"):
            return
        try:
            import shutil
            from datetime import datetime

            bak = f"{self.save.path}.bak-{datetime.now():%Y%m%d-%H%M%S}"
            shutil.copy2(self.save.path, bak)
            shutil.copy2(path, self.save.path)
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"恢复失败：{exc}")
            return
        self._open()
        messagebox.showinfo(APP_TITLE, f"已恢复。\n原文件备份：{bak}")

    def _on_close(self) -> None:
        if self.save and any(s.dirty for s in self.save.slots):
            if not messagebox.askyesno(APP_TITLE, "有未保存的修改，直接退出？"):
                return
        self.destroy()


def run_gui() -> None:
    try:
        App().mainloop()
    except Exception:
        import traceback

        msg = traceback.format_exc()
        try:
            base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
            with open(os.path.join(base, "pbz_error.log"), "a", encoding="utf-8") as fh:
                fh.write(msg + "\n")
        except Exception:
            pass
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(APP_TITLE, msg[-1500:])
            root.destroy()
        except Exception:
            pass
        raise


# --------------------------------------------------------------------------- #
# 命令行
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if not argv:
        run_gui()
        return 0
    cmd = argv[0]
    try:
        load_names()
        if cmd == "list" and len(argv) > 1:
            s = ps.Save(argv[1], KEY)
            for sl in s.slots:
                print(f"{sl.name:<18} algo={sl.algo} 明文={sl.size:>8} 块={sl.block_size:>8}")
            return 0
        if cmd == "find" and len(argv) > 2:
            s = ps.Save(argv[1], KEY)
            for sl, path, value in s.find(argv[2])[:60]:
                print(f"{sl.name:<18} {path} = {value[:60]}")
            return 0
        if cmd == "get" and len(argv) > 3:
            s = ps.Save(argv[1], KEY)
            print(json.dumps(ps.get_path(s.obj(s.slot(argv[2])), argv[3]), ensure_ascii=False))
            return 0
        if cmd == "set" and len(argv) > 4:
            s = ps.Save(argv[1], KEY)
            slot = s.slot(argv[2])
            obj = s.obj(slot)
            old = ps.get_path(obj, argv[3])
            value = int(argv[4]) if isinstance(old, int) else (float(argv[4]) if isinstance(old, float) else argv[4])
            ps.set_path(obj, argv[3], value)
            s.set_raw(slot, json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode())
            print("备份:", s.save())
            return 0
        print(
            "用法：\n  pbz_editor.py            图形界面\n  pbz_editor.py list  存档\n"
            "  pbz_editor.py find  存档 数值\n  pbz_editor.py get   存档 槽位 路径\n"
            "  pbz_editor.py set   存档 槽位 路径 新值"
        )
        return 2
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
