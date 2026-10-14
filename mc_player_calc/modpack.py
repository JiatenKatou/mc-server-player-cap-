"""整合包档案：**一个包一套系数**。

为什么不能共用一套：
    整合包作者对服务端的优化差别极大——有的做了区块加载与实体 tick 优化，
    同样的模组数量能多带 50% 的人；有的几乎没优化，甚至比模组数量更多的包还吃资源。
    所以"科技包 = 1.1 倍负载"这种笼统分类误差会很大，
    正确做法是**按包名建立档案，各自从服主反馈数据里校准**。

数据来源与优先级（从高到低）：

    1. `modpack_profiles.json` 里该包的 `calibrated_factor`（由反馈数据校准出来的）
    2. 同文件里该包的 `declared_factor`（人工预填的估计值）
    3. 按"基础 1.6 × 玩法类型 × 进度阶段"折算（没有任何该包数据时的兜底）

匹配按"规范化包名"（只保留字母数字与中文）做：先精确匹配，再双向包含，
所以 `GTNH 2.7` 能命中档案里的 `GTNH`，`Create: Above and Beyond` 也能命中
`createaboveandbeyond`。
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
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# 玩法类型系数（在没有任何该包数据时用来兜底）
MODPACK_KINDS: Dict[str, float] = {
    "科技 / 自动化": 1.10,
    "魔法 / 探索": 1.00,
    "综合（科技+魔法+任务）": 1.15,
    "生电 / 红石向": 1.20,
    "轻量 / 优化向": 0.90,
}

# 进度阶段（同一包，后期基地比开荒期重）
PROGRESS_STAGES: Dict[str, float] = {
    "开荒期": 0.85,
    "中期": 1.00,
    "大后期 / 长期服": 1.20,
}

MODPACK_BASE_FACTOR = 1.60
"""整合包这个玩法的基准负载倍数（再乘玩法类型与进度阶段）。"""


def normalize_pack(name: str) -> str:
    """规范化整合包名称，用于匹配与分组。"""
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum())


@dataclass
class PackProfile:
    """一个整合包的负载档案。"""

    name: str = ""                       # 包名（用户输入的原样保留）
    factor: float = 1.0                  # 当前生效的负载倍数
    declared_factor: Optional[float] = None   # 人工预填值
    calibrated_factor: Optional[float] = None  # 由反馈数据校准出来的值
    kind: str = ""                       # 玩法类型（兜底用）
    progress: str = ""                   # 常见的进度阶段
    mc_version: str = ""
    mods: int = 0
    optimization: str = ""               # 作者优化状况：良好 / 一般 / 较差
    samples: int = 0                     # 参与校准的样本数
    source: str = ""                     # 数据来源备注
    note: str = ""
    updated_at: str = ""

    @property
    def key(self) -> str:
        return normalize_pack(self.name)

    def to_dict(self) -> Dict:
        data = asdict(self)
        data["key"] = self.key
        return data


PROFILES: Dict[str, PackProfile] = {}
_AUTO_LOAD = os.environ.get("MC_CALC_NO_AUTOLOAD") != "1"


def profile_file() -> str:
    env = os.environ.get("MC_CALC_MODPACKS")
    if env:
        return os.path.abspath(env)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "modpack_profiles.json")


def load_profiles(path: Optional[str] = None) -> int:
    """从 JSON 载入整合包档案，返回载入条数。"""
    target = path or profile_file()
    PROFILES.clear()
    if not os.path.isfile(target):
        return 0
    try:
        with open(target, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return 0
    items = data.get("packs", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        return 0
    for item in items:
        if not isinstance(item, dict):
            continue
        prof = profile_from_dict(item)
        if prof is not None:
            PROFILES[prof.key] = prof
    return len(PROFILES)


def profile_from_dict(item: Dict) -> Optional[PackProfile]:
    name = str(item.get("name") or "").strip()
    if not name:
        return None
    prof = PackProfile(name=name)
    for k in ("kind", "progress", "mc_version", "optimization", "source", "note",
              "updated_at"):
        if item.get(k) is not None:
            setattr(prof, k, str(item[k]))
    for k in ("declared_factor", "calibrated_factor"):
        val = item.get(k)
        if val not in (None, ""):
            try:
                setattr(prof, k, float(val))
            except (TypeError, ValueError):
                pass
    try:
        prof.mods = int(item.get("mods") or 0)
    except (TypeError, ValueError):
        prof.mods = 0
    try:
        prof.samples = int(item.get("samples") or 0)
    except (TypeError, ValueError):
        prof.samples = 0

    # factor 字段（老格式）优先当 calibrated 用
    if item.get("factor") not in (None, ""):
        try:
            prof.calibrated_factor = float(item["factor"])
        except (TypeError, ValueError):
            pass
    prof.factor = prof.calibrated_factor or prof.declared_factor or 0.0
    return prof


def save_profiles(path: Optional[str] = None) -> str:
    target = path or profile_file()
    payload = {
        "note": "整合包负载档案：一个包一套系数。calibrated_factor 由服主反馈数据校准得出，"
                "declared_factor 是人工预填值；两者都空时按 kind/progress 折算兜底。",
        "schema": 1,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "base_factor": MODPACK_BASE_FACTOR,
        "kinds": MODPACK_KINDS,
        "progress_stages": PROGRESS_STAGES,
        "packs": [
            {k: v for k, v in asdict(p).items() if v not in (None, "")}
            for p in sorted(PROFILES.values(), key=lambda x: -x.factor)
        ],
    }
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return target


def find_profile(name: str) -> Optional[PackProfile]:
    """按包名找档案：精确 → 双向包含（取更长的匹配）。"""
    key = normalize_pack(name)
    if not key:
        return None
    if key in PROFILES:
        return PROFILES[key]
    best: Optional[PackProfile] = None
    best_len = 0
    for pkey, prof in PROFILES.items():
        if not pkey:
            continue
        if pkey in key or key in pkey:
            hit = min(len(pkey), len(key))
            if hit > best_len:
                best, best_len = prof, hit
    return best


def fallback_factor(kind: str = "", progress: str = "") -> Tuple[float, str]:
    """没有任何该包数据时的兜底倍数。返回 (倍数, 说明)。"""
    factor = MODPACK_BASE_FACTOR
    parts = [f"基础 {MODPACK_BASE_FACTOR:g}"]
    if kind and kind in MODPACK_KINDS:
        factor *= MODPACK_KINDS[kind]
        parts.append(f"玩法类型 {MODPACK_KINDS[kind]:g}")
    if progress and progress in PROGRESS_STAGES:
        factor *= PROGRESS_STAGES[progress]
        parts.append(f"进度 {PROGRESS_STAGES[progress]:g}")
    return round(factor, 3), " × ".join(parts)


def resolve_pack_factor(name: str, kind: str = "", progress: str = "") -> Tuple[float, str]:
    """解析某个整合包的负载倍数，返回 (倍数, 来源说明)。

    优先级：该包的校准值 → 该包的人工预填值 → 按类型/进度兜底。
    """
    prof = find_profile(name)
    if prof is not None:
        if prof.calibrated_factor:
            return round(float(prof.calibrated_factor), 3), \
                f"来自「{prof.name}」的校准值（{prof.samples} 条样本）"
        if prof.declared_factor:
            return round(float(prof.declared_factor), 3), f"来自「{prof.name}」的预填值"
        fb, why = fallback_factor(prof.kind or kind, prof.progress or progress)
        return fb, f"「{prof.name}」暂无专属数据，按类型/进度折算（{why}）"
    fb, why = fallback_factor(kind, progress)
    if name:
        return fb, f"「{name}」尚未建立档案，按类型/进度折算（{why}）"
    return fb, f"未指定包名，按类型/进度折算（{why}）"


def upsert_profile(name: str, **fields) -> PackProfile:
    """新增或更新一个包的档案。"""
    name = str(name or "").strip()
    if not name:
        raise ValueError("整合包名称不能为空")
    key = normalize_pack(name)
    prof = PROFILES.get(key) or PackProfile(name=name)
    prof.name = name
    for k, v in fields.items():
        if hasattr(prof, k) and v is not None:
            setattr(prof, k, v)
    if prof.calibrated_factor:
        prof.factor = prof.calibrated_factor
    elif prof.declared_factor:
        prof.factor = prof.declared_factor
    else:
        prof.factor = fallback_factor(prof.kind, prof.progress)[0]
    prof.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    PROFILES[key] = prof
    return prof


def reload_profiles() -> int:
    """按当前环境变量重新载入档案（测试与切换数据目录时用）。"""
    return load_profiles()


def remove_profile(name: str) -> bool:
    key = normalize_pack(name)
    if key in PROFILES:
        del PROFILES[key]
        return True
    return False


def list_profiles() -> List[PackProfile]:
    return sorted(PROFILES.values(), key=lambda p: (not p.calibrated_factor, -p.factor))


if _AUTO_LOAD:
    load_profiles()
