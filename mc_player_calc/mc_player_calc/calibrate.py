"""用服主的真实压测数据反推 CPU 承载系数。

**为什么需要它**：`config.cpu_reference_players = 80`（"i5-12400 在中等负载下带 80 人"）
这个数字目前是我根据公开经验估的，**没有任何一条实测数据支撑**。
其余维度（内存每玩家 55MB、每玩家流量、活跃率）都有公开实测出处，唯独 CPU 这一条没有。
这个模块就是把"实测 → 系数"的换算固定下来，让后续收数据这件事可复用、可复查。

反推原理：

    人数上限 = ref_players × (单核加权 ÷ 基准单核加权)^E ÷ (模拟开销 × 玩法倍数)
    单核加权 = CPU-Z 分换算的指数 × 核心数^α

已知实测的 `(CPU型号, 内存/模组/视距配置, 瓶颈维度, TPS, 人数)`，就能反解 `ref_players`：

    ref_players = 实测人数 × (模拟开销 × 玩法倍数) × (基准单核加权 ÷ 单核加权)^E

多条数据取几何平均，并给出离散度作为置信度参考。

用法：

    python -m mc_player_calc.calibrate anchors.json          # 看看现有数据反推出的系数
    python -m mc_player_calc.calibrate anchors.json --write  # 把结果写成 params_override.json

anchors.json 格式（数组或 {"anchors": [...]}）：

    [{"cpu": "i9-14900K", "players": 24, "ram": "32G", "mods": 0,
      "view": 10, "behavior": "原版生存", "player_sim": "原版玩家",
      "tps": 18.5, "bottleneck": "cpu", "source": "某服主 2026-01 实测"}]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple

from .config import DEFAULT_PARAMS, Params
from .cooling import DESKTOP_COOLING
from .cpu_data import CpuSpec
from .engine import CalcInput, calculate
from .parser import (NETWORK_PRESETS, PLAYER_BEHAVIORS, PLAYER_SIM, RawInput, parse_raw,
                     resolve_cooling, resolve_cpu)
from .report import render

# 记录哪些维度的系数"有公开实测出处"，哪些只是估算（用于报告里的标注）
COEFFICIENT_PROVENANCE: Dict[str, str] = {
    "cpu_reference_players": "估算（无实测支撑，需用本工具校准）",
    "cpu_core_scale_alpha": "估算（多核收益，需校准）",
    "cpu_capacity_exponent": "估算（幂律压缩，需校准）",
    "ram_per_player_base_mb": "公开实测口径（2GB≈15人 / 4GB≈35人原版）",
    "ram_per_mod_mb": "公开实测口径（8GB 约带 25 人 / 80 模组）",
    "net_packet_mb_per_player_per_min_base": "公开实测口径（活跃玩家 ≈40KB/s）",
    "net_duty_cycle": "公开实测口径（约 60% 玩家在跑图）",
    "mod_ceiling_vanilla": "估算（内容复杂度天花板，需按整合包实测校准）",
}


@dataclass
class Anchor:
    """一条服主实测数据。"""

    cpu: str
    players: int
    ram: str = "16G"
    mods: int = 0
    view: str = "10"
    behavior: str = PLAYER_BEHAVIORS[0]
    player_sim: str = PLAYER_SIM[0]
    tps: Optional[float] = None
    bottleneck: Optional[str] = None      # cpu / ram / network / mods / None(未知)
    source: str = ""
    note: str = ""
    # 服主反馈带过来的字段（可选）：库里没这个型号时，就用实测分现场换算
    cpuz: Optional[float] = None
    cores: Optional[int] = None
    playstyle: str = ""
    modpack_name: str = ""
    modpack_kind: str = ""
    progress: str = ""
    mc_version: str = ""
    optimization: str = ""
    playstyle_factor: Optional[float] = None
    behavior_factor: Optional[float] = None
    """玩法负载倍数（显式给出，避免 calibrate 再去查一遍）。
    整合包这里传的是"不含该包专属值"的折算倍数，否则会用自己的值推自己。"""

    @classmethod
    def from_dict(cls, d: Dict) -> "Anchor":
        def num(key):
            val = d.get(key)
            if val in (None, ""):
                return None
            try:
                return float(val)
            except (TypeError, ValueError):
                return None

        cores = d.get("cores")
        try:
            cores = int(cores) if cores not in (None, "") else None
        except (TypeError, ValueError):
            cores = None

        return cls(
            cpu=str(d.get("cpu", "")).strip(),
            players=int(d.get("players", 0)),
            ram=str(d.get("ram", "16G")),
            mods=int(d.get("mods", 0)),
            view=str(d.get("view", "10")),
            behavior=str(d.get("behavior", PLAYER_BEHAVIORS[0])),
            player_sim=str(d.get("player_sim", PLAYER_SIM[0])),
            tps=num("tps"),
            bottleneck=(str(d.get("bottleneck")).strip().lower()
                        if d.get("bottleneck") not in (None, "") else None),
            source=str(d.get("source", "")),
            note=str(d.get("note", "")),
            cpuz=num("cpuz_single"),
            cores=cores,
            playstyle=str(d.get("playstyle", "")),
            modpack_name=str(d.get("modpack_name", "")),
            modpack_kind=str(d.get("modpack_kind", "")),
            progress=str(d.get("progress", "")),
            mc_version=str(d.get("mc_version", "")),
            optimization=str(d.get("optimization", "")),
            playstyle_factor=num("playstyle_factor"),
            behavior_factor=num("behavior_factor"),
        )


@dataclass
class AnchorResult:
    anchor: Anchor
    usable: bool
    reason: str = ""
    ref_players: Optional[float] = None
    predicted: Optional[int] = None
    bottleneck_predicted: List[str] = field(default_factory=list)
    index: float = 0.0


def _core_gain(cores: int, alpha: float) -> float:
    return max(1, cores) ** alpha


def _ref_from_anchor(anchor: Anchor, params: Params) -> Tuple[Optional[float], str, CalcInput]:
    """从一条数据反推 ref_players；返回 (值, 说明, 结构化输入)。"""
    raw = RawInput(
        mod_count=str(anchor.mods), cpu=anchor.cpu, ram=anchor.ram,
        network="一般 (100M 家宽 / 普通 VPS)", view_distance=anchor.view,
        behavior=anchor.behavior, player_sim=anchor.player_sim,
    )
    fields, _warnings = parse_raw(raw)
    inp = CalcInput(**fields)

    cpu = inp.cpu
    if cpu.name.endswith("（未收录）") or "估算" in cpu.name:
        # 库里没有这个型号，但数据里带了 CPU-Z 单核分 → 用实测分现场建规格，别浪费数据
        if anchor.cpuz:
            from .cpu_data import cpu_cpuz_to_index
            cores = max(1, int(anchor.cores or 4))
            cpu = replace(cpu, name=f"{anchor.cpu}（实测）",
                          score=cpu_cpuz_to_index(anchor.cpuz), cores=cores,
                          note="来自反馈的 CPU-Z 实测分", custom=True)
            inp = replace(inp, cpu=cpu)
        else:
            return None, (f"CPU「{anchor.cpu}」不在库里，且数据没带 CPU-Z 分"
                          f"（补上跑分即可参与校准）"), inp

    # 散热系数也从输入里取（桌面默认 1.0，笔记本按模具×导热）
    idx = cpu.score * inp.cooling.factor()
    if idx <= 0:
        return None, "CPU 指数为 0", inp

    sim = params.player_sim_overhead.get(anchor.player_sim, 1.0)
    # 玩法倍数优先用锚点显式给出的（反馈数据会带），否则查内置表
    if anchor.behavior_factor is not None and anchor.behavior_factor > 0:
        behavior = float(anchor.behavior_factor)
    else:
        behavior = params.behavior_multiplier.get(anchor.behavior, 1.0)
    ref_score = params.cpu_reference_score
    ref_avg = ref_score * _core_gain(params.cpu_reference_cores, params.cpu_core_scale_alpha)
    cur_avg = idx * _core_gain(cpu.cores, params.cpu_core_scale_alpha)

    ref_players = (anchor.players * sim * behavior
                   * (ref_avg / cur_avg) ** params.cpu_capacity_exponent)
    return ref_players, "ok", inp


def analyze(anchors: List[Anchor], params: Optional[Params] = None) -> List[AnchorResult]:
    p = params or DEFAULT_PARAMS
    out: List[AnchorResult] = []
    for a in anchors:
        ref, reason, inp = _ref_from_anchor(a, p)
        res = AnchorResult(anchor=a, usable=ref is not None, reason=reason,
                           ref_players=ref, index=inp.cpu.score * inp.cooling.factor())

        # 用"当前参数"算一遍，看瓶颈与人数对不对得上（用于判断这条数据是否有参考价值）
        try:
            fields, _w = parse_raw(RawInput(
                mod_count=str(a.mods), cpu=a.cpu, ram=a.ram,
                network="一般 (100M 家宽 / 普通 VPS)", view_distance=a.view,
                behavior=a.behavior, player_sim=a.player_sim))
            full = calculate(CalcInput(**fields), p)
            res.predicted = full.final_players
            res.bottleneck_predicted = [f.key for f in full.factors if f.is_bottleneck]
        except Exception:
            pass

        if res.usable and a.bottleneck and a.bottleneck != "cpu":
            res.usable = False
            res.reason = f"瓶颈是 {a.bottleneck}，不能用来反推 CPU 系数"
        out.append(res)
    return out


def summarize(results: List[AnchorResult]) -> Dict[str, object]:
    """几何平均 + 离散度。"""
    vals = [r.ref_players for r in results if r.usable and r.ref_players]
    if not vals:
        return {"count": 0}
    log_sum = sum(math.log(v) for v in vals)
    geo = math.exp(log_sum / len(vals))
    if len(vals) > 1:
        var = sum((math.log(v) - log_sum / len(vals)) ** 2 for v in vals) / (len(vals) - 1)
        ratio = math.exp(math.sqrt(var))          # 几何标准差
    else:
        ratio = float("nan")
    return {
        "count": len(vals),
        "ref_players_geomean": round(geo, 1),
        "ref_players_min": round(min(vals), 1),
        "ref_players_max": round(max(vals), 1),
        "geo_std_ratio": None if math.isnan(ratio) else round(ratio, 3),
        "suggest_confidence": ("低（数据太少）" if len(vals) < 3 else
                               "中" if len(vals) < 8 else
                               "高" if (ratio < 1.6) else "中（离散度偏大）"),
    }


def load_anchors(path: str) -> List[Anchor]:
    """读取锚点文件。支持三种格式：纯 JSON 数组、{"anchors": [...]}、反馈导出的 Markdown。"""
    # utf-8-sig：兼容 Windows 记事本/PowerShell 导出的带 BOM 文件
    with open(path, "r", encoding="utf-8-sig") as fh:
        text = fh.read()

    # feedback_agent.md 这类交付文件：前面是给人/AI 看的说明，末尾是 ```json 数据块
    stripped = text.lstrip()
    if path.lower().endswith((".md", ".markdown")) or stripped.startswith("#"):
        from .feedback import parse_agent_markdown
        return [Anchor.from_dict(fb.to_anchor()) for fb in parse_agent_markdown(text)]

    data = json.loads(text)
    items = data.get("anchors", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("anchors 文件必须是数组，或 {\"anchors\": [...]}")
    return [Anchor.from_dict(d) for d in items if isinstance(d, dict)]


def _fit_suggestion(results: List[AnchorResult], params: Params) -> List[str]:
    """根据反推值的离散情况，给出是否该调整 alpha / E 的建议。

    原理：`ref_players` 反推公式里含 `E`。如果各条数据反推出的值系统性偏离，
    说明当前 `alpha`/`E` 对"强弱 CPU 差距"的刻画不对，而不只是锚点数值不对。
    """
    usable = [r for r in results if r.usable and r.ref_players]
    out: List[str] = []
    if len(usable) < 3:
        out.append("样本 <3 条，先不要动 alpha / E ——数据量不足以区分「锚点错」和「幂次错」。")
        return out

    # 按单核加权排序，看 ref_players 是否与硬件强弱相关（相关 = 幂次没吃准）
    ordered = sorted(usable, key=lambda r: r.index * (_core_gain(
        max(1, r.anchor.cores or 4), params.cpu_core_scale_alpha)))
    lo = [r.ref_players for r in ordered[:max(1, len(ordered) // 3)]]
    hi = [r.ref_players for r in ordered[-max(1, len(ordered) // 3):]]
    lo_avg = sum(lo) / len(lo)
    hi_avg = sum(hi) / len(hi)
    ratio = hi_avg / lo_avg if lo_avg else 1.0

    out.append(f"最弱 1/3 数据反推均值 {lo_avg:.1f}，最强 1/3 {hi_avg:.1f}，"
               f"比值 {ratio:.2f}")
    if ratio > 1.35:
        out.append("→ 强 CPU 反推出的 ref_players 明显更高：说明当前 E 偏小"
                   "（把硬件差距压得太平），可尝试把 cpu_capacity_exponent 调大"
                   "（例如 0.6 → 0.8），或把 alpha 调小。")
    elif ratio < 0.75:
        out.append("→ 强 CPU 反推出的 ref_players 明显更低：说明当前 E 偏大，"
                   "可尝试把 cpu_capacity_exponent 调小（例如 0.6 → 0.45）。")
    else:
        out.append("→ 强弱 CPU 的反推值没有系统性差异，说明 E / alpha 大致合适，"
                   "只需按几何平均调整 cpu_reference_players。")
    return out


def render_report(anchors: List[Anchor], results: List[AnchorResult],
                  summary: Dict[str, object], params: Params) -> str:
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append("  CPU 承载系数校准报告")
    lines.append("=" * 72)
    lines.append(f"  当前参数：ref_players={params.cpu_reference_players:g} / "
                 f"基准 {params.cpu_reference_score:g} 分（CPU-Z "
                 f"{params.cpuz_reference_score:.0f}）× {params.cpu_reference_cores} 核"
                 f" / 指数 α={params.cpu_core_scale_alpha:g} / 容量幂 {params.cpu_capacity_exponent:g}")
    lines.append("")
    lines.append("【数据逐条】")
    for r in results:
        a = r.anchor
        tag = "可用" if r.usable else "跳过"
        head = (f"  [{tag}] {a.cpu} / {a.ram} / {a.mods} 模组 / 视距{a.view} / "
                f"{a.players} 人")
        if a.tps is not None:
            head += f" @ {a.tps:g} TPS"
        lines.append(head)
        if r.usable and r.ref_players:
            lines.append(f"          → 反推 ref_players ≈ {r.ref_players:.1f}")
        else:
            lines.append(f"          → {r.reason}")
        if r.predicted is not None:
            lines.append(f"          当前模型预测 {r.predicted} 人，"
                         f"瓶颈判定 {r.bottleneck_predicted or '未知'}"
                         + (f"；服主报告瓶颈 {a.bottleneck}" if a.bottleneck else ""))
        if a.source:
            lines.append(f"          来源：{a.source}")
        lines.append("")

    lines.append("【汇总】")
    if summary.get("count"):
        lines.append(f"  可用样本 {summary['count']} 条：ref_players 几何平均 ≈ "
                     f"{summary['ref_players_geomean']}，范围 "
                     f"{summary['ref_players_min']} ~ {summary['ref_players_max']}")
        if summary.get("geo_std_ratio"):
            lines.append(f"  几何标准差 {summary['geo_std_ratio']}（越接近 1 越一致）")
        lines.append(f"  建议置信度：{summary['suggest_confidence']}")
    else:
        lines.append("  没有可用样本。每条数据需要：CPU 型号（库里要有或先录入）、"
                     "内存、模组数、视距、人数，并注明瓶颈是 CPU。")
    lines.append("")
    lines.append("【下一步建议】")
    for tip in _fit_suggestion(results, params):
        lines.append(f"  {tip}")
    lines.append("")
    lines.append("【系数来源标注】")
    for k, v in COEFFICIENT_PROVENANCE.items():
        lines.append(f"  {k:<38} {v}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="mc_player_calc.calibrate",
                                 description="用服主实测数据反推 CPU 承载系数")
    ap.add_argument("anchors", nargs="?", help="实测数据 JSON 文件")
    ap.add_argument("--write", action="store_true",
                    help="把建议值写成 params_override.json（供人工复核后合入 config.py）")
    ap.add_argument("--template", action="store_true", help="打印一份空白采集模板")
    args = ap.parse_args(argv)

    if args.template or not args.anchors:
        print(TEMPLATE_JSON)
        return 0

    try:
        anchors = load_anchors(args.anchors)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"读取失败：{exc}")
        return 1

    params = DEFAULT_PARAMS
    results = analyze(anchors, params)
    summary = summarize(results)
    print(render_report(anchors, results, summary, params))

    if args.write and summary.get("count"):
        out = {
            "note": "由 mc_player_calc.calibrate 生成，人工复核后再合入 config.py 的 DEFAULT_PARAMS",
            "sample_count": summary["count"],
            "suggested": {
                "cpu_reference_players": summary["ref_players_geomean"],
            },
            "raw_estimates": [round(r.ref_players, 1) for r in results
                              if r.usable and r.ref_players],
        }
        path = os.path.join(os.getcwd(), "params_override.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
        print(f"\n已写出建议值：{path}")
    return 0


TEMPLATE_JSON = """把下面这份发给服主填写（有多少填多少，填不了就留空）：

[
  {
    "cpu": "i9-14900K",
    "ram": "32G",
    "mods": 0,
    "view": "10",
    "behavior": "原版生存",
    "player_sim": "原版玩家",
    "players": 24,
    "tps": 18.5,
    "bottleneck": "cpu",
    "source": "某服主，2026-01 周中晚高峰",
    "note": "Paper 1.21，视距10，未开预防性区块加载"
  }
]

字段说明：
  cpu        CPU 型号（尽量精确，最好附 CPU-Z 单核分；开了 PBO/超频请写进 note）
  ram        分配给服务端的堆内存
  mods       服务端模组/插件数量（插件服填插件数，注明在 note）
  view       服务端 view-distance（模拟距离与视距不同的话请注明）
  players    当时在线人数
  tps        当时 TPS（/tps 或 spark 报告）
  bottleneck 你认为的瓶颈：cpu / ram / network / mods / 不知道
             ★ 只有填 cpu 的数据才能用来反推 CPU 系数，其余会跳过
  source     数据来源（服名/时间/采集方式），便于回溯

建议顺手一起记的（写在 note 里即可）：
  - CPU-Z 单核分（Bench → CPU Single Thread）
  - 服务端类型与版本（Paper / Fabric / Forge、1.20.1 等）
  - 是否开启预防性区块加载、实体激活范围等优化参数
  - 在线玩家的分布（是否集中在同一区域、是否挂机）

运行： python -m mc_player_calc.calibrate anchors.json
"""


if __name__ == "__main__":
    sys.exit(main())
