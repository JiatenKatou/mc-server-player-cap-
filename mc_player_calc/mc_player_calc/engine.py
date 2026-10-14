"""木桶效应计算引擎。

核心思想（Liebig's law of the minimum）：
    最终人数上限 = min( CPU可承载, 内存可承载, 网络可承载, 模组负载可承载 )

每个维度先独立算出一个"可承载人数"（ceiling），互相之间不做加权平均，
只取最小值；与最小值相等的维度全部标记为"瓶颈"，接近的标记为"接近瓶颈"。

所有公式系数来自 config.Params，本文件只负责算法，不写死任何数字。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .config import DEFAULT_PARAMS, Params
from .cooling import CoolingConfig, desktop_default
from .cpu_data import CpuSpec, cpu_index_to_cpuz


# ----------------------------------------------------------------------
# 数据结构
# ----------------------------------------------------------------------
@dataclass
class CalcInput:
    """引擎的结构化输入。"""

    mod_count: int = 0
    cpu: CpuSpec = field(default_factory=lambda: CpuSpec("未知型号", 85.0, 4))
    cooling: CoolingConfig = field(default_factory=desktop_default)
    ram_mb: float = 8192.0
    bandwidth_mbps: float = 50.0
    download_mbps: float = 0.0
    """下行带宽：仅作记录展示，不参与人数计算（服务器瓶颈在上行）。"""
    download_input: str = ""
    latency_ms: float = 55.0
    loss_pct: float = 0.3
    behavior: str = "原版"
    player_sim: str = "原版玩家"
    pack_name: str = ""          # 整合包名称（决定用哪个包的专属系数）
    view_distance: str = "10"
    network_preset: str = "一般"

    @property
    def view_chunks(self) -> float:
        try:
            return float(self.view_distance)
        except (TypeError, ValueError):
            return 10.0


@dataclass
class Factor:
    """一个资源维度的计算结果。"""

    key: str                 # cpu / ram / network / mods
    label: str               # 中文名
    ceiling: float           # 该维度可承载人数
    detail: str              # 一行结论
    values: Dict[str, str] = field(default_factory=dict)   # 明细展示
    formulas: List[str] = field(default_factory=list)      # 公式推导
    is_bottleneck: bool = False
    near_bottleneck: bool = False
    load_at_final: float = 0.0      # 最终人数下该维度占用率 0~1+


@dataclass
class CalcResult:
    final_players: int
    binding_factors: List[str] = field(default_factory=list)     # 瓶颈维度 key
    factors: List[Factor] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    params: Optional[Params] = None
    inputs: Optional[CalcInput] = None
    tps_estimate: float = 20.0

    def factor(self, key: str) -> Optional[Factor]:
        for f in self.factors:
            if f.key == key:
                return f
        return None


# ----------------------------------------------------------------------
# 工具
# ----------------------------------------------------------------------
def _round(x: float, nd: int = 1) -> float:
    return float(f"{x:.{nd}f}")


def _view_multiplier(params: Params, chunks: float) -> float:
    """视距倍数：优先用档位表，表外按基准线性外推。"""
    table = params.view_distance_multiplier_table
    key = str(int(chunks))
    if key in table:
        return float(table[key])
    # 线性外推：以最接近的档位为锚点
    anchors = sorted((float(k), v) for k, v in table.items())
    base_chunks, base_mult = anchors[len(anchors) // 2]
    return float(base_mult + (chunks - base_chunks) * 0.05)


# ----------------------------------------------------------------------
# 四个维度
# ----------------------------------------------------------------------
def _behavior_coef(p: Params, behavior: str, pack_name: str = "") -> float:
    """玩法倍数。

    整合包是**一个包一套系数**（见 modpack.py）：
      该包的校准值 > 该包的人工预填值 > 按类型/进度折算 > 玩法分类默认值
    其余玩法走 behavior_multiplier（可被服主反馈汇总出的 behavior_multiplier.json 覆盖）。
    """
    if behavior == "整合包":
        try:
            from .modpack import resolve_pack_factor
            factor, _why = resolve_pack_factor(pack_name)
            if factor > 0:
                return float(factor)
        except Exception:      # 档案文件损坏/权限问题都不该影响计算
            pass

    base = p.behavior_multiplier.get(behavior, 1.0)
    if not p.load_behavior_overrides:
        return base
    try:
        from .feedback import load_behavior_overrides
        overrides = load_behavior_overrides()
    except Exception:      # 覆盖文件损坏/权限问题都不该影响计算
        return base
    try:
        return float(overrides.get(behavior, base))
    except (TypeError, ValueError):
        return base


def _cpu_factor(inp: CalcInput, p: Params) -> Factor:
    """CPU 维度：以"基准配置 → 基准人数"为锚，按幂律缩放。

    为什么不用线性公式：单核分数 × 核心数的线性组合会让顶级 CPU 算出 400+ 人，
    但真实瓶颈（主线程 tick、区块加载、GC 停顿）会先到。幂律缩放让收益递减，
    并且不需要人为的兜底上限把强弱 CPU 压成同一个数字。

    散热系数（详见 cooling.py）：
        有效单核得分 = 原始单核得分 × 散热系数
        桌面默认 1.0；笔记本 = 模具系数 × 导热耗材系数
    """
    raw_score = inp.cpu.score
    cooling = inp.cooling
    cooling_coef = cooling.factor()
    score = raw_score * cooling_coef
    cores = max(1, inp.cpu.cores)
    sim = p.player_sim_overhead.get(inp.player_sim, 1.0)
    behavior = _behavior_coef(p, inp.behavior, inp.pack_name)

    # 保证 CPU-Z ↔ 内部指数的换算与本次参数一致
    p.apply_cpuz_calibration()
    raw_cpuz = inp.cpu.cpuz_score
    eff_cpuz = round(cpu_index_to_cpuz(score)) if score > 0 else 0

    ref_score = max(1.0, p.cpu_reference_score)
    ref_cores = max(1, p.cpu_reference_cores)
    avg_core_score = score * (cores ** p.cpu_core_scale_alpha)
    ref_avg_core_score = ref_score * (ref_cores ** p.cpu_core_scale_alpha)
    raw_ceiling = p.cpu_reference_players * (avg_core_score / ref_avg_core_score) \
        ** p.cpu_capacity_exponent / (sim * behavior)
    ceiling = min(raw_ceiling, p.cpu_base_headroom)

    formulas = [
        f"CPU-Z 单核 {raw_cpuz} 分 → 内部指数 {raw_score:.1f}"
        f"（标定：{p.cpuz_reference_score:.0f} 分 = 指数 {p.cpuz_reference_index:.0f}，"
        f"{p.cpuz_exponent:g} 次幂）",
        f"有效单核得分 = 原始指数 {raw_score:.1f} × 散热系数 {cooling_coef:.3f} = {score:.1f}"
        f"（≈ CPU-Z {eff_cpuz} 分）",
        f"散热系数依据：{cooling.describe()}",
        f"单核加权 = 有效单核得分 × 核心数^{p.cpu_core_scale_alpha} = {score:.1f} × "
        f"{cores}^{p.cpu_core_scale_alpha} = {_round(avg_core_score)}",
        f"基准单核加权 = {ref_score:.0f} × {ref_cores}^{p.cpu_core_scale_alpha} = "
        f"{_round(ref_avg_core_score)}（基准 {p.cpu_reference_players:.0f} 人）",
        f"缩放系数 = ({_round(avg_core_score)} ÷ {_round(ref_avg_core_score)})"
        f"^{p.cpu_capacity_exponent} = "
        f"{_round((avg_core_score / ref_avg_core_score) ** p.cpu_capacity_exponent, 3)}",
        f"扣除玩法与模拟开销后 = {p.cpu_reference_players:.0f} × "
        f"{_round((avg_core_score / ref_avg_core_score) ** p.cpu_capacity_exponent, 3)} ÷ "
        f"({sim:.2f} × {behavior:.2f}) = {_round(raw_ceiling)} 人",
    ]
    if raw_ceiling > p.cpu_base_headroom:
        formulas.append(f"取兜底上限 {p.cpu_base_headroom:.0f} 人（主线程调度与 GC 停顿会先成为事实瓶颈）")
        formulas.append(f"CPU 可承载 = min({_round(raw_ceiling)}, {p.cpu_base_headroom:.0f}) "
                        f"= {_round(ceiling)} 人")
    else:
        formulas.append(f"CPU 可承载 = {_round(ceiling)} 人")

    throttle_note = ""
    if cooling_coef < 0.999:
        throttle_note = f"，散热衰减 {(1 - cooling_coef) * 100:.1f}%"

    detail = f"{inp.cpu.name} CPU-Z 单核 {raw_cpuz} 分 × 散热 {cooling_coef:.3f}" \
             f"（有效 ≈ {eff_cpuz} 分）× {cores} 核{throttle_note}，" \
             f"玩法 {behavior:.2f}× 与每玩家模拟开销 {sim:.2f}×"

    values = {
        "CPU 型号": inp.cpu.name,
        "CPU-Z 单核": f"{raw_cpuz:.0f} 分",
        "单核指数（内部）": f"{raw_score:.1f}",
        "散热系数": f"{cooling_coef:.3f}",
        "有效单核": f"{score:.1f} 指数 ≈ CPU-Z {eff_cpuz} 分",
        "物理核心": f"{cores}",
        "玩法负载倍数": f"{behavior:.2f}×",
        "每玩家模拟开销": f"{sim:.2f}×",
    }
    if inp.cpu.custom:
        values["来源"] = "用户自定义型号"
    values.update({f"散热·{k}": v for k, v in cooling.breakdown().items()})

    return Factor(
        key="cpu",
        label="CPU 算力",
        ceiling=ceiling,
        detail=detail,
        values=values,
        formulas=formulas,
    )


def _ram_factor(inp: CalcInput, p: Params) -> Factor:
    usable = max(0.0, inp.ram_mb - p.ram_reserve_mb)
    mod_part = p.ram_per_mod_mb * math.sqrt(inp.mod_count * p.ram_mod_sqrt_factor)
    view_part = p.ram_mb_per_player_per_view_chunk * (inp.view_chunks - p.ram_baseline_view_chunks)
    per_player = p.ram_per_player_base_mb + mod_part + view_part
    per_player = max(4.0, per_player)          # 防止极端参数导致除零
    ceiling = usable * p.ram_safety_factor / per_player

    return Factor(
        key="ram",
        label="内存容量",
        ceiling=ceiling,
        detail=f"可用 {usable / 1024:.1f}GB ÷ 每玩家 {per_player:.0f}MB"
               f"（基础 {p.ram_per_player_base_mb:.0f} + 模组 {mod_part:.0f} + 视距 {view_part:.0f}）"
               f"× 安全系数 {p.ram_safety_factor:.2f}",
        values={
            "物理内存": f"{inp.ram_mb / 1024:.2f} GB",
            "预留内存": f"{p.ram_reserve_mb / 1024:.2f} GB",
            "每玩家内存": f"{per_player:.0f} MB",
            "其中模组部分": f"{mod_part:.0f} MB",
            "安全系数": f"{p.ram_safety_factor:.2f}",
        },
        formulas=[
            f"可用内存 = {inp.ram_mb:.0f}MB − {p.ram_reserve_mb:.0f}MB = {usable:.0f}MB",
            f"模组内存 = {p.ram_per_mod_mb:.1f} × √({inp.mod_count} × {p.ram_mod_sqrt_factor:.1f}) "
            f"= {mod_part:.1f}MB",
            f"每玩家内存 = {p.ram_per_player_base_mb:.0f}（基础）+ {mod_part:.1f}（模组）"
            f" + {view_part:.1f}（视距）= {per_player:.1f}MB",
            f"内存可承载 = {usable:.0f} × {p.ram_safety_factor:.2f} ÷ {per_player:.1f} "
            f"= {_round(ceiling)} 人",
        ],
    )


def _network_factor(inp: CalcInput, p: Params) -> Factor:
    mod_part = p.net_packet_mb_per_player_per_min_per_mod * math.sqrt(
        inp.mod_count * p.net_mod_sqrt_factor)
    view_part = p.net_mb_per_player_per_min_per_view_chunk * (
        inp.view_chunks - p.net_baseline_view_chunks)
    rate = p.net_packet_mb_per_player_per_min_base + mod_part + view_part

    # 延迟惩罚：延迟超过阈值后每翻倍按强度打折
    latency_factor = 1.0
    if inp.latency_ms > p.net_latency_penalty_ms > 0:
        latency_factor = 1.0 / (
            1.0 + p.net_latency_penalty_strength * (inp.latency_ms / p.net_latency_penalty_ms - 1.0)
        )

    # 丢包惩罚：超过起始丢包率线性打折
    loss_factor = 1.0
    if inp.loss_pct > p.net_loss_penalty_start_pct:
        loss_factor = 1.0 / (
            1.0 + p.net_loss_penalty_strength * (inp.loss_pct - p.net_loss_penalty_start_pct)
        )

    quality = latency_factor * loss_factor
    rate = max(0.05, rate)
    duty = min(1.0, max(0.05, p.net_duty_cycle))
    # 单位换算：(Mbps × 60 秒) ÷ 每玩家峰值 MiB/min × 安全系数 × 质量系数
    # 每玩家流量按"活跃时"标定，除以活跃率折算为在线玩家平均占用
    peak_rate = rate / duty
    ceiling = inp.bandwidth_mbps * 60.0 / peak_rate * (1.0 - p.net_overhead_ratio) \
        * p.net_safety_factor * quality

    return Factor(
        key="network",
        label="网络带宽",
        ceiling=ceiling,
        detail=f"上行 {inp.bandwidth_mbps:.0f}Mbps，每玩家 {peak_rate:.2f} MiB/min"
               f"（活跃率 {duty:.0%}），延迟 {inp.latency_ms:.0f}ms 质量系数 {latency_factor:.2f}，"
               f"丢包 {inp.loss_pct:.2f}% 系数 {loss_factor:.2f}",
        values={
            "上行带宽": f"{inp.bandwidth_mbps:.0f} Mbps",
            "网络档位": inp.network_preset,
            "每玩家流量": f"{peak_rate:.2f} MiB/min",
            "活跃率": f"{duty:.0%}",
            "延迟": f"{inp.latency_ms:.0f} ms",
            "丢包率": f"{inp.loss_pct:.2f} %",
            "安全系数": f"{p.net_safety_factor:.2f}",
        },        formulas=[
            f"模组流量 = {p.net_packet_mb_per_player_per_min_per_mod:.2f} × "
            f"√({inp.mod_count} × {p.net_mod_sqrt_factor:.1f}) = {mod_part:.2f} MiB/min",
            f"活跃时流量 = {p.net_packet_mb_per_player_per_min_base:.2f}（基础）+ {mod_part:.2f}（模组）"
            f" + {view_part:.2f}（视距）= {rate:.2f} MiB/min",
            f"在线玩家平均占用 = {rate:.2f} ÷ 活跃率 {duty:.2f} = {peak_rate:.2f} MiB/min",
            f"质量系数 = 延迟 {latency_factor:.2f} × 丢包 {loss_factor:.2f} = {quality:.2f}",
            f"网络可承载 = {inp.bandwidth_mbps:.0f} × 60 ÷ {peak_rate:.2f} × "
            f"(1−{p.net_overhead_ratio:.3f}) × {p.net_safety_factor:.2f} × {quality:.2f} "
            f"= {_round(ceiling)} 人",
        ],
    )


def _mod_factor(inp: CalcInput, p: Params) -> Factor:
    """模组 / 玩法负载维度：与硬件规格无关的「内容复杂度天花板」。

    它表达的是：模组越多、玩法越重（红石、机械动力），
    单个玩家产生的 tick 工作量越大，即使硬件再强也会先撞到内容复杂度上限。
    因此在原版/轻量服上它的数值刻意高于硬件上限，只有重整合包才会成为瓶颈。
    """
    behavior = _behavior_coef(p, inp.behavior, inp.pack_name)
    load_units = (inp.mod_count / max(1.0, p.mod_load_reference)) * behavior
    ceiling = max(1.0, p.mod_ceiling_vanilla / (1.0 + load_units))

    if inp.mod_count > 0:
        formulas = [
            f"负载单位 = 模组数 ÷ 基准模组数 × 玩法倍数 = {inp.mod_count} ÷ "
            f"{p.mod_load_reference:.0f} × {behavior:.2f} = {load_units:.2f}",
            f"内容复杂度挡位 = 1 + 负载单位 = 1 + {load_units:.2f} = {1.0 + load_units:.2f}",
            f"模组可承载 = {p.mod_ceiling_vanilla:.0f} ÷ {1.0 + load_units:.2f} = {_round(ceiling)} 人",
        ]
    else:
        formulas = [
            "模组数量为 0 → 负载单位 = 0，内容复杂度挡位 = 1 + 0 = 1.00",
            f"模组可承载 = 原版天花板 {p.mod_ceiling_vanilla:.0f} ÷ 1.00 = {_round(ceiling)} 人",
            "该维度在轻量服上刻意高于硬件上限，只负责给重整合包设天花板",
        ]

    return Factor(
        key="mods",
        label="模组 / 玩法负载",
        ceiling=ceiling,
        detail=f"{inp.mod_count} 个服务端模组 → 负载 {load_units:.2f} 单位（玩法倍数 {behavior:.2f}×），"
               f"内容复杂度上限 {p.mod_ceiling_vanilla:.0f} ÷ (1+{load_units:.2f})",
        values={
            "服务端模组数": f"{inp.mod_count}",
            "负载单位": f"{load_units:.2f}",
            "玩法": inp.behavior,
            "玩法倍数": f"{behavior:.2f}×",
            "原版天花板": f"{p.mod_ceiling_vanilla:.0f} 人",
        },
        formulas=formulas,
    )


# ----------------------------------------------------------------------
# 主入口
# ----------------------------------------------------------------------
def calculate(inp: CalcInput, params: Optional[Params] = None) -> CalcResult:
    """执行木桶效应计算。"""
    p = params or DEFAULT_PARAMS
    warnings: List[str] = []

    if inp.mod_count > 400:
        warnings.append(f"模组数量 {inp.mod_count} 极大，估算误差会明显放大")
    if inp.ram_mb <= p.ram_reserve_mb * 1.5:
        warnings.append("内存小于预留值，实际可能连服务器都难以启动")
    if inp.bandwidth_mbps <= 0:
        warnings.append("上行带宽为 0，网络维度按最小 1 人处理")

    factors = [
        _cpu_factor(inp, p),
        _ram_factor(inp, p),
        _network_factor(inp, p),
        _mod_factor(inp, p),
    ]

    ceilings = [max(0.0, f.ceiling) for f in factors]
    raw_min = min(ceilings)
    final = int(math.floor(raw_min))
    final = max(p.min_players, final)

    # 瓶颈判定：命中最小值（含 0.5 人以内误差）为瓶颈；1.25 倍以内为接近瓶颈
    for f in factors:
        c = max(0.0, f.ceiling)
        f.is_bottleneck = c <= raw_min + 0.5
        if not f.is_bottleneck:
            f.near_bottleneck = raw_min > 0 and c <= raw_min * 1.25
        f.load_at_final = (final / c) if c > 1e-9 else float("inf")

    binding = [f.key for f in factors if f.is_bottleneck]

    # TPS 估算：以瓶颈维度在最终人数下的负载反推
    tps = p.cpu_tps_target
    cpu = next(f for f in factors if f.key == "cpu")
    if cpu.ceiling > 0:
        ratio = final / cpu.ceiling
        if ratio > 1.0:
            tps = max(1.0, p.cpu_tps_target * (1.0 - (ratio - 1.0) * p.cpu_tps_drop_per_overload))

    result = CalcResult(
        final_players=final,
        binding_factors=binding,
        factors=factors,
        warnings=warnings,
        params=p,
        inputs=inp,
        tps_estimate=tps,
    )
    result.suggestions = _suggestions(result)
    return result


def _suggestions(res: CalcResult) -> List[str]:
    """依据瓶颈生成改进建议。"""
    out: List[str] = []
    labels = {f.key: f.label for f in res.factors}
    ordered = sorted(res.factors, key=lambda f: f.ceiling)

    for f in ordered:
        if f.is_bottleneck:
            if f.key == "cpu":
                out.append("瓶颈是 CPU：优先换单核性能更强的 CPU，或降低模拟距离 / 减少高频红石与实体。")
            elif f.key == "ram":
                out.append("瓶颈是内存：加内存最直接；其次降低视距、减少模组，或调小 JVM 堆以外的占用。")
            elif f.key == "network":
                out.append("瓶颈是网络：升级上行带宽 / 换优质机房线路，或降低视距以削减区块同步量。")
            elif f.key == "mods":
                out.append("瓶颈是模组与玩法负载：减少服务端模组、关闭自动化密集型内容，或分服分流。")
        elif f.near_bottleneck:
            out.append(f"「{labels[f.key]}」已接近上限（{f.ceiling:.0f} 人），提升瓶颈后它会立刻变成新瓶颈。")

    if len(res.binding_factors) >= 3:
        out.append("多个维度同时触顶，属于「整体贫弱」配置，单点升级收益有限，建议整套换代。")
    if res.final_players >= 100:
        out.append("人数估算超过 100，估算模型误差会显著放大，建议用真实压测（如 100 个假人）校准系数。")
    return out
