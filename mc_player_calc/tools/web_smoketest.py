"""本地网页版的接口自测：真的起一个服务器，用 HTTP 请求打一遍。

    python tools/web_smoketest.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("\\", 1)[0])

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from mc_player_calc.web import build_server  # noqa: E402

FAILURES = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        FAILURES.append(name)


def check_true(name: str, cond: bool, extra: str = "") -> None:
    check(name, bool(cond), extra)


def http(method: str, url: str, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read()
        return resp.status, resp.headers.get("Content-Type", ""), body


def main() -> int:
    # 拦住真实的浏览器启动：把 web._safe_open 换成记录器（否则测速网会被真打开）
    import mc_player_calc.web as webmod
    opened = []
    webmod._safe_open = lambda url: opened.append(url)

    # 测试用的数据目录（放工作区里，沙箱对系统临时目录限制较多）
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ws_tmp = os.path.join(project_root, '_smoketest_tmp')
    shutil.rmtree(ws_tmp, ignore_errors=True)
    os.makedirs(ws_tmp, exist_ok=True)

    # 反馈数据写到临时文件，避免污染用户的 feedback.json
    # 所有数据文件都指向临时位置，避免测试污染工作区里的真实数据
    # （否则跑一次自测就会生成 behavior_multiplier.json / modpack_profiles.json）
    tmp_fb = os.path.join(ws_tmp, "feedback.json")
    os.environ["MC_CALC_FEEDBACK"] = tmp_fb
    os.environ["MC_CALC_BEHAVIOR"] = os.path.join(ws_tmp, "behavior_multiplier.json")
    os.environ["MC_CALC_MODPACKS"] = os.path.join(ws_tmp, "modpack_profiles.json")
    os.environ["MC_CALC_CUSTOM_CPUS"] = os.path.join(ws_tmp, "custom_cpus.json")

    httpd, port = build_server("127.0.0.1", 0)
    base = f"http://127.0.0.1:{port}"
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)
    print(f"测试服务器: {base}")

    try:
        # 1) 首页与静态资源
        code, ctype, body = http("GET", base + "/")
        check("GET / 返回 200", code == 200, f"{code}")
        check("首页是 UTF-8 HTML", "text/html" in ctype and "charset=utf-8" in ctype, ctype)
        check("首页含标题", "人数上限计算器" in body.decode("utf-8"))
        html = body.decode("utf-8")

        for path, needle in (("/static/style.css", "--accent"), ("/static/app.js", "/api/calc")):
            code, ctype, body = http("GET", base + path)
            check(f"GET {path}", code == 200 and needle in body.decode("utf-8"), f"{code} {ctype}")

        # 2) 目录穿越必须被拒
        try:
            code, _, _ = http("GET", base + "/static/../web.py")
            check("目录穿越被拒", code in (403, 404), str(code))
        except urllib.error.HTTPError as e:
            check("目录穿越被拒", e.code in (403, 404), str(e.code))

        # 3) 选项接口
        code, ctype, body = http("GET", base + "/api/options")
        opts = json.loads(body)
        check("GET /api/options", code == 200 and opts.get("ok"), str(code))
        check("选项含网络档位", len(opts["network_presets"]) == 5)
        check("选项含散热三表",
              len(opts["cooling"]["desktop"]) == 6 and len(opts["cooling"]["chassis"]) == 6
              and len(opts["cooling"]["material"]) == 5)
        check("选项含 CPU 库（桌面+移动）",
              len(opts["cpu"]["desktop"]) > 0 and len(opts["cpu"]["mobile"]) > 20,
              f"桌面 {len(opts['cpu']['desktop'])} / 移动 {len(opts['cpu']['mobile'])}")

        # 4) 散热联动接口
        code, _, body = http("POST", base + "/api/cooling",
                             {"cpu": "i7-12700H", "chassis": "轻薄本 / 核显本（单风扇、15~28W 限制）"})
        cool = json.loads(body)
        check("POST /api/cooling（移动端）",
              code == 200 and cool["platform"] == "mobile" and abs(cool["factor"] - 0.85) < 1e-6,
              f"{cool.get('platform')} {cool.get('factor')}")
        check("移动端给出模具候选", len(cool["chassis_options"]) >= 1, str(cool["chassis_options"]))

        code, _, body = http("POST", base + "/api/cooling", {"cpu": "i5-12400"})
        cool = json.loads(body)
        check("POST /api/cooling（桌面端默认 1.0）",
              cool["platform"] == "desktop" and abs(cool["factor"] - 1.0) < 1e-6,
              f"{cool.get('platform')} {cool.get('factor')}")

        # 5) 计算接口
        code, _, body = http("POST", base + "/api/calc",
                             {"mod_count": "30", "cpu": "i5-12400", "ram": "16G",
                              "network": "一般 (100M 家宽 / 普通 VPS)",
                              "behavior": "红石 / 自动化"})
        res = json.loads(body)
        check("POST /api/calc", code == 200 and res.get("ok"), str(code))
        check("返回最终人数", isinstance(res["final_players"], int) and res["final_players"] > 0,
              str(res["final_players"]))
        check("返回四个维度", len(res["factors"]) == 4, str([f["label"] for f in res["factors"]]))
        check("返回瓶颈标注", len(res["binding"]) >= 1, str(res["binding"]))
        check("返回纯文本报告", "结论" in res["report"] and len(res["report"]) > 500)
        check("报告含散热行", "散热" in res["report"])

        # 6) 移动端 + 自定义系数，验证与 GUI/CLI 同源
        code, _, body = http("POST", base + "/api/calc",
                             {"mod_count": "20", "cpu": "i7-12700H", "ram": "16G",
                              "cooling_override": "0.7"})
        res2 = json.loads(body)
        check("自定义散热系数生效", abs(res2["cooling"]["factor"] - 0.7) < 1e-6,
              str(res2["cooling"]["factor"]))
        cpu_factor = [f for f in res2["factors"] if f["key"] == "cpu"][0]
        check("CPU 维度使用有效单核",
              abs(float(cpu_factor["values"]["散热系数"]) - 0.7) < 1e-6,
              cpu_factor["values"]["散热系数"])

        # 7) 错误处理
        try:
            http("POST", base + "/api/calc", None)
            check("空请求体被拒", False)
        except urllib.error.HTTPError as e:
            check("空请求体被拒", e.code == 400, str(e.code))
        try:
            http("GET", base + "/api/nope")
            check("未知接口 404", False)
        except urllib.error.HTTPError as e:
            check("未知接口 404", e.code == 404, str(e.code))

        # 7b) 上下行：上行参与计算，下行只记录
        code, _, body = http("POST", base + "/api/calc",
                             {"mod_count": "0", "cpu": "i5-12400", "ram": "16G",
                              "bandwidth": "35", "download": "300"})
        up = json.loads(body)
        check("上行实测值生效", abs(up["input_summary"]["bandwidth_mbps"] - 35) < 1e-6,
              str(up["input_summary"]["bandwidth_mbps"]))
        check("下行被记录", abs(up["input_summary"]["download_mbps"] - 300) < 1e-6,
              str(up["input_summary"]["download_mbps"]))
        check("报告里出现下行行", "下行" in up["report"])

        code, _, body = http("POST", base + "/api/calc",
                             {"mod_count": "0", "cpu": "i5-12400", "ram": "16G",
                              "bandwidth": "35", "download": "1000"})
        up2 = json.loads(body)
        net1 = [f for f in up["factors"] if f["key"] == "network"][0]["ceiling"]
        net2 = [f for f in up2["factors"] if f["key"] == "network"][0]["ceiling"]
        check("下行不影响人数结果", net1 == net2 and up["final_players"] == up2["final_players"],
              f"{net1} vs {net2}")

        # 7c) 测速网按钮：白名单外必须拒绝，白名单内允许（用记录器替换真实打开）
        try:
            http("POST", base + "/api/open-url", {"url": "https://evil.example.com/"})
            check("白名单外网址被拒", False, "居然放行了")
        except urllib.error.HTTPError as e:
            check("白名单外网址被拒（403）", e.code == 403, str(e.code))
        try:
            http("POST", base + "/api/open-url", {"url": "javascript:alert(1)"})
            check("非 http(s) 被拒", False, "居然放行了")
        except urllib.error.HTTPError as e:
            check("非 http(s) 被拒（403）", e.code == 403, str(e.code))
        check("测速网在允许列表内", any("ustc.edu.cn" in u for u in opts["speedtest"]["allowed"]),
              str(opts["speedtest"]["allowed"]))

        # 7d) 选项里带测速地址
        check("选项含测速地址", opts["speedtest"]["url"].startswith("https://"),
              opts["speedtest"]["url"])

        # 7e) 允许列表内的地址：应由服务端调起浏览器（已替换为记录器，不会真弹窗）
        code, _, body = http("POST", base + "/api/open-url", {"url": opts["speedtest"]["url"]})
        res_open = json.loads(body)
        time.sleep(0.4)   # 打开动作在子线程里做
        check("允许列表内的网址被接受", res_open["ok"], body.decode("utf-8")[:80])
        check("确实触发了打开浏览器", opened == [opts["speedtest"]["url"]], str(opened))

        # 7f) 服主反馈收集
        fb_meta = opts["feedback"]
        check("选项含反馈表单元数据", bool(fb_meta.get("playstyles")), str(sorted(fb_meta)[:5]))
        check("玩法分类为 6 类", [x["name"] for x in fb_meta["playstyles"]],
              [x["name"] for x in fb_meta["playstyles"]])
        check("只有整合包需要扩字段",
              [x["name"] for x in fb_meta["playstyles"] if x["extended"]], ["整合包"])
        check("整合包细分/进度阶段齐备",
              len(fb_meta["modpack_kinds"]) == 5 and len(fb_meta["progress_stages"]) == 3,
              f"{len(fb_meta['modpack_kinds'])}/{len(fb_meta['progress_stages'])}")
        check_true("反馈隐私说明存在", "不会自动上传" in fb_meta["privacy"], fb_meta["privacy"])

        code, _, body = http("POST", base + "/api/feedback",
                             {"cpu": "i5-12400", "cpuz_single": 700, "players": 44, "view": "10",
                              "tps": 19.6, "playstyle": "原版", "bottleneck": "cpu", "ram": "64G"})
        fb1 = json.loads(body)
        check("提交反馈成功", code == 200 and fb1["ok"], str(code))
        check("反馈计数为 1", fb1["count"], 1)
        check("返回玩法负载系数", fb1["saved"]["playstyle_multiplier"], 1.0)

        code, _, body = http("POST", base + "/api/feedback",
                             {"cpu": "i9-14900K", "cpuz_single": 950, "players": 24, "view": "10",
                              "tps": 19.2, "playstyle": "整合包", "modpack_name": "ATM10",
                              "mc_version": "1.21.x", "mods": 400,
                              "modpack_kind": "综合（科技+魔法+任务）",
                              "progress": "大后期 / 长期服", "bottleneck": "cpu", "ram": "64G"})
        fb2 = json.loads(body)
        check("整合包反馈负载系数", fb2["saved"]["playstyle_multiplier"], 2.208)

        try:
            http("POST", base + "/api/feedback",
                 {"cpu": "", "players": 0, "playstyle": "火星玩法"})
            check("非法反馈被拒", False, "居然放行了")
        except urllib.error.HTTPError as e:
            check("非法反馈被拒（400）", e.code == 400, str(e.code))
        try:
            http("POST", base + "/api/feedback",
                 {"cpu": "5800X3D", "players": 15, "playstyle": "整合包"})
            check("整合包缺包名被拒", False, "居然放行了")
        except urllib.error.HTTPError as e:
            check("整合包缺包名被拒（400）", e.code == 400, str(e.code))

        code, _, body = http("GET", base + "/api/feedback")
        lst = json.loads(body)
        check("反馈列表条数", len(lst["entries"]), 2)
        check("统计按玩法分组", lst["stats"]["by_playstyle"].get("整合包"), 1)

        code, _, body = http("POST", base + "/api/feedback", {"action": "summary"})
        sm = json.loads(body)
        check("汇总可生成", "累计反馈" in sm["text"], sm["text"][:40])

        for fmt, needle in (("json", "entries"), ("csv", "cpuz_single"), ("anchors", "anchors")):
            code, _, body = http("POST", base + "/api/feedback",
                                 {"action": "export", "format": fmt})
            ex = json.loads(body)
            check(f"导出 {fmt}", ex["ok"] and needle in ex["content"], ex.get("filename", ""))

        # 7g) agent 交付文件（Markdown，自带说明 + 内嵌 JSON）
        code, _, body = http("POST", base + "/api/feedback",
                             {"action": "export", "format": "agent", "owner": "测试服主"})
        agent = json.loads(body)
        check("导出 agent 交付文件", agent["ok"] and agent["filename"] == "feedback_agent.md",
              agent.get("filename", ""))
        check_true("交付文件含任务说明", "反推 CPU 系数" in agent["content"])
        check_true("交付文件含口径定义", "TPS 首次跌破 19.5" in agent["content"])
        check_true("交付文件含数值表", "| # | CPU 型号" in agent["content"])
        check_true("交付文件含 JSON 块", "```json" in agent["content"])
        check_true("交付文件含提交者", "测试服主" in agent["content"])
        agent_md = tmp_fb.replace(".json", "_agent.md")
        with open(agent_md, "w", encoding="utf-8") as fh:
            fh.write(agent["content"])
        from mc_player_calc.calibrate import load_anchors
        check("calibrate 能读交付文件", len(load_anchors(agent_md)) >= 1)

        code, _, body = http("POST", base + "/api/feedback", {"action": "apply", "min_samples": 1})
        ap = json.loads(body)
        check("应用汇总到玩法系数", ap["ok"], str(ap.get("applied")))

        code, _, body = http("POST", base + "/api/feedback", {"action": "remove", "index": 0})
        rm = json.loads(body)
        check("删除一条反馈", rm["removed"]["cpu"], "i5-12400")
        check("删除后剩余 1 条", rm["count"], 1)

        # 7h) 整合包：自由输入 + 一个包一套系数
        mp = opts["modpacks"]
        check("选项含整合包档案元数据",
              all(k in mp for k in ("base_factor", "kinds", "profiles", "file")), str(sorted(mp)))
        check_true("整合包名称是自由输入（input 而非 select）",
                   'id="modpack"' in html and '<datalist id="pack_hints">' in html,
                   "首页缺少自由输入框/dataList")
        check_true("首页有整合包提示区", 'id="pack-note"' in html)
        check("反馈表单也支持填包名",
              "modpack_name" in json.dumps(opts["feedback"], ensure_ascii=False)
              or 'id="fb-modpack-name"' in html)
        check_true("反馈表单有作者优化状况选项",
                   len(opts["feedback"].get("optimization_levels") or []) >= 3,
                   str(opts["feedback"].get("optimization_levels")))

        # 未建档案时走兜底；建了档案后按包区分
        c_unknown = json.loads(http("POST", base + "/api/calc",
                                    {"cpu": "i9-14900K", "mods": "400", "ram": "64G",
                                     "behavior": "整合包",
                                     "modpack": "某个没见过的包"})[2])
        mod_unknown = [f for f in c_unknown["factors"] if f["key"] == "mods"][0]["ceiling"]

        import mc_player_calc.modpack as mpmod
        mpmod.upsert_profile("测试包 A", calibrated_factor=0.45, samples=3)
        mpmod.upsert_profile("测试包 B", calibrated_factor=1.90, samples=3)
        mpmod.save_profiles()
        c_a = json.loads(http("POST", base + "/api/calc",
                              {"cpu": "i9-14900K", "mods": "400", "ram": "64G",
                               "behavior": "整合包", "modpack": "测试包 A"})[2])
        c_b = json.loads(http("POST", base + "/api/calc",
                              {"cpu": "i9-14900K", "mods": "400", "ram": "64G",
                               "behavior": "整合包", "modpack": "测试包 B"})[2])
        mod_a = [f for f in c_a["factors"] if f["key"] == "mods"][0]["ceiling"]
        mod_b = [f for f in c_b["factors"] if f["key"] == "mods"][0]["ceiling"]
        check_true("同一个 CPU 下不同包承载不同", mod_a != mod_b,
                   f"A {mod_a} vs B {mod_b}")
        check_true("系数小的包承载更高", mod_a > mod_b, f"A {mod_a} > B {mod_b}")
        check_true("两个包都区别于兜底值", mod_a != mod_unknown and mod_b != mod_unknown,
                   f"兜底 {mod_unknown}")

        # 按包汇总 / 应用 的接口
        code, _, body = http("POST", base + "/api/feedback",
                             {"action": "summary", "kind": "packs"})
        pk = json.loads(body)
        check("按包汇总接口", pk["kind"] == "packs" and "整合包系数汇总" in pk["text"],
              pk["text"][:30])
        code, _, body = http("POST", base + "/api/feedback",
                             {"action": "apply", "kind": "packs", "min_samples": 3})
        app = json.loads(body)
        check_true("按包应用接口可用", app["kind"] == "packs" and "file" in app,
                   str(app.get("applied")))
        for name in ("测试包 A", "测试包 B"):
            mpmod.remove_profile(name)
        mpmod.save_profiles()

        # 7i) 本地状态 / 恢复默认
        st = json.loads(http("GET", base + "/api/state")[2])
        check("GET /api/state 可用", st["ok"] and len(st["items"]) >= 4,
              f"{len(st.get('items', []))} 项")
        check_true("状态项区分 user/derived",
                   {"user", "derived"} <= {x["kind"] for x in st["items"]},
                   str(sorted({x["kind"] for x in st["items"]})))
        check_true("每项都带删除影响说明", all(x.get("hint") for x in st["items"]))
        check_true("状态里带备份分组", "backup_groups" in st)
        check_true("首页有恢复默认面板",
                   'id="state-card"' in html and "st-reset-all" in html)
        app_js = http("GET", base + "/static/app.js")[2].decode("utf-8")
        check_true("危险按钮有二次确认", "window.confirm" in app_js)

        pre = json.loads(http("POST", base + "/api/reset",
                             {"scope": "all", "dry_run": True})[2])
        check("预演不真删", pre["ok"] and pre["report"]["dry_run"], pre["text"][:24])
        check_true("预演会列出将清除的项", len(pre["report"]["cleared"]) >= 1,
                   str([c["label"] for c in pre["report"]["cleared"]]))
        check_true("预演不改动任何文件",
                   {x["key"]: x["exists"] for x in pre["state"]["items"]}
                   == {x["key"]: x["exists"] for x in st["items"]},
                   "预演把文件动了")

        # 真删用户数据 → 校准产物（整合包档案）必须保留
        before = {x["key"]: x["exists"] for x in st["items"]}
        real = json.loads(http("POST", base + "/api/reset", {"scope": "user"})[2])
        after = {x["key"]: x["exists"] for x in real["state"]["items"]}
        check_true("清用户数据后反馈文件消失",
                   before["feedback"] and not after["feedback"],
                   f"{before['feedback']} -> {after['feedback']}")
        check_true("校准产物被保留", before["modpacks"] == after["modpacks"],
                   f"modpacks {before['modpacks']} -> {after['modpacks']}")
        check_true("产生了备份", len(real["report"]["backups"]) >= 1,
                   str(len(real["report"]["backups"])))

        stamp = list(real["state"]["backup_groups"])[0]
        undo = json.loads(http("POST", base + "/api/reset",
                              {"action": "undo", "stamp": stamp})[2])
        check_true("整组撤销成功", len(undo["undone"]) >= 1, str(undo["undone"]))
        check_true("撤销后反馈文件回来了",
                   {x["key"]: x["exists"] for x in undo["state"]["items"]}["feedback"])
        try:
            http("POST", base + "/api/reset", {"action": "undo", "stamp": "bogus"})
            check("非法时间戳被拒", False, "居然放行了")
        except urllib.error.HTTPError as e:
            check("非法时间戳被拒（400）", e.code == 400, str(e.code))

        # 8) 本地 GUI 结果一致性抽查（同一输入应给出同一结论）
        from mc_player_calc.engine import CalcInput, calculate
        from mc_player_calc.parser import RawInput, parse_raw
        f, w = parse_raw(RawInput(mod_count="30", cpu="i5-12400", ram="16G",
                                  network="一般 (100M 家宽 / 普通 VPS)", behavior="红石生电"))
        local = calculate(CalcInput(**f))
        check("网页与内核结论一致", local.final_players == res["final_players"],
              f"{local.final_players} == {res['final_players']}")
    finally:
        httpd.shutdown()
        httpd.server_close()
        for key in ("MC_CALC_FEEDBACK", "MC_CALC_BEHAVIOR", "MC_CALC_MODPACKS",
                    "MC_CALC_CUSTOM_CPUS"):
            os.environ.pop(key, None)
        shutil.rmtree(ws_tmp, ignore_errors=True)

    print("\n" + ("网页接口自测全部通过 ✅" if not FAILURES else f"失败 {len(FAILURES)} 项 ❌: {FAILURES}"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
