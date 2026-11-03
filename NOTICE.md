# 第三方组件与来源说明

本项目的容器格式、存档解密、Oodle 解压、pak/IoStore/locres 读取方法，来自下列开源项目；
本体（`pbz_editor.py`、`pbz_save.py`、`pbz_core.py`、界面与打包脚本）为 MIT 授权，见 `LICENSE`。

## PBZ-Editor（MIT）

- 仓库：https://github.com/qry6868/PBZ-Editor
- 版权：Copyright (c) 2026 PBZ Editor contributors
- 许可证全文：`refpak/LICENSE-PBZ-Editor.txt`
- 使用范围：`refpak/` 下的 `pak_reader.py`、`resources_reader.py`、`catalog_builder.py`、
  `region_builder.py`、`catalog.py`、`regions.py` 直接取自该项目；PBZS 容器结构、
  AES-256-GCM 分块、Oodle 存储块写回方案也参考了它。

## oozextract（MIT）

- 仓库：https://github.com/WorkingRobot/oozextract
- 用途：`native/pbz_codec.dll` 由该项目的 Oodle 解码器编译而成，用于解压存档块。
- 版权与许可：见 `native/oozextract-NOTICE.md`。

## PyCryptodome（public domain / BSD 2-Clause）

- 用途：AES-256-GCM 加解密。打包时随 exe 一起分发。

## PyInstaller（GPL-2.0 with bootloader exception）

- 用途：打包 Windows 可执行文件。其 bootloader 例外允许分发打包后的程序。

## cryptography（Apache-2.0 / BSD-3-Clause）

- 用途：仅打包脚本与 `refpak/resources_reader.py` 读取 pak 索引时使用。

## 游戏数据

`names.json` 中的物品名称由本机安装的游戏资源导出（`game.locres` 与数据表），
仅用于在界面上显示中文名。游戏名称、物品名与相关文本版权归 S-Game 所有。
本项目与 S-Game 无关联。
