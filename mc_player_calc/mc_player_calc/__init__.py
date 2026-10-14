"""Minecraft 服务器人数上限本地计算工具。

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
