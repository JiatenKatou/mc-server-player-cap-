"""Minecraft 服务器人数上限本地计算工具。

    Minecraft Server Player Cap
    Copyright (C) 2026 <请填写你的名字或昵称>

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, version 3 of the License.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.

许可：GPL-3.0（全文见项目根目录 LICENSE）。
项目声明与 GPLv3 第 7 节附加条款见项目根目录 COPYRIGHT。

⚠ 本程序输出的是**模型估算值，不是实测保证**，请勿用作服务器采购或容量承诺的依据。
   CPU 维度的核心系数目前仍为估算值，项目正在收集真实实测数据用于校准。

设计原则：
1. 木桶效应（Liebig's law of the minimum）：最终人数上限 = min(各资源维度可承载人数)。
2. 所有影响系数集中在 config.py，后续拿到真实数据后只改那一处。
"""

from .config import DEFAULT_PARAMS, Params
from .engine import CalcInput, CalcResult, Factor, calculate

__all__ = [
    "DEFAULT_PARAMS",
    "Params",
    "CalcInput",
    "CalcResult",
    "Factor",
    "calculate",
]

__version__ = "0.1.0"

# 供其他地方引用，避免每处都写一遍许可名
__license__ = "GPL-3.0"
