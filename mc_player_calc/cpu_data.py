"""CPU 型号库：把 CPU 名称映射到「单核性能 + 物理核心数」。

两套标尺（很重要，别混用）：

* **内部指数** `CpuSpec.score`：基准 100 ≈ Ryzen 5 5600，1.0 ~ 3.6 倍的跨度，
  引擎的 CPU 维度公式用它（见 config.cpu_reference_score）。
* **CPU-Z 单核分**：用户在 CPU-Z 里直接看到的数字（R5 5600 ≈ 662，i9-14900K ≈ 950，
  i7-4790K ≈ 430）。界面上展示、以及用户自己录入的都是这一套。

两者用幂律互转（CPU-Z 分数天然是「压缩」过的标尺）：

    index = cpu_cpuz_to_index(cpuz)
    cpuz  = cpu_index_to_cpuz(index)

标定锚点（取自公开实测）：R5 5600 → CPU-Z 662 = 指数 100；i9-14900K → CPU-Z ≈ 950 = 指数 132。
可调系数在 config.py 的 `cpuz_*` 字段。

用户自定义的型号存在工作目录的 custom_cpus.json 里，启动时自动加载并参与匹配。
"""
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 <请填写你的名字或昵称>
#
# 本文件是「Minecraft 服务器人数上限计算器」的一部分，按 GPL-3.0 授权。
# 完整声明见 mc_player_calc/__init__.py 与项目根目录的 COPYRIGHT。
# 本程序不提供任何担保；输出为模型估算值，不是实测保证。


from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, replace
from typing import Dict, List, Optional

# ----------------------------------------------------------------------
# CPU-Z 标尺标定（与 config.py 里的 cpuz_* 保持一致，改一处即可）
# ----------------------------------------------------------------------
CPUZ_REF_SCORE = 662.0      # Ryzen 5 5600 的 CPU-Z 单核分（公开实测）
CPUZ_REF_INDEX = 100.0      # 它对应的内部指数
CPUZ_EXPONENT = 2.0         # index ∝ cpuz^exponent


def _cpuz_k() -> float:
    return (CPUZ_REF_SCORE ** CPUZ_EXPONENT) / CPUZ_REF_INDEX


def cpu_cpuz_to_index(cpuz: float) -> float:
    """CPU-Z 单核分 → 内部指数。"""
    if cpuz is None or cpuz <= 0:
        return 0.0
    return (float(cpuz) ** CPUZ_EXPONENT) / _cpuz_k()


def cpu_index_to_cpuz(index: float) -> float:
    """内部指数 → CPU-Z 单核分。"""
    if index is None or index <= 0:
        return 0.0
    return (_cpuz_k() * float(index)) ** (1.0 / CPUZ_EXPONENT)


def cpuz_scale_info() -> Dict[str, float]:
    return {
        "ref_cpuz": CPUZ_REF_SCORE,
        "ref_index": CPUZ_REF_INDEX,
        "exponent": CPUZ_EXPONENT,
    }


def register_cpuz_calibration(ref_cpuz: float, ref_index: float, exponent: float) -> None:
    """允许 config.py 覆盖标定（保持单一数据源）。"""
    global CPUZ_REF_SCORE, CPUZ_REF_INDEX, CPUZ_EXPONENT
    if ref_cpuz and ref_cpuz > 0:
        CPUZ_REF_SCORE = float(ref_cpuz)
    if ref_index and ref_index > 0:
        CPUZ_REF_INDEX = float(ref_index)
    if exponent and exponent > 0:
        CPUZ_EXPONENT = float(exponent)


_MOBILE_SUFFIX_RE = re.compile(
    # Intel 移动后缀：i7-12700H / i9-14900HX / i7-10510U / i5-1135G7 / i3-1115G4
    r"i[3579][-\s]?\d{3,5}(hx|hk|hs|h|u|p|y|g[147])\b"
    # AMD 移动后缀：Ryzen 7 7840HS / R7 5800H / R9 8945HX / R7 5825U
    r"|(?:ryzen\s*[3579]|[re][3579])\s*[-\s]?\d{4}(hx|hk|hs|h|u|e|c)\b"
    # Core Ultra 移动版（H / U / V），注意排除 Ultra 9 285K 这类桌面型号
    r"|core\s*ultra\s*[3579]\s*\d{3}(h|u|v)\b",
    re.IGNORECASE,
)
# 明确属于桌面的后缀：K / KF / KS / F / X / XE / X3D / T 等
_DESKTOP_SUFFIX_RE = re.compile(
    r"i[3579][-\s]?\d{3,5}(kf|ks|k|x|xe|f|t)\b"
    r"|(?:ryzen\s*[3579]|[re][3579])\s*[-\s]?\d{4}(x3d|xt|x|xs|ge|g)\b",
    re.IGNORECASE,
)
_MOBILE_HINTS = ("移动", "笔记本", "笔电", "laptop", "mobile", "轻薄本", "游戏本", "标压", "低压")


def intel_mobile_suffix(name: str) -> str:
    """取出 Intel 型号的移动后缀（大写）：'i7-12700H' -> 'H'，桌面型号返回 ''。"""
    m = re.search(r"i[3579][-\s]?\d{3,5}(hx|hk|hs|h|u|p|y|g[147])\b", str(name), re.IGNORECASE)
    return m.group(1).upper() if m else ""


def is_mobile_name(name: str) -> bool:
    """按 Intel / AMD 命名规则判断是否为移动端型号。

    Intel：H / HK / HX / HS（标压高性能）、U / Y（低压）、P（准标压）、G1~G7（核显本）
    AMD  ：HX（桌面级模具）、HS（低功耗高性能）、H（标压）、U / C / E（低功耗）
    桌面后缀 K / KF / X / X3D 等一律不算移动端（例如 Core Ultra 9 285K）。
    """
    if not name:
        return False
    text = str(name)
    if any(h in text.lower() for h in _MOBILE_HINTS):
        return True
    if _DESKTOP_SUFFIX_RE.search(text):
        return False
    return bool(_MOBILE_SUFFIX_RE.search(text))


def resolve_platform(spec: "CpuSpec") -> str:
    """返回 desktop / mobile。库里的显式标注优先，其次按型号名规则识别。"""
    if getattr(spec, "platform", "desktop") == "mobile":
        return "mobile"
    return "mobile" if is_mobile_name(spec.name) else "desktop"


@dataclass(frozen=True)
class CpuSpec:
    name: str
    score: float          # 内部单核指数（基准 100 ≈ R5 5600）；用 cpu_index_to_cpuz 换算 CPU-Z 分
    cores: int            # 物理核心数
    note: str = ""
    platform: str = "desktop"   # desktop / mobile（也可留空由型号名自动识别）
    custom: bool = False        # True = 用户自己录入的型号

    @property
    def cpuz_score(self) -> float:
        """换算成 CPU-Z 单核分，用于界面展示与用户对照。"""
        return round(cpu_index_to_cpuz(self.score)) if self.score else 0.0


# 型号 -> 规格。键为小写、只保留字母数字，便于模糊匹配。
CPU_DB: Dict[str, CpuSpec] = {
    # ---- Intel 12/13/14 代 ----
    "i312100": CpuSpec("i3-12100", 105, 4, "单核强、核心少，小服首选"),
    "i312400": CpuSpec("i3-12400", 108, 4),
    "i512400": CpuSpec("i5-12400", 108, 6, "开服甜点"),
    "i512400f": CpuSpec("i5-12400F", 108, 6),
    "i512600k": CpuSpec("i5-12600K", 118, 10),
    "i513400": CpuSpec("i5-13400", 112, 10),
    "i513490f": CpuSpec("i5-13490F", 114, 10),
    "i513600k": CpuSpec("i5-13600K", 124, 14),
    "i513600kf": CpuSpec("i5-13600KF", 124, 14),
    "i514600k": CpuSpec("i5-14600K", 126, 14),
    "i514600kf": CpuSpec("i5-14600KF", 126, 14),
    "i712700k": CpuSpec("i7-12700K", 117, 12),
    "i712700kf": CpuSpec("i7-12700KF", 117, 12),
    "i713700k": CpuSpec("i7-13700K", 125, 16),
    "i713700kf": CpuSpec("i7-13700KF", 125, 16),
    "i713900k": CpuSpec("i9-13900K", 129, 24),
    "i713900kf": CpuSpec("i9-13900KF", 129, 24),
    "i714700k": CpuSpec("i7-14700K", 128, 20),
    "i714700kf": CpuSpec("i7-14700KF", 128, 20),
    "i914900k": CpuSpec("i9-14900K", 132, 24),
    "i914900kf": CpuSpec("i9-14900KF", 132, 24),
    # ---- Intel 更老世代 ----
    "i74790k": CpuSpec("i7-4790K", 68, 4, "老平台，模组多时主线程首先崩"),
    "i56600k": CpuSpec("i5-6600K", 72, 4),
    "i58400": CpuSpec("i5-8400", 78, 6),
    "i59400f": CpuSpec("i5-9400F", 80, 6),
    "i710700": CpuSpec("i7-10700", 95, 8),
    "i910900k": CpuSpec("i9-10900K", 103, 10),
    # ---- AMD Ryzen ----
    "r51600": CpuSpec("Ryzen 5 1600", 60, 6),
    "r52600": CpuSpec("Ryzen 5 2600", 70, 6),
    "r53600": CpuSpec("Ryzen 5 3600", 86, 6),
    "r55500": CpuSpec("Ryzen 5 5500", 92, 6),
    "r55600": CpuSpec("Ryzen 5 5600", 100, 6, "基准线"),
    "r55600x": CpuSpec("Ryzen 5 5600X", 103, 6),
    "r55600x3d": CpuSpec("Ryzen 5 5600X3D", 100, 6),
    "r55700x3d": CpuSpec("Ryzen 5 5700X3D", 101, 8),
    "r55800x3d": CpuSpec("Ryzen 5 5800X3D", 104, 8, "大三级缓存，模组服表现优秀"),
    # 别名：玩家习惯把 5800X3D 写成 R7 5800X3D
    "ryzen75800x3d": CpuSpec("Ryzen 7 5800X3D（即 R5 5800X3D）", 104, 8, "大三级缓存，模组服表现优秀"),
    "r57500f": CpuSpec("Ryzen 5 7500F", 118, 6),
    "r57600": CpuSpec("Ryzen 5 7600", 121, 6),
    "r57600x": CpuSpec("Ryzen 5 7600X", 124, 6),
    "r77700x": CpuSpec("Ryzen 7 7700X", 123, 8),
    "r77800x3d": CpuSpec("Ryzen 7 7800X3D", 128, 8, "MC 服务器最强消费级之一"),
    "r77800x": CpuSpec("Ryzen 7 7800X", 124, 8),
    "r97950x": CpuSpec("Ryzen 9 7950X", 126, 16),
    "r97950x3d": CpuSpec("Ryzen 9 7950X3D", 129, 16),
    "r79800x3d": CpuSpec("Ryzen 7 9800X3D", 136, 8, "当前第一梯队"),
    "r79700x": CpuSpec("Ryzen 7 9700X", 130, 8),
    "r59600x": CpuSpec("Ryzen 5 9600X", 128, 6),
    "r99900x": CpuSpec("Ryzen 9 9900X", 131, 12),
    "r99950x": CpuSpec("Ryzen 9 9950X", 133, 16),
    # ---- 服务器 / 洋垃圾 ----
    "e52680v4": CpuSpec("Xeon E5-2680 v4", 62, 14, "单核弱、核心多，适合多开不适合高 TPS"),
    "e52696v3": CpuSpec("Xeon E5-2696 v3", 60, 18),
    "e52680v3": CpuSpec("Xeon E5-2680 v3", 58, 12),
    "e52310": CpuSpec("Xeon E5-2310", 45, 4),
    "e52650v2": CpuSpec("Xeon E5-2650 v2", 50, 8),
    "epyc7302": CpuSpec("EPYC 7302", 78, 16),
    "epyc7542": CpuSpec("EPYC 7542", 80, 32),
    "xeonsilver4210": CpuSpec("Xeon Silver 4210", 72, 10),
    "xeongold6133": CpuSpec("Xeon Gold 6133", 74, 20),
    # ---- 移动端 Intel（H = 标压高性能，U = 低压轻薄，Y = 极低功耗）----
    "i710750h": CpuSpec("i7-10750H", 92, 6, "H 标压"),
    "i710870h": CpuSpec("i7-10870H", 95, 8, "H 标压"),
    "i511400h": CpuSpec("i5-11400H", 96, 6, "H 标压"),
    "i711800h": CpuSpec("i7-11800H", 100, 8, "H 标压"),
    "i712650h": CpuSpec("i7-12650H", 105, 10, "H 标压"),
    "i712700h": CpuSpec("i7-12700H", 110, 14, "H 标压"),
    "i712700hx": CpuSpec("i7-12700HX", 112, 16, "HX 桌面级模具"),
    "i512500h": CpuSpec("i5-12500H", 108, 12, "H 标压"),
    "i513500h": CpuSpec("i5-13500H", 108, 12, "H 标压"),
    "i713700h": CpuSpec("i7-13700H", 114, 14, "H 标压"),
    "i713700hx": CpuSpec("i7-13700HX", 116, 16, "HX 桌面级模具"),
    "i713800h": CpuSpec("i7-13800H", 115, 14),
    "i914900hx": CpuSpec("i9-14900HX", 124, 24, "HX 桌面级模具"),
    "i513500u": CpuSpec("i5-13500U", 95, 10, "U 低压"),
    "i71260u": CpuSpec("i7-1260U", 92, 10, "U 低压"),
    "i78565u": CpuSpec("i7-8565U", 62, 4, "U 低压"),
    "i510210u": CpuSpec("i5-10210U", 68, 4, "U 低压"),
    "i710510u": CpuSpec("i7-10510U", 72, 4, "U 低压"),
    "i51135g7": CpuSpec("i5-1135G7", 82, 4, "U 低压"),
    "i71165g7": CpuSpec("i7-1165G7", 88, 4, "U 低压"),
    "i51240p": CpuSpec("i5-1240P", 100, 12, "P 准标压"),
    "i71240p": CpuSpec("i7-1260P", 104, 12, "P 准标压"),
    "ultra5125h": CpuSpec("Core Ultra 5 125H", 108, 14, "Meteor Lake"),
    "ultra7155h": CpuSpec("Core Ultra 7 155H", 114, 16, "Meteor Lake"),
    "ultra9285h": CpuSpec("Core Ultra 9 285H", 120, 16),
    # ---- 移动端 AMD（HX = 桌面级，HS = 高性能，U = 低压）----
    "r74800h": CpuSpec("Ryzen 7 4800H", 92, 8, "H 标压"),
    "r75800h": CpuSpec("Ryzen 7 5800H", 98, 8, "H 标压"),
    "r76800h": CpuSpec("Ryzen 7 6800H", 105, 8, "H 标压"),
    "r76800hs": CpuSpec("Ryzen 7 6800HS", 103, 8, "HS 低功耗版"),
    "r96900hx": CpuSpec("Ryzen 9 6900HX", 108, 8, "HX 桌面级模具"),
    "r77735hs": CpuSpec("Ryzen 7 7735HS", 108, 8, "HS 低功耗版"),
    "r77840hs": CpuSpec("Ryzen 7 7840HS", 115, 8, "HS 低功耗版"),
    "r97940hs": CpuSpec("Ryzen 9 7940HS", 118, 8, "HS 低功耗版"),
    "r78845h": CpuSpec("Ryzen 7 8845H", 118, 8, "H 标压"),
    "r98945hx": CpuSpec("Ryzen 9 8945HX", 122, 16, "HX 桌面级模具"),
    "r78840u": CpuSpec("Ryzen 7 8840U", 105, 8, "U 低压"),
    "r75825u": CpuSpec("Ryzen 7 5825U", 92, 8, "U 低压"),
    "r73880u": CpuSpec("Ryzen 7 3880U", 88, 8, "U 低压"),
    # ---- 迷你主机 / NAS ----
    "n100": CpuSpec("Intel N100", 55, 4, "只能带极小人数的原版服"),
    "n305": CpuSpec("Intel N305", 58, 8),
    "j4125": CpuSpec("Celeron J4125", 38, 4, "不建议开模组服"),
}

# ----------------------------------------------------------------------
# 用户自定义 CPU（持久化到 custom_cpus.json）
# ----------------------------------------------------------------------
CUSTOM_DB: Dict[str, CpuSpec] = {}
_AUTO_LOAD = os.environ.get("MC_CALC_NO_AUTOLOAD") != "1"


def custom_cpu_file() -> str:
    """自定义型号的存放位置：默认在 mc_player_calc 包的上一级目录。"""
    env = os.environ.get("MC_CALC_CUSTOM_CPUS")
    if env:
        return os.path.abspath(env)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "custom_cpus.json")


def db_key(name: str) -> str:
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


def merged_db() -> Dict[str, CpuSpec]:
    """内置 + 自定义（自定义优先，可覆盖内置型号）。"""
    return {**CPU_DB, **CUSTOM_DB}


def custom_models() -> List[CpuSpec]:
    return sorted(CUSTOM_DB.values(), key=lambda s: s.name)


def load_custom_cpus(path: Optional[str] = None) -> int:
    """从 JSON 载入自定义型号，返回载入条数。"""
    target = path or custom_cpu_file()
    CUSTOM_DB.clear()
    if not os.path.isfile(target):
        return 0
    try:
        with open(target, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return 0
    entries = data.get("cpus", data) if isinstance(data, dict) else data
    if not isinstance(entries, list):
        return 0
    for item in entries:
        if not isinstance(item, dict):
            continue
        spec = custom_from_dict(item)
        if spec is not None:
            CUSTOM_DB[db_key(spec.name)] = spec
    return len(CUSTOM_DB)


def save_custom_cpus(path: Optional[str] = None) -> str:
    """把自定义型号写回 JSON（内部指数与 CPU-Z 分都存，方便人肉编辑）。"""
    target = path or custom_cpu_file()
    payload = {
        "note": "用户自定义 CPU 型号；cpuz_single 为 CPU-Z 单核分，score 为内部指数（自动换算）",
        "cpuz_calibration": cpuz_scale_info(),
        "cpus": [
            {
                "name": s.name,
                "cores": s.cores,
                "platform": s.platform,
                "cpuz_single": s.cpuz_score,
                "score": round(s.score, 2),
                "note": s.note,
            }
            for s in sorted(CUSTOM_DB.values(), key=lambda x: -x.score)
        ],
    }
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return target


def custom_from_dict(item: Dict) -> Optional[CpuSpec]:
    """从字典构造 CpuSpec：优先用 cpuz_single（用户口径），否则用 score（内部指数）。"""
    name = str(item.get("name") or "").strip()
    if not name:
        return None
    try:
        cores = max(1, int(item.get("cores") or 4))
    except (TypeError, ValueError):
        cores = 4

    cpuz = item.get("cpuz_single")
    score_raw = item.get("score")
    if cpuz not in (None, "", 0):
        try:
            score = cpu_cpuz_to_index(float(cpuz))
        except (TypeError, ValueError):
            score = _UNKNOWN.score
    elif score_raw not in (None, "", 0):
        try:
            score = float(score_raw)
        except (TypeError, ValueError):
            score = _UNKNOWN.score
    else:
        return None

    platform = str(item.get("platform") or "").strip().lower()
    if platform not in ("desktop", "mobile"):
        platform = "mobile" if is_mobile_name(name) else "desktop"
    note = str(item.get("note") or "").strip() or "用户自定义型号"
    return CpuSpec(name, score, cores, note, platform, custom=True)


def add_custom_cpu(name: str, cpuz_single: float, cores: int = 4,
                   platform: str = "", note: str = "") -> CpuSpec:
    """新增/覆盖一个自定义型号（cpuz_single = CPU-Z 单核分）。"""
    name = str(name or "").strip()
    if not name:
        raise ValueError("型号名称不能为空")
    try:
        cpuz = float(cpuz_single)
    except (TypeError, ValueError):
        raise ValueError("CPU-Z 单核分必须是数字")
    if cpuz <= 0 or cpuz > 5000:
        raise ValueError("CPU-Z 单核分看起来不合理（应在 0~5000 之间）")
    try:
        cores = max(1, min(256, int(cores)))
    except (TypeError, ValueError):
        raise ValueError("核心数必须是整数")

    plat = (platform or "").strip().lower()
    if plat not in ("desktop", "mobile"):
        plat = "mobile" if is_mobile_name(name) else "desktop"

    spec = CpuSpec(name, cpu_cpuz_to_index(cpuz), cores,
                   note or f"用户自定义（CPU-Z 单核 {cpuz:.0f}）", plat, custom=True)
    CUSTOM_DB[db_key(name)] = spec
    return spec


def remove_custom_cpu(name: str) -> bool:
    """删除自定义型号；返回是否真的删掉了。"""
    key = db_key(name)
    if key in CUSTOM_DB:
        del CUSTOM_DB[key]
        return True
    return False


if _AUTO_LOAD:
    load_custom_cpus()


_UNKNOWN = CpuSpec("未知型号", 85.0, 4, "按「中端 4 核」保守估算，建议后续校准")


def all_models() -> List[str]:
    """供下拉框使用的型号列表（自定义在前，其余按单核分数降序）。"""
    db = merged_db()
    seen: Dict[str, CpuSpec] = {}
    for spec in db.values():
        seen[spec.name] = spec
    specs = sorted(seen.values(), key=lambda x: (not x.custom, -x.score))
    return [s.name for s in specs]


def _core_name(key: str) -> Optional[str]:
    """去掉 Ryzen 的系列前缀，得到纯型号：'r75800x3d' -> '5800x3d'。"""
    if key.startswith("r") and len(key) > 4 and key[1].isdigit() and key[2].isdigit():
        return key[2:]
    return None


def _numeric_key(spec: CpuSpec) -> str:
    """把型号名压缩成数字串：'Ryzen 5 5800X3D' -> '55800x3d'。"""
    return "".join(ch for ch in spec.name.lower() if ch.isalnum())


def _name_matches(key: str, spec: CpuSpec) -> bool:
    """纯型号输入在型号名里的匹配：'5800x3d' / '12400' 命中对应型号。

    只在型号名的尾部匹配（允许 "12400" 命中 "i5-12400F"），避免 "1600" 误伤 "5600"。
    """
    name_key = _numeric_key(spec)
    if key in ("r", "i", "e"):
        return False
    if name_key.endswith(key):
        return True
    idx = name_key.find(key)
    return idx > 0 and not name_key[idx - 1].isdigit()


def _candidate_rank(dbk: str, source: str, core: Optional[str]) -> tuple:
    """候选择优打分（越小越优先）。

    顺序：完全相等 → 用户自定义 → 覆盖输入更完整 → 同系列核心 → 键更长 → 键更短。
    自定义排在前面是关键：用户特意录入的型号应该赢过内置的近似型号。
    """
    if dbk == source:
        coverage = 0
    elif source.startswith(dbk):
        coverage = len(source) - len(dbk)
    elif dbk.startswith(source):
        coverage = len(dbk) - len(source)
    else:
        coverage = len(source)
    series_ok = 0 if (core and _core_name(dbk) == core) else 1
    return (coverage, series_ok, -len(dbk))


def _number_tokens(key: str) -> List[str]:
    """取出型号里的数字 token（长度 ≥3）：'i714700kf超58g' -> ['714700','58']。"""
    return [t for t in re.findall(r"\d{3,}", key)]


def _numbers_compatible(query_key: str, candidate_key: str) -> bool:
    """数字型号必须对得上，否则只是"厂商名/系列名"撞车。

    例：查询 "coreultra7155h" 与自定义 "intelcoreultra9285k自测" 共享 "coreultra"，
    但 155 与 285 是不同型号，必须拒绝；
    而 "285k自测" 与 "intelcoreultra9285k自测" 共享 285，应当接受。
    """
    tokens = _number_tokens(query_key)
    if not tokens:
        return False
    return any(t in candidate_key for t in tokens)


def lookup(model: str) -> Optional[CpuSpec]:
    """按名称模糊匹配 CPU 库（内置 + 用户自定义）。

    支持这些写法：i5-12400 / i5 12400F / R7 5800X3D / 5800X3D / 7800x3d / epyc 7542
    以及用户自己录入的长型号名（"E5-2686 v4" 能命中 "Intel Xeon E5-2686 v4 ES"）。
    """
    if not model:
        return None
    db = merged_db()
    key = db_key(model)
    if not key:
        return None
    if key in db:
        return db[key]

    # 统一别名：'ryzen75800x3d' -> 'r75800x3d'
    if key.startswith("ryzen"):
        key = "r" + key[len("ryzen"):]

    variants = [key]
    if key[0].isdigit():
        variants.append("r7" + key)   # 桌面 Ryzen 写法
        variants.append("r" + key)
    if key.startswith("r") and len(key) > 1:
        variants.append(key[1:])

    # 1) 变体完全相等
    for v in variants:
        if v in db:
            return db[v]

    core = _core_name(key)

    # 2) 纯数字/无系列号写法："5800X3D"、"9900X"、"12400"（按型号名里的数字串匹配）
    if key[0].isdigit():
        hits = [(k, s) for k, s in db.items() if _name_matches(key, s)]
        if hits:
            hits.sort(key=lambda ks: (
                0 if ks[0] == key else 1,
                0 if _numeric_key(ks[1]).startswith(
                    ("i5", "i7", "i9", "r5", "r7", "r9", "u5", "u7", "u9")) else 1,
                len(_numeric_key(ks[1])),
            ))
            return hits[0][1]

    # 3) 把所有候选合并后统一打分，不再"命中即返回"
    #    （否则 "i7-14700KF 超5.8G" 会被内置的 "i7-14700K" 抢先）
    pool: Dict[str, str] = {}       # 库键 -> 参与打分的来源串

    def _offer(dbk: str, source: str) -> None:
        prev = pool.get(dbk)
        if prev is None or _candidate_rank(dbk, source, core) < _candidate_rank(dbk, prev, core):
            pool[dbk] = source

    for v in variants:
        for dbk in db:
            if dbk.startswith(v) or v.startswith(dbk):
                _offer(dbk, v)
            elif dbk in v and len(dbk) >= 4:
                # 候选只是输入的一小截时，必须数字型号对得上，否则容易"厂商名撞车"
                if db[dbk].custom and not _numbers_compatible(v, dbk):
                    continue
                _offer(dbk, v)

    # 自定义型号常用"厂商+型号+备注"的长名字，额外做一次最长公共子串匹配
    for v in variants:
        if len(v) < 5:
            continue
        for dbk, spec in db.items():
            if not spec.custom or dbk in pool:
                continue
            best_sub = 0
            for i in range(len(v)):
                for j in range(i + 5, len(v) + 1):
                    if v[i:j] in dbk:
                        best_sub = max(best_sub, j - i)
            if best_sub >= 5 and _numbers_compatible(v, dbk):
                _offer(dbk, v)

    if pool:
        best_key = sorted(pool, key=lambda k: (not db[k].custom,
                                               _candidate_rank(k, pool[k], core)))[0]
        return db[best_key]

    # 4) 最后兜底：核心号共享（'r75800x3d' 与 'r55800x3d' 共享 '5800x3d'）
    if core:
        exact = [k for k in db if _core_name(k) == core]
        if exact:
            same_series = [k for k in exact if k[:2] == key[:2]]
            return db[(same_series or exact)[0]]
    return None


def unknown_spec(model: str = "") -> CpuSpec:
    spec = _UNKNOWN
    platform = "mobile" if is_mobile_name(model) else "desktop"
    if model:
        note = spec.note
        if platform == "mobile":
            note = "未收录的移动端型号，单核按中端保守估算，散热按笔记本模具计算"
        return CpuSpec(f"{model}（未收录）", spec.score, spec.cores, note, platform)
    return spec
