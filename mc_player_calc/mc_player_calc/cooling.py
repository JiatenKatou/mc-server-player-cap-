"""散热系数：桌面 CPU 默认 1.0；移动端 CPU 由「笔记本模具 × 导热耗材」决定。

计算口径（按需求定义）：
    散热系数 = 模具系数 × 导热耗材系数 × 用户自定义系数
    CPU 有效单核得分 = 原始单核得分 × 散热系数

为什么这样建模：
    笔记本上 CPU 的单核持续性能几乎完全由散热决定 —— 同样的 i7-12700H，
    在 45W 轻薄本上跑到 100℃ 就降频，在 150W 均热板游戏本上能长时间保持满血。
    单核得分（决定 MC 主线程 tick）因此要乘上散热衰减系数。

所有系数都在本文件里，直接改数字即可（或从 GUI 的"自定义系数"输入）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Optional


# ----------------------------------------------------------------------
# 桌面：由散热器决定。基准 = 中端风冷 = 1.00
# ----------------------------------------------------------------------
DESKTOP_COOLING: Dict[str, float] = {
    "原装散热器 / 老旧散热": 0.95,
    "中端风冷（4 热管单塔）": 1.00,
    "高端风冷（双塔 / 6 热管以上）": 1.02,
    "240 水冷": 1.025,
    "360 水冷及以上": 1.04,
    "被动散热 / 无风扇（迷你主机、NAS）": 0.88,
}
DESKTOP_COOLING_DEFAULT = "中端风冷（4 热管单塔）"


# ----------------------------------------------------------------------
# 笔记本模具：基准 = 主流游戏本（散热规格与中端台式风冷相当）= 1.00
# ----------------------------------------------------------------------
LAPTOP_CHASSIS: Dict[str, float] = {
    "轻薄本 / 核显本（单风扇、15~28W 限制）": 0.85,
    "全能本 / 轻薄独显（双风扇、35~45W）": 0.92,
    "主流游戏本（双风扇多热管、45~65W 长时）": 1.00,
    "高端游戏本（均热板 / 三风扇、65~100W）": 1.05,
    "移动工作站 / 厚砖本（100W+、可上桌面级）": 1.10,
    "迷你主机 / NUC / 掌机（受限模具）": 0.88,
}
LAPTOP_CHASSIS_DEFAULT = "主流游戏本（双风扇多热管、45~65W 长时）"


# ----------------------------------------------------------------------
# 导热耗材：基准 = 普通硅脂 = 1.00
# ----------------------------------------------------------------------
THERMAL_MATERIAL: Dict[str, float] = {
    "普通硅脂（出厂 / 杂牌）": 1.00,
    "高性能硅脂（信越 7921 / 暴力熊等）": 1.02,
    "相变片 / 石墨烯贴片": 1.03,
    "液金导热（需专业维护）": 1.06,
    "导热垫老化 / 未维护（3 年以上未换硅脂）": 0.92,
}
THERMAL_MATERIAL_DEFAULT = "普通硅脂（出厂 / 杂牌）"


# ----------------------------------------------------------------------
# 平台约束：某些后缀物理上就配不到强散热
# ----------------------------------------------------------------------
PLATFORM_CHASSIS_CAP: Dict[str, str] = {
    "U": "轻薄本 / 核显本（单风扇、15~28W 限制）",
    "Y": "轻薄本 / 核显本（单风扇、15~28W 限制）",
    "G": "全能本 / 轻薄独显（双风扇、35~45W）",
    "P": "全能本 / 轻薄独显（双风扇、35~45W）",
    "H": "高端游戏本（均热板 / 三风扇、65~100W）",
    "HS": "高端游戏本（均热板 / 三风扇、65~100W）",
    "HK": "移动工作站 / 厚砖本（100W+、可上桌面级）",
    "HX": "移动工作站 / 厚砖本（100W+、可上桌面级）",
}

_COOLING_SANITY_RANGE = (0.3, 1.6)


_SUFFIX_RE = re.compile(
    r"(?<=\d)(HX|HK|HS|H|U|P|Y|G[147])\b",
    re.IGNORECASE,
)
# 桌面后缀：出现这些一律不当作移动端（K / KF / X / X3D / F / T ...）
_DESKTOP_SUFFIX_RE = re.compile(
    r"(?<=\d)(KF|KS|K|X3D|XT|XE|X|F|T)\b",
    re.IGNORECASE,
)


def suffix_of(model: str) -> str:
    """提取移动端后缀：'i7-12700H' -> 'H'，'R7 7840HS' -> 'HS'，'R9 8945HX' -> 'HX'。

    必须有数字紧跟在前，且不能被桌面后缀（K/KF/X/X3D...）抢先，避免把
    "Core Ultra 9 285K" 的 K、'Ryzen' 的 y、'X3D' 的 d 之类当成移动后缀。
    """
    if not model:
        return ""
    text = str(model).strip()
    mobile = _SUFFIX_RE.search(text)
    if not mobile:
        return ""
    desktop = _DESKTOP_SUFFIX_RE.search(text)
    if desktop and desktop.start() < mobile.start():
        return ""
    suf = mobile.group(1).upper()
    return "G" if suf.startswith("G") else suf


def chassis_options(suffix: str) -> list:
    """按后缀给出可选的模具（第一项为推荐值）。

    这里不只是"建议"，而是物理约束：U/Y 低压 U 的封装功耗上限只有 15~28W，
    塞进厚砖模具也没意义，所以只给轻薄本档。
    """
    cap = PLATFORM_CHASSIS_CAP.get(suffix or "", None)
    if cap is None:
        return [LAPTOP_CHASSIS_DEFAULT] + [k for k in LAPTOP_CHASSIS if k != LAPTOP_CHASSIS_DEFAULT]
    rest = [k for k in LAPTOP_CHASSIS if k != cap]
    # 允许比推荐档高一档（玩家自己改了散热），但不给到最高档
    order = list(LAPTOP_CHASSIS)
    idx = order.index(cap)
    allowed = order[max(0, idx - 1): idx + 1]
    return allowed


@dataclass
class CoolingConfig:
    """散热配置。桌面：只有 radiator；移动端：chassis + material。"""

    platform: str = "desktop"                 # desktop / mobile
    radiator: str = DESKTOP_COOLING_DEFAULT   # 桌面散热器
    chassis: str = LAPTOP_CHASSIS_DEFAULT     # 笔记本模具
    material: str = THERMAL_MATERIAL_DEFAULT  # 导热耗材
    override: Optional[float] = None          # 用户直接指定的总散热系数
    auto_detected: bool = False               # 是否由型号名自动判定为移动端

    # ------------------------------------------------------------------
    def radiator_coef(self) -> float:
        return float(DESKTOP_COOLING.get(self.radiator, 1.0))

    def chassis_coef(self) -> float:
        return float(LAPTOP_CHASSIS.get(self.chassis, 1.0))

    def material_coef(self) -> float:
        return float(THERMAL_MATERIAL.get(self.material, 1.0))

    def clamp(self, value: float) -> float:
        lo, hi = _COOLING_SANITY_RANGE
        return min(hi, max(lo, value))

    def factor(self) -> float:
        """最终散热系数（默认桌面 = 1.0）。"""
        if self.override is not None:
            return self.clamp(float(self.override))
        if self.platform == "mobile":
            return self.clamp(self.chassis_coef() * self.material_coef())
        return self.clamp(self.radiator_coef())

    # ------------------------------------------------------------------
    def describe(self) -> str:
        if self.override is not None:
            return f"用户指定总散热系数 {self.factor():.3f}"
        if self.platform == "mobile":
            return (f"移动端：模具「{self.chassis}」{self.chassis_coef():.3f} × "
                    f"导热「{self.material}」{self.material_coef():.3f} = {self.factor():.3f}")
        return f"桌面端：散热器「{self.radiator}」= {self.factor():.3f}"

    def breakdown(self) -> Dict[str, str]:
        out: Dict[str, str] = {"平台": "移动端（笔记本）" if self.platform == "mobile" else "桌面端"}
        if self.override is not None:
            out["用户指定系数"] = f"{self.factor():.3f}"
            return out
        if self.platform == "mobile":
            out["笔记本模具"] = f"{self.chassis_coef():.3f}"
            out["导热耗材"] = f"{self.material_coef():.3f}"
        else:
            out["桌面散热器"] = f"{self.radiator_coef():.3f}"
        out["散热系数"] = f"{self.factor():.3f}"
        return out

    def copy(self, **kw) -> "CoolingConfig":
        data = dict(platform=self.platform, radiator=self.radiator, chassis=self.chassis,
                    material=self.material, override=self.override,
                    auto_detected=self.auto_detected)
        data.update(kw)
        return CoolingConfig(**data)


def desktop_default() -> CoolingConfig:
    return CoolingConfig(platform="desktop", radiator=DESKTOP_COOLING_DEFAULT)


def mobile_default(chassis: Optional[str] = None, auto: bool = True) -> CoolingConfig:
    return CoolingConfig(
        platform="mobile",
        chassis=chassis or LAPTOP_CHASSIS_DEFAULT,
        material=THERMAL_MATERIAL_DEFAULT,
        auto_detected=auto,
    )
