"""本地图形界面（tkinter，Python 标准库，无需联网、无需安装依赖）。

    python -m mc_player_calc.gui
"""

from __future__ import annotations

import os
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from typing import Optional

from . import __version__
from .cooling import (DESKTOP_COOLING, LAPTOP_CHASSIS, THERMAL_MATERIAL, chassis_options,
                      suffix_of)
from .cpu_data import (add_custom_cpu, all_models, custom_cpu_file, custom_models,
                       remove_custom_cpu, resolve_platform, save_custom_cpus)
from .feedback import (BOTTLENECKS, MC_VERSIONS, MODPACK_KINDS, OPTIMIZATION_LEVELS,
                       PLAYSTYLES, PROGRESS_STAGES)
from .feedback import SERVER_SOFTWARE as FB_SOFTWARE
from .feedback import append_feedback, feedback_file, stats_overview, summarize, validate
from .engine import CalcInput, CalcResult, calculate
from .parser import (NETWORK_PRESETS, PLAYER_BEHAVIORS, PLAYER_SIM, VIEW_DISTANCES,
                     RawInput, parse_raw, resolve_cooling, resolve_cpu)
from .report import render

BG = "#1e2229"
PANEL = "#272c35"
FG = "#e8eaed"
ACCENT = "#4caf50"
WARN = "#ffb300"
DIM = "#9aa0a6"
SPEEDTEST_URL = "https://test.ustc.edu.cn/"


class App(ttk.Frame):
    def __init__(self, master: tk.Misc):
        super().__init__(master, padding=12)
        self.grid(row=0, column=0, sticky="nsew")
        master.rowconfigure(0, weight=1)
        master.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        self.vars = {
            "mod_count": tk.StringVar(value="0"),
            "cpu": tk.StringVar(value=os.environ.get("MC_CALC_INIT_CPU", "Ryzen 5 5600")),
            "ram": tk.StringVar(value="8G"),
            "network": tk.StringVar(value=list(NETWORK_PRESETS)[2]),
            "bandwidth": tk.StringVar(value=""),
            "download": tk.StringVar(value=""),
            "latency": tk.StringVar(value=""),
            "loss": tk.StringVar(value=""),
            "behavior": tk.StringVar(value=PLAYER_BEHAVIORS[0]),
            "player_sim": tk.StringVar(value=PLAYER_SIM[0]),
            "view_distance": tk.StringVar(value="10"),
            "modpack": tk.StringVar(value=""),
            # 散热：platform 留空 = 按 CPU 型号自动识别
            "platform": tk.StringVar(value=""),
            "chassis": tk.StringVar(value=""),
            "material": tk.StringVar(value=""),
            "radiator": tk.StringVar(value=""),
            "cooling_override": tk.StringVar(value=""),
        }
        self.last_result: Optional[CalcResult] = None
        self._platform_now = "desktop"
        self._cool_note = tk.StringVar(value="桌面 CPU：散热系数默认 1.00（可改散热器档位）")

        self._build_header()
        self._build_form()
        self._build_output()
        self._sync_cooling_ui()
        self._on_calc()

    # ------------------------------------------------------------------
    # 构建界面
    # ------------------------------------------------------------------
    def _build_header(self) -> None:
        head = ttk.Frame(self)
        head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Label(head, text="Minecraft 服务器人数上限计算器", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            head,
            text="木桶效应：四类资源各自算出可承载人数，取最小值作为上限",
            style="Dim.TLabel",
        ).pack(anchor="w")

    def _build_form(self) -> None:
        box = ttk.LabelFrame(self, text=" 输入参数 ", padding=10)
        box.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        box.columnconfigure(1, weight=1)

        row = 0

        def label(text: str, hint: str = "") -> None:
            nonlocal row
            ttk.Label(box, text=text).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 6))
            if hint:
                ttk.Label(box, text=hint, style="Dim.TLabel").grid(
                    row=row, column=2, sticky="w", pady=4, padx=(6, 0))

        row += 1
        label("① 模组数量", "服务端模组数")
        ttk.Entry(box, textvariable=self.vars["mod_count"], width=14).grid(
            row=row, column=1, sticky="ew", pady=4)

        row += 1
        label("② CPU 型号", "可输入可下拉")
        cpu_row = ttk.Frame(box)
        cpu_row.grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)
        cpu_row.columnconfigure(0, weight=1)
        self._cpu_box = ttk.Combobox(cpu_row, textvariable=self.vars["cpu"],
                                     values=all_models(), width=14)
        self._cpu_box.grid(row=0, column=0, sticky="ew")
        ttk.Button(cpu_row, text="录入型号", width=8,
                   command=self._open_cpu_editor).grid(row=0, column=1, padx=(6, 0))

        row += 1
        label("", "CPU-Z 单核分对照")
        self._cpu_score_note = tk.StringVar(value="")
        ttk.Label(box, textvariable=self._cpu_score_note, style="Dim.TLabel",
                  wraplength=330, justify="left").grid(row=row, column=1, columnspan=2,
                                                       sticky="w", pady=(0, 2))

        row += 1
        label("③ 内存大小", "16G / 16384MB")
        ttk.Entry(box, textvariable=self.vars["ram"], width=14).grid(
            row=row, column=1, sticky="ew", pady=4)

        row += 1
        label("④ 网络状况", "决定默认带宽")
        ttk.Combobox(box, textvariable=self.vars["network"], values=list(NETWORK_PRESETS),
                     state="readonly", width=14).grid(row=row, column=1, sticky="ew", pady=4)

        for key, text, hint in (
            ("bandwidth", "上行 Mbps", "填了就用实测值"),
            ("download", "下行 Mbps", "仅记录不参与计算"),
            ("latency", "延迟 ms", "留空用档位默认"),
            ("loss", "丢包率 %", "留空用档位默认"),
        ):
            row += 1
            label(text, hint)
            ttk.Entry(box, textvariable=self.vars[key], width=14).grid(
                row=row, column=1, sticky="ew", pady=4)

        row += 1
        label("不知道上行？", "调用本机默认浏览器")
        speed_row = ttk.Frame(box)
        speed_row.grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)
        ttk.Button(speed_row, text="测速（中国科技大学测速网）",
                   command=self._on_speedtest).pack(side="left")

        ttk.Separator(box, orient="horizontal").grid(
            row=row + 1, column=0, columnspan=3, sticky="ew", pady=8)
        row += 2

        # ---------------- 散热系数 ----------------
        row += 1
        ttk.Label(box, text="散热系数（CPU 单核得分乘数）", style="Section.TLabel").grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(0, 2))

        row += 1
        label("平台识别", "留空按型号自动")
        ttk.Combobox(box, textvariable=self.vars["platform"],
                     values=["", "桌面端（台式机 / 服务器）", "移动端（笔记本）"],
                     state="readonly", width=14).grid(row=row, column=1, sticky="ew", pady=4)
        self._row_platform = row

        row += 1
        label("桌面散热器", "仅桌面端生效")
        self._radiator_box = ttk.Combobox(box, textvariable=self.vars["radiator"],
                                          values=list(DESKTOP_COOLING), state="readonly", width=14)
        self._radiator_box.grid(row=row, column=1, sticky="ew", pady=4)
        self._row_radiator = row

        row += 1
        label("笔记本模具", "仅移动端生效")
        self._chassis_box = ttk.Combobox(box, textvariable=self.vars["chassis"],
                                         values=list(LAPTOP_CHASSIS), state="readonly", width=14)
        self._chassis_box.grid(row=row, column=1, sticky="ew", pady=4)
        self._row_chassis = row

        row += 1
        label("导热耗材", "仅移动端生效")
        self._material_box = ttk.Combobox(box, textvariable=self.vars["material"],
                                          values=list(THERMAL_MATERIAL), state="readonly", width=14)
        self._material_box.grid(row=row, column=1, sticky="ew", pady=4)
        self._row_material = row

        row += 1
        label("自定义总系数", "填写后覆盖上面")
        ttk.Entry(box, textvariable=self.vars["cooling_override"], width=14).grid(
            row=row, column=1, sticky="ew", pady=4)

        row += 1
        self._cool_note_label = ttk.Label(box, textvariable=self._cool_note, style="Dim.TLabel",
                                          wraplength=330, justify="left")
        self._cool_note_label.grid(row=row, column=0, columnspan=3, sticky="w", pady=(2, 0))

        for key, text, values in (
            ("behavior", "玩法类型", PLAYER_BEHAVIORS),
            ("player_sim", "每玩家负载", PLAYER_SIM),
            ("view_distance", "视距（区块）", VIEW_DISTANCES),
        ):
            row += 1
            label(text)
            ttk.Combobox(box, textvariable=self.vars[key], values=values, state="readonly",
                         width=14).grid(row=row, column=1, sticky="ew", pady=4)
            if key == "behavior":
                self._behavior_box = box.grid_slaves(row=row, column=1)[0]

        # 整合包名称：手动输入（自由文本），决定用哪个包的专属系数
        row += 1
        label("整合包名称", "手动输入，仅整合包用")
        ttk.Entry(box, textvariable=self.vars["modpack"], width=14).grid(
            row=row, column=1, sticky="ew", pady=4)
        self._pack_row = row
        row += 1
        self._pack_note = tk.StringVar(value="")
        ttk.Label(box, textvariable=self._pack_note, style="Dim.TLabel",
                  wraplength=330, justify="left").grid(row=row, column=1, columnspan=2,
                                                       sticky="w", pady=(0, 2))
        self._pack_note_row = row

        btns = ttk.Frame(box)
        btns.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        ttk.Button(btns, text="计算（Enter）", command=self._on_calc, style="Accent.TButton").pack(
            side="left")
        ttk.Button(btns, text="重置", command=self._on_reset).pack(side="left", padx=6)
        ttk.Button(btns, text="复制结果", command=self._on_copy).pack(side="left")
        ttk.Button(btns, text="服主反馈", command=self._open_feedback_dialog).pack(side="left",
                                                                                padx=6)
        ttk.Button(btns, text="恢复默认", command=self._open_reset_dialog).pack(side="left")
        self.bind_all("<Return>", lambda _e: self._on_calc())
        # CPU 型号一变就重新判定平台、刷新散热选项与 CPU-Z 对照
        self.vars["cpu"].trace_add("write", lambda *_: self._on_cpu_changed())
        for key in ("platform", "chassis", "material", "radiator", "cooling_override"):
            self.vars[key].trace_add("write", lambda *_: self._refresh_cooling_note())
        self._refresh_cpu_score_note()
        # 玩法/包名一变就刷新整合包系数提示
        self.vars["behavior"].trace_add("write", lambda *_: self._refresh_pack_note())
        self.vars["modpack"].trace_add("write", lambda *_: self._refresh_pack_note())
        self._refresh_pack_note()

    # ------------------------------------------------------------------
    # 整合包名称（一个包一套系数）
    # ------------------------------------------------------------------
    def _refresh_pack_note(self) -> None:
        if not hasattr(self, "_pack_note"):
            return
        if self.vars["behavior"].get() != "整合包":
            self._pack_note.set("（仅「整合包」玩法会用到包名）")
            return
        name = self.vars["modpack"].get().strip()
        try:
            from .modpack import MODPACK_BASE_FACTOR, resolve_pack_factor
        except Exception:
            self._pack_note.set("")
            return
        if not name:
            self._pack_note.set(f"填包名后按该包自己的系数；不填则按兜底 {MODPACK_BASE_FACTOR:g}")
            return
        factor, why = resolve_pack_factor(name)
        self._pack_note.set(f"负载系数 {factor:.2f} ← {why}")

    # ------------------------------------------------------------------
    # CPU-Z 分数对照 + 自定义型号录入
    # ------------------------------------------------------------------
    def _on_cpu_changed(self) -> None:
        self._sync_cooling_ui()
        self._refresh_cpu_score_note()

    def _refresh_cpu_score_note(self) -> None:
        """显示当前型号的 CPU-Z 单核分，方便跟自己在 CPU-Z 里测到的数对照。"""
        text = self.vars["cpu"].get().strip()
        if not text:
            self._cpu_score_note.set("")
            return
        spec = resolve_cpu(text)
        if "未收录" in spec.name or "估算" in spec.name:
            self._cpu_score_note.set(
                f"库里没有该型号，按 {spec.cores} 核 / CPU-Z ≈ {spec.cpuz_score:.0f} 分保守估算\n"
                f"建议点「录入型号」填你自己的 CPU-Z 单核跑分")
            return
        origin = "自定义" if spec.custom else "内置估算"
        self._cpu_score_note.set(
            f"{spec.name}：CPU-Z 单核 ≈ {spec.cpuz_score:.0f} 分（{origin}，{spec.cores} 核）")

    def _open_cpu_editor(self) -> None:
        """弹出一个录入窗口：型号 + CPU-Z 单核分 + 核心数 + 平台。"""
        win = tk.Toplevel(self)
        win.title("录入自定义 CPU 型号")
        win.configure(bg=BG)
        win.transient(self.winfo_toplevel())
        win.geometry("560x460")
        win.minsize(520, 420)

        tip = ttk.Label(
            win, style="Dim.TLabel", wraplength=510, justify="left",
            text="在 CPU-Z 里跑一下 Bench → CPU Single Thread，把那个分数填进来即可。\n"
                 "保存后会写入 custom_cpus.json，并自动选用这个型号重新计算。")
        tip.pack(anchor="w", padx=14, pady=(12, 6))

        fields = ttk.Frame(win)
        fields.pack(fill="x", padx=14)
        fields.columnconfigure(1, weight=1)

        v_name = tk.StringVar()
        v_cpuz = tk.StringVar()
        v_cores = tk.StringVar(value="4")
        v_plat = tk.StringVar(value="自动识别")
        v_note = tk.StringVar()

        rows = (
            ("型号名称", v_name, "如 Ryzen 7 5800X3D 开PBO"),
            ("CPU-Z 单核分", v_cpuz, "如 690"),
            ("物理核心数", v_cores, "如 8"),
            ("备注（可选）", v_note, "如 自测，室温 25℃"),
        )
        for i, (text, var, hint) in enumerate(rows):
            ttk.Label(fields, text=text).grid(row=i, column=0, sticky="w", pady=5, padx=(0, 8))
            ttk.Entry(fields, textvariable=var).grid(row=i, column=1, sticky="ew", pady=5)

        ttk.Label(fields, text="平台").grid(row=len(rows), column=0, sticky="w", pady=5)
        ttk.Combobox(fields, textvariable=v_plat, state="readonly",
                     values=["自动识别", "桌面端（台式机 / 服务器）", "移动端（笔记本）"]
                     ).grid(row=len(rows), column=1, sticky="ew", pady=5)

        hint_var = tk.StringVar()
        ttk.Label(win, textvariable=hint_var, style="Dim.TLabel", wraplength=510,
                  justify="left").pack(anchor="w", padx=14, pady=(6, 0))

        ttk.Label(win, text="已录入的自定义型号：").pack(anchor="w", padx=14, pady=(10, 2))
        list_frame = ttk.Frame(win)
        list_frame.pack(fill="both", expand=True, padx=14)
        listbox = tk.Listbox(list_frame, bg=PANEL, fg=FG, selectbackground="#2f6f3a",
                             relief="flat", highlightthickness=0, height=6)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scroll.set)
        listbox.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        def refresh_list() -> None:
            listbox.delete(0, "end")
            for s in custom_models():
                listbox.insert("end", f"{s.name}  |  CPU-Z {s.cpuz_score:.0f}  |  "
                                      f"{s.cores} 核  |  指数 {s.score:.1f}  |  {s.platform}")
            if not custom_models():
                listbox.insert("end", "（还没有自定义型号）")

        def do_save() -> None:
            try:
                spec = add_custom_cpu(
                    v_name.get(), v_cpuz.get(), v_cores.get() or 4,
                    platform=("mobile" if v_plat.get().startswith("移动") else
                              "desktop" if v_plat.get().startswith("桌面") else ""),
                    note=v_note.get(),
                )
            except ValueError as exc:
                hint_var.set(f"⚠ {exc}")
                return
            except OSError as exc:
                hint_var.set(f"⚠ 保存失败：{exc}")
                return
            path = save_custom_cpus()
            self._cpu_box.configure(values=all_models())
            refresh_list()
            self.vars["cpu"].set(spec.name)
            self._on_calc()
            hint_var.set(f"✅ 已保存「{spec.name}」：CPU-Z {spec.cpuz_score:.0f} → "
                         f"内部指数 {spec.score:.1f}，已自动选用\n文件：{path}")

        def do_delete() -> None:
            sel = listbox.curselection()
            if not sel or not custom_models():
                hint_var.set("先在下面选中一条要删除的型号")
                return
            name = custom_models()[sel[0]].name
            remove_custom_cpu(name)
            save_custom_cpus()
            self._cpu_box.configure(values=all_models())
            refresh_list()
            hint_var.set(f"已删除「{name}」")
            if self.vars["cpu"].get() == name:
                self.vars["cpu"].set("Ryzen 5 5600")
                self._on_calc()

        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=14, pady=(10, 14))
        ttk.Button(btns, text="保存并选用", style="Accent.TButton",
                   command=do_save).pack(side="left")
        ttk.Button(btns, text="删除选中", command=do_delete).pack(side="left", padx=6)
        ttk.Button(btns, text="关闭", command=win.destroy).pack(side="left")

        refresh_list()
        hint_var.set(f"自定义型号文件：{custom_cpu_file()}")
        win.bind("<Return>", lambda _e: do_save())
        v_name.trace_add("write", lambda *_: None)
        win.focus_set()

    # ------------------------------------------------------------------
    # 散热联动
    # ------------------------------------------------------------------
    def _current_cooling(self):
        """按当前界面选择解析出散热配置，返回 (config, 警告列表)。"""
        cpu = resolve_cpu(self.vars["cpu"].get())
        return resolve_cooling(
            cpu,
            platform_raw=self.vars["platform"].get(),
            chassis=self.vars["chassis"].get(),
            material=self.vars["material"].get(),
            radiator=self.vars["radiator"].get(),
            override=self.vars["cooling_override"].get(),
        )

    def _sync_cooling_ui(self) -> None:
        """根据 CPU 是否移动端，显示对应的散热选项（模具+导热 / 散热器）。"""
        cpu = resolve_cpu(self.vars["cpu"].get())
        mobile = resolve_platform(cpu) == "mobile"
        suffix = suffix_of(cpu.name) if mobile else ""
        self._platform_now = "mobile" if mobile else "desktop"

        options = chassis_options(suffix) if mobile else []
        self._chassis_box.configure(values=options or list(LAPTOP_CHASSIS))
        # 只补默认值，不覆盖用户已选的档位（用户选择优先，不符时由提示告知）
        if mobile and self.vars["chassis"].get() not in list(LAPTOP_CHASSIS):
            self.vars["chassis"].set(options[0] if options else "")
        if not self.vars["material"].get():
            self.vars["material"].set(list(THERMAL_MATERIAL)[0])
        if not self.vars["radiator"].get():
            self.vars["radiator"].set(list(DESKTOP_COOLING)[1])

        # 显隐：移动端显示模具+导热，桌面端显示散热器
        if mobile:
            self._radiator_box.grid_remove()
            self._chassis_box.grid()
            self._material_box.grid()
        else:
            self._chassis_box.grid_remove()
            self._material_box.grid_remove()
            self._radiator_box.grid()

        self._refresh_cooling_note()

    def _refresh_cooling_note(self) -> None:
        """按当前选项刷新散热说明（每次点击计算、切换 CPU、切换档位都会调用）。"""
        cfg, warns = self._current_cooling()
        if cfg.platform == "mobile":
            suf = suffix_of(resolve_cpu(self.vars["cpu"].get()).name)
            note = (f"检测到移动端型号（后缀 {suf or '未知'}）："
                    f"散热系数 = 模具 {cfg.chassis_coef():.3f} × 导热 {cfg.material_coef():.3f}"
                    f" = {cfg.factor():.3f}")
            if cfg.override is not None:
                note = f"已使用自定义总散热系数 {cfg.factor():.3f}（覆盖模具与导热）"
            else:
                note += "\n笔记本实际性能还取决于温度墙与功耗墙，模具档位误差影响很大"
        else:
            note = f"桌面端型号：散热系数 {cfg.factor():.3f}（{cfg.radiator}）"
            if cfg.override is not None:
                note = f"已使用自定义总散热系数 {cfg.factor():.3f}"
        if warns:
            note += "\n⚠ " + warns[0]
        self._cool_note.set(note)

    def _build_output(self) -> None:
        box = ttk.Frame(self)
        box.grid(row=1, column=1, sticky="nsew")
        box.rowconfigure(2, weight=1)
        box.columnconfigure(0, weight=1)

        score = ttk.Frame(box, style="Panel.TFrame", padding=12)
        score.grid(row=0, column=0, sticky="ew")
        score.columnconfigure(1, weight=1)
        self.verdict = ttk.Label(score, text="— 人", style="Score.TLabel")
        self.verdict.grid(row=0, column=0, sticky="w")
        self.verdict_note = ttk.Label(score, text="", style="Dim.TLabel", justify="left")
        self.verdict_note.grid(row=0, column=1, sticky="w", padx=12)

        ttk.Label(box, text="各维度可承载人数（最小值即上限）").grid(
            row=1, column=0, sticky="w", pady=(10, 4))

        cols = ("factor", "ceiling", "load", "status")
        self.tree = ttk.Treeview(box, columns=cols, show="headings", height=5)
        for col, text, width in (
            ("factor", "维度", 130), ("ceiling", "可承载", 82),
            ("load", "占用率", 74), ("status", "状态", 92),
        ):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor="center")
        self.tree.grid(row=2, column=0, sticky="nsew")
        self.tree.tag_configure("bottleneck", foreground="#ff6b6b")
        self.tree.tag_configure("near", foreground=WARN)

        # width=60 仅作为"请求宽度"的下限，避免长文本把窗口撑宽（靠 wrap 换行）
        self.detail = tk.Text(box, height=14, width=58, bg=PANEL, fg=FG, insertbackground=FG,
                              relief="flat", wrap="word", padx=10, pady=8)
        self.detail.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        box.rowconfigure(3, weight=2)

    # ------------------------------------------------------------------
    # 行为
    # ------------------------------------------------------------------
    def _raw(self) -> RawInput:
        return RawInput(**{k: v.get() for k, v in self.vars.items()})

    def _on_calc(self) -> None:
        raw = self._raw()
        try:
            fields, warnings = parse_raw(raw)
            result = calculate(CalcInput(**fields))
        except Exception as exc:  # 不让界面崩掉
            self.verdict.configure(text="输入有误", foreground="#ff6b6b")
            self.verdict_note.configure(text=str(exc))
            return
        result.warnings = warnings + result.warnings
        self.last_result = result
        self._refresh_cooling_note()
        self._render(result)

    def _render(self, res: CalcResult) -> None:
        self.verdict.configure(text=f"{res.final_players} 人", foreground=ACCENT)

        binding = [f.label for f in res.factors if f.is_bottleneck]
        note = "瓶颈：" + "、".join(binding) if binding else "未识别到瓶颈"
        note += f"\n估算 TPS ≈ {res.tps_estimate:.1f}（目标 20）"
        if res.warnings:
            note += "\n⚠ " + res.warnings[0]
        self.verdict_note.configure(text=note)

        self.tree.delete(*self.tree.get_children())
        for f in sorted(res.factors, key=lambda x: x.ceiling):
            status = "瓶颈" if f.is_bottleneck else ("接近瓶颈" if f.near_bottleneck else "余量充足")
            tag = "bottleneck" if f.is_bottleneck else ("near" if f.near_bottleneck else "")
            self.tree.insert("", "end", tags=(tag,), values=(
                f.label, f"{f.ceiling:.1f} 人", f"{f.load_at_final * 100:.0f}%", status))

        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("end", render(res, show_formulas=True))
        self.detail.configure(state="disabled")

    def _on_reset(self) -> None:
        defaults = {
            "mod_count": "0", "cpu": "Ryzen 5 5600", "ram": "8G",
            "network": list(NETWORK_PRESETS)[2], "bandwidth": "", "download": "",
            "latency": "", "loss": "",
            "behavior": PLAYER_BEHAVIORS[0], "player_sim": PLAYER_SIM[0], "view_distance": "10",
            "platform": "", "chassis": "", "material": "", "radiator": "", "cooling_override": "",
        }
        for k, v in defaults.items():
            self.vars[k].set(v)
        self._sync_cooling_ui()
        self._on_calc()

    def _on_copy(self) -> None:
        if not self.last_result:
            return
        self.clipboard_clear()
        self.clipboard_append(render(self.last_result, show_formulas=False))
        self.verdict_note.configure(text="结果已复制到剪贴板")

    def _on_speedtest(self, url: str = SPEEDTEST_URL) -> None:
        """用本机默认浏览器打开测速网，测完把上行填进「上行 Mbps」。"""
        try:
            ok = webbrowser.open(url)
        except Exception as exc:  # 浏览器缺失等情况不要让界面崩
            ok = False
            self.verdict_note.configure(text=f"打开浏览器失败：{exc}")
        if ok:
            self.verdict_note.configure(
                text=f"已打开测速网：{url}\n测完把上行 Mbps 填到「上行 Mbps」，下行填「下行 Mbps」")
        else:
            self.verdict_note.configure(text=f"未找到默认浏览器，请手动访问：{url}")

    # ------------------------------------------------------------------
    # 本地状态 / 恢复默认
    # ------------------------------------------------------------------
    def _open_reset_dialog(self) -> None:
        """查看本地数据文件，并可恢复默认（默认先备份，可整组撤销）。"""
        from .reset import inspect_state

        win = tk.Toplevel(self.winfo_toplevel())
        win.title("本地状态 / 恢复默认")
        win.transient(self.winfo_toplevel())
        win.geometry("640x600")
        win.minsize(560, 480)

        ttk.Label(win, text="本地状态", style="Section.TLabel").pack(anchor="w", padx=14,
                                                                    pady=(12, 2))
        ttk.Label(win, wraplength=600, justify="left", style="Dim.TLabel",
                  text="所有数据都在你自己机器上。恢复默认会先把文件改名成 "
                       "「原名.时间戳.bak」，可以整组撤销，不会直接销毁。"
                       "★ 恢复前建议先点反馈面板里的「导出」保存一份。").pack(
            anchor="w", padx=14)

        body = ttk.Frame(win)
        body.pack(fill="both", expand=True, padx=14, pady=(8, 0))
        listbox = tk.Listbox(body, activestyle="none")
        scroll = ttk.Scrollbar(body, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scroll.set)
        listbox.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        vars_ = {
            "user": tk.BooleanVar(value=True),
            "derived": tk.BooleanVar(value=True),
            "exports": tk.BooleanVar(value=False),
        }
        hint_var = tk.StringVar(value="")

        def refresh() -> None:
            listbox.delete(0, "end")
            for x in inspect_state():
                mark = "有 " if x["exists"] else "—  "
                detail = f"　{x['detail']}" if x["detail"] else ""
                listbox.insert("end", f"[{mark}] {x['label']}（{x['kind']}）{detail}")
                listbox.insert("end", f"        {x['path']}")
            hint_var.set("")

        opts = ttk.LabelFrame(win, text=" 要恢复的内容 ", padding=10)
        opts.pack(fill="x", padx=14, pady=(10, 0))
        ttk.Checkbutton(opts, text="用户数据（自定义 CPU 型号、服主反馈）",
                        variable=vars_["user"]).pack(anchor="w")
        ttk.Checkbutton(opts, text="校准产物（玩法系数、整合包档案）",
                        variable=vars_["derived"]).pack(anchor="w")
        ttk.Checkbutton(opts, text="导出文件（json / csv / md，删掉无影响）",
                        variable=vars_["exports"]).pack(anchor="w")

        def do_reset() -> None:
            from .reset import reset

            keys = []
            if vars_["user"].get():
                keys += ["custom_cpus", "feedback"]
            if vars_["derived"].get():
                keys += ["behavior", "modpacks"]
            if not keys and not vars_["exports"].get():
                hint_var.set("⚠ 请至少勾选一项。")
                return
            if not messagebox.askyesno(
                    "确认恢复默认",
                    "将恢复默认（先把文件备份成 .bak，可整组撤销）：\n\n"
                    + ("· 用户数据（自定义 CPU、服主反馈）\n" if vars_["user"].get() else "")
                    + ("· 校准产物（玩法系数、整合包档案）\n" if vars_["derived"].get() else "")
                    + ("· 导出文件\n" if vars_["exports"].get() else "")
                    + "\n★ 确定要继续吗？", parent=win):
                return
            report = reset(keys, backup_first=True,
                           include_exports=vars_["exports"].get())
            refresh()
            hint_var.set("已恢复默认：\n" + report.render())

        def do_undo() -> None:
            from .reset import backup_groups, restore_group

            groups = backup_groups()
            if not groups:
                hint_var.set("没有可撤销的备份。")
                return
            stamp = next(iter(groups))
            if not messagebox.askyesno("整组撤销",
                                       f"把 {stamp} 这组备份（{len(groups[stamp])} 个文件）"
                                       f"全部还原？", parent=win):
                return
            try:
                restored = restore_group(stamp)
            except OSError as exc:
                hint_var.set(f"⚠ 撤销失败：{exc}")
                return
            refresh()
            hint_var.set("已整组还原：\n" + "\n".join(os.path.basename(r) for r in restored))

        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=14, pady=(10, 4))
        ttk.Button(btns, text="刷新", command=refresh).pack(side="left")
        ttk.Button(btns, text="恢复默认", style="Accent.TButton",
                   command=do_reset).pack(side="left", padx=6)
        ttk.Button(btns, text="撤销上一次", command=do_undo).pack(side="left")
        ttk.Button(btns, text="关闭", command=win.destroy).pack(side="left", padx=6)

        ttk.Label(win, textvariable=hint_var, wraplength=600, justify="left",
                  style="Dim.TLabel").pack(anchor="w", padx=14, pady=(4, 10))
        refresh()

    # ------------------------------------------------------------------
    # 服主信息反馈收集
    # ------------------------------------------------------------------
    def _open_feedback_dialog(self) -> None:
        """收集一条服主的真实承载数据（存到 feedback.json）。"""
        win = tk.Toplevel(self.winfo_toplevel())
        win.title("服主信息反馈收集")
        win.configure(bg=BG)
        win.transient(self.winfo_toplevel())
        win.geometry("660x800")
        win.minsize(620, 700)

        head = ttk.Frame(win)
        head.pack(fill="x", padx=14, pady=(12, 4))
        ttk.Label(head, text="填写一条承载数据",
                  style="Section.TLabel").pack(anchor="w")
        ttk.Label(head, style="Dim.TLabel", wraplength=580, justify="left",
                  text="口径：在线人数增长到 TPS 首次跌破 19.5 时的人数。\n"
                       "只有「瓶颈判断 = CPU」的数据才会用于校准 CPU 系数与玩法系数；"
                       "其余会被记录但跳过统计。").pack(anchor="w", pady=(4, 0))

        form = ttk.Frame(win)
        form.pack(fill="x", padx=14)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        v = {k: tk.StringVar() for k in
             ("cpu", "cpuz", "players", "view", "tps", "playstyle", "bottleneck",
              "pack", "mcver", "mods", "kind", "ram", "software", "progress", "opt", "note")}
        v["view"].set("10")
        v["bottleneck"].set("cpu")
        v["playstyle"].set(PLAYER_BEHAVIORS[0])
        v["software"].set(FB_SOFTWARE[0])
        v["progress"].set(list(PROGRESS_STAGES)[1])
        v["kind"].set(list(MODPACK_KINDS)[0])
        v["mcver"].set(MC_VERSIONS[0])
        v["ram"].set("32G")
        v["opt"].set(OPTIMIZATION_LEVELS[0])

        r = 0

        def row2(l1, k1, l2, k2, widget="entry", values=None):
            nonlocal r
            ttk.Label(form, text=l1).grid(row=r, column=0, sticky="w", pady=4, padx=(0, 6))
            if widget == "combo":
                ttk.Combobox(form, textvariable=v[k1], values=values or [],
                             state="readonly", width=14).grid(row=r, column=1, sticky="ew",
                                                              pady=4, padx=(0, 12))
            else:
                ttk.Entry(form, textvariable=v[k1], width=14).grid(row=r, column=1, sticky="ew",
                                                                  pady=4, padx=(0, 12))
            ttk.Label(form, text=l2).grid(row=r, column=2, sticky="w", pady=4, padx=(0, 6))
            if widget == "combo":
                ttk.Combobox(form, textvariable=v[k2], values=values or [],
                             state="readonly", width=14).grid(row=r, column=3, sticky="ew", pady=4)
            else:
                ttk.Entry(form, textvariable=v[k2], width=14).grid(row=r, column=3, sticky="ew",
                                                                   pady=4)
            r += 1

        row2("CPU 型号", "cpu", "CPU-Z 单核分", "cpuz")
        row2("活跃用户", "players", "TPS", "tps")
        row2("区块视距", "view", "内存", "ram", "combo", VIEW_DISTANCES)

        ttk.Label(form, text="玩法").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Combobox(form, textvariable=v["playstyle"], values=PLAYER_BEHAVIORS,
                     state="readonly").grid(row=r, column=1, sticky="ew", pady=4, padx=(0, 12))
        ttk.Label(form, text="瓶颈判断").grid(row=r, column=2, sticky="w", pady=4)
        ttk.Combobox(form, textvariable=v["bottleneck"], values=BOTTLENECKS,
                     state="readonly").grid(row=r, column=3, sticky="ew", pady=4)
        r += 1

        ttk.Label(form, text="进度阶段").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Combobox(form, textvariable=v["progress"], values=list(PROGRESS_STAGES),
                     state="readonly").grid(row=r, column=1, sticky="ew", pady=4, padx=(0, 12))
        ttk.Label(form, text="（只有瓶颈=CPU 的数据参与统计）",
                  style="Dim.TLabel").grid(row=r, column=2, columnspan=2, sticky="w", pady=4)
        r += 1

        # 整合包专属区域
        pack_box = ttk.LabelFrame(win, text=" 整合包补充信息（玩法选「整合包」时填写） ", padding=10)
        pack_box.pack(fill="x", padx=14, pady=(10, 0))
        pack_box.columnconfigure(1, weight=1)
        pack_box.columnconfigure(3, weight=1)

        def prow(i, l1, k1, l2, k2, values=None):
            ttk.Label(pack_box, text=l1).grid(row=i, column=0, sticky="w", pady=4, padx=(0, 6))
            if values:
                ttk.Combobox(pack_box, textvariable=v[k1], values=values, state="readonly",
                             width=14).grid(row=i, column=1, sticky="ew", pady=4, padx=(0, 12))
            else:
                ttk.Entry(pack_box, textvariable=v[k1], width=14).grid(row=i, column=1, sticky="ew",
                                                                      pady=4, padx=(0, 12))
            ttk.Label(pack_box, text=l2).grid(row=i, column=2, sticky="w", pady=4, padx=(0, 6))
            if values:
                ttk.Combobox(pack_box, textvariable=v[k2], values=values, state="readonly",
                             width=14).grid(row=i, column=3, sticky="ew", pady=4)
            else:
                ttk.Entry(pack_box, textvariable=v[k2], width=14).grid(row=i, column=3, sticky="ew",
                                                                      pady=4)

        prow(0, "整合包名称", "pack", "MC 版本", "mcver", MC_VERSIONS)
        prow(1, "模组数量", "mods", "玩法类型", "kind", list(MODPACK_KINDS))

        more = ttk.Frame(win)
        more.pack(fill="x", padx=14, pady=(10, 0))
        more.columnconfigure(1, weight=1)
        ttk.Label(more, text="服务端").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 6))
        ttk.Combobox(more, textvariable=v["software"], values=FB_SOFTWARE, state="readonly",
                     width=18).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(more, text="作者优化状况").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 6))
        ttk.Combobox(more, textvariable=v["opt"], values=OPTIMIZATION_LEVELS,
                     state="readonly", width=18).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(more, text="备注 / 来源").grid(row=2, column=0, sticky="w", pady=4, padx=(0, 6))
        ttk.Entry(more, textvariable=v["note"]).grid(row=2, column=1, sticky="ew", pady=4)

        hint_var = tk.StringVar(value=f"数据文件：{feedback_file()}")
        ttk.Label(win, textvariable=hint_var, style="Dim.TLabel", wraplength=580,
                  justify="left").pack(anchor="w", padx=14, pady=(10, 0))

        stat_var = tk.StringVar()
        ttk.Label(win, textvariable=stat_var, style="Dim.TLabel",
                  justify="left").pack(anchor="w", padx=14)

        def refresh_stats() -> None:
            st = stats_overview()
            parts = " · ".join(f"{k} {n}" for k, n in st["by_playstyle"].items())
            stat_var.set(f"已收集 {st['count']} 条" + (f"（{parts}）" if parts else ""))

        def do_submit() -> None:
            data = {
                "cpu": v["cpu"].get(), "cpuz_single": v["cpuz"].get(),
                "players": v["players"].get(), "view": v["view"].get(),
                "tps": v["tps"].get(), "playstyle": v["playstyle"].get(),
                "bottleneck": v["bottleneck"].get(),
                "modpack_name": v["pack"].get(), "mc_version": v["mcver"].get(),
                "mods": v["mods"].get(), "modpack_kind": v["kind"].get(),
                "ram": v["ram"].get(), "software": v["software"].get(),
                "progress": v["progress"].get(), "note": v["note"].get(),
                "optimization": v["opt"].get(),
            }
            fb, errors, warns = validate(data)
            if errors:
                hint_var.set("⚠ " + "；".join(errors))
                return
            try:
                path, count = append_feedback(fb)
            except OSError as exc:
                hint_var.set(f"⚠ 保存失败：{exc}")
                return
            refresh_stats()
            msg = (f"✅ 已收录：{fb.cpu} / {fb.playstyle} / {fb.players} 人，"
                   f"负载系数 {fb.playstyle_multiplier()}，累计 {count} 条")
            if warns:
                msg = msg + "\n提示：" + warns[0]
            msg = msg + f"\n文件：{path}"
            hint_var.set(msg)
            for key in ("cpu", "cpuz", "players", "tps", "pack", "mods", "note"):
                v[key].set("")

        def do_summary() -> None:
            text = summarize()
            st = text
            lines = [f"累计 {st['total']} 条，可用于统计的分组 {st['usable_groups']} 个", ""]
            for name, s in st["suggested"].items():
                if not s["samples"]:
                    lines.append(f"【{name}】暂无样本（沿用 {s['current_multiplier']}）")
                    continue
                lines.append(f"【{name}】样本 {s['samples']} 条："
                             f"{s['current_multiplier']} → {s['suggested_multiplier']}"
                             + ("　⚠ 样本偏少" if s["samples"] < 3 else ""))
                lines.append(f"    反推明细 {s['values']}")
            for item in st["skipped"][:8]:
                lines.append(f"  跳过 {item['entry']}：{item['reason']}")
            hint_var.set("\n".join(lines))

        def do_export_agent() -> None:
            """导出一份给 agent / 别人看的 Markdown 交付文件。"""
            from .feedback import export_agent_markdown, load_feedback
            if not load_feedback():
                hint_var.set("还没有数据可导出，先提交一条。")
                return
            content = export_agent_markdown(server_owner=v["note"].get() or "")
            path = os.path.join(os.getcwd(), "feedback_agent.md")
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(content)
            except OSError as exc:
                hint_var.set(f"⚠ 导出失败：{exc}")
                return
            hint_var.set(f"✅ 已导出交付文件：{path}\n"
                         f"它自带任务说明、口径定义与待校准参数，直接发给对方即可。")

        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=14, pady=(12, 4))
        ttk.Button(btns, text="提交这条数据", style="Accent.TButton",
                   command=do_submit).pack(side="left")
        ttk.Button(btns, text="查看汇总", command=do_summary).pack(side="left", padx=6)
        ttk.Button(btns, text="导出给 Agent 的文件",
                   command=do_export_agent).pack(side="left", padx=6)
        ttk.Button(btns, text="关闭", command=win.destroy).pack(side="left")

        refresh_stats()
        win.bind("<Return>", lambda _e: do_submit())


def _setup_style(root: tk.Tk) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(".", background=BG, foreground=FG, fieldbackground=PANEL,
                    font=("Microsoft YaHei UI", 10))
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("Dim.TLabel", background=BG, foreground=DIM)
    style.configure("Title.TLabel", font=("Microsoft YaHei UI", 15, "bold"))
    style.configure("Section.TLabel", font=("Microsoft YaHei UI", 10, "bold"), foreground=ACCENT)
    style.configure("Score.TLabel", font=("Microsoft YaHei UI", 30, "bold"), foreground=ACCENT,
                    background=PANEL)
    style.configure("TLabelframe", background=BG, foreground=FG)
    style.configure("TLabelframe.Label", background=BG, foreground=FG)
    style.configure("TEntry", fieldbackground=PANEL, foreground=FG, insertcolor=FG,
                    bordercolor="#3a4150", lightcolor="#3a4150", darkcolor="#3a4150")
    style.map("TEntry", fieldbackground=[("disabled", "#20242b")],
              foreground=[("disabled", DIM)])
    style.configure("TButton", padding=(10, 5), background="#333a45", foreground=FG,
                    bordercolor="#3a4150", focuscolor="#4caf50")
    style.map("TButton", background=[("active", "#3d4552"), ("pressed", "#2b313b")])
    style.configure("Accent.TButton", padding=(10, 5), background="#2f6f3a", foreground="#ffffff")
    style.map("Accent.TButton", background=[("active", "#38844a"), ("pressed", "#276032")])
    # 下拉框：clam 主题下 arrow/field 颜色都要显式指定，否则会出现浅灰底看不清字
    for name in ("TCombobox",):
        style.configure(name, fieldbackground=PANEL, background="#333a45", foreground=FG,
                        arrowcolor=FG, bordercolor="#3a4150", lightcolor="#3a4150",
                        darkcolor="#3a4150", selectbackground=PANEL, selectforeground=FG)
        style.map(name,
                  fieldbackground=[("readonly", PANEL), ("disabled", "#20242b")],
                  foreground=[("readonly", FG), ("disabled", DIM)],
                  background=[("active", "#3d4552"), ("readonly", "#333a45")],
                  selectbackground=[("readonly", PANEL)],
                  selectforeground=[("readonly", FG)],
                  arrowcolor=[("active", ACCENT)])
    root.option_add("*TCombobox*Listbox.background", PANEL)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", "#2f6f3a")
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
    style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG,
                    rowheight=24, bordercolor="#3a4150")
    style.configure("Treeview.Heading", background="#333a45", foreground=FG)
    style.map("Treeview", background=[("selected", "#2f6f3a")])
    style.configure("TSeparator", background="#3a4150")


def main() -> int:
    root = tk.Tk()
    root.title(f"Minecraft 服务器人数上限计算器 v{__version__}")
    root.geometry("1000x850")
    root.minsize(920, 810)
    root.configure(bg=BG)
    _setup_style(root)
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
