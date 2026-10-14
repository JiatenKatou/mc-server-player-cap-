"""框架自检：验证木桶效应与解析层是否按预期工作。

    python -m mc_player_calc.selftest
"""

from __future__ import annotations

import sys
from dataclasses import replace

from .config import Params
from .cooling import (DESKTOP_COOLING, LAPTOP_CHASSIS, THERMAL_MATERIAL, CoolingConfig,
                      chassis_options, desktop_default, mobile_default, suffix_of)
from .cpu_data import cpu_index_to_cpuz, resolve_platform
from .engine import CalcInput, calculate
from .parser import (NETWORK_PRESETS, RawInput, parse_bandwidth_mbps, parse_ram_mb, parse_raw,
                     resolve_cooling, resolve_cpu)

# Windows 控制台默认 GBK，强制 UTF-8 以便打印中文与符号
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

_FAILURES = []


def check(name: str, got, want) -> None:
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: got={got!r} want={want!r}")
    if not ok:
        _FAILURES.append(name)


def check_true(name: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _FAILURES.append(name)


def test_parsers() -> None:
    print("\n== 解析层 ==")
    check("parse_ram_mb('16G')", parse_ram_mb("16G"), 16384.0)
    check("parse_ram_mb('16384MB')", parse_ram_mb("16384MB"), 16384.0)
    check("parse_ram_mb('8')", parse_ram_mb("8"), 8192.0)
    check("parse_ram_mb('512MB')", parse_ram_mb("512MB"), 512.0)
    check("parse_bandwidth_mbps('100Mbps')", parse_bandwidth_mbps("100Mbps"), 100.0)
    check("parse_bandwidth_mbps('1Gbps')", parse_bandwidth_mbps("1Gbps"), 1000.0)
    check("parse_bandwidth_mbps('千兆')", parse_bandwidth_mbps("千兆"), 1000.0)
    check("parse_bandwidth_mbps('50')", parse_bandwidth_mbps("50"), 50.0)
    check("上行留空时取 0（由档位兜底）", parse_bandwidth_mbps(""), 0.0)
    check("parse_bandwidth_mbps('35.6')", parse_bandwidth_mbps("35.6"), 35.6)


def test_cpu() -> None:
    print("\n== CPU 型号库 ==")
    check("resolve_cpu('i5-12400').score", resolve_cpu("i5-12400").score, 108.0)
    check("resolve_cpu('R7 5800X3D').cores", resolve_cpu("R7 5800X3D").cores, 8)
    check("resolve_cpu('7800x3d').name", resolve_cpu("7800x3d").name, "Ryzen 7 7800X3D")
    check_true("未收录型号回退", resolve_cpu("FancyCPU-9000").score == 85.0)
    check("输入里带核心数", resolve_cpu("未知U 12核").cores, 12)


def test_bucket_principle() -> None:
    print("\n== 木桶效应 ==")
    # 内存极小 -> 内存必须是唯一瓶颈
    inp = CalcInput(mod_count=0, cpu=resolve_cpu("i9-14900K"), ram_mb=1536,
                    bandwidth_mbps=1000, latency_ms=10, loss_pct=0.0)
    res = calculate(inp)
    ram = res.factor("ram")
    check_true("内存瓶颈被识别", ram is not None and ram.is_bottleneck, f"ceiling={ram.ceiling:.1f}")
    ceiling = min(f.ceiling for f in res.factors)
    check("最终人数 = 最小值向下取整", res.final_players, max(1, int(ceiling)))

    # 带宽极小 -> 网络必须是瓶颈
    inp2 = CalcInput(mod_count=0, cpu=resolve_cpu("i9-14900K"), ram_mb=65536,
                     bandwidth_mbps=0.2, latency_ms=10, loss_pct=0.0)
    res2 = calculate(inp2)
    net = res2.factor("network")
    check_true("网络瓶颈被识别", net is not None and net.is_bottleneck, f"ceiling={net.ceiling:.1f}")

    # 弱鸡 CPU + 其他资源充足 -> CPU 必须是瓶颈
    inp4 = CalcInput(mod_count=0, cpu=resolve_cpu("J4125"), ram_mb=65536,
                     bandwidth_mbps=10000, latency_ms=5, loss_pct=0.0)
    res4 = calculate(inp4)
    cpu = res4.factor("cpu")
    check_true("CPU 瓶颈被识别", cpu is not None and cpu.is_bottleneck, f"ceiling={cpu.ceiling:.1f}")

    # 硬件拉满 + 巨型整合包 -> 瓶颈必然落在模组/玩法负载上
    inp3 = CalcInput(mod_count=600, cpu=resolve_cpu("i9-14900K"), ram_mb=131072,
                     bandwidth_mbps=10000, latency_ms=5, loss_pct=0.0)
    res3 = calculate(inp3)
    mods = res3.factor("mods")
    check_true("巨型整合包时模组瓶颈被识别", mods is not None and mods.is_bottleneck,
               f"ceiling={mods.ceiling:.1f}")
    check_true("硬件拉满时上限由模组负载决定",
               res3.final_players == max(1, int(mods.ceiling)),
               f"final={res3.final_players} mods={mods.ceiling:.1f}")


def test_monotonic_and_edges() -> None:
    print("\n== 单调性 / 边界 ==")
    base = dict(cpu=resolve_cpu("i5-12400"), ram_mb=16384, bandwidth_mbps=100,
                latency_ms=30, loss_pct=0.1)
    a = calculate(CalcInput(mod_count=10, **base)).factor("ram").ceiling
    b = calculate(CalcInput(mod_count=100, **base)).factor("ram").ceiling
    check_true("模组越多，每玩家内存越高 → 内存可承载下降", b < a, f"{a:.1f} -> {b:.1f}")

    c = calculate(CalcInput(mod_count=10, **base)).factor("cpu").ceiling
    strong_cpu = replace(resolve_cpu("i5-12400"), score=resolve_cpu("i9-14900K").score,
                         cores=resolve_cpu("i9-14900K").cores)
    d = calculate(CalcInput(mod_count=10, **{**base, "cpu": strong_cpu})).factor("cpu").ceiling
    check_true("CPU 越强，CPU 可承载越高", d > c, f"{c:.1f} -> {d:.1f}")

    e = calculate(CalcInput(mod_count=10, **{**base, "latency_ms": 300, "loss_pct": 5.0})).factor("network").ceiling
    f = calculate(CalcInput(mod_count=10, **base)).factor("network").ceiling
    check_true("高延迟 + 高丢包会压低网络可承载", e < f, f"{f:.1f} -> {e:.1f}")

    small_vd = calculate(CalcInput(mod_count=10, **{**base, "view_distance": "6"}))
    big_vd = calculate(CalcInput(mod_count=10, **{**base, "view_distance": "24"}))
    check_true("视距越大，内存可承载越低",
               big_vd.factor("ram").ceiling < small_vd.factor("ram").ceiling,
               f"{small_vd.factor('ram').ceiling:.1f} -> {big_vd.factor('ram').ceiling:.1f}")
    check_true("视距越大，网络可承载越低",
               big_vd.factor("network").ceiling < small_vd.factor("network").ceiling,
               f"{small_vd.factor('network').ceiling:.1f} -> {big_vd.factor('network').ceiling:.1f}")

    tiny = calculate(CalcInput(mod_count=0, cpu=resolve_cpu("N100"), ram_mb=1024,
                               bandwidth_mbps=1, latency_ms=200, loss_pct=10.0))
    check_true("极端差配置仍返回 >= 1 人", tiny.final_players >= 1, f"{tiny.final_players} 人")

    zero_mods = calculate(CalcInput(mod_count=0, cpu=resolve_cpu("i5-12400"), ram_mb=16384,
                                    bandwidth_mbps=100, latency_ms=30, loss_pct=0.1))
    check_true("0 模组可正常计算", zero_mods.final_players > 0, f"{zero_mods.final_players} 人")


def test_params_override() -> None:
    print("\n== 参数外置（后续校准入口）==")
    base = CalcInput(mod_count=50, cpu=resolve_cpu("i5-12400"), ram_mb=16384,
                     bandwidth_mbps=100, latency_ms=30, loss_pct=0.1)
    default = calculate(base)
    strict = calculate(base, Params(ram_per_player_base_mb=200.0))
    check_true("改写 config 参数会改变结果", strict.factor("ram").ceiling < default.factor("ram").ceiling,
               f"{default.factor('ram').ceiling:.1f} -> {strict.factor('ram').ceiling:.1f}")


def test_parse_raw_pipeline() -> None:
    print("\n== 完整输入链路 ==")
    raw = RawInput(mod_count="30", cpu="i5-12400", ram="16G",
                   network="良好 (千兆家宽 / 优质机房)", bandwidth="", latency="", loss="",
                   behavior="红石生电", player_sim="少量模组交互", view_distance="12")
    fields, warnings = parse_raw(raw)
    check("模组数", fields["mod_count"], 30)
    check("内存 MiB", fields["ram_mb"], 16384.0)
    check("带宽取档位默认", fields["bandwidth_mbps"], 200.0)
    check("玩法", fields["behavior"], "红石生电")
    check_true("无解析警告", warnings == [], str(warnings))

    res = calculate(CalcInput(**fields))
    check_true("最终人数为正", res.final_players > 0, f"{res.final_players} 人")
    check_true("瓶颈非空", len(res.binding_factors) >= 1, str(res.binding_factors))
    check_true("每个维度都有推导", all(len(f.formulas) >= 3 for f in res.factors))


def test_cooling() -> None:
    print("\n== 散热系数 ==")
    # 桌面默认必须是 1.0
    desktop = desktop_default()
    check("桌面默认散热系数", round(desktop.factor(), 3), 1.0)
    check("桌面默认平台", desktop.platform, "desktop")

    # 移动端识别
    check("i7-12700H -> mobile", resolve_platform(resolve_cpu("i7-12700H")), "mobile")
    check("i5-12400 -> desktop", resolve_platform(resolve_cpu("i5-12400")), "desktop")
    check("R7 7840HS -> mobile", resolve_platform(resolve_cpu("R7 7840HS")), "mobile")
    check("R7 7800X3D -> desktop", resolve_platform(resolve_cpu("R7 7800X3D")), "desktop")
    check("i7-10510U 后缀", suffix_of("i7-10510U"), "U")
    check("i9-14900HX 后缀", suffix_of("i9-14900HX"), "HX")
    check("R9 8945HX 后缀", suffix_of("Ryzen 9 8945HX"), "HX")
    check("桌面型号无后缀", suffix_of("Ryzen 7 7800X3D"), "")

    # 公式：散热系数 = 模具 × 导热
    light = list(LAPTOP_CHASSIS)[0]
    heavy = list(LAPTOP_CHASSIS)[3]
    mat_hi = list(THERMAL_MATERIAL)[1]
    cpu_m = resolve_cpu("i7-12700H")
    cfg_light, _ = resolve_cooling(cpu_m, chassis=light)
    cfg_heavy, w_heavy = resolve_cooling(cpu_m, chassis=heavy, material=mat_hi)
    expect = round(LAPTOP_CHASSIS[light] * THERMAL_MATERIAL["普通硅脂（出厂 / 杂牌）"], 4)
    check("模具 × 导热 = 散热系数", round(cfg_light.factor(), 4), expect)
    check("高端模具 + 高性能硅脂", round(cfg_heavy.factor(), 4),
          round(LAPTOP_CHASSIS[heavy] * THERMAL_MATERIAL[mat_hi], 4))
    check_true("GUI 可选档位不产生警告", w_heavy == [], str(w_heavy))

    # 用户显式选择优先（只提示、不拦截）
    cfg_forced, w_forced = resolve_cooling(cpu_m, chassis=light)
    check("显式选择被尊重", round(cfg_forced.factor(), 3), round(LAPTOP_CHASSIS[light], 3))
    check_true("与后缀不符时有提示", len(w_forced) >= 1)

    # 自定义总系数覆盖
    cfg_ov, _ = resolve_cooling(cpu_m, override="0.75")
    check("自定义系数覆盖", round(cfg_ov.factor(), 3), 0.75)

    # 桌面散热器影响
    cpu_d = resolve_cpu("i5-12400")
    cfg_passive, _ = resolve_cooling(cpu_d, radiator="被动散热 / 无风扇（迷你主机、NAS）")
    cfg_water, _ = resolve_cooling(cpu_d, radiator="360 水冷及以上")
    base = dict(mod_count=0, cpu=cpu_d, ram_mb=65536, bandwidth_mbps=10000, latency_ms=10,
                loss_pct=0.0)
    c_passive = calculate(CalcInput(cooling=cfg_passive, **base)).factor("cpu")
    c_water = calculate(CalcInput(cooling=cfg_water, **base)).factor("cpu")
    check_true("散热差 → CPU 可承载更低",
               c_passive.ceiling < c_water.ceiling,
               f"{c_passive.ceiling:.1f} < {c_water.ceiling:.1f}")
    check("CPU 维度展示有效单核", c_passive.values["有效单核"],
          f"{cpu_d.score * cfg_passive.factor():.1f} 指数 ≈ CPU-Z "
          f"{round(cpu_index_to_cpuz(cpu_d.score * cfg_passive.factor()))} 分")

    # 同一 CPU：散热越差，最终人数不能更多
    base_m = dict(mod_count=20, cpu=cpu_m, ram_mb=32768, bandwidth_mbps=1000, latency_ms=20,
                  loss_pct=0.1)
    worst = calculate(CalcInput(cooling=resolve_cooling(cpu_m, chassis=light)[0], **base_m))
    best = calculate(CalcInput(cooling=resolve_cooling(cpu_m, chassis=heavy, material=mat_hi)[0],
                               **base_m))
    check_true("整机结论随散热变化", worst.final_players <= best.final_players,
               f"{worst.final_players} <= {best.final_players}")

    # 所有后缀的可选档位都应可用
    for suf, model in (("U", "i7-10510U"), ("P", "i5-1240P"), ("H", "i7-12700H"),
                       ("HS", "R7 7840HS"), ("HX", "R9 8945HX")):
        opts = chassis_options(suf)
        noisy = [ch for ch in opts if resolve_cooling(resolve_cpu(model), chassis=ch)[1]]
        check_true(f"{suf} 后缀 {len(opts)} 档全部可用", len(noisy) == 0 and len(opts) >= 1)

    # parse_raw 全链路应带上 cooling
    raw = RawInput(mod_count="10", cpu="i7-12700H", ram="16G",
                   network="良好 (千兆家宽 / 优质机房)",
                   chassis="轻薄本 / 核显本（单风扇、15~28W 限制）")
    fields, warns = parse_raw(raw)
    check("parse_raw 产出 cooling", type(fields["cooling"]).__name__, "CoolingConfig")
    check("parse_raw 应用了模具", round(fields["cooling"].factor(), 3), round(LAPTOP_CHASSIS[light], 3))
    check_true("parse_raw 带上散热提示", any("轻薄本" in w for w in warns), str(warns))


def test_speedtest_inputs() -> None:
    print("\n== 自填测速结果（上行参与计算 / 下行仅记录）==")
    base = dict(mod_count=0, cpu=resolve_cpu("i5-12400"), ram_mb=16384, latency_ms=55,
                loss_pct=0.3)

    # 1) 不填上行 → 用档位默认
    f, _ = parse_raw(RawInput(network="一般 (100M 家宽 / 普通 VPS)", bandwidth=""))
    check("不填上行 → 档位默认 50Mbps", f["bandwidth_mbps"], 50.0)
    check("不填下行 → 0", f["download_mbps"], 0.0)

    # 2) 自填上行覆盖档位
    f, w = parse_raw(RawInput(network="一般 (100M 家宽 / 普通 VPS)", bandwidth="35", behavior="原版"))
    check("自填上行覆盖档位", f["bandwidth_mbps"], 35.0)
    check_true("无多余提示", w == [], str(w))

    # 3) 上下行都填
    f, _ = parse_raw(RawInput(bandwidth="35.6", download="300"))
    check("上行支持小数", f["bandwidth_mbps"], 35.6)
    check("下行解析", f["download_mbps"], 300.0)
    check("下行原文保留", f["download_input"], "300")

    # 4) 单位写法
    f, _ = parse_raw(RawInput(bandwidth="500 Mbps", download="1Gbps"))
    check("上行带单位", f["bandwidth_mbps"], 500.0)
    check("下行带单位", f["download_mbps"], 1000.0)

    # 5) 下行不参与计算：改下行结果必须不变
    r1 = calculate(CalcInput(download_mbps=100, **base))
    r2 = calculate(CalcInput(download_mbps=2000, **base))
    check("下行不影响结论", r1.final_players, r2.final_players)
    check("下行不影响网络维度", round(r1.factor("network").ceiling, 3),
          round(r2.factor("network").ceiling, 3))

    # 6) 上行变化必须影响网络维度（且单调）
    lo = calculate(CalcInput(bandwidth_mbps=20, **base)).factor("network").ceiling
    hi = calculate(CalcInput(bandwidth_mbps=80, **base)).factor("network").ceiling
    check_true("上行越高，网络可承载越高", hi > lo, f"{lo:.1f} < {hi:.1f}")

    # 7) 报告里要有下行那一行
    res = calculate(CalcInput(bandwidth_mbps=35, download_mbps=300, download_input="300", **base))
    res.warnings = list(res.warnings)
    text = __import__("mc_player_calc.report", fromlist=["render"]).render(res)
    check_true("报告含下行记录行", "下行" in text and "300" in text)

    # 8) 无法识别的上行要给出提示并回退档位
    f, w = parse_raw(RawInput(network="一般 (100M 家宽 / 普通 VPS)", bandwidth="很快"))
    check_true("无法识别的上行有提示", any("上行带宽" in x for x in w), str(w))
    check("无法识别时回退档位默认", f["bandwidth_mbps"], 50.0)


def test_cpuz_and_custom_cpu() -> None:
    print("\n== CPU-Z 标尺与自定义型号录入 ==")
    import os
    import tempfile

    from . import cpu_data as cd

    # 1) 双向换算必须自洽
    for cpuz in (300, 500, 662, 800, 950, 1200):
        idx = cd.cpu_cpuz_to_index(cpuz)
        back = cd.cpu_index_to_cpuz(idx)
        check_true(f"CPU-Z {cpuz} 往返换算", abs(back - cpuz) < 0.01, f"{back:.3f}")
    check("基准锚点：CPU-Z 662 → 指数 100", round(cd.cpu_cpuz_to_index(662), 4), 100.0)
    check("基准锚点反向：指数 100 → 662", round(cd.cpu_index_to_cpuz(100), 1), 662.0)

    # 2) 库内展示要与换算一致
    spec = resolve_cpu("i5-12400")
    check("库内 CPU-Z 展示 = 指数换算", spec.cpuz_score, round(cd.cpu_index_to_cpuz(spec.score)))

    # 3) 用临时文件隔离，避免污染真实 custom_cpus.json
    fd, tmp = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.unlink(tmp)
    old_env = os.environ.get("MC_CALC_CUSTOM_CPUS")
    os.environ["MC_CALC_CUSTOM_CPUS"] = tmp
    try:
        check_true("自定义文件路径跟随环境变量", cd.custom_cpu_file() == os.path.abspath(tmp))

        item = cd.add_custom_cpu("Ryzen 7 5800X3D 开PBO", 690, 8, "desktop", "自测")
        check("自定义型号 CPU-Z 分", item.cpuz_score, 690.0)
        check("自定义型号指数换算", round(item.score, 1), round(cd.cpu_cpuz_to_index(690), 1))
        check_true("自定义型号被标记", item.custom is True)

        # 4) 立刻能查到，且长名字也能模糊命中
        for q in ("Ryzen 7 5800X3D 开PBO", "5800X3D 开PBO", "5800x3d开pbo"):
            hit = resolve_cpu(q)
            check_true(f"能查到「{q}」", hit.custom and hit.name == item.name, hit.name)
        check_true("型号片段也能命中", resolve_cpu("3d开pbo").custom,
                   resolve_cpu("3d开pbo").name)

        # 5) 持久化 → 重新载入（先清空内存态，确保只依赖文件内容）
        path = cd.save_custom_cpus()
        check_true("已写入文件", os.path.isfile(path), path)
        cd.CUSTOM_DB.clear()
        check_true("清空后查不到", not resolve_cpu("Ryzen 7 5800X3D 开PBO").custom)
        loaded = cd.load_custom_cpus()
        check_true("重新载入成功", loaded >= 1, f"载入 {loaded} 条")
        again = resolve_cpu("Ryzen 7 5800X3D 开PBO")
        check_true("重启后仍在（模拟重启）", again.custom and again.cpuz_score == 690.0,
                   f"{again.name} {again.cpuz_score}")

        # 6) 覆盖同名型号
        cd.add_custom_cpu("Ryzen 7 5800X3D 开PBO", 720, 8, "desktop")
        check("同名覆盖", resolve_cpu("Ryzen 7 5800X3D 开PBO").cpuz_score, 720.0)

        # 7) 参数校验
        for bad, why in ((("", 700), "空名称"), (("X", "很快"), "分数非数字"),
                         (("X", 0), "分数为 0"), (("X", 99999), "分数过大"),
                         (("X", 500, "四核"), "核心非整数")):
            try:
                cd.add_custom_cpu(*bad)
                check_true(f"拒绝{why}", False, "居然通过了")
            except ValueError:
                check_true(f"拒绝{why}", True)

        # 8) 移动端自定义型号要能触发散热细分
        mob = cd.add_custom_cpu("Ryzen 9 8945HX 魔改", 820, 16)
        check("移动端后缀被识别", resolve_platform(mob), "mobile")
        from .cooling import chassis_options, suffix_of
        check_true("可给出模具档位", len(chassis_options(suffix_of(mob.name))) >= 1)

        # 9) 散热要作用在 CPU-Z 分上（有效分 = 原始 × 系数）
        from .cooling import mobile_default
        cfg = mobile_default(list(__import__("mc_player_calc.cooling",
                                            fromlist=["LAPTOP_CHASSIS"]).LAPTOP_CHASSIS)[0])
        res = calculate(CalcInput(mod_count=0, cpu=mob, cooling=cfg, ram_mb=65536,
                                  bandwidth_mbps=10000, latency_ms=10, loss_pct=0.0))
        cpu_factor = res.factor("cpu")
        expect_idx = mob.score * cfg.factor()
        check("散热作用在有效分上", cpu_factor.values["有效单核"],
              f"{expect_idx:.1f} 指数 ≈ CPU-Z {round(cd.cpu_index_to_cpuz(expect_idx))} 分")
        check_true("有效 CPU-Z 分低于原始分", round(cd.cpu_index_to_cpuz(expect_idx)) < mob.cpuz_score,
                   f"{cd.cpu_index_to_cpuz(expect_idx):.0f} < {mob.cpuz_score:.0f}")

        # 10) 记录原样保留 + 删除
        cd.add_custom_cpu("Xeon W-2145 二手", 520, 8, note="编号 12345")
        check("备注原样保留", resolve_cpu("Xeon W-2145 二手").note, "编号 12345")
        check_true("删除成功", cd.remove_custom_cpu("Xeon W-2145 二手") is True)
        check_true("重复删除返回 False", cd.remove_custom_cpu("Xeon W-2145 二手") is False)
    finally:
        cd.CUSTOM_DB.clear()
        if old_env is None:
            os.environ.pop("MC_CALC_CUSTOM_CPUS", None)
        else:
            os.environ["MC_CALC_CUSTOM_CPUS"] = old_env
        for f in (tmp,):
            try:
                os.unlink(f)
            except OSError:
                pass
        cd.load_custom_cpus()


def test_feedback() -> None:
    print("\n== 服主反馈收集 ==")
    import os

    from . import feedback as fb

    with _IsolatedEnv("feedback") as tmpdir:
        tmp = os.path.join(tmpdir, "feedback.json")
        # 1) 玩法分类与工具侧必须一致
        from .parser import PLAYER_BEHAVIORS
        check("玩法分类与工具一致", list(fb.PLAYSTYLES), PLAYER_BEHAVIORS)
        check("整合包是唯一需要扩字段的",
              [k for k, v in fb.PLAYSTYLES.items() if v.get("extended")], ["整合包"])

        # 2) 校验：必填项与范围
        _, errs, _ = fb.validate({"cpu": "", "players": 0, "tps": 99, "playstyle": "火星"})
        check_true("必填项被拦", len(errs) == 4, str(errs))
        _, errs, warns = fb.validate({"cpu": "5800X3D", "players": 15, "playstyle": "整合包"})
        check_true("整合包缺包名被拦", any("整合包名称" in e for e in errs), str(errs))
        check_true("整合包缺细节有警告", len(warns) >= 2, str(warns))
        ok, errs, _ = fb.validate({"cpu": "i5-12400", "cpuz_single": 700, "players": 44,
                                   "view": "10", "tps": 19.6, "playstyle": "原版",
                                   "bottleneck": "cpu"})
        check_true("合法数据通过", ok is not None and not errs, str(errs))
        check("CPU-Z 分被记录", ok.cpuz_single, 700.0)

        # 3) 玩法负载系数（含整合包细分与进度阶段）
        full, _, _ = fb.validate({"cpu": "5800X3D", "players": 15, "playstyle": "整合包",
                                  "modpack_name": "ATM10", "mc_version": "1.21.x", "mods": 380,
                                  "modpack_kind": "综合（科技+魔法+任务）",
                                  "progress": "大后期 / 长期服"})
        expect = round(fb.PLAYSTYLES["整合包"]["multiplier"]
                       * fb.MODPACK_KINDS["综合（科技+魔法+任务）"]
                       * fb.PROGRESS_STAGES["大后期 / 长期服"], 3)
        check("整合包负载系数", full.playstyle_multiplier(), expect)

        # 4) 落盘 + 读回 + 锚点导出
        path, n = fb.append_feedback(ok)
        check("首次写入", n, 1)
        fb.append_feedback(full)
        entries = fb.load_feedback()
        check("读回条数", len(entries), 2)
        check_true("文件路径跟随环境变量", path == os.path.abspath(tmp), path)
        anchors = fb.anchors_payload(entries)
        check("锚点条数", len(anchors["anchors"]), 2)
        check_true("锚点带玩法系数", "playstyle_factor" in anchors["anchors"][1])

        # 5) 汇总：非 CPU 瓶颈必须被跳过
        ram_fb, errs, _ = fb.validate({"cpu": "E5-2680 v4", "players": 30, "view": "8", "tps": 18,
                                       "playstyle": "红石生电", "bottleneck": "ram", "ram": "16G"})
        check_true("内存瓶颈数据本身合法", ram_fb is not None and not errs, str(errs))
        fb.append_feedback(ram_fb)
        summary = fb.summarize()
        check("总条数", summary["total"], 3)
        check_true("内存瓶颈被跳过",
                   any("ram" in s["reason"] or "内存" in s["reason"]
                       for s in summary["skipped"]), str(summary["skipped"]))

        # 6) 应用系数 → 引擎必须读到
        fb.apply_suggestions(summary, min_samples=1)
        overrides = fb.load_behavior_overrides()
        check_true("覆盖文件已写出", len(overrides) >= 1, str(overrides))
        if "原版" in overrides:
            check("覆盖值与汇总一致", overrides["原版"],
                  summary["suggested"]["原版"]["suggested_multiplier"])
            from .config import DEFAULT_PARAMS
            from .engine import _behavior_coef
            check("引擎读到覆盖值", round(_behavior_coef(DEFAULT_PARAMS, "原版"), 3),
                  summary["suggested"]["原版"]["suggested_multiplier"])

        # 7) CSV 导出
        csv_text = fb.export_csv(entries)
        check("CSV 行数 = 数据+表头", len(csv_text.strip().splitlines()), 3)
        check_true("CSV 含表头字段", "cpuz_single" in csv_text.splitlines()[0])

        # 7b) agent 交付文件：自带说明 + 内嵌 JSON，且能被 calibrate 直接读
        entries = fb.load_feedback()          # 重新读全（含上面追加的内存瓶颈那条）
        md = fb.export_agent_markdown(entries, server_owner="测试服主")
        check_true("交付文件含任务说明", "反推 CPU 系数" in md)
        check_true("交付文件含待校准参数", "ref_players" in md and "alpha" in md)
        check_true("交付文件含口径定义", "TPS 首次跌破 19.5" in md)
        check_true("交付文件含数据表", "| # | CPU 型号" in md)
        check_true("交付文件含期望输出格式", "请按这个格式给出结论" in md)
        check_true("交付文件含 JSON 块", "```json" in md)
        back = fb.parse_agent_markdown(md)
        check("回读条数", len(back), 3)
        check("回读保留 CPU-Z 分", back[0].cpuz_single, entries[0].cpuz_single)
        check("回读保留整合包字段", back[1].modpack_name, "ATM10")
        check("回读保留模组数量", back[1].mods, entries[1].mods)
        check("回读后玩法倍数可复原", back[1].playstyle_multiplier(),
              entries[1].playstyle_multiplier())

        # 7c) 让 calibrate 直接读这个 Markdown（模拟"服主回传文件给我"）
        from .calibrate import load_anchors
        md_path = tmp.replace(".json", ".md")
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(md)
        anchors_from_md = load_anchors(md_path)
        check("calibrate 能读 Markdown", len(anchors_from_md), 3)
        check_true("Markdown 里的锚点能用",
                   any(a.cpuz for a in anchors_from_md), f"{len(anchors_from_md)} 条锚点")

        # 8) 旧玩法名归一化
        check("旧名归一化：原版生存", fb.normalize_playstyle("原版生存"), "原版")
        check("旧名归一化：红石 / 自动化", fb.normalize_playstyle("红石 / 自动化"), "红石生电")
        check("自由文本归一化", fb.normalize_playstyle("整合包服"), "整合包")
        check("无法识别返回 None", fb.normalize_playstyle("火星玩法"), None)


class _IsolatedEnv:
    """把全部本地状态文件重定向到工作区内的临时目录。

    为什么不用系统临时目录：本机沙箱允许 mkstemp，但**后续对系统临时目录的写入会被拒**；
    而且放在工作区内更贴近真实用法（数据文件本来就在工作区）。
    """

    KEYS = ("MC_CALC_FEEDBACK", "MC_CALC_CUSTOM_CPUS", "MC_CALC_MODPACKS",
            "MC_CALC_BEHAVIOR")

    def __init__(self, tag: str) -> None:
        import os
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.dir = os.path.join(here, f"_selftest_{tag}")
        self.old: dict = {}

    def __enter__(self) -> str:
        import os
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)
        os.makedirs(self.dir, exist_ok=True)
        for key in self.KEYS:
            self.old[key] = os.environ.get(key)
        os.environ["MC_CALC_FEEDBACK"] = os.path.join(self.dir, "feedback.json")
        os.environ["MC_CALC_CUSTOM_CPUS"] = os.path.join(self.dir, "custom_cpus.json")
        os.environ["MC_CALC_MODPACKS"] = os.path.join(self.dir, "modpack_profiles.json")
        os.environ["MC_CALC_BEHAVIOR"] = os.path.join(self.dir, "behavior_multiplier.json")
        from . import modpack
        modpack.PROFILES.clear()
        return self.dir

    def __exit__(self, *exc) -> None:
        import os
        import shutil
        for key, old in self.old.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        shutil.rmtree(self.dir, ignore_errors=True)
        from . import modpack
        modpack.PROFILES.clear()
        modpack.load_profiles()


def test_modpack_profiles() -> None:
    print("\n== 整合包档案（一个包一套系数）==")
    import os

    from . import modpack as mp
    from .engine import CalcInput, calculate
    from .parser import resolve_cpu

    with _IsolatedEnv("modpack") as tmp:
        mp.PROFILES.clear()

        # 1) 没有档案时按类型/进度兜底
        f, why = mp.resolve_pack_factor("GTNH 2.7")
        check("无档案时用兜底值", f, mp.MODPACK_BASE_FACTOR)
        check_true("兜底说明提到包名", "GTNH" in why, why)
        f2, _ = mp.resolve_pack_factor("某包", kind="科技 / 自动化")
        check("兜底值含玩法类型", round(f2, 3),
              round(mp.MODPACK_BASE_FACTOR * mp.MODPACK_KINDS["科技 / 自动化"], 3))

        # 2) 写入校准值后按包区分
        mp.upsert_profile("GTNH 2.7", calibrated_factor=0.63, samples=3,
                          kind="综合（科技+魔法+任务）", optimization="作者几乎没优化")
        mp.upsert_profile("ATM10", calibrated_factor=0.45, samples=4,
                          optimization="作者优化良好")
        got, why2 = mp.resolve_pack_factor("GTNH 2.7")
        check("校准值生效", got, 0.63)
        check_true("来源说明是校准值", "校准值" in why2, why2)
        check("不同包不同系数", mp.resolve_pack_factor("ATM10")[0], 0.45)

        # 3) 包名模糊匹配（简化写法 / 部分包含）
        check("部分包含匹配", mp.resolve_pack_factor("GTNH")[0], 0.63)
        check("简化写法匹配", mp.resolve_pack_factor("gtnh27")[0], 0.63)
        check("大小写与空格无关", mp.resolve_pack_factor("at m10")[0], 0.45)

        # 4) 持久化
        path = mp.save_profiles()
        check_true("档案已写盘", os.path.isfile(path), path)
        mp.PROFILES.clear()
        loaded = mp.load_profiles()
        check("重新载入条数", loaded, 2)
        check("重载后仍有校准值", mp.resolve_pack_factor("GTNH 2.7")[0], 0.63)

        # 5) 计算里真的按包取系数。
        #    注意语义：系数是「每模组的负载倍数」，**越大 = 越吃资源 = 承载越低**。
        from .engine import _behavior_coef as _bc
        base = dict(mod_count=400, cpu=resolve_cpu("i9-14900K"), ram_mb=65536,
                    bandwidth_mbps=10000, latency_ms=20, loss_pct=0.0, behavior="整合包")
        r_gtnh = calculate(CalcInput(pack_name="GTNH 2.7", **base))    # 系数 0.63
        r_atm = calculate(CalcInput(pack_name="ATM10", **base))        # 系数 0.45
        r_unknown = calculate(CalcInput(pack_name="没见过的包", **base))  # 兜底 1.60
        check("引擎按包取系数", _bc(r_gtnh.params, "整合包", "GTNH 2.7"), 0.63)
        check("另一个包取另一个系数", _bc(r_atm.params, "整合包", "ATM10"), 0.45)
        mod_gtnh = r_gtnh.factor("mods").ceiling
        mod_atm = r_atm.factor("mods").ceiling
        mod_unknown = r_unknown.factor("mods").ceiling
        check_true("系数小的包承载更高（负载轻）", mod_atm > mod_gtnh,
                   f"ATM10 {mod_atm:.1f} > GTNH {mod_gtnh:.1f}")
        check_true("没有档案的包走兜底（比已校准的重）", mod_unknown < mod_gtnh,
                   f"兜底 {mod_unknown:.1f} < GTNH {mod_gtnh:.1f}")
        check_true("模组维度明细里显示该包倍数",
                   "0.63" in r_gtnh.factor("mods").values["玩法倍数"],
                   r_gtnh.factor("mods").values["玩法倍数"])

        # 6) 反馈数据带的 playstyle_multiplier 与引擎一致
        from .feedback import Feedback
        fb = Feedback.from_dict({"cpu": "i9-14900K", "players": 18, "playstyle": "整合包",
                                 "modpack_name": "GTNH 2.7", "bottleneck": "cpu",
                                 "modpack_kind": "综合（科技+魔法+任务）"})
        check("反馈侧的倍数是该包的", fb.playstyle_multiplier(), 0.63)
        check("反推时用不含该包专属值的倍数", fb.playstyle_multiplier(use_profile=False),
              round(mp.MODPACK_BASE_FACTOR * mp.MODPACK_KINDS["综合（科技+魔法+任务）"], 3))

        # 7) 按包汇总 + 写回档案
        from . import feedback as fbm
        # 用同一隔离目录下的 feedback.json（_IsolatedEnv 已设好环境变量）
        if os.path.isfile(fbm.feedback_file()):
            os.unlink(fbm.feedback_file())
        for cpu, cpuz, cores, players in (("i9-14900K", 950, 24, 18),
                                          ("R7 7800X3D", 790, 8, 20),
                                          ("i5-13600K", 820, 14, 22)):
            item, errs, _ = fbm.validate({
                "cpu": cpu, "cpuz_single": cpuz, "cores": cores, "players": players,
                "tps": 19.3, "playstyle": "整合包", "modpack_name": "PACK-X",
                "mods": 400, "modpack_kind": "综合（科技+魔法+任务）",
                "progress": "大后期 / 长期服", "bottleneck": "cpu", "ram": "64G"})
            check_true(f"{cpu} 反馈合法", item is not None and not errs, str(errs))
            fbm.append_feedback(item)
        summ = fbm.summarize_packs()
        check("按包汇总有 1 个包", len(summ["packs"]), 1)
        entry = list(summ["packs"].values())[0]
        check_true("反推出建议系数", 0 < entry["suggested_factor"] <= 8,
                   str(entry["suggested_factor"]))
        check("mods 瓶颈不再被跳过", entry["samples"], 3)
        applied = fbm.apply_pack_suggestions(summ, min_samples=3)
        check("写入档案成功", len(applied), 1)
        check_true("档案里出现 PACK-X",
                   any(p.name == "PACK-X" for p in mp.list_profiles()),
                   str([p.name for p in mp.list_profiles()]))
        # 样本不足时不写
        summ2 = fbm.summarize_packs()
        for name, s in summ2["packs"].items():
            s["samples"] = 1
        check("样本不足不写入", fbm.apply_pack_suggestions(summ2, min_samples=3), {})


def test_reset() -> None:
    print("\n== 恢复默认 ==")
    import os
    import shutil

    from . import reset as rs

    # 用工作区内的临时目录：贴近真实用法（数据文件就在工作区里）
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmpdir = os.path.join(here, "_selftest_reset")
    shutil.rmtree(tmpdir, ignore_errors=True)
    os.makedirs(tmpdir, exist_ok=True)
    paths = {
        "MC_CALC_FEEDBACK": os.path.join(tmpdir, "feedback.json"),
        "MC_CALC_CUSTOM_CPUS": os.path.join(tmpdir, "custom_cpus.json"),
        "MC_CALC_MODPACKS": os.path.join(tmpdir, "modpack_profiles.json"),
        "MC_CALC_BEHAVIOR": os.path.join(tmpdir, "behavior_multiplier.json"),
    }
    old_env = {k: os.environ.get(k) for k in paths}
    os.environ.update(paths)
    try:
        # 1) 造数据：三个文件
        for key in ("MC_CALC_FEEDBACK", "MC_CALC_CUSTOM_CPUS", "MC_CALC_MODPACKS"):
            with open(paths[key], "w", encoding="utf-8") as fh:
                fh.write("{}\n")

        state = rs.inspect_state()
        by_key = {x["key"]: x for x in state}
        check_true("状态能识别出用户数据文件", by_key["feedback"]["exists"],
                   by_key["feedback"]["path"])
        check_true("状态能识别出校准产物文件", by_key["modpacks"]["exists"])
        check_true("状态里区分了 kind",
                   {by_key["feedback"]["kind"], by_key["modpacks"]["kind"]} == {"user", "derived"},
                   str((by_key["feedback"]["kind"], by_key["modpacks"]["kind"])))
        check_true("每一项都带说明", all(x["hint"] for x in by_key.values()))

        # 2) 预演不能真的删
        rep = rs.reset(dry_run=True)
        check("预演标记为 dry_run", rep.dry_run, True)
        check_true("预演也不动文件",
                   all(os.path.isfile(paths[k]) for k in
                       ("MC_CALC_FEEDBACK", "MC_CALC_CUSTOM_CPUS", "MC_CALC_MODPACKS")),
                   "预演把文件删了")

        # 3) 只清用户数据 → 校准产物必须保留
        rep = rs.reset_user_data()
        cleared_keys = {c["key"] for c in rep.cleared}
        check("只清了用户数据", cleared_keys, {"custom_cpus", "feedback"})
        check_true("用户数据文件已不在", not os.path.isfile(paths["MC_CALC_FEEDBACK"]))
        check_true("校准产物仍保留", os.path.isfile(paths["MC_CALC_MODPACKS"]))
        check("备份数等于清除数", len(rep.backups), len(rep.cleared))
        check_true("备份文件确实存在", all(os.path.isfile(b) for b in rep.backups),
                   str(rep.backups))

        # 4) 整组撤销要把这一组都还原
        stamp = rs.backup_stamp(rep.backups[0])
        check_true("能从备份名取出时间戳", len(stamp) == 15, stamp)
        groups = rs.backup_groups()
        check("备份按时间戳成组", len(groups.get(stamp, [])), len(rep.cleared))
        restored = rs.restore_group(stamp)
        check("整组撤销数量", len(restored), len(rep.cleared))
        check_true("撤销后文件回来了", os.path.isfile(paths["MC_CALC_FEEDBACK"]))
        check("撤销后备份清空", rs.backup_groups(), {})

        # 5) 撤销非法时间戳要报错，而不是静默
        try:
            rs.restore_group("19700101-000000")
            check("非法时间戳被拒", False, "居然没报错")
        except (ValueError, OSError) as exc:
            check_true("非法时间戳被拒", True, str(exc)[:40])

        # 6) 无备份时删除备份返回 0
        check("没有备份时清理返回 0", rs.delete_backups(), 0)

        # 7) 关掉备份（不可撤销模式）也能工作
        rep2 = rs.reset(backup_first=False)
        check_true("不备份模式也清除", len(rep2.cleared) >= 1, str(len(rep2.cleared)))
        check("不备份模式无备份文件", rep2.backups, [])
        check_true("不备份模式下没有 .bak 残留",
                   not any(f.endswith(".bak") for f in os.listdir(tmpdir)),
                   str(os.listdir(tmpdir)))

        # 8) 一次恢复默认碰多个文件时，时间戳应便于整组撤销
        with open(paths["MC_CALC_FEEDBACK"], "w", encoding="utf-8") as fh:
            fh.write("{}\n")
        with open(paths["MC_CALC_CUSTOM_CPUS"], "w", encoding="utf-8") as fh:
            fh.write("{}\n")
        rep3 = rs.reset()
        stamps = {rs.backup_stamp(b) for b in rep3.backups}
        check("同一次恢复默认只产生一个时间戳", len(stamps), 1)
        check("该组包含全部被清项", rs.backup_groups()[stamps.pop()].__len__(),
              len(rep3.cleared))
    finally:
        for key, old in old_env.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        shutil.rmtree(tmpdir, ignore_errors=True)
        from . import modpack
        modpack.PROFILES.clear()
        modpack.load_profiles()


def run() -> int:
    print("Minecraft 人数上限计算器 — 框架自检")
    print("网络档位：", list(NETWORK_PRESETS))
    test_parsers()
    test_cpu()
    test_bucket_principle()
    test_monotonic_and_edges()
    test_cooling()
    test_speedtest_inputs()
    test_cpuz_and_custom_cpu()
    test_modpack_profiles()
    test_feedback()
    test_reset()
    test_params_override()
    test_parse_raw_pipeline()
    print("\n" + ("全部通过 ✅" if not _FAILURES else f"失败 {len(_FAILURES)} 项 ❌: {_FAILURES}"))
    return 1 if _FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(run())
