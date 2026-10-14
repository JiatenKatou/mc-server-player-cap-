"""恢复默认：把用户数据/校准产物清掉，回到出厂状态。

为什么要单独一个模块：这个项目有 5 处本地状态文件，分散在不同模块里，
如果各处自己写"删文件"，很容易漏掉某一个（尤其是新加的文件），
也容易把"用户输入的数据"和"自动生成的校准产物"混在一起删。

三类东西，**恢复默认时要不要删必须区分清楚**：

    user     用户自己录入的数据（自定义 CPU、收集到的服主反馈）——删掉要慎重
    derived  由数据自动生成的校准产物（玩法系数、整合包档案）——删掉即回内置值
    debug    调试/草稿产物（导出文件、参数覆盖）——删掉基本无影响

安全设计：
    1. 默认**先备份再删**（重命名为 `<原名>.bak`），所以"恢复默认"是可撤销的
    2. 每一项都能单独重置，也能一键全恢复
    3. `inspect_state()` 让人在动手前先看清"会失去什么"
"""
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 <请填写你的名字或昵称>
#
# 本文件是「Minecraft 服务器人数上限计算器」的一部分，按 GPL-3.0 授权。
# 完整声明见 mc_player_calc/__init__.py 与项目根目录的 COPYRIGHT。
# 本程序不提供任何担保；输出为模型估算值，不是实测保证。


from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

# ----------------------------------------------------------------------
# 状态项清单
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class StateItem:
    """一份本地状态的说明。"""

    key: str
    label: str
    kind: str          # user / derived / debug
    desc: str
    getter: str        # 取路径的模块函数名，统一用 "模块.函数" 形式
    hint: str = ""     # 删掉之后会怎样

    @property
    def is_user_data(self) -> bool:
        return self.kind == "user"


ITEMS: List[StateItem] = [
    StateItem("custom_cpus", "自定义 CPU 型号", "user",
              "你自己录入的 CPU 型号与 CPU-Z 跑分",
              "cpu_data.custom_cpu_file",
              "删掉后这些型号查不到，会退回库内估算值"),
    StateItem("feedback", "服主反馈数据", "user",
              "收集到的服主承载数据（用于校准）",
              "feedback.feedback_file",
              "删掉后汇总与校准就空了，★ 建议先导出再删"),
    StateItem("behavior", "玩法系数覆盖", "derived",
              "由反馈汇总出的玩法负载倍数",
              "feedback.behavior_file",
              "删掉后玩法倍数回到 config.py 里的内置默认值"),
    StateItem("modpacks", "整合包档案", "derived",
              "各整合包的专属负载系数（一个包一套）",
              "modpack.profile_file",
              "删掉后所有整合包回到兜底折算值"),
]

EXPORT_ITEMS: List[StateItem] = [
    StateItem("anchors", "校准锚点草稿", "debug",
              "导出给 calibrate.py 的锚点文件",
              "export:anchors.json",
              "删掉不影响工具运行"),
    StateItem("agent_md", "Agent 交付文件", "debug",
              "导出给服主/别的 agent 的 Markdown",
              "export:feedback_agent.md",
              "删掉不影响工具运行，需要时重新导出即可"),
    StateItem("csv", "反馈表格导出", "debug",
              "导出成 CSV 的反馈数据",
              "export:feedback.csv",
              "删掉不影响工具运行"),
    StateItem("export_json", "原始 JSON 导出", "debug",
              "导出的完整反馈数据",
              "export:feedback_export.json",
              "删掉不影响工具运行"),
]


def all_items(include_exports: bool = True) -> List[StateItem]:
    return ITEMS + (EXPORT_ITEMS if include_exports else [])


def _project_root() -> str:
    """项目根目录（mc_player_calc 的上一级），导出文件默认落在这里。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve(item: StateItem) -> str:
    """把 StateItem 解析成绝对路径。"""
    if item.getter.startswith("export:"):
        name = item.getter.split(":", 1)[1]
        # 导出文件可能落在"当前目录"（CLI 导出时的 cwd）或"项目根目录"，
        # 两个位置都检查，优先返回实际存在的那份，否则返回项目根目录下的路径。
        root = os.path.join(_project_root(), name)
        here = os.path.join(os.getcwd(), name)
        if os.path.isfile(here) and not os.path.isfile(root):
            return os.path.abspath(here)
        return os.path.abspath(root)
    mod_name, func_name = item.getter.split(".", 1)
    module = __import__(f"mc_player_calc.{mod_name}", fromlist=[func_name])
    func = getattr(module, func_name, None)
    return os.path.abspath(func()) if callable(func) else ""


def item_path(item_or_key) -> str:
    item = _find(item_or_key)
    return _resolve(item) if item else ""


def _find(key_or_item) -> Optional[StateItem]:
    if isinstance(key_or_item, StateItem):
        return key_or_item
    for item in all_items():
        if item.key == key_or_item:
            return item
    return None


def _backup_path(path: str) -> str:
    """备份名带上时间戳，避免第二次恢复默认覆盖掉第一次的备份。"""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{path}.{stamp}.bak"


def backup(path: str) -> Optional[str]:
    """把文件改名成带时间戳的 .bak（相当于"移动"而非复制，省空间）。"""
    if not os.path.isfile(path):
        return None
    target = _backup_path(path)
    os.replace(path, target)
    return target


# ----------------------------------------------------------------------
# 抽查现状（动手前先看清会失去什么）
# ----------------------------------------------------------------------
def inspect_state(include_exports: bool = True) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in all_items(include_exports):
        path = _resolve(item)
        exists = bool(path) and os.path.isfile(path)
        size = os.path.getsize(path) if exists else 0
        detail = ""
        if exists:
            detail = _detail(item, path)
        out.append({
            "key": item.key,
            "label": item.label,
            "kind": item.kind,
            "desc": item.desc,
            "hint": item.hint,
            "path": path,
            "exists": exists,
            "size": size,
            "detail": detail,
        })
    return out


def _detail(item: StateItem, path: str) -> str:
    """给出一句"这里面有多少东西"，让人判断该不该删。"""
    import json

    try:
        if item.key == "custom_cpus":
            from .cpu_data import load_custom_cpus
            load_custom_cpus()
            from .cpu_data import CUSTOM_DB
            return f"{len(CUSTOM_DB)} 个型号"
        if item.key == "feedback":
            from .feedback import load_feedback
            return f"{len(load_feedback())} 条反馈"
        if item.key == "behavior":
            from .feedback import load_behavior_overrides
            ov = load_behavior_overrides()
            return f"{len(ov)} 个玩法被覆盖" if ov else "空文件"
        if item.key == "modpacks":
            from .modpack import load_profiles, list_profiles
            load_profiles()
            packs = list_profiles()
            cal = [p for p in packs if p.calibrated_factor]
            return f"{len(packs)} 个档案（其中 {len(cal)} 个已校准）" if packs else "空文件"
    except Exception as exc:                     # 文件坏了也要能显示
        return f"读取失败：{exc}"
    return ""


# ----------------------------------------------------------------------
# 恢复默认
# ----------------------------------------------------------------------
@dataclass
class ResetReport:
    """一次恢复默认的结果。"""

    cleared: List[Dict[str, str]] = field(default_factory=list)     # 删掉的
    skipped: List[Dict[str, str]] = field(default_factory=list)     # 本来就不存在
    backups: List[str] = field(default_factory=list)                # 备份文件
    dry_run: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cleared": self.cleared,
            "skipped": self.skipped,
            "backups": self.backups,
            "dry_run": self.dry_run,
            "backup_dir_note": "备份文件与原文件同目录，名为 <原名>.<时间戳>.bak",
        }

    def render(self) -> str:
        lines: List[str] = []
        if self.dry_run:
            lines.append("（预演：不会真的删）")
        if self.cleared:
            lines.append(f"已恢复默认 {len(self.cleared)} 项：")
            for c in self.cleared:
                lines.append(f"  - {c['label']}（{c['detail'] or c['path']}）")
        if self.skipped:
            lines.append(f"跳过 {len(self.skipped)} 项（文件不存在）：")
            for s in self.skipped:
                lines.append(f"  - {s['label']}")
        if self.backups:
            lines.append("")
            lines.append(f"备份 {len(self.backups)} 个（想撤销就把 .bak 改回原名）：")
            for b in self.backups:
                lines.append(f"  - {b}")
        if not self.cleared and not self.skipped:
            lines.append("没有需要恢复的项目。")
        return "\n".join(lines)


def reset(items=None, backup_first: bool = True, dry_run: bool = False,
          include_exports: bool = False) -> ResetReport:
    """恢复默认。

    items: 要重置的 StateItem / key 列表；None 表示"全部用户数据与校准产物"
           （默认不含导出文件，那些在 include_exports=True 时才处理）
    backup_first: 先备份成 .bak（可撤销）
    """
    if items is None:
        pool = list(ITEMS) + (list(EXPORT_ITEMS) if include_exports else [])
    else:
        if isinstance(items, (str, StateItem)):
            items = [items]
        pool = [x for x in (_find(i) for i in items) if x is not None]
        distinct, seen = [], set()
        for item in pool:
            if item.key not in seen:
                seen.add(item.key)
                distinct.append(item)
        pool = distinct

    report = ResetReport(dry_run=dry_run)
    for item in pool:
        path = _resolve(item)
        if not path or not os.path.isfile(path):
            report.skipped.append({"key": item.key, "label": item.label, "path": path})
            continue
        detail = _detail(item, path)
        if not dry_run:
            if backup_first:
                try:
                    bak = backup(path)
                    if bak:
                        report.backups.append(bak)
                except OSError as exc:
                    report.skipped.append({"key": item.key, "label": item.label,
                                           "path": path, "error": f"备份失败：{exc}"})
                    continue
            else:
                try:
                    os.remove(path)
                except OSError as exc:
                    report.skipped.append({"key": item.key, "label": item.label,
                                           "path": path, "error": f"删除失败：{exc}"})
                    continue
        report.cleared.append({"key": item.key, "label": item.label,
                              "path": path, "detail": detail})

    if not dry_run:
        _reload_caches(pool)
    return report


def _reload_caches(pool) -> None:
    """删完文件之后把内存里的缓存也同步清掉，否则本次进程里还是旧数据。"""
    keys = {item.key for item in pool}
    try:
        if "custom_cpus" in keys:
            from .cpu_data import CUSTOM_DB, load_custom_cpus
            CUSTOM_DB.clear()
            load_custom_cpus()
        if "modpacks" in keys:
            from .modpack import PROFILES, load_profiles
            PROFILES.clear()
            load_profiles()
    except Exception:
        pass


def reset_user_data(backup_first: bool = True, dry_run: bool = False) -> ResetReport:
    """只恢复"用户自己录入的数据"（自定义 CPU + 服主反馈），保留校准产物。"""
    return reset([i for i in ITEMS if i.is_user_data],
                 backup_first=backup_first, dry_run=dry_run)


def reset_derived(backup_first: bool = True, dry_run: bool = False) -> ResetReport:
    """只恢复"自动生成的校准产物"，保留用户数据。"""
    return reset([i for i in ITEMS if not i.is_user_data],
                 backup_first=backup_first, dry_run=dry_run)


def list_backups() -> List[str]:
    """找出所有恢复默认留下的备份文件。"""
    found: List[str] = []
    for item in all_items():
        path = _resolve(item)
        folder = os.path.dirname(path)
        if not folder or not os.path.isdir(folder):
            continue
        base = os.path.basename(path)
        for name in os.listdir(folder):
            if name.startswith(base + ".") and name.endswith(".bak"):
                found.append(os.path.join(folder, name))
    return sorted(set(found))


def backup_stamp(backup_path: str) -> str:
    """取出备份的时间戳（一次恢复默认的多个备份共用同一个时间戳）。"""
    import re

    m = re.search(r"\.(\d{8}-\d{6})\.bak$", os.path.basename(backup_path))
    return m.group(1) if m else ""


def backup_groups() -> Dict[str, List[str]]:
    """把所有备份按时间戳分组：一个组 = 一次"恢复默认"，可整组撤销。"""
    groups: Dict[str, List[str]] = {}
    for path in list_backups():
        groups.setdefault(backup_stamp(path), []).append(path)
    return {k: sorted(v) for k, v in sorted(groups.items(), reverse=True)}


def restore_backup(backup_path: str) -> str:
    """把某个 .bak 恢复回原名（撤销单份文件）。

    备份名格式固定为 `<原名>.<YYYYmmdd-HHMMSS>.bak`，
    所以直接按这个模式剥掉后缀，比"数点号"稳健（原名本身可能含点号）。
    """
    import re

    if not os.path.isfile(backup_path):
        raise FileNotFoundError(backup_path)
    name = os.path.basename(backup_path)
    m = re.match(r"^(?P<orig>.+)\.\d{8}-\d{6}\.bak$", name)
    if not m:
        raise ValueError(f"不是本工具生成的备份文件名：{name}")
    target = os.path.join(os.path.dirname(backup_path), m.group("orig"))
    if os.path.exists(target):
        raise FileExistsError(f"{target} 已存在，先自行处理再恢复")
    os.replace(backup_path, target)
    _reload_caches(all_items())
    return target


def restore_group(stamp: str) -> List[str]:
    """整组撤销（推荐）。

    一次"恢复默认"可能碰了多份文件（例如同时清了自定义 CPU 与反馈数据），
    只撤销其中一个会留下"一半新一半旧"的不一致状态，所以默认按组撤销。
    """
    groups = backup_groups()
    if stamp not in groups:
        raise ValueError(f"没有时间戳为 {stamp} 的备份"
                         + (f"；可用的有：{' / '.join(groups)}" if groups else "（当前没有任何备份）"))
    restored: List[str] = []
    failures: List[str] = []
    for path in groups[stamp]:
        try:
            restored.append(restore_backup(path))
        except (OSError, ValueError) as exc:
            failures.append(f"{os.path.basename(path)}：{exc}")
    if restored:
        _reload_caches(all_items())
    if failures:
        raise OSError("；".join(failures))
    return restored


def delete_backups() -> int:
    """清掉所有备份文件（确认不再需要撤销时用）。"""
    count = 0
    for path in list_backups():
        try:
            os.remove(path)
            count += 1
        except OSError:
            pass
    return count


def render_state() -> str:
    """给 CLI 看的现状报告。"""
    lines = ["=" * 72, "  本地状态检查", "=" * 72]
    user = [x for x in inspect_state() if x["kind"] == "user"]
    derived = [x for x in inspect_state() if x["kind"] == "derived"]
    debug = [x for x in inspect_state() if x["kind"] == "debug"]
    for title, group in (("用户数据（★ 删掉会失去你录入的内容）", user),
                         ("校准产物（删掉即回内置默认）", derived),
                         ("导出/草稿（删掉无影响）", debug)):
        lines.append(f"\n  【{title}】")
        for x in group:
            mark = "有" if x["exists"] else "—"
            size = f"{x['size'] / 1024:.1f} KB" if x["exists"] else ""
            detail = f"　{x['detail']}" if x["detail"] else ""
            lines.append(f"    [{mark}] {x['label']:<18}{size:>10}{detail}")
            lines.append(f"          {x['path']}")
    backups = list_backups()
    if backups:
        lines.append(f"\n  【备份文件 {len(backups)} 个（.bak，可撤销）】")
        for b in backups:
            lines.append(f"    {b}")
    lines.append("")
    lines.append("  恢复默认：--reset-data（只清用户数据）/ --reset-all（清用户数据+校准产物）")
    lines.append("            --reset-all --with-exports（连导出文件一起清）")
    return "\n".join(lines)
