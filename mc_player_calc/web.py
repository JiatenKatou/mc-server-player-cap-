"""本地网页界面：用 Python 标准库自带的 HTTP 服务器托管一个单页应用。

设计要点：
- 零依赖：http.server + json + 原生 HTML/CSS/JS，不引入任何第三方包
- 只监听 127.0.0.1，默认端口 8765（被占用时自动换空闲端口），不对外暴露
- 计算仍然复用同一套内核（parser / engine / report），网页与 GUI/CLI 结果完全一致
- 前端资源放在同目录的 web/ 下，按文件后缀给正确 MIME，全部 UTF-8

启动：
    python -m mc_player_calc.web            # 默认 127.0.0.1:8765，自动开浏览器
    python -m mc_player_calc.web --port 9000 --no-browser
"""
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 <请填写你的名字或昵称>
#
# 本文件是「Minecraft 服务器人数上限计算器」的一部分，按 GPL-3.0 授权。
# 完整声明见 mc_player_calc/__init__.py 与项目根目录的 COPYRIGHT。
# 本程序不提供任何担保；输出为模型估算值，不是实测保证。


from __future__ import annotations

import json
import mimetypes
import os
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from . import __version__
from .config import DEFAULT_PARAMS
from .cooling import (DESKTOP_COOLING, LAPTOP_CHASSIS, PLATFORM_CHASSIS_CAP, THERMAL_MATERIAL,
                      chassis_options, suffix_of)
from .cpu_data import (add_custom_cpu, all_models, cpuz_scale_info, custom_cpu_file,
                       custom_models, merged_db, remove_custom_cpu, resolve_platform,
                       save_custom_cpus)
from .engine import CalcInput, CalcResult, calculate
from .parser import (NETWORK_PRESETS, PLAYER_BEHAVIORS, PLAYER_SIM, VIEW_DISTANCES, RawInput,
                     parse_raw, resolve_cooling, resolve_cpu)
from .report import render

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_BODY_BYTES = 64 * 1024

# 允许"由服务端调起浏览器打开"的网址白名单（默认只放测速网，可用环境变量追加）
SPEEDTEST_URL = os.environ.get("MC_CALC_SPEEDTEST_URL", "https://test.ustc.edu.cn/")
_EXTRA_ALLOWED = [u.strip() for u in os.environ.get("MC_CALC_ALLOWED_URLS", "").split(",") if u.strip()]
ALLOWED_OPEN_URLS = [SPEEDTEST_URL, *_EXTRA_ALLOWED]

_MIME_OVERRIDES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".png": "image/png",
}


def is_url_allowed(url: str) -> bool:
    """只允许 http/https，且必须命中白名单（按去掉末尾斜杠的规范化形式比较）。"""
    try:
        parsed = urlparse(url or "")
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    def norm(u: str) -> str:
        return (u or "").rstrip("/").lower()
    target = norm(url)
    return any(target == norm(a) or target.startswith(norm(a) + "/") for a in ALLOWED_OPEN_URLS if a)


# ----------------------------------------------------------------------
# 选项（供前端构建下拉框）
# ----------------------------------------------------------------------
def _cpu_catalog() -> Dict[str, Any]:
    """CPU 下拉数据：按平台分组，并带上是否需要散热细分。"""
    desktop: List[Dict[str, Any]] = []
    mobile: List[Dict[str, Any]] = []
    seen = set()
    for spec in merged_db().values():
        if spec.name in seen:
            continue
        seen.add(spec.name)
        item = {
            "name": spec.name,
            "score": spec.score,
            "cpuz": spec.cpuz_score,
            "cores": spec.cores,
            "platform": resolve_platform(spec),
            "note": spec.note,
            "custom": spec.custom,
        }
        (mobile if item["platform"] == "mobile" else desktop).append(item)
    desktop.sort(key=lambda x: (not x["custom"], -x["score"]))
    mobile.sort(key=lambda x: (not x["custom"], -x["score"]))
    return {"desktop": desktop, "mobile": mobile, "all": all_models()}


def custom_cpu_list() -> List[Dict[str, Any]]:
    return [
        {
            "name": s.name,
            "cores": s.cores,
            "platform": s.platform,
            "cpuz": s.cpuz_score,
            "index": round(s.score, 1),
            "note": s.note,
        }
        for s in custom_models()
    ]


def add_custom_cpu_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """录入一个自定义型号：name / cpuz / cores / platform / note。"""
    name = str(data.get("name") or "").strip()
    cpuz_raw = data.get("cpuz", data.get("cpuz_single"))
    try:
        cpuz = float(str(cpuz_raw).strip())
    except (TypeError, ValueError):
        raise ValueError(f"CPU-Z 单核分「{cpuz_raw}」不是数字")
    cores_raw = data.get("cores")
    if cores_raw is None or str(cores_raw).strip() == "":
        cores = 4
    else:
        try:
            cores = int(float(str(cores_raw).strip()))
        except (TypeError, ValueError):
            raise ValueError(f"核心数「{cores_raw}」不是整数")
    platform = str(data.get("platform") or "")
    note = str(data.get("note") or "")

    spec = add_custom_cpu(name, cpuz, cores, platform, note)
    save_custom_cpus()
    return {
        "spec": {"name": spec.name, "cpuz": spec.cpuz_score, "index": round(spec.score, 1),
                 "cores": spec.cores, "platform": spec.platform},
        "list": custom_cpu_list(),
        "file": custom_cpu_file(),
    }


def remove_custom_cpu_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    name = str(data.get("name") or "").strip()
    removed = remove_custom_cpu(name)
    if removed:
        save_custom_cpus()
    return {"removed": removed, "list": custom_cpu_list()}


def state_payload() -> Dict[str, Any]:
    """本地状态（哪些数据文件存在、里面有多少东西、能不能撤销）。"""
    from .reset import backup_groups, inspect_state
    return {
        "items": inspect_state(),
        "backup_groups": backup_groups(),
        "note": "恢复默认会先把文件改名成 <原名>.<时间戳>.bak，可整组撤销",
    }


def reset_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """恢复默认。

    scope: user（只清用户数据）/ derived（只清校准产物）/ all（两者都清）
    with_exports: 是否连导出文件一起清
    dry_run: 只预演，不真删
    backup: 是否先备份（默认 True，可撤销）
    keys: 只重置指定项（数组）
    """
    from .reset import all_items, item_path, reset, restore_group
    action = str(data.get("action") or "reset").lower()

    if action in ("undo", "restore"):
        stamp = str(data.get("stamp") or "")
        if not stamp:
            raise ValueError("需要提供要撤销的备份时间戳 stamp")
        restored = restore_group(stamp)
        if not restored:
            raise ValueError(f"没有找到时间戳为 {stamp} 的备份（可能已被撤销或已清理）")
        return {"undone": [os.path.basename(r) for r in restored], "stamp": stamp,
                "text": "已撤销：把 " + "、".join(os.path.basename(r) for r in restored)
                        + " 改回原名，数据恢复原状",
                "state": state_payload(),
                "note": "已把备份改回原名，数据恢复原状"}

    scope = str(data.get("scope") or "user").lower()
    keys = data.get("keys")
    if keys:
        chosen = [k for k in keys if item_path(k)]
        if not chosen:
            raise ValueError(f"没有可识别的项目：{keys}")
        label = "指定项"
    elif scope == "all":
        chosen = [i.key for i in all_items(include_exports=bool(data.get("with_exports")))]
        label = "全部（用户数据 + 校准产物）"
    elif scope == "derived":
        chosen = ["behavior", "modpacks"]
        label = "校准产物"
    else:
        chosen = ["custom_cpus", "feedback"]
        label = "用户数据"

    report = reset(chosen,
                   backup_first=bool(data.get("backup", True)),
                   dry_run=bool(data.get("dry_run")),
                   include_exports=bool(data.get("with_exports")))
    return {"scope": scope, "scope_label": label, "report": report.to_dict(),
            "text": report.render(), "state": state_payload()}


def feedback_meta() -> Dict[str, Any]:
    """反馈表单需要的选项与说明（供前端渲染）。"""
    from .feedback import (BOTTLENECKS, MC_VERSIONS, MODPACK_KINDS, OPTIMIZATION_LEVELS,
                           PLAYSTYLES, PROGRESS_STAGES, SERVER_SOFTWARE, feedback_file,
                           stats_overview)
    return {
        "playstyles": [
            {"name": k, "desc": v["desc"], "multiplier": v["multiplier"],
             "extended": bool(v.get("extended"))}
            for k, v in PLAYSTYLES.items()
        ],
        "modpack_kinds": [{"name": k, "coef": v} for k, v in MODPACK_KINDS.items()],
        "progress_stages": [{"name": k, "coef": v} for k, v in PROGRESS_STAGES.items()],
        "mc_versions": MC_VERSIONS,
        "software": SERVER_SOFTWARE,
        "bottlenecks": BOTTLENECKS,
        "player_sims": PLAYER_SIM,
        "view_distances": VIEW_DISTANCES,
        "file": feedback_file(),
        "stats": stats_overview(),
        "optimization_levels": OPTIMIZATION_LEVELS,
        "privacy": "提交内容只写入你本机的 feedback.json，不会自动上传；"
                   "要分享给别人时请点「导出」自己发送。",
        "export_formats": [
            {"key": "agent", "label": "给 Agent 的文件",
             "desc": "Markdown，自带任务说明、口径定义与待校准参数，直接发给对方即可"},
            {"key": "anchors", "label": "校准锚点", "desc": "JSON，本机 calibrate 用"},
            {"key": "csv", "label": "表格 CSV", "desc": "用 Excel / 表格软件看"},
            {"key": "json", "label": "原始 JSON", "desc": "完整原始数据，便于备份"},
        ],
    }


def modpack_payload() -> Dict[str, Any]:
    """整合包档案（一个包一套系数）与兜底规则。"""
    from .modpack import (MODPACK_BASE_FACTOR, MODPACK_KINDS, PROGRESS_STAGES,
                          list_profiles, profile_file)
    return {
        "base_factor": MODPACK_BASE_FACTOR,
        "kinds": [{"name": k, "coef": v} for k, v in MODPACK_KINDS.items()],
        "progress_stages": [{"name": k, "coef": v} for k, v in PROGRESS_STAGES.items()],
        "profiles": [p.to_dict() for p in list_profiles()],
        "file": profile_file(),
        "hint": "整合包的作者优化状况差别很大，所以一个包一套系数："
                "有服主反馈数据时用校准值，否则按类型/进度折算兜底。",
    }


def options_payload() -> Dict[str, Any]:
    return {
        "version": __version__,
        "network_presets": [
            {"name": k, "bandwidth_mbps": v["bandwidth_mbps"], "latency_ms": v["latency_ms"],
             "loss_pct": v["loss_pct"]}
            for k, v in NETWORK_PRESETS.items()
        ],
        "behaviors": PLAYER_BEHAVIORS,
        "player_sims": PLAYER_SIM,
        "view_distances": VIEW_DISTANCES,
        "cpu": _cpu_catalog(),
        "custom_cpu": {
            "list": custom_cpu_list(),
            "file": custom_cpu_file(),
            "calibration": cpuz_scale_info(),
            "hint": "填 CPU-Z 的「单核」分数（例如 R5 5600 ≈ 662、i9-14900K ≈ 950）",
        },
        "feedback": feedback_meta(),
        "modpacks": modpack_payload(),
        "cooling": {
            "desktop": [{"name": k, "coef": v} for k, v in DESKTOP_COOLING.items()],
            "chassis": [{"name": k, "coef": v} for k, v in LAPTOP_CHASSIS.items()],
            "material": [{"name": k, "coef": v} for k, v in THERMAL_MATERIAL.items()],
            "defaults": {
                "desktop": list(DESKTOP_COOLING)[1],
                "chassis": list(LAPTOP_CHASSIS)[2],
                "material": list(THERMAL_MATERIAL)[0],
            },
            "suffix_map": PLATFORM_CHASSIS_CAP,
            "chassis_options": {s: chassis_options(s) for s in ("U", "Y", "G", "P", "H", "HS", "HK", "HX")},
        },
        "speedtest": {
            "url": SPEEDTEST_URL,
            "label": "中国科技大学测速网",
            "allowed": ALLOWED_OPEN_URLS,
        },
        "params": DEFAULT_PARAMS.to_dict(),
    }


# ----------------------------------------------------------------------
# 计算
# ----------------------------------------------------------------------
def cooling_payload(raw: RawInput) -> Dict[str, Any]:
    """只解析 CPU + 散热，供前端联动刷新（不跑完整计算）。"""
    cpu = resolve_cpu(raw.cpu)
    cfg, warnings = resolve_cooling(
        cpu,
        platform_raw=raw.platform,
        chassis=raw.chassis,
        material=raw.material,
        radiator=raw.radiator,
        override=raw.cooling_override,
    )
    platform = resolve_platform(cpu)
    suf = suffix_of(cpu.name) if platform == "mobile" else ""
    return {
        "cpu_name": cpu.name,
        "platform": platform,
        "platform_label": "移动端（笔记本）" if platform == "mobile" else "桌面端",
        "suffix": suf,
        "chassis_options": chassis_options(suf) if platform == "mobile" else [],
        "factor": round(cfg.factor(), 4),
        "chassis_coef": cfg.chassis_coef(),
        "material_coef": cfg.material_coef(),
        "radiator_coef": cfg.radiator_coef(),
        "override": cfg.override,
        "description": cfg.describe(),
        "chassis": cfg.chassis,
        "material": cfg.material,
        "radiator": cfg.radiator,
        "warnings": warnings,
    }


def _result_payload(res: CalcResult) -> Dict[str, Any]:
    inp = res.inputs
    return {
        "final_players": res.final_players,
        "tps_estimate": round(res.tps_estimate, 1),
        "binding": [{"key": f.key, "label": f.label} for f in res.factors if f.is_bottleneck],
        "factors": [
            {
                "key": f.key,
                "label": f.label,
                "ceiling": round(f.ceiling, 1),
                "load_pct": None if f.load_at_final == float("inf") else round(f.load_at_final * 100),
                "status": ("瓶颈" if f.is_bottleneck else
                           ("接近瓶颈" if f.near_bottleneck else "余量充足")),
                "is_bottleneck": f.is_bottleneck,
                "near_bottleneck": f.near_bottleneck,
                "detail": f.detail,
                "values": f.values,
                "formulas": f.formulas,
            }
            for f in sorted(res.factors, key=lambda x: x.ceiling)
        ],
        "warnings": res.warnings,
        "suggestions": res.suggestions,
        "input_summary": {
            "mod_count": inp.mod_count,
            "cpu": inp.cpu.name,
            "cooling": inp.cooling.describe(),
            "cooling_factor": inp.cooling.factor(),
            "ram_gb": round(inp.ram_mb / 1024, 2),
            "network": inp.network_preset,
            "bandwidth_mbps": inp.bandwidth_mbps,
            "download_mbps": inp.download_mbps,
            "download_input": inp.download_input,
            "latency_ms": inp.latency_ms,
            "loss_pct": inp.loss_pct,
            "behavior": inp.behavior,
            "player_sim": inp.player_sim,
            "view_distance": inp.view_distance,
        },
        "params": res.params.to_dict() if res.params else DEFAULT_PARAMS.to_dict(),
    }


# ----------------------------------------------------------------------
# 服主反馈收集
# ----------------------------------------------------------------------
def feedback_list_payload() -> Dict[str, Any]:
    from .feedback import load_feedback, stats_overview, summarize
    entries = load_feedback()
    return {
        "entries": [e.__dict__ for e in entries],
        "stats": stats_overview(entries),
        "summary": summarize(entries),
    }


def feedback_submit_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """校验 + 落盘一条反馈。"""
    from .feedback import append_feedback, load_feedback, stats_overview, summarize, validate
    fb, errors, warnings = validate(data)
    if errors:
        raise ValueError("；".join(errors))
    path, count = append_feedback(fb)
    entries = load_feedback()
    saved = dict(fb.__dict__)
    saved["playstyle_multiplier"] = fb.playstyle_multiplier()
    return {
        "saved": saved,
        "warnings": warnings,
        "file": path,
        "count": count,
        "stats": stats_overview(entries),
        "summary": summarize(entries),
    }


def feedback_action_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """导出 / 汇总应用 / 删除。"""
    from .feedback import (anchors_payload, apply_pack_suggestions, apply_suggestions,
                           export_agent_markdown, export_csv, feedback_file, load_feedback,
                           render_pack_summary, render_summary, save_feedback, stats_overview,
                           summarize, summarize_packs)
    action = str(data.get("action") or "summary").lower()
    kind = str(data.get("kind") or "playstyles").lower()
    want_packs = kind in ("packs", "modpacks", "整合包")
    entries = load_feedback()

    if action == "summary":
        if want_packs:
            s = summarize_packs(entries)
            return {"kind": "packs", "summary": s, "text": render_pack_summary(s)}
        s = summarize(entries)
        return {"kind": "playstyles", "summary": s, "text": render_summary(s)}

    if action == "export":
        fmt = str(data.get("format") or "json").lower()
        owner = str(data.get("owner") or "").strip()
        if fmt == "agent":
            from .feedback import export_agent_markdown
            return {"format": "markdown", "filename": "feedback_agent.md",
                    "content": export_agent_markdown(entries, server_owner=owner)}
        if fmt == "csv":
            return {"format": "csv", "content": export_csv(entries),
                    "filename": "feedback.csv"}
        if fmt == "anchors":
            payload = anchors_payload(entries)
            return {"format": "json", "content": json.dumps(payload, ensure_ascii=False, indent=2),
                    "filename": "anchors.json"}
        payload = {
            "note": "服主反馈数据；可直接作为 calibrate.py 的 anchors 使用",
            "schema": 1,
            "count": len(entries),
            "stats": stats_overview(entries),
            "entries": [__dict__ if not hasattr(e, "__dict__") else e.__dict__ for e in entries],
        }
        return {"format": "json", "content": json.dumps(payload, ensure_ascii=False, indent=2),
                "filename": "feedback.json"}

    if action == "apply":
        min_samples = int(data.get("min_samples") or 3)
        if want_packs:
            applied = apply_pack_suggestions(summarize_packs(entries), min_samples=min_samples)
            from .modpack import profile_file
            return {"kind": "packs", "applied": applied, "file": profile_file(),
                    "min_samples": min_samples,
                    "summary": summarize_packs(entries),
                    "note": "已写入 modpack_profiles.json（一个包一套系数），下次计算自动生效"}
        summary = summarize(entries)
        path, applied = apply_suggestions(summary, min_samples=min_samples)
        return {"kind": "playstyles", "applied": applied, "file": path,
                "min_samples": min_samples, "summary": summary,
                "note": "已写入 behavior_multiplier.json，工具下次计算时会自动加载"}

    if action in ("remove", "delete"):
        idx = data.get("index")
        try:
            idx = int(idx)
        except (TypeError, ValueError):
            raise ValueError("需要提供要删除的序号 index")
        if not (0 <= idx < len(entries)):
            raise ValueError(f"序号 {idx} 超出范围（共 {len(entries)} 条）")
        removed = entries.pop(idx)
        save_feedback(entries)
        return {"removed": removed.__dict__, "count": len(entries),
                "stats": stats_overview(entries) if entries else {},
                "file": feedback_file()}

    raise ValueError(f"未知操作：{action}")


def _raw_from(data: Dict[str, Any]) -> RawInput:
    """前端 JSON → RawInput（统一入口，避免字段遗漏）。"""
    return RawInput(
        mod_count=str(data.get("mod_count", data.get("mods", "0"))),
        cpu=str(data.get("cpu", "")),
        ram=str(data.get("ram", "")),
        network=str(data.get("network", "")),
        bandwidth=str(data.get("bandwidth", "")),
        download=str(data.get("download", "")),
        latency=str(data.get("latency", "")),
        loss=str(data.get("loss", "")),
        behavior=str(data.get("behavior", PLAYER_BEHAVIORS[0])),
        player_sim=str(data.get("player_sim", PLAYER_SIM[0])),
        view_distance=str(data.get("view_distance", "10")),
        modpack=str(data.get("modpack", data.get("modpack_name", ""))),
        platform=str(data.get("platform", "")),
        chassis=str(data.get("chassis", "")),
        material=str(data.get("material", "")),
        radiator=str(data.get("radiator", "")),
        cooling_override=str(data.get("cooling_override", "")),
    )


def calculate_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """接收前端 JSON，返回完整结果（结构化 + 纯文本报告）。"""
    raw = _raw_from(data)
    fields, warnings = parse_raw(raw)
    res = calculate(CalcInput(**fields))
    res.warnings = warnings + res.warnings

    payload = _result_payload(res)
    payload["report"] = render(res, show_formulas=True)
    payload["report_short"] = render(res, show_formulas=False)
    payload["cooling"] = cooling_payload(raw)
    return payload


# ----------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = f"MCCalc/{__version__}"
    protocol_version = "HTTP/1.1"

    # ---------- 工具 ----------
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, data: Any, code: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def _error(self, code: int, message: str) -> None:
        self._json({"ok": False, "error": message}, code)

    def log_message(self, fmt: str, *args) -> None:  # 安静一点，只在需要时打印
        if os.environ.get("MC_CALC_WEB_VERBOSE"):
            super().log_message(fmt, *args)

    # ---------- 路由 ----------
    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._serve_static("index.html")
        if path == "/api/options":
            try:
                return self._json({"ok": True, **options_payload()})
            except Exception as exc:  # pragma: no cover
                return self._error(500, f"生成选项失败：{exc}")
        if path == "/api/cpu/custom":
            return self._json({"ok": True, "list": custom_cpu_list(),
                               "file": custom_cpu_file(), "calibration": cpuz_scale_info()})
        if path == "/api/feedback":
            try:
                return self._json({"ok": True, **feedback_list_payload()})
            except Exception as exc:
                return self._error(500, f"读取反馈失败：{exc}")
        if path == "/api/state":
            try:
                return self._json({"ok": True, **state_payload()})
            except Exception as exc:
                return self._error(500, f"读取本地状态失败：{exc}")
        if path.startswith("/static/"):
            return self._serve_static(path[len("/static/"):])
        if path == "/favicon.ico":
            return self._send(204, b"", "image/x-icon")
        return self._error(404, "未找到该地址")

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/cooling":
            data = self._read_json()
            if data is None:
                return
            try:
                return self._json({"ok": True, **cooling_payload(_raw_from(data))})
            except Exception as exc:
                return self._error(400, f"散热参数解析失败：{exc}")
        if path == "/api/open-url":
            data = self._read_json()
            if data is None:
                return
            return self._open_url(str(data.get("url", "")))
        if path == "/api/reset":
            data = self._read_json()
            if data is None:
                return
            try:
                return self._json({"ok": True, **reset_payload(data)})
            except ValueError as exc:
                return self._error(400, str(exc))
            except OSError as exc:
                return self._error(500, f"文件操作失败：{exc}")
        if path == "/api/feedback":
            data = self._read_json()
            if data is None:
                return
            # 带 action 的是 导出/汇总/应用/删除；不带 action 视为提交新反馈
            if str(data.get("action") or "").strip():
                try:
                    return self._json({"ok": True, **feedback_action_payload(data)})
                except ValueError as exc:
                    return self._error(400, str(exc))
                except OSError as exc:
                    return self._error(500, f"写文件失败：{exc}")
            try:
                return self._json({"ok": True, **feedback_submit_payload(data)})
            except ValueError as exc:
                return self._error(400, str(exc))
            except OSError as exc:
                return self._error(500, f"保存反馈失败：{exc}")
        if path == "/api/cpu/custom":
            data = self._read_json()
            if data is None:
                return
            action = str(data.get("action") or "add").lower()
            try:
                if action == "add":
                    return self._json({"ok": True, **add_custom_cpu_payload(data)})
                if action in ("remove", "delete"):
                    return self._json({"ok": True, **remove_custom_cpu_payload(data)})
                if action == "list":
                    return self._json({"ok": True, "list": custom_cpu_list()})
                return self._error(400, f"未知操作：{action}")
            except ValueError as exc:
                return self._error(400, str(exc))
            except OSError as exc:
                return self._error(500, f"保存自定义型号失败：{exc}")
        if path != "/api/calc":
            return self._error(404, "未找到该地址")
        data = self._read_json()
        if data is None:
            return
        try:
            payload = calculate_payload(data)
        except Exception as exc:
            return self._error(400, f"计算失败：{exc}")
        self._json({"ok": True, **payload})

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    # ---------- 打开测速网 ----------
    def _open_url(self, url: str) -> None:
        if not is_url_allowed(url):
            return self._error(403, f"该网址不在允许列表内：{url}")
        # 不阻塞响应线程，浏览器启动失败也不影响页面
        threading.Thread(target=_safe_open, args=(url,), daemon=True).start()
        self._json({"ok": True, "opened": url})

    # ---------- 辅助 ----------
    def _read_json(self) -> Optional[Dict[str, Any]]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._error(400, "Content-Length 非法")
            return None
        if length <= 0:
            self._error(400, "请求体为空")
            return None
        if length > MAX_BODY_BYTES:
            self._error(413, "请求体过大")
            return None
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._error(400, f"JSON 解析失败：{exc}")
            return None
        if not isinstance(data, dict):
            self._error(400, "请求体必须是 JSON 对象")
            return None
        return data

    def _serve_static(self, rel: str) -> None:
        rel = rel.split("?", 1)[0].lstrip("/")
        full = os.path.normpath(os.path.join(WEB_DIR, rel))
        # 防目录穿越：必须落在 web/ 内
        if not full.startswith(WEB_DIR + os.sep) and full != WEB_DIR:
            return self._error(403, "拒绝访问")
        if not os.path.isfile(full):
            return self._error(404, f"静态资源不存在：{rel}")
        ext = os.path.splitext(full)[1].lower()
        ctype = _MIME_OVERRIDES.get(ext) or mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as fh:
            self._send(200, fh.read(), ctype)


def _safe_open(url: str) -> None:
    try:
        if not webbrowser.open(url):
            print(f"[提示] 未能自动打开浏览器，请手动访问：{url}")
    except Exception as exc:  # pragma: no cover
        print(f"[提示] 打开浏览器失败（{exc}），请手动访问：{url}")


def build_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> Tuple[ThreadingHTTPServer, int]:
    """创建服务器；port=0 时由系统分配空闲端口。"""
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    return httpd, httpd.server_address[1]


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, open_browser: bool = True,
          quiet: bool = False) -> int:
    """阻塞式启动本地网页服务。"""
    if not os.path.isdir(WEB_DIR) or not os.path.isfile(os.path.join(WEB_DIR, "index.html")):
        print(f"找不到前端资源目录：{WEB_DIR}")
        return 1

    wanted = port
    if port and _port_in_use(host, port):
        print(f"端口 {port} 已被占用，改为自动分配空闲端口。")
        port = 0

    httpd, actual_port = build_server(host, port)
    url = f"http://{host}:{actual_port}/"

    if not quiet:
        print("=" * 62)
        print("  Minecraft 服务器人数上限计算器 — 本地网页版")
        print("=" * 62)
        print(f"  地址：{url}")
        print(f"  端口：{actual_port}" + (f"（原定 {wanted} 被占用）" if port == 0 and wanted else ""))
        print(f"  测速：页面上的「{SPEEDTEST_URL}」按钮会打开 {SPEEDTEST_URL}")
        print("  提示：这是纯本地服务，只监听 127.0.0.1，关闭本窗口即停止")
        print("  按 Ctrl+C 退出")
        print("=" * 62)

    if open_browser:
        threading.Thread(target=lambda: _safe_open(url), daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        if not quiet:
            print("\n已停止本地网页服务。")
    finally:
        httpd.server_close()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="mc_player_calc.web",
                                 description="以本地网页方式打开人数上限计算器")
    ap.add_argument("--host", default=DEFAULT_HOST, help=f"监听地址（默认 {DEFAULT_HOST}）")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT,
                    help=f"监听端口（默认 {DEFAULT_PORT}，0 = 自动分配）")
    ap.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = ap.parse_args(argv)

    if args.host not in ("127.0.0.1", "localhost"):
        print(f"注意：当前监听 {args.host}，局域网内其他设备也能访问，请自行确认网络环境。")
    return serve(args.host, args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    raise SystemExit(main())
