"""信息反馈收集系统：收集服主的真实承载数据，反哺工具的玩法系数。

设计原则：
- **纯本地**：提交内容只写到你工作目录的 `feedback.json`，页面不会自动上传任何东西。
  要分享给别人（或汇总给作者）时，由你在页面上点「导出」自己发出去。
- **一份数据两用**：
  1. `feedback.json` 直接就是 `calibrate.py` 认的锚点格式 → 可以直接反推 CPU 系数；
  2. 汇总统计出来的 `playstyle_factor` 可以回填到 `config.behavior_multiplier`，
     让工具的玩法列表带上真实数据（而不是我拍的数字）。
- **整合包单独扩字段**：玩法选到"模组 / 整合包"时，额外收集整合包名称、MC 版本、
  模组数量、玩法类型（科技/魔法/综合/生电/轻量）。

数据流向：

    服主填表 ──► /api/feedback (POST) ──► feedback.json
                                        │
                    ┌───────────────────┴────────────────────┐
                    ▼                                        ▼
        calibrate.py 反推 CPU 系数              汇总玩法系数 → config.behavior_multiplier
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .cooling import suffix_of
from .cpu_data import cpu_cpuz_to_index, resolve_platform
from .parser import NETWORK_PRESETS, PLAYER_SIM, VIEW_DISTANCES, parse_bandwidth_mbps, parse_number
from .parser import resolve_cpu

# ----------------------------------------------------------------------
# 玩法分类（服主填这个；工具里的"玩法倍数"由它汇总而来）
# ----------------------------------------------------------------------
PLAYSTYLES: Dict[str, Dict[str, Any]] = {
    "原版": {
        "desc": "接近原版生存，无大型自动化",
        "multiplier": 1.00,
        "aliases": ["原版生存", "vanilla", "原版红石"],
    },
    "小游戏": {
        "desc": "起床战争 / 空岛 / 跑酷等，玩家分散在不同世界",
        "multiplier": 1.05,
        "aliases": ["小游戏服", "minigames", "竞技"],
    },
    "插件": {
        "desc": "Spigot / Paper + 功能插件（经济、领地、任务）",
        "multiplier": 1.15,
        "aliases": ["插件服", "bukkit", "spigot", "paper"],
    },
    "红石生电": {
        "desc": "大型红石机械、刷怪塔、生电工程",
        "multiplier": 1.45,
        "aliases": ["生电", "红石", "技术服", "redstone"],
    },
    "模组": {
        "desc": "少量模组（<50），以增强原版为主",
        "multiplier": 1.35,
        "aliases": ["模组服", "forge", "fabric", "mod"],
    },
    "整合包": {
        "desc": "大型整合包（≥50 模组），需要额外填包名与版本",
        "multiplier": 1.60,
        "aliases": ["整合", "modpack", "整合包服"],
        "extended": True,          # 需要额外字段
    },
}

# 整合包内部再分玩法类型（用于细分科技/魔法/综合的负载差异）
# 整合包的细分维度统一放在 modpack.py（"一个包一套系数"），这里只做转发引用
from .modpack import (MODPACK_BASE_FACTOR, MODPACK_KINDS, PROGRESS_STAGES,  # noqa: F401
                      normalize_pack, resolve_pack_factor, save_profiles, upsert_profile)

MC_VERSIONS = ["1.21.x", "1.20.x", "1.19.x", "1.18.x", "1.16.x", "1.12.x", "其他 / 不确定"]
SERVER_SOFTWARE = ["Paper / Purpur", "Spigot / Bukkit", "Fabric", "Forge", "NeoForge",
                   "Vanilla 原版端", "Folia / 其他", "不确定"]
BOTTLENECKS = ["cpu", "ram", "network", "mods", "unknown"]
OPTIMIZATION_LEVELS = ["作者优化良好", "作者优化一般", "作者几乎没优化", "不确定"]

_CPUZ_HINT = "在 CPU-Z 里跑 Bench → CPU Single Thread，把那个数字填进来"


# ----------------------------------------------------------------------
# 数据结构
# ----------------------------------------------------------------------
@dataclass
class Feedback:
    """一条服主反馈。字段命名尽量跟 calibrate 的锚点对齐，便于直接复用。"""

    # —— 必填核心 ——
    cpu: str = ""
    cpuz_single: Optional[float] = None      # 服主填的 CPU-Z 单核分
    players: int = 0                          # 活跃用户（同时在线）
    view: str = "10"
    tps: Optional[float] = None
    playstyle: str = "原版"

    # —— 整合包扩字段 ——
    modpack_name: str = ""
    mc_version: str = ""
    mods: int = 0
    modpack_kind: str = ""
    optimization: str = ""                   # 作者优化状况（反馈时可选填）

    # —— 可选补充 ——
    ram: str = "16G"
    software: str = ""
    bottleneck: str = "unknown"
    progress: str = "中期"
    bandwidth_mbps: Optional[float] = None
    player_sim: str = PLAYER_SIM[0]
    note: str = ""
    source: str = ""

    # —— 由系统补全 ——
    submitted_at: str = ""
    cores: Optional[int] = None
    platform: str = ""
    cpuz_effective: Optional[float] = None    # 若库里已有该型号，记录库内估计值供对照
    schema: int = 1

    # ------------------------------------------------------------------
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Feedback":
        f = cls()
        for key in f.__dataclass_fields__:
            if key in d and d[key] is not None:
                setattr(f, key, d[key])
        # 类型清洗
        f.players = int(parse_number(str(f.players), 0))
        f.mods = int(parse_number(str(f.mods), 0))
        f.view = str(f.view or "10")
        f.cpu = str(f.cpu or "").strip()
        f.playstyle = str(f.playstyle or "原版").strip()
        if f.playstyle not in PLAYSTYLES:
            matched = normalize_playstyle(f.playstyle)
            f.playstyle = matched or "原版"
        for key in ("cpuz_single", "tps", "bandwidth_mbps"):
            val = getattr(f, key)
            if val in (None, ""):
                setattr(f, key, None)
            else:
                try:
                    setattr(f, key, float(val))
                except (TypeError, ValueError):
                    setattr(f, key, None)
        if f.bottleneck not in BOTTLENECKS:
            f.bottleneck = "unknown"
        if f.progress not in PROGRESS_STAGES:
            f.progress = "中期"
        if f.modpack_kind and f.modpack_kind not in MODPACK_KINDS:
            f.modpack_kind = ""
        return f

    @property
    def needs_modpack_fields(self) -> bool:
        return bool(PLAYSTYLES.get(self.playstyle, {}).get("extended"))

    def playstyle_multiplier(self, use_profile: bool = True) -> float:
        """这条数据对应的玩法负载倍数。

        - 整合包：**按包名取该包自己的系数**（一个包一套，见 modpack.py）
        - 其余玩法：取玩法分类的系数
        - 整合包再乘上"玩法类型"与"进度阶段"（仅当该包还没有专属系数时才有影响）

        `use_profile=False` 时忽略该包已校准的值，用于"反推这个包自己的系数"
        （否则会用自己的值推自己，永远得到 1.0）。
        """
        if self.playstyle == "整合包":
            if use_profile and self.modpack_name:
                factor, _why = resolve_pack_factor(self.modpack_name, self.modpack_kind,
                                                   self.progress)
                if factor > 0:
                    return round(factor, 3)
            f = MODPACK_BASE_FACTOR
            if self.modpack_kind:
                f *= MODPACK_KINDS.get(self.modpack_kind, 1.0)
            if self.progress:
                f *= PROGRESS_STAGES.get(self.progress, 1.0)
            return round(f, 3)

        base = float(PLAYSTYLES.get(self.playstyle, {}).get("multiplier", 1.0))
        if self.progress and self.playstyle in ("模组", "红石生电", "插件"):
            base *= PROGRESS_STAGES.get(self.progress, 1.0)
        return round(base, 3)

    def to_anchor(self) -> Dict[str, Any]:
        """转成 calibrate.py 的锚点格式。

        `behavior_factor` 显式带上，避免 calibrate 再去查一遍玩法系数——
        而且整合包要传"不含该包专属值"的折算倍数，否则会用自己的值推自己。
        """
        return {
            "cpu": self.cpu,
            "ram": self.ram,
            "mods": self.mods,
            "view": self.view,
            "behavior": "原版",             # 反推时统一按基准玩法，负载由 behavior_factor 承担
            "behavior_factor": self.playstyle_multiplier(use_profile=False),
            "player_sim": self.player_sim,
            "players": self.players,
            "tps": self.tps,
            "bottleneck": self.bottleneck,
            "source": self.source or f"反馈 {self.submitted_at}",
            "note": self.note,
            "cpuz_single": self.cpuz_single,   # 库里没这个型号时，用它现场换算指数
            "cores": self.cores,
            "playstyle_factor": self.playstyle_multiplier(),
            "playstyle": self.playstyle,
            "modpack_name": self.modpack_name,
            "modpack_kind": self.modpack_kind,   # 细分项也带上，回读后倍数才能复原
            "progress": self.progress,
            "optimization": self.optimization,
            "mc_version": self.mc_version,
            "modpack_name": self.modpack_name,
        }

    def enrich(self) -> None:
        """补全 CPU 相关信息（核心数、平台、库内对照分）。

        核心数优先用提交者填的值；没填才取库里的。这样避免把"没填"覆盖成默认 4 核，
        导致导出的数据自相矛盾（例如 i9-13900K 被写成 4 核）。
        """
        if not self.cpu:
            return
        spec = resolve_cpu(self.cpu)
        unknown = "未收录" in spec.name or "估算" in spec.name
        if not self.cores:
            self.cores = spec.cores
        if not self.platform:
            self.platform = resolve_platform(spec)
        if not unknown:
            self.cpuz_effective = spec.cpuz_score
        elif self.cpuz_single:
            self.cpuz_effective = round(self.cpuz_single)
        if not self.submitted_at:
            self.submitted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_playstyle(text: str) -> Optional[str]:
    """把各种写法归一化到标准玩法名（含旧的玩法名）。"""
    if not text:
        return None
    t = str(text).strip()
    if t in PLAYSTYLES:
        return t
    low = t.lower()
    for name, meta in PLAYSTYLES.items():
        if name.lower() in low:
            return name
        for alias in meta.get("aliases", []):
            if alias.lower() in low:
                return name
    # 旧的工具内置玩法名兼容
    legacy = {
        "原版生存": "原版",
        "红石 / 自动化": "红石生电",
        "机械动力 / 科技": "整合包",
        "多维度挂机 / 农场": "插件",
    }
    return legacy.get(t)


# ----------------------------------------------------------------------
# 校验
# ----------------------------------------------------------------------
def validate(data: Dict[str, Any]) -> Tuple[Optional[Feedback], List[str], List[str]]:
    """返回 (反馈对象, 错误列表, 警告列表)。错误非空则不接受提交。"""
    errors: List[str] = []
    warnings: List[str] = []

    cpu = str(data.get("cpu") or "").strip()
    if not cpu:
        errors.append("请填写 CPU 型号")

    cpuz_raw = data.get("cpuz_single")
    cpuz: Optional[float] = None
    if cpuz_raw in (None, ""):
        warnings.append("没填 CPU-Z 单核分，将只采用库内估算值（建议补上，否则这条数据价值有限）")
    else:
        try:
            cpuz = float(str(cpuz_raw).strip())
            if not (50 <= cpuz <= 2000):
                errors.append(f"CPU-Z 单核分 {cpuz:g} 超出合理范围（50~2000）")
        except (TypeError, ValueError):
            errors.append(f"CPU-Z 单核分「{cpuz_raw}」不是数字")

    try:
        players = int(parse_number(str(data.get("players")), 0))
    except (TypeError, ValueError):
        players = 0
    if players <= 0:
        errors.append("活跃用户数必须大于 0")
    elif players > 2000:
        warnings.append("活跃用户超过 2000，确认一下单位是否是「同时在线人数」")

    view = str(data.get("view") or "10").strip()
    if view not in VIEW_DISTANCES:
        warnings.append(f"视距「{view}」不在常规档位内，已按原值记录")

    tps: Optional[float] = None
    if data.get("tps") not in (None, ""):
        try:
            tps = float(str(data["tps"]).strip())
            if not (0 < tps <= 20.5):
                errors.append(f"TPS {tps:g} 超出 0~20.5 的范围")
            elif tps < 15:
                warnings.append(f"TPS {tps:g} 偏低，这条数据更适合作为「崩溃临界点」而非承载上限")
        except (TypeError, ValueError):
            errors.append(f"TPS「{data['tps']}」不是数字")
    else:
        warnings.append("没填 TPS：建议按「TPS 首次跌破 19.5 时的人数」口径填写，方便数据合并")

    playstyle = normalize_playstyle(str(data.get("playstyle") or ""))
    if playstyle is None:
        errors.append(f"玩法「{data.get('playstyle')}」无法识别，请从列表中选择")

    # 整合包额外字段
    if playstyle and PLAYSTYLES[playstyle].get("extended"):
        if not str(data.get("modpack_name") or "").strip():
            errors.append("玩法选了「整合包」，请填写整合包名称")
        if not str(data.get("mc_version") or "").strip():
            warnings.append("整合包建议填写 MC 版本")
        if not str(data.get("mods") or "").strip():
            warnings.append("整合包建议填写模组数量（会影响内存与负载估算）")
        if not str(data.get("modpack_kind") or "").strip():
            warnings.append("整合包建议选择玩法类型（科技/魔法/综合/生电/轻量）")

    if errors:
        return None, errors, warnings

    fb = Feedback.from_dict(data)
    fb.playstyle = playstyle or "原版"
    fb.enrich()
    return fb, errors, warnings


# ----------------------------------------------------------------------
# 存储
# ----------------------------------------------------------------------
def feedback_file() -> str:
    env = os.environ.get("MC_CALC_FEEDBACK")
    if env:
        return os.path.abspath(env)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "feedback.json")


def load_feedback(path: Optional[str] = None) -> List[Feedback]:
    target = path or feedback_file()
    if not os.path.isfile(target):
        return []
    try:
        with open(target, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return []
    items = data.get("entries", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    return [Feedback.from_dict(d) for d in items if isinstance(d, dict)]


def save_feedback(entries: List[Feedback], path: Optional[str] = None) -> str:
    target = path or feedback_file()
    payload = {
        "note": "服主反馈数据；可直接作为 calibrate.py 的 anchors 使用",
        "schema": 1,
        "count": len(entries),
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "playstyles": {k: v["multiplier"] for k, v in PLAYSTYLES.items()},
        "entries": [asdict(e) for e in entries],
    }
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return target


def append_feedback(fb: Feedback, path: Optional[str] = None) -> Tuple[str, int]:
    entries = load_feedback(path)
    entries.append(fb)
    target = save_feedback(entries, path)
    return target, len(entries)


def anchors_payload(entries: Optional[List[Feedback]] = None) -> Dict[str, Any]:
    """导出成 calibrate.py 直接能吃的格式。"""
    entries = entries if entries is not None else load_feedback()
    return {"anchors": [e.to_anchor() for e in entries]}


# ----------------------------------------------------------------------
# 汇总：把数据变成玩法系数
# ----------------------------------------------------------------------
def summarize(entries: Optional[List[Feedback]] = None,
              params: Any = None, include_unknown: bool = True) -> Dict[str, Any]:
    """按玩法分组统计，给出建议的玩法倍数。

    做法：复用 calibrate 的反推逻辑，先算出「这条数据在基准玩法下能带多少人」，
    再除以实测人数，得到该玩法的实际负载强度；组内取中位数（抗离群）。

    只有瓶颈是 CPU（或未标注瓶颈）的数据才参与——瓶颈在内存/网络时，
    人数少不是因为玩法重，不能用来估玩法系数。
    """
    from .calibrate import Anchor, analyze
    from .config import DEFAULT_PARAMS

    p = params or DEFAULT_PARAMS
    entries = entries if entries is not None else load_feedback()

    groups: Dict[str, List[float]] = {}
    skipped: List[Dict[str, str]] = []

    for e in entries:
        if e.bottleneck not in ("cpu", "unknown"):
            skipped.append({"entry": f"{e.cpu} / {e.playstyle}",
                            "reason": f"瓶颈是 {e.bottleneck}，不能用于玩法系数"})
            continue
        if e.bottleneck == "unknown" and not include_unknown:
            skipped.append({"entry": f"{e.cpu} / {e.playstyle}", "reason": "未标注瓶颈"})
            continue

        anchor = Anchor.from_dict(e.to_anchor())
        res = analyze([anchor], p)[0]
        if not res.usable or not res.ref_players:
            skipped.append({"entry": f"{e.cpu} / {e.playstyle}", "reason": res.reason})
            continue

        # 交叉验证：按模型跑一遍，只接受「CPU 算力确实是瓶颈」的数据。
        # - 瓶颈是内存/网络 → 人数受它们限制，估玩法倍数会得到荒谬值
        # - 瓶颈只是模组天花板 → 这条数据属于"模组天花板"的校准素材（mod_ceiling_vanilla），
        #   不能用来改玩法倍数，否则两个杠杆会互相污染
        binding = set(res.bottleneck_predicted or [])
        if binding and "cpu" not in binding:
            if "mods" in binding:
                skipped.append({
                    "entry": f"{e.cpu} / {e.playstyle}",
                    "reason": "按模型是「模组/玩法天花板」先到顶，这条数据留给模组天花板校准用",
                })
            else:
                labels = "、".join(sorted(binding))
                skipped.append({
                    "entry": f"{e.cpu} / {e.playstyle}",
                    "reason": f"按模型该配置的瓶颈是「{labels}」，人数受它限制，不能估玩法倍数",
                })
            continue

        # 反推出的 ref_players 已含玩法系数，乘回去得到「基准玩法下的预期人数」
        base_expected = res.ref_players / max(1e-6, e.playstyle_multiplier())
        ratio = base_expected / anchor.players if anchor.players else 0
        if not (0 < ratio <= 8):
            skipped.append({"entry": f"{e.cpu} / {e.playstyle}",
                            "reason": f"反推倍数 {ratio:.2f} 不合理（应落在 0~8），已跳过"})
            continue
        groups.setdefault(e.playstyle, []).append(ratio)

    suggested: Dict[str, Dict[str, Any]] = {}
    for name in PLAYSTYLES:
        vals = groups.get(name, [])
        cur = PLAYSTYLES[name]["multiplier"]
        if not vals:
            suggested[name] = {"samples": 0, "suggested_multiplier": cur,
                               "current_multiplier": cur, "spread": None, "values": []}
            continue
        med = statistics.median(vals)
        suggested[name] = {
            "samples": len(vals),
            "suggested_multiplier": round(med, 3),
            "current_multiplier": cur,
            "spread": round(max(vals) / min(vals), 2) if min(vals) > 0 else None,
            "values": [round(v, 2) for v in sorted(vals)],
        }

    return {
        "total": len(entries),
        "usable_groups": sum(1 for s in suggested.values() if s["samples"]),
        "suggested": suggested,
        "skipped": skipped,
        "pending": {k: v for k, v in suggested.items()
                    if v["samples"] >= 3
                    and abs(v["suggested_multiplier"] - v["current_multiplier"]) > 0.05},
    }


def behavior_file() -> str:
    env = os.environ.get("MC_CALC_BEHAVIOR")
    if env:
        return os.path.abspath(env)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "behavior_multiplier.json")


def apply_suggestions(summary: Dict[str, Any], min_samples: int = 3,
                      path: Optional[str] = None) -> Tuple[str, Dict[str, float]]:
    """把汇总出的玩法系数写进 behavior_multiplier.json（工具启动时自动加载生效）。

    只应用样本数 ≥ min_samples 的分组；返回 (文件路径, 实际应用的分组)。

    没有任何分组达标时**不写文件**——否则会留下一个
    `{"multipliers": {}}` 的空壳，看起来像"已经校准过了"，容易误导。
    """
    applied: Dict[str, float] = {}
    for name, s in summary.get("suggested", {}).items():
        if s.get("samples", 0) >= min_samples:
            applied[name] = s["suggested_multiplier"]

    target = path or behavior_file()
    if not applied:
        return target, {}

    payload = {
        "note": "由服主反馈汇总生成的玩法倍数；工具启动时自动加载并覆盖内置默认值",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "min_samples": min_samples,
        "multipliers": applied,
    }
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return target, applied


def load_behavior_overrides(path: Optional[str] = None) -> Dict[str, float]:
    """读取已应用的玩法倍数（工具启动时用来自动更新玩法列表）。"""
    target = path or behavior_file()
    if not os.path.isfile(target):
        return {}
    try:
        with open(target, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    mult = data.get("multipliers") if isinstance(data, dict) else None
    if not isinstance(mult, dict):
        return {}
    out: Dict[str, float] = {}
    for k, v in mult.items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def render_summary(summary: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append("  服主反馈汇总（玩法系数）")
    lines.append("=" * 72)
    lines.append(f"  累计反馈 {summary['total']} 条，可用于统计的分组 {summary['usable_groups']} 个")
    lines.append("")
    if not summary["suggested"]:
        lines.append("  还没有可用样本。需要「瓶颈 = cpu」且 CPU 型号能查到的数据。")
    for name, s in summary["suggested"].items():
        lines.append(f"  【{name}】样本 {s['samples']} 条")
        lines.append(f"      当前系数 {s['current_multiplier']:.2f} → "
                     f"建议 {s['suggested_multiplier']:.2f}"
                     + (f"（组内离散 {s['spread']}×）" if s["spread"] else ""))
        lines.append(f"      反推明细 {s['values']}")
        if s["samples"] < 3:
            lines.append("      ⚠ 样本偏少，建议攒到 ≥3 条再改系数")
        lines.append("")
    if summary["skipped"]:
        lines.append("  跳过的数据：")
        for item in summary["skipped"][:12]:
            lines.append(f"    - {item['entry']}：{item['reason']}")
    lines.append("")
    lines.append("  使用提示：")
    lines.append("    1. 先用「瓶颈=cpu 且玩法=原版」的数据校准 CPU 锚点"
                 "（python -m mc_player_calc.calibrate），")
    lines.append("       再回头改玩法倍数——否则两个参数会互相吸收误差。")
    lines.append("    2. 如果所有玩法反推出来的系数都系统性偏低/偏高，问题在 CPU 锚点，不在玩法。")
    lines.append("    3. 样本 <3 条建议先别改系数（当前只影响建议值，不会自动改默认配置）。")
    lines.append("    4. 玩法倍数很敏感：同一条数据里把它设成 1.15 还是 1.6，"
                 "反推结果会差 40%。")
    lines.append("       所以同一玩法至少要 3 条、且服务端/视距/进度阶段尽量同质，"
                 "再考虑应用。")
    return "\n".join(lines)


def summarize_packs(entries: Optional[List[Feedback]] = None,
                    params: Any = None) -> Dict[str, Any]:
    """**按整合包名分组**汇总，给出每个包自己的负载系数。

    同一套类型的整合包，作者优化状况不同，负载能差一大截，
    所以这里一个包一套系数（写进 modpack_profiles.json）。

    反推方式：把"该包当前生效的系数"当未知量解出来——
    先用"不含该包专属值"的折算倍数算出基准人数，再除以实测人数。
    """
    from .calibrate import Anchor, analyze
    from .config import DEFAULT_PARAMS

    p = params or DEFAULT_PARAMS
    entries = entries if entries is not None else load_feedback()

    groups: Dict[str, List[float]] = {}
    meta: Dict[str, Dict[str, Any]] = {}
    skipped: List[Dict[str, str]] = []

    for e in entries:
        if e.playstyle != "整合包" or not e.modpack_name:
            continue
        if e.bottleneck not in ("cpu", "unknown"):
            skipped.append({"entry": f"{e.modpack_name} / {e.cpu}",
                            "reason": f"瓶颈是 {e.bottleneck}，不能用于玩法系数"})
            continue
        anchor = Anchor.from_dict(e.to_anchor())
        res = analyze([anchor], p)[0]
        if not res.usable or not res.ref_players:
            skipped.append({"entry": f"{e.modpack_name} / {e.cpu}", "reason": res.reason})
            continue
        binding = set(res.bottleneck_predicted or [])
        # 与 CPU 校准不同：这里 mods 是瓶颈**正是有效信息**——
        # 人数就是被"这个包的内容复杂度"卡住的，反推出来的就是该包真实的负载系数。
        # 只排除内存/网络这类与该包负载无关的瓶颈。
        if "ram" in binding or "network" in binding:
            labels = "、".join(sorted(binding))
            skipped.append({"entry": f"{e.modpack_name} / {e.cpu}",
                            "reason": f"按模型瓶颈是「{labels}」，与包负载无关"})
            continue
        if binding and not (binding & {"cpu", "mods"}):
            labels = "、".join(sorted(binding))
            skipped.append({"entry": f"{e.modpack_name} / {e.cpu}",
                            "reason": f"按模型瓶颈是「{labels}」，不能反推包系数"})
            continue

        # ref_players 已含 behavior_factor，除回去得到「基准玩法人数」
        factor_without_pack = e.playstyle_multiplier(use_profile=False)
        base_expected = res.ref_players / max(1e-6, factor_without_pack)
        factor = base_expected / anchor.players if anchor.players else 0
        if not (0 < factor <= 8):
            skipped.append({"entry": f"{e.modpack_name} / {e.cpu}",
                            "reason": f"反推倍数 {factor:.2f} 不合理（应落在 0~8）"})
            continue

        # 关键：按**规范化包名**分组，否则「GTNH 2.7」和「gtnh27」会被算成两个包，
        # 样本被拆散、每边都不够 3 条，最后一条都写不进档案。
        key = normalize_pack(e.modpack_name)
        if not key:
            continue
        groups.setdefault(key, []).append(factor)
        m = meta.setdefault(key, {"display": str(e.modpack_name).strip(), "spellings": {}})
        # 显示名选"出现次数最多的写法"（同票时选更长的，信息更全）
        shown = str(e.modpack_name).strip()
        spell = m["spellings"]
        spell[shown] = spell.get(shown, 0) + 1
        m["display"] = sorted(spell.items(), key=lambda kv: (-kv[1], -len(kv[0])))[0][0]
        for field, val in (("mc_version", e.mc_version), ("kind", e.modpack_kind),
                           ("progress", e.progress), ("optimization", e.optimization)):
            if val and not m.get(field):
                m[field] = val
        if e.mods and not m.get("mods"):
            m["mods"] = e.mods

    suggested: Dict[str, Dict[str, Any]] = {}
    for key, vals in groups.items():
        med = statistics.median(vals)
        display = meta.get(key, {}).get("display") or key
        suggested[display] = {
            "key": key,
            "samples": len(vals),
            "suggested_factor": round(med, 3),
            "current_factor": resolve_pack_factor(display)[0],
            "spread": round(max(vals) / min(vals), 2) if min(vals) > 0 else None,
            "values": [round(v, 2) for v in sorted(vals)],
            **{k: v for k, v in meta.get(key, {}).items()
               if v and k not in ("display", "spellings")},
        }

    return {
        "total": len(entries),
        "packs": suggested,
        "ready": {k: v for k, v in suggested.items() if v["samples"] >= 3},
        "skipped": skipped,
    }


def apply_pack_suggestions(summary: Dict[str, Any], min_samples: int = 3) -> Dict[str, float]:
    """把按包汇总的结果写进 modpack_profiles.json。"""
    applied: Dict[str, float] = {}
    for name, s in summary.get("packs", {}).items():
        if s.get("samples", 0) < min_samples:
            continue
        upsert_profile(
            name,
            calibrated_factor=s["suggested_factor"],
            samples=s["samples"],
            kind=s.get("kind", ""),
            progress=s.get("progress", ""),
            mc_version=s.get("mc_version", ""),
            mods=s.get("mods", 0),
            optimization=s.get("optimization", ""),
            source=f"服主反馈 {s['samples']} 条（离散 {s.get('spread')}×）",
        )
        applied[name] = s["suggested_factor"]
    if applied:
        save_profiles()
    return applied


def render_pack_summary(summary: Dict[str, Any]) -> str:
    from .modpack import MODPACK_BASE_FACTOR, profile_file

    lines: List[str] = ["=" * 72, "  整合包系数汇总（一个包一套系数）", "=" * 72]
    lines.append(f"  累计反馈 {summary['total']} 条；有整合包数据的包 "
                 f"{len(summary['packs'])} 个，其中样本够用的 {len(summary['ready'])} 个")
    lines.append("")
    if not summary["packs"]:
        lines.append("  还没有带整合包名称的可用数据。")
        lines.append("  需要在反馈里填「整合包名称」，且瓶颈不是内存/网络。")
    for name, s in summary["packs"].items():
        lines.append(f"  【{name}】样本 {s['samples']} 条")
        if s.get("mc_version") or s.get("mods") or s.get("kind"):
            lines.append(f"      版本 {s.get('mc_version') or '—'} / "
                         f"{s.get('mods') or '—'} 模组 / {s.get('kind') or '—'}"
                         + (f" / {s['optimization']}" if s.get("optimization") else ""))
        lines.append(f"      当前系数 {s['current_factor']:.2f} → "
                     f"建议 {s['suggested_factor']:.2f}"
                     + (f"（离散 {s['spread']}×）" if s.get("spread") else ""))
        lines.append(f"      反推明细 {s['values']}")
        if s["samples"] < 3:
            lines.append("      ⚠ 样本不足 3 条，暂不写进档案（避免用过拟合的值）")
        lines.append("")
    if summary["skipped"]:
        lines.append("  跳过的数据：")
        for item in summary["skipped"][:10]:
            lines.append(f"    - {item['entry']}：{item['reason']}")
        lines.append("")
    lines.append(f"  档案文件：{profile_file()}")
    lines.append(f"  兜底规则（该包没有专属数据时）：基础 {MODPACK_BASE_FACTOR:g} × 玩法类型 × 进度阶段")
    lines.append(f"    玩法类型：{dict(MODPACK_KINDS)}")
    lines.append(f"    进度阶段：{dict(PROGRESS_STAGES)}")
    return "\n".join(lines)


def export_csv(entries: Optional[List[Feedback]] = None) -> str:
    entries = entries if entries is not None else load_feedback()
    cols = ["submitted_at", "cpu", "cpuz_single", "cores", "platform", "players", "tps", "view",
            "playstyle", "modpack_name", "mc_version", "mods", "modpack_kind", "progress",
            "playstyle_multiplier", "ram", "software", "bottleneck", "bandwidth_mbps", "note",
            "source"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols)
    writer.writeheader()
    for e in entries:
        row = asdict(e)
        row["playstyle_multiplier"] = e.playstyle_multiplier()
        writer.writerow({c: row.get(c, "") for c in cols})
    return buf.getvalue()


# ----------------------------------------------------------------------
# 给 AI agent 读的交付文件（Markdown，自带说明 + 内嵌机器可读 JSON）
# ----------------------------------------------------------------------
def _fmt(value: Any, unit: str = "", dash: str = "—") -> str:
    if value in (None, ""):
        return dash
    if isinstance(value, float):
        text = f"{value:g}"
    else:
        text = str(value)
    return f"{text}{unit}"


def export_agent_markdown(entries: Optional[List[Feedback]] = None,
                          server_owner: str = "") -> str:
    """生成一份「发给 agent 就能算」的 Markdown 文件。

    设计目标：任何人（或任何 AI）拿到这个文件，不需要额外上下文就能算出 CPU 系数。
    所以文件里包含：任务说明 → 口径定义 → 逐条记录 → 已会自动跳过的数据 → 期望输出格式
    → 末尾一个 ```json 代码块（机器可读，`calibrate.load_anchors` 能直接吃）。
    """
    from .calibrate import Anchor, analyze, summarize as cal_summarize
    from .config import DEFAULT_PARAMS

    entries = entries if entries is not None else load_feedback()
    anchors = [Anchor.from_dict(e.to_anchor()) for e in entries]
    results = analyze(anchors, DEFAULT_PARAMS)
    summary = cal_summarize(results)
    cal = DEFAULT_PARAMS

    lines: List[str] = []
    lines.append("# Minecraft 服务器承载数据（服主反馈）")
    lines.append("")
    lines.append("> 本文件由「Minecraft 服务器人数上限计算器」导出，供分析/校准使用。")
    lines.append("> 目标是**反推 CPU 承载系数**（基准配置能带多少人），并给出结论。")
    lines.append("")
    lines.append(f"- 导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 数据条数：{len(entries)}")
    if server_owner:
        lines.append(f"- 提交者：{server_owner}")
    lines.append(f"- 生成工具：mc_player_calc v{_version()}")
    lines.append("")
    lines.append("## 任务说明")
    lines.append("")
    lines.append("请完成两件事：")
    lines.append("1. **反推 CPU 系数**：用 `ref_players = 实测人数 × (基准单核加权 ÷ 该配置单核加权)^E`")
    lines.append("   逐条反推，再取几何平均，并给出离散度。")
    lines.append("2. **判断数据可信度**：指出哪些记录互相矛盾、哪些变量没控住（版本/优化/玩家分布）。")
    lines.append("")
    lines.append("已知参数（当前模型，可作为起点，也可以提出修改建议）：")
    lines.append("")
    lines.append("| 参数 | 值 | 含义 |")
    lines.append("| --- | --- | --- |")
    lines.append(f"| `ref_players` | {cal.cpu_reference_players:g} | 基准配置在 TPS≥19.5 下能带的人数（**待校准**）|")
    lines.append(f"| `ref_score` | {cal.cpu_reference_score:g} | 基准单核指数（i5-12400）|")
    lines.append(f"| `ref_cores` | {cal.cpu_reference_cores} | 基准物理核心数 |")
    lines.append(f"| `alpha` | {cal.cpu_core_scale_alpha:g} | 多核收益指数（单核加权 = 指数 × 核心数^alpha）|")
    lines.append(f"| `E` | {cal.cpu_capacity_exponent:g} | 容量幂（人数 ∝ 单核加权^E）|")
    lines.append(f"| CPU-Z 标定 | {cal.cpuz_reference_score:.0f} 分 = 指数 {cal.cpuz_reference_index:.0f} |")
    lines.append(f"|  |  | 换算：指数 = (CPU-Z 分)^{cal.cpuz_exponent:g} ÷ "
                 f"{(cal.cpuz_reference_score ** cal.cpuz_exponent) / cal.cpuz_reference_index:.1f} |")
    lines.append("")
    lines.append("口径定义（重要，数据合并的前提）：")
    lines.append("")
    lines.append("- **活跃用户**＝同时在线人数，且**TPS 首次跌破 19.5 时**的人数（不是「卡到不能玩」）")
    lines.append("- 只有 `bottleneck = cpu` 的记录能用于反推 CPU 系数")
    lines.append("- CPU-Z 单核分取 Bench → CPU Single Thread 的分数")
    lines.append("")
    lines.append("## 数据记录")
    lines.append("")
    lines.append("| # | CPU 型号 | CPU-Z 单核 | 核心 | 活跃用户 | TPS | 视距 | 玩法 | "
                 "整合包 | 优化状况 | MC 版本 | 模组数 | 玩法类型 | 进度 | 瓶颈 | 反推 ref_players |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for i, (e, r) in enumerate(zip(entries, results)):
        est = f"{r.ref_players:.1f}" if (r.usable and r.ref_players) else "不可用"
        lines.append(
            f"| {i + 1} | {e.cpu or '—'} | {_fmt(e.cpuz_single)} | {_fmt(e.cores)} | "
            f"{e.players} | {_fmt(e.tps)} | {e.view} | {e.playstyle} | "
            f"{e.modpack_name or '—'} | {e.optimization or '—'} | {e.mc_version or '—'} | "
            f"{_fmt(e.mods)} | {e.modpack_kind or '—'} | {e.progress or '—'} | "
            f"{e.bottleneck} | {est} |")
    lines.append("")
    if summary.get("count"):
        lines.append("## 当前模型的反推结果（导出时自动算出，供对照）")
        lines.append("")
        lines.append(f"- 可用样本 **{summary['count']}** 条")
        lines.append(f"- `ref_players` 几何平均 ≈ **{summary['ref_players_geomean']}**"
                     f"（范围 {summary['ref_players_min']} ~ {summary['ref_players_max']}）")
        if summary.get("geo_std_ratio"):
            lines.append(f"- 几何标准差 **{summary['geo_std_ratio']}**（越接近 1 越一致）")
        lines.append(f"- 建议置信度：{summary['suggest_confidence']}")
        lines.append("")
    if summary.get("skipped") or [r for r in results if not r.usable]:
        lines.append("## 不能用于反推的记录（已自动跳过，请复核原因）")
        lines.append("")
        for r in results:
            if not r.usable:
                lines.append(f"- **{r.anchor.cpu}** / {r.anchor.playstyle or r.anchor.behavior}：{r.reason}")
        lines.append("")
    lines.append("## 请按这个格式给出结论")
    lines.append("")
    lines.append("1. `ref_players` 建议值（几何平均，保留 1 位小数）")
    lines.append("2. 每条数据的反推值，以及哪些数据彼此矛盾")
    lines.append("3. 是否建议同时调整 `alpha` / `E`（说明理由；数据不足时明确说「不建议改」）")
    lines.append("4. 还缺什么数据才能提高可信度（例如：同一台机器的不同配置、同配置不同版本）")
    lines.append("")
    lines.append("## 机器可读数据（等价于上面表格）")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps({
        "schema": "mc_player_calc.feedback/v1",
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "server_owner": server_owner,
        "task": "calibrate_cpu_reference_players",
        "calibration": {
            "cpu_reference_players": cal.cpu_reference_players,
            "cpu_reference_score": cal.cpu_reference_score,
            "cpu_reference_cores": cal.cpu_reference_cores,
            "cpu_core_scale_alpha": cal.cpu_core_scale_alpha,
            "cpu_capacity_exponent": cal.cpu_capacity_exponent,
            "cpuz_reference_score": cal.cpuz_reference_score,
            "cpuz_reference_index": cal.cpuz_reference_index,
            "cpuz_exponent": cal.cpuz_exponent,
        },
        "anchors": [e.to_anchor() for e in entries],
    }, ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("> 这个 JSON 块可以被 `python -m mc_player_calc.calibrate <文件>` 直接读取并反推。")
    return "\n".join(lines)


def _version() -> str:
    from . import __version__
    return __version__


def parse_agent_markdown(text: str) -> List[Feedback]:
    """从 agent 交付文件里取回数据（读 ```json 代码块），用于复核别人发来的文件。

    注意用贪婪匹配：笔记里可能出现 "}" 之类的字符，非贪婪会在第一个花括号就截断。
    """
    import re as _re
    m = _re.search(r"```json\s*(\{.*\})\s*```", text, _re.DOTALL)
    if not m:
        raise ValueError("文件里没有找到 ```json 数据块")
    data = json.loads(m.group(1))
    items = data.get("anchors") or data.get("entries") or []
    return [Feedback.from_dict(d) for d in items if isinstance(d, dict)]


def stats_overview(entries: Optional[List[Feedback]] = None) -> Dict[str, Any]:
    entries = entries if entries is not None else load_feedback()
    by_style: Dict[str, int] = {}
    for e in entries:
        by_style[e.playstyle] = by_style.get(e.playstyle, 0) + 1
    by_bottleneck: Dict[str, int] = {}
    for e in entries:
        by_bottleneck[e.bottleneck] = by_bottleneck.get(e.bottleneck, 0) + 1
    return {
        "count": len(entries),
        "by_playstyle": by_style,
        "by_bottleneck": by_bottleneck,
        "latest": entries[-1].submitted_at if entries else "",
        "file": feedback_file(),
    }
