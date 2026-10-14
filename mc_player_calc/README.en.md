# Minecraft Server Player Cap

**Estimate how many players your Minecraft server can handle — mods, CPU, RAM, network,
bottlenecked by the weakest link.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Zero dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](#quick-start)

[English](README.en.md) | [中文](README.md)

> This is the **English quick-start**. The in-depth documentation (coefficient provenance,
> calibration workflow, troubleshooting) is currently Chinese-only — see [`README.md`](README.md).
> The tool's UI is Chinese; the calculation model itself is language-independent.

---

## What it does

It models four independent limits and reports the **smallest** one (Liebig's law of the minimum):

| Dimension | What it depends on |
| --- | --- |
| **CPU** | Effective single-core score (CPU-Z) × cooling factor × physical cores, scaled by a power law |
| **RAM** | Fixed overhead + per-player + per-mod allocation |
| **Network** | Uplink bandwidth ÷ per-player traffic (with a duty-cycle factor for peak load) |
| **Mods / gameplay** | Content-complexity ceiling; per-modpack profiles |

The result tells you the ceiling **and which dimension is binding** — that's usually more
useful than the raw number.

## Quick start

Requires Python 3.10+ (3.12 recommended). **No `pip install` of anything.**

```bash
python -m mc_player_calc                 # local web UI (default, opens in your browser)
python -m mc_player_calc --gui           # tkinter desktop window
python -m mc_player_calc --help          # command line
```

On Windows you can also just double-click `启动计算器.cmd` (web) or `桌面窗口版.cmd` (desktop).

## Features

- **Zero dependencies** — pure Python standard library, including the web UI (`http.server`
  + vanilla JS). Nothing to install, nothing to break.
- **One engine, three front-ends** — the web UI, the desktop window and the CLI share
  `parser` / `engine` / `report`, so they can never disagree.
- **Everything stays local** — binds to `127.0.0.1`, no telemetry, no account, no uploads.
- **Cooling factor** — desktop by cooler class; laptops by chassis × thermal compound.
  Mobile CPUs are auto-detected from the model suffix.
- **CPU-Z scale** — the UI works in the single-thread CPU-Z score you already know, and you
  can register your own CPU models.
- **Per-modpack coefficients** — pack authors optimise very differently, so each pack gets
  its own calibrated load factor instead of one shared "modpack" number.
- **Feedback loop** — server owners can submit real measured limits; the tool aggregates them
  and writes the derived coefficients back into the model.
- **Reset to defaults** — clears local state by category, backs up first, and the whole
  reset can be undone as a group.

## ⚠ This is an estimator, not a guarantee

The CPU-dimension coefficients (reference player count, multi-core scaling, capacity exponent)
are currently **estimates with no solid empirical backing**. RAM and network numbers do trace
back to public second-hand measurements; the cooling tables are relative.

**Do not use the output for purchasing or capacity commitments.**

That is exactly why this project is **collecting real measured data from server owners** to
replace the estimated coefficients. If you run a server, see
[section 14 of the Chinese README](README.md#14-提交数据-报告问题) — the tool exports a
self-describing data file that both you and a human/AI reviewer can read.

## Repository layout

```
mc_player_calc/
├─ config.py      ★ all tunable coefficients (bucket dimensions) + CPU-Z calibration
├─ cooling.py     ★ cooling tables (desktop cooler / laptop chassis / thermal compound)
├─ cpu_data.py    ★ CPU database, CPU-Z ↔ internal index, desktop/mobile detection
├─ parser.py      lenient input parsing (RAM, bandwidth, CPU model, cooling, modpack name)
├─ engine.py      ★ the bucket-effect core: four dimensions, bottleneck, suggestions
├─ report.py      text report rendering
├─ web.py         ★ local web server (http.server + JSON API)
├─ web/           vanilla HTML/CSS/JS front-end
├─ gui.py         tkinter desktop window
├─ cli.py         command line
├─ calibrate.py   ★ reverse-engineer CPU coefficients from measured data
├─ modpack.py     ★ per-modpack load profiles
├─ feedback.py    ★ server-owner feedback collection and aggregation
├─ reset.py       reset-to-defaults with group undo
└─ selftest.py    210+ assertions
```

## Contributing

For the full architecture, hard constraints and known gaps, read
[`AGENTS.md`](AGENTS.md) and [`HANDOFF.md`](HANDOFF.md) (both Chinese).

**Before committing, all five checks must pass:**

```bash
python -m mc_player_calc.selftest        # core self-test (210+ assertions)
python tools/web_smoketest.py            # HTTP API smoke test (real server, 85+ checks)
python tools/gui_smoketest.py            # tkinter smoke test
python tools/check_web_ids.py            # front-end static check
python tools/check_readme_links.py       # doc anchors and relative links
```

## License

[MIT](LICENSE). The output is an estimate, not a measurement — see the disclaimer in `LICENSE`.
