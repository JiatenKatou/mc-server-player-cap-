"""把 CalcResult 渲染成人类可读文本（CLI 与 GUI 复制结果都用它）。"""

from __future__ import annotations

from typing import List

from .engine import CalcResult

_LINE = "=" * 64


def render(res: CalcResult, show_formulas: bool = True) -> str:
    inp = res.inputs
    lines: List[str] = []
    lines.append(_LINE)
    lines.append("  Minecraft 服务器人数上限估算（木桶效应）")
    lines.append(_LINE)
    lines.append(f"  结论：人数上限 ≈ {res.final_players} 人")
    lines.append("")

    lines.append("【输入】")
    if inp is not None:
        lines.append(f"  模组数量   : {inp.mod_count}")
        lines.append(f"  CPU        : {inp.cpu.name}")
        lines.append(f"  散热       : {inp.cooling.describe()}")
        if inp.cooling.factor() != 1.0:
            lines.append(f"               有效单核 = {inp.cpu.score:.0f} × {inp.cooling.factor():.3f}"
                         f" = {inp.cpu.score * inp.cooling.factor():.1f}")
        lines.append(f"  内存       : {inp.ram_mb / 1024:.2f} GB")
        lines.append(f"  网络       : {inp.network_preset}（上行 {inp.bandwidth_mbps:.0f} Mbps，"
                     f"延迟 {inp.latency_ms:.0f} ms，丢包 {inp.loss_pct:.2f}%）")
        if inp.download_input or inp.download_mbps:
            shown = (f"{inp.download_mbps:.0f} Mbps" if inp.download_mbps
                     else f"{inp.download_input} Mbps")
            lines.append(f"  下行       : {shown}（仅记录，不参与人数计算；服务器瓶颈在上行）")
        lines.append(f"  玩法       : {inp.behavior} / {inp.player_sim}")
        lines.append(f"  视距       : {inp.view_distance} 区块")
    lines.append("")

    lines.append("【木桶各维度可承载人数】（最小值决定上限）")
    for f in sorted(res.factors, key=lambda x: x.ceiling):
        tag = "  <== 瓶颈" if f.is_bottleneck else ("  (接近瓶颈)" if f.near_bottleneck else "")
        lines.append(f"  {f.label:<12} {f.ceiling:8.1f} 人   占用 {f.load_at_final * 100:5.0f}%{tag}")
    lines.append("")

    lines.append("【明细】")
    for f in res.factors:
        lines.append(f"  · {f.label}：{f.detail}")
    lines.append("")

    if show_formulas:
        lines.append("【推导过程】")
        for f in res.factors:
            lines.append(f"  ── {f.label} ──")
            for formula in f.formulas:
                lines.append(f"     {formula}")
            lines.append("")

    lines.append(f"【TPS 估算】最终人数负载下约 {res.tps_estimate:.1f} TPS（目标 20）")
    lines.append("")

    if res.suggestions:
        lines.append("【优化建议】")
        for s in res.suggestions:
            lines.append(f"  - {s}")
        lines.append("")

    if res.warnings:
        lines.append("【提示 / 警告】")
        for w in res.warnings:
            lines.append(f"  ! {w}")
        lines.append("")

    lines.append("说明：所有系数均为框架占位值，拿到真实压测数据后在 config.py 校准。")
    return "\n".join(lines)
