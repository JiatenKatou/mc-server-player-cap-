"""输入解析层：把用户随手写的字符串变成结构化数值。

用户可能输入："16G" / "16 GB" / "16384MB" / "8"
              "100Mbps" / "100M" / "千兆" / "家宽 50M 上行"
              "中等" / "好" / "光纤"
              "5800X3D" / "i5-12400 6核"
"""
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 <请填写你的名字或昵称>
#
# 本文件是「Minecraft 服务器人数上限计算器」的一部分，按 GPL-3.0 授权。
# 完整声明见 mc_player_calc/__init__.py 与项目根目录的 COPYRIGHT。
# 本程序不提供任何担保；输出为模型估算值，不是实测保证。


from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Optional, Tuple

from .cooling import (DESKTOP_COOLING, DESKTOP_COOLING_DEFAULT, LAPTOP_CHASSIS,
                      LAPTOP_CHASSIS_DEFAULT, THERMAL_MATERIAL, THERMAL_MATERIAL_DEFAULT,
                      CoolingConfig, chassis_options, desktop_default, mobile_default, suffix_of)
from .cpu_data import CpuSpec, is_mobile_name, lookup, resolve_platform, unknown_spec

# ----------------------------------------------------------------------
# 网络状况预设
# ----------------------------------------------------------------------
NETWORK_PRESETS = {
    "极差 (手机热点 / 高丢包)": {"bandwidth_mbps": 10.0, "latency_ms": 150.0, "loss_pct": 3.0},
    "较差 (家用 ADSL 上行)": {"bandwidth_mbps": 20.0, "latency_ms": 90.0, "loss_pct": 1.0},
    "一般 (100M 家宽 / 普通 VPS)": {"bandwidth_mbps": 50.0, "latency_ms": 55.0, "loss_pct": 0.3},
    "良好 (千兆家宽 / 优质机房)": {"bandwidth_mbps": 200.0, "latency_ms": 30.0, "loss_pct": 0.1},
    "极佳 (BGP 高防专线)": {"bandwidth_mbps": 1000.0, "latency_ms": 15.0, "loss_pct": 0.0},
}

PLAYER_BEHAVIORS = ["原版", "小游戏", "插件", "红石生电", "模组", "整合包"]
"""玩法分类。与 feedback.PLAYSTYLES 是同一套，服主反馈也按这套收集。

早期版本用的是另一组名字（原版生存 / 红石 / 自动化 …），仍能识别并自动归一化。
"""
PLAYER_SIM = ["原版玩家", "少量模组交互", "大量模组交互"]
VIEW_DISTANCES = ["6", "8", "10", "12", "16", "24"]

_NUM = r"(\d+(?:\.\d+)?)"


def parse_ram_mb(text: str, default_mb: float = 0.0) -> float:
    """解析内存输入，统一返回 MiB。默认按 GB 理解裸数字。"""
    if text is None:
        return default_mb
    s = str(text).strip().lower()
    if not s:
        return default_mb
    m = re.search(_NUM + r"\s*(tb|t|gb|g|mb|m|kb|k|b)?", s)
    if not m:
        return default_mb
    value = float(m.group(1))
    unit = m.group(2) or "g"
    if unit in ("tb", "t"):
        return value * 1024 * 1024
    if unit in ("gb", "g", "b", ""):
        # 裸数字与 "b" 都按 GB 处理（用户说"内存 8"通常就是 8G）
        return value * 1024
    if unit in ("mb", "m"):
        return value
    if unit in ("kb", "k"):
        return value / 1024
    return default_mb


def parse_bandwidth_mbps(text: str, default_mbps: float = 0.0) -> float:
    """解析带宽输入，统一返回 Mbps。裸数字按 Mbps 处理。"""
    if text is None:
        return default_mbps
    s = str(text).strip().lower()
    if not s:
        return default_mbps
    if "千兆" in s or "gigabit" in s:
        return 1000.0
    if "百兆" in s:
        return 100.0
    m = re.search(_NUM + r"\s*(gbps|gbit|g|mbps|mbit|m|kbps|k)?", s)
    if not m:
        return default_mbps
    value = float(m.group(1))
    unit = m.group(2) or "m"
    if unit in ("gbps", "gbit", "g"):
        return value * 1000.0
    if unit in ("mbps", "mbit", "m", ""):
        return value
    if unit in ("kbps", "k"):
        return value / 1000.0
    return default_mbps


def parse_number(text: str, default: float = 0.0) -> float:
    if text is None:
        return default
    m = re.search(_NUM, str(text))
    return float(m.group(1)) if m else default


def parse_cores(text: str, default: int = 0) -> int:
    """从 CPU 输入里抓"6核 / 8C / 16 threads"这类信息。"""
    if not text:
        return default
    s = str(text).lower()
    m = re.search(r"(\d+)\s*(?:核|cores?|c\b)", s)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*(?:线程|threads?|t\b)", s)
    if m:
        return max(1, int(m.group(1)) // 2)
    return default


def resolve_cpu(text: str) -> CpuSpec:
    """CPU 输入 → CpuSpec。优先查库（含用户自定义），查不到再用核心数兜底。"""
    raw = (text or "").strip()
    spec = lookup(raw)
    cores = parse_cores(raw)
    if spec is not None:
        if cores and cores != spec.cores:
            return replace(spec, name=f"{spec.name}（按 {cores} 核估算）", cores=cores)
        return spec
    if cores:
        plat = "mobile" if is_mobile_name(raw) else "desktop"
        return CpuSpec(f"{raw or '未知型号'}（按 {cores} 核估算）", unknown_spec().score, cores,
                       "未收录型号，单核性能按中端保守估算", plat)
    return unknown_spec(raw)


# ----------------------------------------------------------------------
# 散热系数解析
# ----------------------------------------------------------------------
def resolve_cooling(cpu: CpuSpec, platform_raw: str = "", chassis: str = "",
                    material: str = "", radiator: str = "",
                    override: str = "") -> Tuple[CoolingConfig, list]:
    """根据 CPU 平台与用户选择，给出最终散热配置。

    规则：
    1. 桌面 CPU → 默认散热系数 1.0（可改散热器档位，仍为 1.0 附近）
    2. 移动端 CPU → 由「模具系数 × 导热耗材系数」决定，默认取该后缀的推荐模具
    3. 若模具与 CPU 后缀物理不符（如 U 低压选厚砖本），回退到推荐档并给出提示
    4. 用户显式填写"自定义系数"时，直接以它作为总散热系数
    """
    warnings: list = []
    plat = resolve_platform(cpu)
    want = (platform_raw or "").strip().lower()

    if want.startswith("移动") or want == "mobile":
        if plat != "mobile":
            warnings.append(f"「{cpu.name}」按命名规则属于桌面型号，已按桌面散热处理")
    elif want.startswith("桌面") or want == "desktop":
        if plat == "mobile":
            warnings.append(f"「{cpu.name}」按命名规则属于移动端型号，已按笔记本散热处理")

    # 自定义总系数优先
    ov: Optional[float] = None
    if str(override).strip():
        try:
            val = float(str(override).strip())
            if val <= 0:
                warnings.append("自定义散热系数必须大于 0，已忽略")
            else:
                ov = val
        except ValueError:
            warnings.append(f"自定义散热系数「{override}」不是数字，已忽略")

    if plat == "mobile":
        suf = suffix_of(cpu.name)
        allowed = chassis_options(suf)
        chosen = chassis if chassis in LAPTOP_CHASSIS else ""
        if not chosen:
            chosen = allowed[0] if allowed else LAPTOP_CHASSIS_DEFAULT
        elif chosen not in allowed:
            # 用户显式选择优先（模具系数本来就是可自定义的），只做提示不拦截
            warnings.append(f"{suf or '该后缀'} 平台通常是「{allowed[0]}」，"
                            f"你选了「{chosen}」（系数以你的选择为准）")
        mat = material if material in THERMAL_MATERIAL else THERMAL_MATERIAL_DEFAULT
        cfg = mobile_default(chosen, auto=True)
        cfg.material = mat
        cfg.override = ov
        return cfg, warnings

    rad = radiator if radiator in DESKTOP_COOLING else DESKTOP_COOLING_DEFAULT
    cfg = desktop_default()
    cfg.radiator = rad
    cfg.override = ov
    return cfg, warnings


def match_preset(text: str, presets) -> Optional[str]:
    """把用户写的网络描述匹配到预设名（支持"良好"/"一般"/"光纤"这类模糊词）。"""
    if not text:
        return None
    s = str(text).strip()
    if s in presets:
        return s
    for name in presets:
        if s and (s in name or name.split(" ")[0] in s):
            return name
    keyword_map = {
        "极差": "极差", "差": "较差", "一般": "一般", "普通": "一般",
        "良好": "良好", "好": "良好", "光纤": "良好", "千兆": "良好",
        "极佳": "极佳", "专线": "极佳", "机房": "极佳", "BGP": "极佳",
    }
    for key, target in keyword_map.items():
        if key in s:
            for name in presets:
                if name.startswith(target):
                    return name
    return None


@dataclass
class RawInput:
    """GUI / CLI 的原始输入集合。"""

    mod_count: str = "0"
    cpu: str = "Ryzen 5 5600"
    ram: str = "8G"
    network: str = "一般 (100M 家宽 / 普通 VPS)"
    bandwidth: str = ""
    download: str = ""
    latency: str = ""
    loss: str = ""
    behavior: str = "原版"
    player_sim: str = "原版玩家"
    view_distance: str = "10"
    modpack: str = ""           # 整合包名称（玩法=整合包时决定用哪个包的系数）
    # 散热：platform 留空 = 按 CPU 型号自动识别；也可强制 desktop / mobile
    platform: str = ""
    chassis: str = ""           # 笔记本模具（移动端）
    material: str = ""          # 导热耗材（移动端）
    radiator: str = ""          # 桌面散热器
    cooling_override: str = ""  # 用户直接指定的总散热系数


def normalize_behavior(text: str) -> Tuple[str, str]:
    """把玩法名归一化到标准分类；返回 (标准名, 警告或空字符串)。

    兼容早期版本的玩法名（"原版生存" / "红石 / 自动化" / "机械动力 / 科技" /
    "多维度挂机 / 农场"），以及服主反馈里可能写的自由文本（如 "整合包服"）。
    """
    from .feedback import normalize_playstyle

    raw = str(text or "").strip()
    if raw in PLAYER_BEHAVIORS:
        return raw, ""
    matched = normalize_playstyle(raw)
    if matched:
        if matched != raw:
            return matched, f"玩法「{raw}」已按标准分类「{matched}」处理"
        return matched, ""
    return PLAYER_BEHAVIORS[0], f"玩法「{raw}」无法识别，按「{PLAYER_BEHAVIORS[0]}」处理"


def parse_raw(raw: RawInput) -> Tuple[dict, list]:
    """解析所有输入，返回 (结构化字段 dict, 警告列表)。"""
    warnings: list = []

    mod_count = int(max(0.0, parse_number(raw.mod_count, 0)))
    if not str(raw.mod_count).strip():
        warnings.append("未填写模组数量，按 0 处理")

    cpu_spec = resolve_cpu(raw.cpu)
    if "未收录" in cpu_spec.name or "估算" in cpu_spec.name:
        warnings.append(f"CPU「{raw.cpu}」不在型号库中，已按单核 {cpu_spec.score:.0f} / {cpu_spec.cores} 核估算")

    cooling_cfg, cooling_warnings = resolve_cooling(
        cpu_spec,
        platform_raw=getattr(raw, "platform", ""),
        chassis=getattr(raw, "chassis", ""),
        material=getattr(raw, "material", ""),
        radiator=getattr(raw, "radiator", ""),
        override=getattr(raw, "cooling_override", ""),
    )
    warnings += cooling_warnings
    if cooling_cfg.platform == "mobile" and not cooling_cfg.auto_detected:
        warnings.append("已按移动端 CPU 处理，散热系数取自笔记本模具与导热耗材")

    ram_mb = parse_ram_mb(raw.ram, 0.0)
    if ram_mb <= 0:
        warnings.append("内存输入无法识别，按 8GB 处理")
        ram_mb = 8192.0

    preset_name = match_preset(raw.network, NETWORK_PRESETS)
    preset = NETWORK_PRESETS.get(preset_name or "", NETWORK_PRESETS["一般 (100M 家宽 / 普通 VPS)"])
    if preset_name is None and raw.network.strip():
        warnings.append(f"网络状况「{raw.network}」未匹配到预设，按「一般」处理")

    # 上行：不填就用档位默认；填了以实测值为准
    bw_text = str(raw.bandwidth).strip()
    has_digit = bool(re.search(r"\d", bw_text))
    if bw_text and not has_digit:
        warnings.append(f"上行带宽「{raw.bandwidth}」看不出数字，已用档位默认 "
                        f"{preset['bandwidth_mbps']:.0f} Mbps")
        bandwidth = preset["bandwidth_mbps"]
    else:
        bandwidth = parse_bandwidth_mbps(bw_text, preset["bandwidth_mbps"])

    # 下行：不参与人数计算，仅作记录展示；看不出数字就忽略
    dl_text = str(getattr(raw, "download", "")).strip()
    if dl_text and not re.search(r"\d", dl_text):
        warnings.append(f"下行带宽「{raw.download}」看不出数字，已忽略（它本来也不参与计算）")
        dl_text = ""
    download_mbps = parse_bandwidth_mbps(dl_text, 0.0) if dl_text else 0.0

    latency = parse_number(raw.latency, preset["latency_ms"])
    loss = parse_number(raw.loss, preset["loss_pct"])

    vd = str(raw.view_distance).strip() or "10"
    if vd not in VIEW_DISTANCES:
        vd = "10"
        warnings.append("视距不在档位内，按 10 区块处理")

    behavior, behavior_warn = normalize_behavior(raw.behavior)
    if behavior_warn:
        warnings.append(behavior_warn)
    if raw.player_sim not in PLAYER_SIM:
        warnings.append(f"玩家负载「{raw.player_sim}」未知，按原版玩家处理")

    fields = {
        "mod_count": mod_count,
        "cpu": cpu_spec,
        "cooling": cooling_cfg,
        "ram_mb": ram_mb,
        "network_preset": preset_name or "一般 (100M 家宽 / 普通 VPS)",
        "bandwidth_mbps": bandwidth,
        "download_mbps": download_mbps,
        "download_input": dl_text,
        "latency_ms": latency,
        "loss_pct": loss,
        "behavior": behavior,
        "pack_name": str(getattr(raw, "modpack", "") or "").strip(),
        "player_sim": raw.player_sim if raw.player_sim in PLAYER_SIM else "原版玩家",
        "view_distance": vd,
    }
    return fields, warnings
