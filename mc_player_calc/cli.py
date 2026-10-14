"""命令行入口：

    python -m mc_player_calc --mods 30 --cpu "i5-12400" --ram 16G --net 良好
    python -m mc_player_calc --mods 30 --cpu 5800X3D --ram 16G --bw 100 --latency 30 --loss 0.1

交互模式（不带参数时依次询问四个输入）：
    python -m mc_player_calc
"""
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 <请填写你的名字或昵称>
#
# 本文件是「Minecraft 服务器人数上限计算器」的一部分，按 GPL-3.0 授权。
# 完整声明见 mc_player_calc/__init__.py 与项目根目录的 COPYRIGHT。
# 本程序不提供任何担保；输出为模型估算值，不是实测保证。


from __future__ import annotations

import argparse
import os
import sys
import webbrowser

from .cooling import (DESKTOP_COOLING, LAPTOP_CHASSIS, THERMAL_MATERIAL, CoolingConfig,
                      chassis_options, suffix_of)
from .cpu_data import (add_custom_cpu, all_models, cpuz_scale_info, custom_cpu_file,
                       custom_models, remove_custom_cpu, resolve_platform, save_custom_cpus)
from .engine import calculate
from .parser import (NETWORK_PRESETS, PLAYER_BEHAVIORS, PLAYER_SIM, RawInput,
                     VIEW_DISTANCES, parse_raw, resolve_cpu)
from .report import render

SPEEDTEST_URL = "https://test.ustc.edu.cn/"
CPUZ_SCALE = cpuz_scale_info()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mc_player_calc",
        description="Minecraft 服务器人数上限估算（木桶效应）",
    )
    p.add_argument("--mods", default=None, help="服务端模组数量")
    p.add_argument("--cpu", default=None, help="CPU 型号，例如 i5-12400 / 5800X3D / i7-12700H")
    p.add_argument("--ram", default=None, help="内存，例如 16G / 16384MB")
    p.add_argument("--net", default=None, choices=list(NETWORK_PRESETS), help="网络状况档位")
    p.add_argument("--bw", default=None, help="上行带宽 Mbps，覆盖档位（填测速实测值）")
    p.add_argument("--download", default=None, help="下行带宽 Mbps，仅记录不参与计算")
    p.add_argument("--latency", default=None, help="延迟 ms，覆盖档位")
    p.add_argument("--loss", default=None, help="丢包率 %%，覆盖档位")
    p.add_argument("--modpack", default=None, metavar="整合包名称",
                   help="整合包名称（玩法=整合包时决定用哪个包的专属系数）")
    p.add_argument("--behavior", default=None, choices=PLAYER_BEHAVIORS, help="玩法类型")
    p.add_argument("--player-sim", default=None, choices=PLAYER_SIM, dest="player_sim", help="每玩家负载")
    p.add_argument("--view", default=None, choices=VIEW_DISTANCES, help="视距（区块）")
    # ---- 散热系数 ----
    p.add_argument("--platform", default=None, choices=["desktop", "mobile"],
                   help="强制平台；默认按 CPU 型号自动识别")
    p.add_argument("--radiator", default=None, choices=list(DESKTOP_COOLING),
                   help="桌面散热器档位（桌面端生效）")
    p.add_argument("--chassis", default=None, choices=list(LAPTOP_CHASSIS),
                   help="笔记本模具档位（移动端生效）")
    p.add_argument("--material", default=None, choices=list(THERMAL_MATERIAL),
                   help="导热耗材档位（移动端生效）")
    p.add_argument("--cooling", default=None, dest="cooling_override",
                   help="直接指定总散热系数，例如 0.85（覆盖模具/耗材）")
    p.add_argument("--no-formulas", action="store_true", help="不打印推导过程")
    p.add_argument("--list-cpu", action="store_true", help="列出内置 CPU 型号库")
    p.add_argument("--list-cooling", action="store_true", help="列出散热系数表")
    p.add_argument("--speedtest", action="store_true", help="用默认浏览器打开中科大测速网")
    # ---- 自定义 CPU 型号 ----
    p.add_argument("--add-cpu", default=None, dest="add_cpu", metavar="型号:CPUZ分[:核心数[:平台]]",
                   help='录入自定义 CPU，如 --add-cpu "Ryzen 7 5800X3D 开PBO:690:8:desktop"')
    p.add_argument("--remove-cpu", default=None, dest="remove_cpu", metavar="型号",
                   help="删除自定义 CPU 型号")
    p.add_argument("--list-custom-cpu", action="store_true", dest="list_custom_cpu",
                   help="列出已录入的自定义 CPU 型号")
    # ---- 服主信息反馈 ----
    p.add_argument("--feedback", action="store_true",
                   help="交互式录入一条服主承载数据（存到 feedback.json）")
    p.add_argument("--feedback-list", action="store_true", dest="feedback_list",
                   help="列出已收集的反馈数据")
    p.add_argument("--feedback-summary", action="store_true", dest="feedback_summary",
                   help="汇总反馈并给出建议的玩法系数")
    p.add_argument("--feedback-packs", action="store_true", dest="feedback_packs",
                   help="按整合包分组汇总（一个包一套系数）")
    p.add_argument("--feedback-apply-packs", action="store_true", dest="feedback_apply_packs",
                   help="把按包汇总结果写入 modpack_profiles.json（样本 ≥3 条）")
    p.add_argument("--list-modpacks", action="store_true", dest="list_modpacks",
                   help="列出已建立档案的整合包及其系数")
    p.add_argument("--feedback-export", default=None, dest="feedback_export",
                   choices=["json", "csv", "anchors", "agent"],
                   help="导出反馈数据（json / csv / anchors 锚点 / agent 可读的 Markdown）")
    p.add_argument("--feedback-apply", action="store_true", dest="feedback_apply",
                   help="把汇总结果写入 behavior_multiplier.json（样本 ≥3 条的分组）")
    # ---- 本地状态 / 恢复默认 ----
    p.add_argument("--state", action="store_true",
                   help="查看本地有哪些数据文件、里面有多少内容")
    p.add_argument("--reset-data", action="store_true", dest="reset_data",
                   help="恢复默认：只清用户数据（自定义 CPU + 服主反馈），保留校准产物")
    p.add_argument("--reset-all", action="store_true", dest="reset_all",
                   help="恢复默认：清用户数据 + 校准产物（导出文件默认保留）")
    p.add_argument("--with-exports", action="store_true", dest="with_exports",
                   help="配合 --reset-all：连导出的 json/csv/md 一起清")
    p.add_argument("--dry-run", action="store_true", dest="dry_run",
                   help="配合恢复默认：只预演，不真删")
    p.add_argument("--no-backup", action="store_true", dest="no_backup",
                   help="配合恢复默认：不生成 .bak 备份（不可撤销，慎用）")
    p.add_argument("--yes", action="store_true", dest="assume_yes",
                   help="跳过恢复默认的二次确认（脚本里用）")
    p.add_argument("--list-backups", action="store_true", dest="list_backups",
                   help="列出可撤销的备份（.bak）")
    p.add_argument("--restore-backups", default=None, dest="restore_backups",
                   metavar="时间戳|all",
                   help="整组撤销恢复默认（传时间戳，或 all 撤销全部）")
    p.add_argument("--clean-backups", action="store_true", dest="clean_backups",
                   help="删除所有 .bak 备份（删后不可再撤销）")
    return p


def _ask(prompt: str, default: str) -> str:
    try:
        got = input(f"{prompt} [{default}]: ").strip()
    except EOFError:
        return default
    return got or default


# ----------------------------------------------------------------------
# 自定义 CPU 型号
# ----------------------------------------------------------------------
def _print_custom_cpus() -> int:
    items = custom_models()
    print(f"自定义 CPU 型号文件：{custom_cpu_file()}")
    if not items:
        print("（还没有录入任何型号）")
        print('录入方式： --add-cpu "型号:CPU-Z单核分[:核心数[:desktop|mobile]]"')
        return 0
    print(f"{'型号':<34}{'CPU-Z':>7}{'核心':>6}{'指数':>8}  平台")
    for s in items:
        print(f"{s.name:<34}{s.cpuz_score:>7.0f}{s.cores:>6}{s.score:>8.1f}  {s.platform}")
    return 0


def _handle_add_cpu(raw: str) -> int:
    parts = [p.strip() for p in str(raw).split(":")]
    if len(parts) < 2 or not parts[0]:
        print('格式：--add-cpu "型号:CPU-Z单核分[:核心数[:desktop|mobile]]"')
        print('例如：--add-cpu "Ryzen 7 5800X3D 开PBO:690:8:desktop"')
        return 2
    name = parts[0]
    try:
        cpuz = float(parts[1])
    except ValueError:
        print(f"CPU-Z 单核分「{parts[1]}」不是数字")
        return 2
    cores = parts[2] if len(parts) > 2 and parts[2] else 4
    platform = parts[3] if len(parts) > 3 else ""
    try:
        spec = add_custom_cpu(name, cpuz, cores, platform)
    except ValueError as exc:
        print(f"录入失败：{exc}")
        return 2
    path = save_custom_cpus()
    print(f"已录入：{spec.name}")
    print(f"  CPU-Z 单核 {spec.cpuz_score:.0f} → 内部指数 {spec.score:.1f}"
          f"（标定：{CPUZ_SCALE['ref_cpuz']:.0f} 分 = 指数 {CPUZ_SCALE['ref_index']:.0f}）")
    print(f"  平台 {spec.platform} / {spec.cores} 核")
    print(f"  文件 {path}")
    print(f'  直接计算：python -m mc_player_calc --cpu "{spec.name}" --mods 30 --ram 16G')
    return 0


def _handle_remove_cpu(name: str) -> int:
    if remove_custom_cpu(name):
        save_custom_cpus()
        print(f"已删除：{name}")
        return 0
    print(f"没找到自定义型号「{name}」。可用 --list-custom-cpu 查看。")
    return 1


# ----------------------------------------------------------------------
# 服主信息反馈
# ----------------------------------------------------------------------
def _feedback_interactive() -> int:
    """逐项问一条承载数据。"""
    from .feedback import (BOTTLENECKS, MC_VERSIONS, MODPACK_KINDS, OPTIMIZATION_LEVELS,
                           PLAYSTYLES, PROGRESS_STAGES, SERVER_SOFTWARE, append_feedback,
                           feedback_file, summarize_packs, validate)
    from .modpack import resolve_pack_factor

    print("=== 服主承载数据录入 ===")
    print("口径：在线人数增长到 TPS 首次跌破 19.5 时的人数。")
    print("只有「瓶颈 = cpu」的数据才会被用于反推 CPU 系数；")
    print("带整合包名称的数据还会用于校准**那个包自己的**负载系数。\n")
    data = {
        "cpu": _ask("CPU 型号", "i5-12400"),
        "cpuz_single": _ask("CPU-Z 单核跑分（回车跳过）", ""),
        "players": _ask("活跃用户（同时在线）", "20"),
        "view": _ask("区块视距（" + " / ".join(VIEW_DISTANCES) + "）", "10"),
        "tps": _ask("TPS", "19.5"),
        "playstyle": _ask("玩法（" + " / ".join(PLAYSTYLES) + "）", "原版"),
        "bottleneck": _ask("瓶颈（" + " / ".join(BOTTLENECKS) + "）", "cpu"),
        "ram": _ask("内存（如 32G）", "32G"),
        "software": _ask("服务端（" + " / ".join(SERVER_SOFTWARE) + "）", SERVER_SOFTWARE[0]),
        "progress": _ask("进度阶段（" + " / ".join(PROGRESS_STAGES) + "）", "中期"),
        "optimization": _ask("作者优化状况（" + " / ".join(OPTIMIZATION_LEVELS) + "）",
                             OPTIMIZATION_LEVELS[-1]),
        "note": _ask("备注 / 来源（回车跳过）", ""),
    }
    from .feedback import normalize_playstyle
    if normalize_playstyle(data["playstyle"]) == "整合包":
        print("\n【整合包补充信息】（一个包一套系数，包名请手打）")
        from .modpack import list_profiles
        known = list_profiles()
        if known:
            print("  已知档案：" + " / ".join(f"{p.name}（{p.factor:.2f}）" for p in known[:6]))
        data["modpack_name"] = _ask("整合包名称", "")
        data["mc_version"] = _ask("MC 版本（" + " / ".join(MC_VERSIONS) + "）", MC_VERSIONS[0])
        data["mods"] = _ask("模组数量", "200")
        data["modpack_kind"] = _ask("玩法类型（" + " / ".join(MODPACK_KINDS) + "）",
                                    list(MODPACK_KINDS)[0])

    fb, errors, warns = validate(data)
    if errors:
        print("\n录入失败：")
        for e in errors:
            print(f"  - {e}")
        return 2
    path, count = append_feedback(fb)
    print(f"\n已收录：{fb.cpu} / {fb.playstyle} / {fb.players} 人 @ {fb.tps or '—'} TPS")
    if fb.playstyle == "整合包" and fb.modpack_name:
        factor, why = resolve_pack_factor(fb.modpack_name)
        print(f"  该包负载系数 {factor}（{why}）")
    else:
        print(f"  玩法负载系数 {fb.playstyle_multiplier()}")
    if warns:
        print(f"  提示：{warns[0]}")
    print(f"  累计 {count} 条，文件 {path}")
    print("  下一步：python -m mc_player_calc --feedback-summary    （玩法系数）")
    print("          python -m mc_player_calc --feedback-packs      （按整合包）")
    return 0


def _feedback_list() -> int:
    from .feedback import load_feedback, stats_overview
    entries = load_feedback()
    st = stats_overview(entries)
    print(f"反馈文件：{st['file']}")
    if not entries:
        print("（还没有收集到数据）录入：python -m mc_player_calc --feedback")
        return 0
    print(f"共 {st['count']} 条；按玩法 {st['by_playstyle']}；按瓶颈 {st['by_bottleneck']}\n")
    print(f"{'#':>3} {'CPU':<20}{'CPU-Z':>6}{'人数':>5}{'TPS':>6}{'视距':>5}  "
          f"{'玩法':<8}{'瓶颈':<8}整合包")
    for i, e in enumerate(entries):
        print(f"{i:>3} {e.cpu[:20]:<20}{e.cpuz_single or 0:>6.0f}{e.players:>5}"
              f"{e.tps if e.tps is not None else 0:>6.1f}{e.view:>5}  "
              f"{e.playstyle:<8}{e.bottleneck:<8}{e.modpack_name or '-'}")
    return 0


def _feedback_summary() -> int:
    from .feedback import render_summary, summarize
    print(render_summary(summarize()))
    return 0


def _feedback_packs() -> int:
    from .feedback import render_pack_summary, summarize_packs
    print(render_pack_summary(summarize_packs()))
    return 0


def _feedback_apply_packs() -> int:
    from .feedback import apply_pack_suggestions, summarize_packs
    summary = summarize_packs()
    applied = apply_pack_suggestions(summary, min_samples=3)
    if not applied:
        print("没有样本数 ≥3 的整合包分组，未修改任何档案。")
        print("先用 --feedback 多收集几条带包名的数据，再跑 --feedback-packs 看建议值。")
        return 1
    from .modpack import profile_file
    print(f"已写入 {profile_file()}")
    for name, val in applied.items():
        print(f"  {name}：负载系数 → {val}")
    print("下次计算时自动生效（按包名匹配）；想改回兜底值就把该条从档案里删掉。")
    return 0


def _list_modpacks() -> int:
    from .modpack import (MODPACK_BASE_FACTOR, MODPACK_KINDS, PROGRESS_STAGES,
                          list_profiles, profile_file)
    packs = list_profiles()
    print(f"整合包档案：{profile_file()}")
    if not packs:
        print("（还没有任何档案，全部按兜底规则折算）")
    else:
        print(f"{'整合包':<24}{'系数':>7}  {'来源':<8}{'样本':>4}  版本 / 模组 / 优化")
        for p in packs:
            src = "校准值" if p.calibrated_factor else ("预填值" if p.declared_factor else "兜底")
            print(f"{p.name[:24]:<24}{p.factor:>7.3f}  {src:<8}{p.samples:>4}  "
                  f"{p.mc_version or '—'} / {p.mods or '—'} / {p.optimization or '—'}")
    print()
    print(f"兜底规则：基础 {MODPACK_BASE_FACTOR:g} × 玩法类型 × 进度阶段")
    print(f"  玩法类型：{' / '.join(f'{k}={v}' for k, v in MODPACK_KINDS.items())}")
    print(f"  进度阶段：{' / '.join(f'{k}={v}' for k, v in PROGRESS_STAGES.items())}")
    return 0


def _feedback_export(fmt: str) -> int:
    import json as _json
    from .feedback import (anchors_payload, export_agent_markdown, export_csv, feedback_file,
                           load_feedback)
    entries = load_feedback()
    if not entries:
        print("没有可导出的数据。")
        return 1
    if fmt == "csv":
        content = export_csv(entries)
        out = os.path.join(os.getcwd(), "feedback.csv")
    elif fmt == "anchors":
        content = _json.dumps(anchors_payload(entries), ensure_ascii=False, indent=2)
        out = os.path.join(os.getcwd(), "anchors.json")
    elif fmt == "agent":
        content = export_agent_markdown(entries)
        out = os.path.join(os.getcwd(), "feedback_agent.md")
    else:
        content = _json.dumps({"count": len(entries),
                               "entries": [e.__dict__ for e in entries]},
                              ensure_ascii=False, indent=2)
        out = os.path.join(os.getcwd(), "feedback_export.json")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(content)
    print(f"已导出 {len(entries)} 条到：{out}")
    if fmt == "agent":
        print("把这个文件发给对方（人或 AI）即可；它自带任务说明、口径定义与待校准参数。")
        print("对方回传结论后，你也可以本地复核：python -m mc_player_calc.calibrate 该文件")
    elif fmt == "anchors":
        print("可直接用于校准：python -m mc_player_calc.calibrate anchors.json")
    else:
        print(f"（原始数据文件：{feedback_file()}）")
    return 0


def _feedback_apply() -> int:
    from .feedback import apply_suggestions, summarize
    summary = summarize()
    path, applied = apply_suggestions(summary, min_samples=3)
    if not applied:
        print("没有样本数 ≥3 的玩法分组，未修改任何系数。")
        print("先用 --feedback 多收集几条，再跑 --feedback-summary 看建议值。")
        return 1
    print(f"已写入 {path}")
    for name, val in applied.items():
        base = __import__("mc_player_calc.config", fromlist=["DEFAULT_PARAMS"]) \
            .DEFAULT_PARAMS.behavior_multiplier.get(name)
        print(f"  {name}：内置 {base} → 应用 {val}")
    print("下次计算时自动生效；想改回内置值，删掉该文件即可。")
    return 0


def _show_state() -> int:
    from .reset import render_state
    print(render_state())
    return 0


def _do_reset(scope: str, with_exports: bool = False, dry_run: bool = False,
              backup_first: bool = True, assume_yes: bool = False) -> int:
    from .reset import reset, reset_derived, reset_user_data
    if scope == "user":
        report = reset_user_data(backup_first=backup_first, dry_run=dry_run)
        what = "用户数据（自定义 CPU + 服主反馈）"
    elif scope == "derived":
        report = reset_derived(backup_first=backup_first, dry_run=dry_run)
        what = "校准产物（玩法系数 + 整合包档案）"
    else:
        report = reset(backup_first=backup_first, dry_run=dry_run,
                       include_exports=with_exports)
        what = "全部" + ("（含导出文件）" if with_exports else "")

    if dry_run:
        print(f"[预演] 即将恢复默认：{what}")
        print(report.render())
        return 0

    if not report.cleared:
        print(f"没有需要恢复的内容（{what} 都是空的）。")
        return 0

    print(f"即将恢复默认：{what}")
    print(report.render())
    if not assume_yes:
        print()
        try:
            answer = input("确认？(y/N) ").strip().lower()
        except EOFError:
            answer = "n"
        if answer not in ("y", "yes", "是"):
            print("已取消，什么都没动。")
            return 1
    print()
    print("已恢复默认。想撤销：python -m mc_player_calc --restore-backups")
    return 0


def _show_backups() -> int:
    from .reset import backup_groups
    groups = backup_groups()
    if not groups:
        print("没有可撤销的备份。")
        return 0
    print("可撤销的备份（一个时间戳 = 一次恢复默认，建议整组撤销）：")
    for stamp, paths in groups.items():
        print(f"  {stamp}（{len(paths)} 个文件）")
        for p in paths:
            print(f"      {os.path.basename(p)}")
    print()
    print("整组撤销：python -m mc_player_calc --restore-backups <时间戳>")
    print("全部撤销：python -m mc_player_calc --restore-backups all")
    return 0


def _restore_backups(which: str) -> int:
    from .reset import backup_groups, restore_group
    groups = backup_groups()
    if not groups:
        print("没有可撤销的备份。")
        return 1
    if which in ("all", "*"):
        total, failed = 0, []
        for stamp in list(groups):
            try:
                total += len(restore_group(stamp))
            except OSError as exc:
                failed.append(str(exc))
        print(f"已整组撤销 {total} 个文件。")
        if failed:
            print("部分失败：" + "；".join(failed))
            return 1
        return 0
    if which not in groups:
        print(f"没找到时间戳 {which} 的备份。可用：{' / '.join(groups)}")
        return 1
    try:
        restored = restore_group(which)
    except OSError as exc:
        print(f"撤销失败：{exc}")
        return 1
    print(f"已整组撤销 {len(restored)} 个文件：")
    for r in restored:
        print(f"  {os.path.basename(r)}")
    return 0


def _clean_backups(assume_yes: bool = False) -> int:
    from .reset import delete_backups, list_backups
    backups = list_backups()
    if not backups:
        print("没有备份文件需要清理。")
        return 0
    print(f"将删除 {len(backups)} 个备份文件（删了就**不能再撤销**）：")
    for b in backups:
        print(f"  {b}")
    if not assume_yes:
        try:
            answer = input("确认删除？(y/N) ").strip().lower()
        except EOFError:
            answer = "n"
        if answer not in ("y", "yes", "是"):
            print("已取消。")
            return 1
    print(f"已删除 {delete_backups()} 个备份文件。")
    return 0


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)

    if args.list_cpu:
        print("内置 CPU 型号库（单核指数，基准 R5 5600 = 100）：")
        for name in all_models():
            print("  -", name)
        return 0

    if args.list_cooling:
        print("散热系数表（散热系数 = 模具系数 × 导热耗材系数；桌面默认 1.00）")
        print("\n[桌面散热器]")
        for k, v in DESKTOP_COOLING.items():
            print(f"  {v:.3f}  {k}")
        print("\n[笔记本模具]")
        for k, v in LAPTOP_CHASSIS.items():
            print(f"  {v:.3f}  {k}")
        print("\n[导热耗材]")
        for k, v in THERMAL_MATERIAL.items():
            print(f"  {v:.3f}  {k}")
        print("\n[后缀可选模具]")
        for suf in ("U", "P", "H", "HS", "HX"):
            print(f"  {suf:<3}: " + " | ".join(chassis_options(suf)))
        return 0

    if args.add_cpu is not None:
        return _handle_add_cpu(args.add_cpu)
    if args.remove_cpu is not None:
        return _handle_remove_cpu(args.remove_cpu)
    if args.list_custom_cpu:
        return _print_custom_cpus()
    if args.feedback:
        return _feedback_interactive()
    if args.feedback_list:
        return _feedback_list()
    if args.feedback_summary:
        return _feedback_summary()
    if args.feedback_packs:
        return _feedback_packs()
    if args.feedback_apply_packs:
        return _feedback_apply_packs()
    if args.list_modpacks:
        return _list_modpacks()
    # ---- 本地状态 / 恢复默认 ----
    if args.state:
        return _show_state()
    if args.list_backups:
        return _show_backups()
    if args.restore_backups is not None:
        return _restore_backups(args.restore_backups)
    if args.clean_backups:
        return _clean_backups(assume_yes=args.assume_yes)
    if args.reset_data or args.reset_all:
        scope = "all" if args.reset_all else "user"
        return _do_reset(scope, with_exports=args.with_exports, dry_run=args.dry_run,
                         backup_first=not args.no_backup, assume_yes=args.assume_yes)
    if args.feedback_export:
        return _feedback_export(args.feedback_export)
    if args.feedback_apply:
        return _feedback_apply()

    if args.speedtest:
        url = SPEEDTEST_URL
        ok = False
        try:
            ok = webbrowser.open(url)
        except Exception as exc:
            print(f"打开浏览器失败：{exc}")
        print(("已打开：" if ok else "未能自动打开，请手动访问：") + url)
        print("测完后把上行写到 --bw，下行写到 --download。")
        return 0

    interactive = all(v is None for v in (args.mods, args.cpu, args.ram, args.net))
    raw = RawInput()
    if interactive:
        print("=== Minecraft 服务器人数上限估算（木桶效应）===")
        print("直接回车使用括号内的默认值。\n")
        raw.mod_count = _ask("① 服务端模组数量", raw.mod_count)
        raw.cpu = _ask("② CPU 型号", raw.cpu)
        raw.ram = _ask("③ 内存大小（如 16G）", raw.ram)
        print("   网络档位可选：" + " / ".join(NETWORK_PRESETS))
        raw.network = _ask("④ 网络状况", raw.network)
        raw.bandwidth = _ask("   上行带宽 Mbps（回车用档位默认；建议先跑 --speedtest 测一遍）", "")
        raw.download = _ask("   下行带宽 Mbps（仅记录，回车跳过）", "")
        raw.latency = _ask("   延迟 ms（回车用档位默认）", "")
        raw.loss = _ask("   丢包率 %（回车用档位默认）", "")
        # 散热：移动端问模具+耗材，桌面端问散热器
        cpu_spec = resolve_cpu(raw.cpu)
        if resolve_platform(cpu_spec) == "mobile":
            suf = suffix_of(cpu_spec.name)
            opts = chassis_options(suf)
            print(f"   【散热】检测到移动端型号（后缀 {suf or '未知'}）")
            print("     可选模具：" + " / ".join(opts))
            raw.chassis = _ask("     笔记本模具", opts[0] if opts else "")
            raw.material = _ask("     导热耗材（" + " / ".join(THERMAL_MATERIAL) + "）",
                                list(THERMAL_MATERIAL)[0])
        else:
            print("   【散热】桌面端，可选散热器：" + " / ".join(DESKTOP_COOLING))
            raw.radiator = _ask("     散热器档位", list(DESKTOP_COOLING)[1])
        raw.cooling_override = _ask("     自定义总散热系数（回车用档位，如 0.85）", "")
        raw.behavior = _ask("⑤ 玩法（" + " / ".join(PLAYER_BEHAVIORS) + "）", raw.behavior)
        if raw.behavior == "整合包":
            from .modpack import list_profiles
            known = " / ".join(p.name for p in list_profiles()[:6])
            if known:
                print(f"   （已知档案：{known}）")
            raw.modpack = _ask("   整合包名称（手动输入，决定用哪个包的系数）", "")
        raw.player_sim = _ask("⑥ 每玩家负载（" + " / ".join(PLAYER_SIM) + "）", raw.player_sim)
        raw.view_distance = _ask("⑦ 视距区块（" + " / ".join(VIEW_DISTANCES) + "）", raw.view_distance)
    else:
        if args.mods is not None:
            raw.mod_count = args.mods
        if args.cpu is not None:
            raw.cpu = args.cpu
        if args.ram is not None:
            raw.ram = args.ram
        if args.net is not None:
            raw.network = args.net
        if args.bw is not None:
            raw.bandwidth = args.bw
        if args.download is not None:
            raw.download = args.download
        if args.latency is not None:
            raw.latency = args.latency
        if args.loss is not None:
            raw.loss = args.loss
        if args.behavior is not None:
            raw.behavior = args.behavior
        if args.modpack is not None:
            raw.modpack = args.modpack
        if args.player_sim is not None:
            raw.player_sim = args.player_sim
        if args.view is not None:
            raw.view_distance = args.view
        if args.platform is not None:
            raw.platform = "移动端（笔记本）" if args.platform == "mobile" else "桌面端（台式机 / 服务器）"
        if args.radiator is not None:
            raw.radiator = args.radiator
        if args.chassis is not None:
            raw.chassis = args.chassis
        if args.material is not None:
            raw.material = args.material
        if args.cooling_override is not None:
            raw.cooling_override = args.cooling_override

    fields, warnings = parse_raw(raw)
    from .engine import CalcInput
    result = calculate(CalcInput(**fields))
    result.warnings = warnings + result.warnings
    print(render(result, show_formulas=not args.no_formulas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
