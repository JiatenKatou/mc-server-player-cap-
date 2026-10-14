"""集中存放全部可调参数（占位默认值，等待后续真实数据接入）。

为什么单独一层？
    框架先跑通，公式和系数全部外置。以后你给出真实测试数据（例如
    "i5-12400 + 8G + 4 模组，实测 12 人 TPS 掉到 17"），只需要改本文件里的数字，
    计算逻辑 (engine.py) 不用动。

单位约定：
    所有 *_mb 参数单位都是 MiB，所有带宽单位都是 Mbps。
"""
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 <请填写你的名字或昵称>
#
# 本文件是「Minecraft 服务器人数上限计算器」的一部分，按 GPL-3.0 授权。
# 完整声明见 mc_player_calc/__init__.py 与项目根目录的 COPYRIGHT。
# 本程序不提供任何担保；输出为模型估算值，不是实测保证。


from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict


@dataclass
class Params:
    """木桶四个维度的全部系数。"""

    # ------------------------------------------------------------------
    # 1. 内存维度
    # ------------------------------------------------------------------
    ram_reserve_mb: float = 1024.0
    """留给 JVM 堆外/GC/metaspace 与操作系统的内存，不参与分给玩家。"""

    ram_per_player_base_mb: float = 55.0
    """原版每个在线玩家约占用的堆内存（约 3x3 ~ 5x5 常驻区块）。
    口径：2GB 堆 ≈ 15 人原版，4GB ≈ 35 人（含世界/区块常驻开销）。"""

    ram_per_mod_mb: float = 12.0
    """每个服务端模组，每玩家平均额外占用的堆内存。"""

    ram_mod_sqrt_factor: float = 3.0
    """模组数量对内存的影响按 sqrt(mods × 本系数) 增长，避免大整合包被严重高估。"""

    ram_mb_per_player_per_view_chunk: float = 0.12
    """视距每比基准视距多 1 个区块，每玩家额外内存。"""

    ram_baseline_view_chunks: float = 10.0
    """内存基准视距（区块，半径）。"""

    ram_safety_factor: float = 0.85
    """内存安全系数：永远不要把堆吃满，否则 GC 抖动会先于 OOM 杀死 TPS。"""

    # ------------------------------------------------------------------
    # 2. CPU 维度
    # ------------------------------------------------------------------
    cpu_core_scale_alpha: float = 0.75
    """多核利用率指数。1.0 = 线性扩展（理想），越小说明主线程瓶颈越重。"""

    cpu_tps_target: float = 20.0
    """目标 TPS。低于这个值视为"人数上限已到"。"""

    cpu_base_headroom: float = 200.0
    """CPU 维度的兜底上限（人）。防止极端参数下出现无意义的巨大数字。"""

    cpu_reference_score: float = 108.0
    """基准单核分数（默认 = i5-12400）。"""

    cpu_reference_cores: int = 6
    """基准物理核心数（默认 = i5-12400）。"""

    cpu_reference_players: float = 45.0
    """基准配置在"TPS ≥ 19.5"口径下可承载的人数。

    ★ 这是全套系数里唯一**没有公开实测支撑**的数字，属于保守估值：
      中等负载（原版、视距 10、无预防性区块加载）下 i5-12400 量级的量级判断。
      口径定义：在线人数增长到 TPS 首次跌破 19.5 时的人数。
      校准方式：`python -m mc_player_calc.calibrate anchors.json`（见 calibrate.py）。
    """

    cpu_capacity_exponent: float = 0.6
    """CPU 容量的缩放指数。越大 = 越吃硬件；越小 = 越快触顶。"""

    # ---- CPU-Z 标尺换算（用户界面用 CPU-Z 单核分，引擎内部用指数）----
    cpuz_reference_score: float = 662.0
    """基准 CPU-Z 单核分：Ryzen 5 5600 的公开实测值。"""

    cpuz_reference_index: float = 100.0
    """上面的 CPU-Z 分对应的内部指数（= cpu_reference_score 的量级）。"""

    cpuz_exponent: float = 2.0
    """换算指数：内部指数 ∝ (CPU-Z 分)^cpuz_exponent。

    CPU-Z 的分数刻度天然被"压缩"过（最强与最弱只差 2 倍左右），
    而内部指数跨度约 3.6 倍，用 2 次幂正好对得上。
    自己用 CPU-Z 实测两个型号后，可以用这两点反推更合适的值。
    """

    cpu_tps_drop_per_overload: float = 0.85
    """每超出安全负载 1 倍所损失的 TPS（用于生成提示文本的估算）。"""

    cpu_thread_exponent: float = 1.35
    """玩家负载的增长指数：负载 ≈ 玩家数 ^ exponent。
    略大于 1 是因为玩家之间的区块加载/实体碰撞存在超线性争用。"""

    # ------------------------------------------------------------------
    # 3. 网络维度
    # ------------------------------------------------------------------
    net_baseline_view_chunks: float = 10.0
    """网络基准视距（区块，半径），与内存基准可分别设定。"""

    net_packet_mb_per_player_per_min_base: float = 2.5
    """每玩家每分钟上下行数据量（MiB，含区块与实体同步）。

    口径参考公开实测：原版活跃玩家约 40 KB/s ≈ 0.32 Mbps（≈ 2.3 MiB/min），
    50 人原版服（约 60% 活跃）实测吞吐 ≈ 10~16 Mbps，与 20M 带宽建议相符。
    """

    net_packet_mb_per_player_per_min_per_mod: float = 0.25
    """每个模组为每玩家每分钟额外增加的数据量（按 sqrt 缩放）。
    口径参考：整合包/科技模组服活跃玩家 60~120 KB/s。"""

    net_mod_sqrt_factor: float = 3.0
    """网络侧模组影响同样按 sqrt(mods × 本系数) 增长。"""

    net_mb_per_player_per_min_per_view_chunk: float = 0.10
    """视距每比基准多 1 区块，每玩家每分钟额外数据量（视距是带宽最大杠杆）。"""

    net_overhead_ratio: float = 0.025
    """TCP/TLS/协议头/重传等额外开销占净荷的比例。"""

    net_duty_cycle: float = 0.6
    """活跃率：在线玩家中正在跑图/交互（产生峰值流量）的比例。

    每玩家流量按"活跃时"标定，这里把平均值折算成峰值口径，
    否则会把带宽算得过于乐观（公开实测：20M 上行可支撑约 50 人原版服）。
    """

    net_safety_factor: float = 0.70
    """带宽安全系数：留出 30% 余量应对突发（大范围区块加载、集体传送）。"""

    net_latency_penalty_ms: float = 120.0
    """超过该延迟开始惩罚可承载人数。"""

    net_latency_penalty_strength: float = 0.5
    """延迟惩罚强度：延迟翻倍最多砍掉该比例的人数。"""

    net_loss_penalty_start_pct: float = 0.5
    """丢包率超过该百分比开始惩罚（单位 %）。"""

    net_loss_penalty_strength: float = 4.0
    """每 1% 超额丢包扣掉的比例。"""

    # ------------------------------------------------------------------
    # 4. 模组 / 玩法负载维度
    # ------------------------------------------------------------------
    mod_ceiling_vanilla: float = 200.0
    """原版（0 模组）下的"内容复杂度"人数上限。

    这一维度只用来给重整合包设天花板，所以在轻量服上应当高于硬件上限，
    避免它抢在 CPU / 内存 / 网络之前成为瓶颈。
    """

    mod_players_per_unit: float = 60.0
    """每 1 单位模组负载可承载的玩家数（越小 = 模组惩罚越重）。"""

    mod_load_reference: float = 100.0
    """基准模组数量：模组数达到该值时，负载记为 1.0 单位。"""

    behavior_multiplier: Dict[str, float] = field(
        default_factory=lambda: {
            # —— 规范分类（与 feedback.PLAYSTYLES 同一套，服主反馈也按这套收集）——
            "原版": 1.00,
            "小游戏": 1.05,
            "插件": 1.15,
            "红石生电": 1.45,
            "模组": 1.35,
            "整合包": 1.60,
            # —— 兼容早期版本的玩法名，仍然可用 ——
            "原版生存": 1.00,
            "红石 / 自动化": 1.35,
            "机械动力 / 科技": 1.55,
            "多维度挂机 / 农场": 1.30,
        }
    )
    """玩家行为对负载的放大倍数。

    规范分类见 mc_player_calc/feedback.py 的 PLAYSTYLES；服主反馈汇总出的系数由
    feedback.apply_suggestions 写入 behavior_multiplier.json，引擎计算时会自动叠加。
    """

    load_behavior_overrides: bool = True
    """是否加载 behavior_multiplier.json（由服主反馈汇总生成）。"""

    view_distance_multiplier_table: Dict[str, float] = field(
        default_factory=lambda: {
            "6": 0.85,
            "8": 0.92,
            "10": 1.00,
            "12": 1.10,
            "16": 1.30,
            "24": 1.60,
        }
    )
    """视距档位 → 负载倍数。"""

    player_sim_overhead: Dict[str, float] = field(
        default_factory=lambda: {
            "原版玩家": 1.00,
            "少量模组交互": 1.15,
            "大量模组交互": 1.35,
        }
    )
    """每玩家模拟开销倍数（用于 CPU 维度）。"""

    # ------------------------------------------------------------------
    # 兜底
    # ------------------------------------------------------------------
    min_players: int = 1
    """任何情况下至少返回 1 人（只要服务器能启动）。"""

    def to_dict(self) -> dict:
        return asdict(self)

    def apply_cpuz_calibration(self) -> None:
        """把 CPU-Z 标定参数推给 cpu_data 模块（保证只有这一处数据源）。"""
        from .cpu_data import register_cpuz_calibration
        register_cpuz_calibration(self.cpuz_reference_score, self.cpuz_reference_index,
                                  self.cpuz_exponent)

    @classmethod
    def from_dict(cls, data: dict) -> "Params":
        """从 dict 覆盖默认值；未知键直接忽略，便于以后迁移。"""
        known = {f for f in cls.__dataclass_fields__}
        clean = {k: v for k, v in (data or {}).items() if k in known}
        return cls(**clean)


DEFAULT_PARAMS = Params()
"""框架默认参数。后续真实数据到手后，在这里替换即可。"""

# 让 CPU-Z 换算与 config 里的标定保持同步
DEFAULT_PARAMS.apply_cpuz_calibration()
