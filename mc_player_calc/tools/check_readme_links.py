"""检查 README 的站内锚点与相对链接是否有效。

GitHub 的标题锚点算法：转小写 → 删掉标点（保留字母数字/连字符/空格/中文）→ 空格转连字符。
中文标题不做拼音化，所以中文锚点会原样保留（URL 里会显示成百分号编码，但能跳）。

    python tools/check_readme_links.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

FAILURES: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        FAILURES.append(name)


def slug(title: str) -> str:
    """按 GitHub 的规则把标题转成锚点。

    注意 GitHub 是**删除**标点而不是替换成连字符，所以
    "14. 提交数据 / 报告问题" → "14-提交数据-报告问题"（`/` 被删掉，不留连字符）。
    """
    s = title.strip().lower()
    # 去掉 markdown 行内标记
    s = re.sub(r"[`*_\[\]()]", "", s)
    # 删掉除字母数字、中文、空格、连字符以外的字符
    s = re.sub(r"[^\w\u4e00-\u9fff\s-]", "", s)
    return re.sub(r"\s+", "-", s).strip("-")


def main() -> int:
    md_files = sorted(ROOT.glob("*.md"))
    total_anchors = 0
    total_links = 0
    for md in md_files:
        text = md.read_text(encoding="utf-8")
        heads = {slug(m.group(2)) for m in re.finditer(r"^(#{1,6})\s+(.*)$", text, re.M)}
        anchors = set(re.findall(r"\]\(#([^)]+)\)", text))
        total_anchors += len(anchors)
        bad = sorted(a for a in anchors if a not in heads)
        check(f"{md.name} 站内锚点有效", not bad, f"失效：{bad}" if bad else "")

        # 相对文件链接
        links = {m for m in re.findall(r"\]\((?!https?:|#|mailto:)([^)#]+)\)", text)}
        total_links += len(links)
        missing = sorted(f for f in links if not (ROOT / f.strip()).exists())
        check(f"{md.name} 相对链接指向真实文件", not missing,
              f"缺失：{missing}" if missing else "")

    print(f"\n共检查 {len(md_files)} 个 Markdown、{total_anchors} 个站内锚点、"
          f"{total_links} 个相对链接")

    # 打包脚本会往 HANDOFF.md 刷新"测试基线"表格。
    # 早期实现只在第一次替换占位符，导致之后永远不更新——这里守住：
    # 表格必须恰好出现一次，且必须覆盖全部测试套件。
    handoff = ROOT / "HANDOFF.md"
    if handoff.is_file():
        text = handoff.read_text(encoding="utf-8")
        header_count = len(re.findall(r"\| 测试 \| 命令 \| 本次结果 \| 输出末尾 \|", text))
        check("HANDOFF 里测试基线表格恰好一份", header_count == 1, f"出现 {header_count} 次")
        check("HANDOFF 里不再残留占位符", "<!-- TEST_BASELINE -->" not in text)
        for suite in ("内核自检", "网页接口自测", "桌面窗口自测", "前端静态检查", "文档链接检查"):
            check(f"测试基线含「{suite}」", f"| {suite} |" in text)

    if FAILURES:
        print(f"失败 {len(FAILURES)} 项：{FAILURES}")
        return 1
    print("Markdown 链接检查通过 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
