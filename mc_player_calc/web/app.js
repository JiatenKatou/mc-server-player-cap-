/* Minecraft 服务器人数上限计算器 — 本地网页版前端
 * 只做三件事：拉选项 → 收集输入 → 调 /api/calc 渲染结果。计算全在 Python 侧。
 */
'use strict';

const $ = (id) => document.getElementById(id);
let OPTIONS = null;
let LAST_SHORT = '';
let COOL_TIMER = null;

const FIELDS = ['mod_count', 'cpu', 'ram', 'network', 'bandwidth', 'download', 'latency', 'loss',
                'behavior', 'player_sim', 'view_distance', 'modpack',
                'platform', 'chassis', 'material', 'radiator', 'cooling_override'];

/* ---------------- 初始化 ---------------- */
async function init() {
  try {
    const res = await fetch('/api/options');
    OPTIONS = await res.json();
  } catch (err) {
    $('detail').textContent = '无法连接到本地计算服务：' + err;
    return;
  }
  if (!OPTIONS.ok) {
    $('detail').textContent = '选项加载失败：' + (OPTIONS.error || '未知错误');
    return;
  }

  $('version').textContent = '（v' + OPTIONS.version + '）';
  const c = OPTIONS.cooling;

  buildCpuList();
  fillSelect($('network'), OPTIONS.network_presets.map((x) => x.name));
  fillSelect($('behavior'), OPTIONS.behaviors);
  fillSelect($('player_sim'), OPTIONS.player_sims);
  fillSelect($('view_distance'), OPTIONS.view_distances);
  fillPackHints();
  fillSelect($('radiator'), c.desktop.map((x) => x.name));
  fillSelect($('chassis'), c.chassis.map((x) => x.name));
  fillSelect($('material'), c.material.map((x) => x.name));

  $('radiator').value = c.defaults.desktop;
  $('chassis').value = c.defaults.chassis;
  $('material').value = c.defaults.material;
  $('network').value = OPTIONS.network_presets[2].name;

  renderCustomCpuList();
  initFeedback();
  bindStateEvents();
  await loadState();
  bindEvents();
  await refreshCooling(true);
  await calc();
}

/* ==================================================================
 * 服主反馈收集
 * ================================================================== */
const FB_FIELDS = ['fb-cpu', 'fb-cpuz', 'fb-players', 'fb-view', 'fb-tps', 'fb-playstyle',
                   'fb-bottleneck', 'fb-modpack-name', 'fb-mc-version', 'fb-mods',
                   'fb-modpack-kind', 'fb-ram', 'fb-software', 'fb-progress', 'fb-note'];

function initFeedback() {
  const meta = OPTIONS.feedback;
  if (!meta) return;

  $('fb-privacy').textContent = meta.privacy;
  $('fb-hint').textContent = '文件位置：' + meta.file;
  fillSelect($('fb-view'), meta.view_distances);
  $('fb-view').value = '10';
  fillSelect($('fb-playstyle'), meta.playstyles.map((x) => x.name));
  fillSelect($('fb-mc-version'), meta.mc_versions);
  fillSelect($('fb-modpack-kind'), meta.modpack_kinds.map((x) => x.name));
  fillSelect($('fb-software'), meta.software);
  fillSelect($('fb-progress'), meta.progress_stages.map((x) => x.name));
  if (meta.progress_stages[1]) $('fb-progress').value = meta.progress_stages[1].name;

  $('fb-playstyle').addEventListener('change', syncModpackFields);
  fillSelect($('fb-optimization'), meta.optimization_levels || []);
  $('behavior').addEventListener('change', syncPackBox);
  $('modpack').addEventListener('input', updatePackNote);
  syncPackBox();
  syncModpackFields();
  renderFeedbackList({ entries: [], stats: meta.stats || {} });
}

function currentPlaystyleMeta() {
  const name = $('fb-playstyle').value;
  return ((OPTIONS.feedback || {}).playstyles || []).find((x) => x.name === name) || {};
}

function syncModpackFields() {
  const meta = currentPlaystyleMeta();
  $('fb-modpack').classList.toggle('hidden', !meta.extended);
  $('fb-playstyle-desc').textContent = meta.name
    ? `当前玩法「${meta.name}」：${meta.desc}（内置负载系数 ${meta.multiplier}）` : '';
}

function collectFeedback() {
  return {
    cpu: $('fb-cpu').value,
    cpuz_single: $('fb-cpuz').value,
    players: $('fb-players').value,
    view: $('fb-view').value,
    tps: $('fb-tps').value,
    playstyle: $('fb-playstyle').value,
    bottleneck: $('fb-bottleneck').value,
    modpack_name: $('fb-modpack-name').value,
    mc_version: $('fb-mc-version').value,
    mods: $('fb-mods').value,
    modpack_kind: $('fb-modpack-kind').value,
    ram: $('fb-ram').value,
    software: $('fb-software').value,
    progress: $('fb-progress').value,
    optimization: $('fb-optimization') ? $('fb-optimization').value : '',
    note: $('fb-note').value,
    source: '',
  };
}

async function submitFeedback() {
  const hint = $('fb-hint');
  const payload = collectFeedback();
  if (!payload.cpu.trim()) { hint.textContent = '⚠ 请填写 CPU 型号'; return; }
  if (!String(payload.players).trim()) { hint.textContent = '⚠ 请填写活跃用户数'; return; }

  $('fb-submit').disabled = true;
  hint.textContent = '正在提交…';
  try {
    const res = await fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!data.ok) { hint.textContent = '⚠ ' + (data.error || '提交失败'); return; }

    const s = data.saved;
    let msg = `✅ 已收录：${s.cpu} / ${s.playstyle} / ${s.players} 人 @ ${s.tps || '—'} TPS`
            + `（负载系数 ${s.playstyle_multiplier}），累计 ${data.count} 条`;
    if ((data.warnings || []).length) msg += `\n提示：${data.warnings[0]}`;
    msg += `\n文件：${data.file}`;
    hint.textContent = msg;
    clearFeedbackForm(false);
    await refreshFeedback();
  } catch (err) {
    hint.textContent = '⚠ 提交请求失败：' + err;
  } finally {
    $('fb-submit').disabled = false;
  }
}

function clearFeedbackForm(clearHint = true) {
  FB_FIELDS.forEach((id) => {
    const el = $(id);
    if (el && el.tagName === 'INPUT') el.value = '';
  });
  $('fb-view').value = '10';
  $('fb-bottleneck').value = 'unknown';
  if (clearHint) $('fb-hint').textContent = '';
}

async function refreshFeedback() {
  try {
    const res = await fetch('/api/feedback');
    const data = await res.json();
    if (!data.ok) return;
    OPTIONS.feedback.stats = data.stats;
    renderFeedbackList(data);
    renderSummary(data.summary, null);
  } catch (err) { /* 忽略 */ }
}

function renderFeedbackList(data) {
  const stats = (data && data.stats) || {};
  const byStyle = stats.by_playstyle || {};
  const parts = Object.entries(byStyle).map(([k, v]) => `${k} ${v}`).join(' · ');
  $('fb-count').textContent = `已收集 ${stats.count || 0} 条`
    + (parts ? `（${parts}）` : '');

  const entries = (data && data.entries) || [];
  const box = $('fb-list');
  if (!entries.length) {
    box.innerHTML = '<li class="cc-empty">还没有收到反馈数据</li>';
    return;
  }
  box.innerHTML = entries.map((e, i) => {
    const bt = e.bottleneck === 'cpu' ? 'cpu' : 'other';
    const btLabel = { cpu: 'CPU 瓶颈', ram: '内存瓶颈', network: '网络瓶颈',
                      mods: '模组瓶颈', unknown: '瓶颈未知' }[e.bottleneck] || e.bottleneck;
    const pack = e.modpack_name
      ? ` · ${e.modpack_name}${e.mc_version ? ' ' + e.mc_version : ''}`
        + `${e.mods ? ` ${e.mods} 模组` : ''}`
      : '';
    return `<li>
      <span class="fb-list-main">
        <span class="fb-tag ${bt}">${btLabel}</span>
        <b>${e.cpu}</b>${e.cpuz_single ? ` (CPU-Z ${e.cpuz_single})` : ''}
        · ${e.players} 人 @ ${e.tps == null ? '—' : e.tps} TPS · 视距 ${e.view}
        · ${e.playstyle}${pack}
      </span>
      <button type="button" class="cc-del" data-index="${i}">删除</button>
    </li>`;
  }).join('');
  box.querySelectorAll('.cc-del').forEach((btn) => {
    btn.addEventListener('click', () => removeFeedback(Number(btn.dataset.index)));
  });
}

function renderSummary(summary, text) {
  const box = $('fb-summary-text');
  if (text) { box.textContent = text; box.classList.remove('hidden'); return; }
  if (!summary) return;
  const lines = [`累计 ${summary.total} 条，可用于统计的分组 ${summary.usable_groups} 个`, ''];
  Object.entries(summary.suggested || {}).forEach(([name, s]) => {
    if (!s.samples) {
      lines.push(`【${name}】暂无样本，沿用当前系数 ${s.current_multiplier}`);
      return;
    }
    const delta = s.suggested_multiplier - s.current_multiplier;
    lines.push(`【${name}】样本 ${s.samples} 条：${s.current_multiplier} → ${s.suggested_multiplier}`
      + `（${delta > 0 ? '+' : ''}${delta.toFixed(2)}）`
      + (s.spread ? ` 组内离散 ${s.spread}×` : '')
      + (s.samples < 3 ? ' ⚠ 样本偏少' : ''));
    lines.push(`    反推明细 ${JSON.stringify(s.values)}`);
  });
  if ((summary.skipped || []).length) {
    lines.push('', '跳过的数据：');
    summary.skipped.slice(0, 10).forEach((x) => lines.push(`  - ${x.entry}：${x.reason}`));
  }
  box.textContent = lines.join('\n');
  box.classList.remove('hidden');
}

async function removeFeedback(index) {
  if (!confirm('确认删除这条反馈数据？')) return;
  try {
    const res = await fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'remove', index }),
    });
    const data = await res.json();
    if (!data.ok) { $('fb-hint').textContent = '⚠ ' + (data.error || '删除失败'); return; }
    $('fb-hint').textContent = `已删除 ${data.removed.cpu} / ${data.removed.playstyle}，`
                             + `剩余 ${data.count} 条`;
    await refreshFeedback();
  } catch (err) {
    $('fb-hint').textContent = '⚠ 删除请求失败：' + err;
  }
}

async function feedbackAction(action, format) {
  const hint = $('fb-hint');
  try {
    const res = await fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, format }),
    });
    const data = await res.json();
    if (!data.ok) { hint.textContent = '⚠ ' + (data.error || '操作失败'); return; }

    if (action === 'summary') {
      renderSummary(data.summary, data.text);
      hint.textContent = '已生成汇总（见下方文本）';
      return;
    }
    if (action === 'apply') {
      const names = Object.keys(data.applied || {});
      hint.textContent = names.length
        ? `✅ 已把 ${names.length} 个玩法的系数写入 ${data.file}（样本门槛 ${data.min_samples} 条），`
          + '下次计算自动生效'
        : `没有满足样本门槛（${data.min_samples} 条）的分组，未修改任何系数`;
      renderSummary(data.summary, null);
      return;
    }
    if (action === 'export') {
      downloadText(data.filename, data.content);
      hint.textContent = `已导出 ${data.filename}`;
    }
  } catch (err) {
    hint.textContent = '⚠ 操作请求失败：' + err;
  }
}

function downloadText(filename, content) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function buildCpuList() {
  const names = [...OPTIONS.cpu.desktop, ...OPTIONS.cpu.mobile].map((x) => x.name);
  $('cpu_list').innerHTML = names.map((n) => `<option value="${n}"></option>`).join('');
}

/* ---------------- 整合包名称（一个包一套系数） ---------------- */
function fillPackHints() {
  const packs = (OPTIONS.modpacks && OPTIONS.modpacks.profiles) || [];
  $('pack_hints').innerHTML = packs.map((p) => `<option value="${p.name}"></option>`).join('');
}

function syncPackBox() {
  const isPack = $('behavior').value === '整合包';
  $('pack-box').classList.toggle('hidden', !isPack);
  if (isPack) updatePackNote();
}

function updatePackNote() {
  if ($('behavior').value !== '整合包') return;
  const name = $('modpack').value.trim();
  const packs = (OPTIONS.modpacks && OPTIONS.modpacks.profiles) || [];
  const key = name.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]/g, '');
  const hit = key
    ? packs.find((p) => p.key && (p.key === key || p.key.includes(key) || key.includes(p.key)))
    : null;
  if (hit) {
    $('pack-note').textContent =
      `已匹配档案「${hit.name}」：负载系数 ${hit.factor}`
      + (hit.calibrated_factor
          ? `（由 ${hit.samples} 条服主反馈校准）`
          : '（人工预填值）')
      + (hit.optimization ? `　${hit.optimization}` : '');
  } else if (name) {
    $('pack-note').textContent =
      `「${name}」还没有专属档案，先按类型/进度折算兜底（基础 `
      + `${(OPTIONS.modpacks && OPTIONS.modpacks.base_factor) || 1.6}）。`
      + '多收几条该包的服主数据就能自动校准出它自己的系数。';
  } else {
    $('pack-note').textContent = '填包名后工具会用这个包自己的负载系数；不填则按通用兜底值估算。';
  }
}

/* ---------------- 本地状态 / 恢复默认 ---------------- */
const STATE_LABEL = { user: '用户数据', derived: '校准产物', debug: '导出/草稿' };

function stateText(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

async function postJson(url, payload) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || '请求失败');
  return data;
}

async function loadState() {
  try {
    const res = await fetch('/api/state');
    const state = await res.json();
    if (!state.ok) throw new Error(state.error || '读取失败');
    renderState(state);
  } catch (err) {
    showReport(`读取本地状态失败：${err.message}`);
  }
}

function renderState(state) {
  $('state-list').innerHTML = (state.items || []).map((it) => `
    <li class="${it.exists ? '' : 'state-gone'}">
      <span class="state-tag ${it.kind}">${STATE_LABEL[it.kind] || it.kind}</span>
      <b>${stateText(it.label)}</b>
      ${it.exists
        ? `<span class="dim">${stateText(it.detail || '')}</span>`
        : '<span class="dim">（无）</span>'}
      <div class="dim" style="font-size:0.85em">${stateText(it.hint || '')}</div>
    </li>`).join('');

  const groups = Object.entries(state.backup_groups || {});
  $('st-backups-wrap').classList.toggle('hidden', groups.length === 0);
  $('st-backups').innerHTML = groups.map(([stamp, paths]) => `
    <li>
      <b>${stateText(stamp)}</b>
      <span class="dim">${paths.length} 个文件</span>
      <button type="button" data-undo="${stateText(stamp)}">整组还原</button>
    </li>`).join('');
  $('st-backups').querySelectorAll('button[data-undo]').forEach((btn) => {
    btn.addEventListener('click', () => undoReset(btn.dataset.undo));
  });
}

function showReport(text) {
  const pre = $('st-report');
  pre.classList.remove('hidden');
  pre.textContent = text;
}

async function refreshAfterReset(state) {
  if (state) renderState(state);
  try {
    const res = await fetch('/api/options');
    const data = await res.json();
    if (data.ok) {
      OPTIONS = data;
      buildCpuList();
      fillPackHints();
      renderCustomCpuList();
    }
  } catch (_err) { /* 选项刷新失败不影响"已恢复默认"这个结论 */ }
  await refreshFeedback();
  await calc();
}

async function doReset(scope, { dryRun = false, withExports = false } = {}) {
  if (!dryRun) {
    const msg = (scope === 'all'
      ? '将清除用户数据与校准产物'
      : scope === 'user' ? '将清除你自己录入的数据（自定义 CPU、服主反馈）'
        : '将清除自动生成的校准产物（玩法系数、整合包档案）')
      + '。\n\n会先备份成 .bak，可以整组撤销。确定继续？'
      + (scope === 'user' || scope === 'all' ? '\n\n★ 建议先用「导出」保存一份反馈数据。' : '');
    if (!window.confirm(msg)) return;
  }
  try {
    const res = await postJson('/api/reset',
                               { scope, dry_run: dryRun, with_exports: withExports });
    showReport(res.text + (dryRun ? '\n\n（这只是预演，没有真的删）' : ''));
    if (!dryRun) await refreshAfterReset(res.state);
  } catch (err) {
    showReport(`操作失败：${err.message}`);
  }
}

async function undoReset(stamp) {
  if (!window.confirm(`把 ${stamp} 这组备份全部还原？`)) return;
  try {
    const res = await postJson('/api/reset', { action: 'undo', stamp });
    showReport(res.text || '已还原');
    await refreshAfterReset(res.state);
  } catch (err) {
    showReport(`撤销失败：${err.message}`);
  }
}

function bindStateEvents() {
  $('st-preview').addEventListener('click', () => doReset('all', { dryRun: true }));
  $('st-reset-user').addEventListener('click', () => doReset('user'));
  $('st-reset-derived').addEventListener('click', () => doReset('derived'));
  $('st-reset-all').addEventListener('click', () => doReset('all'));
}

/* ---------------- 自定义 CPU 录入器 ---------------- */
function renderCustomCpuList() {
  const box = $('cc-list');
  const items = (OPTIONS.custom_cpu && OPTIONS.custom_cpu.list) || [];
  if (!items.length) {
    box.innerHTML = '<li class="cc-empty">还没有自定义型号</li>';
    return;
  }
  box.innerHTML = items.map((x) => `
    <li>
      <span class="cc-name" title="${x.name}">${x.name}</span>
      <span class="dim">CPU-Z ${x.cpuz} · ${x.cores}核 · 指数 ${x.index}</span>
      <button type="button" class="cc-del" data-name="${x.name}">删除</button>
    </li>`).join('');
  box.querySelectorAll('.cc-del').forEach((btn) => {
    btn.addEventListener('click', () => removeCustomCpu(btn.dataset.name));
  });
}

async function saveCustomCpu() {
  const name = $('cc-name').value.trim();
  const cpuz = $('cc-cpuz').value.trim();
  const cores = $('cc-cores').value.trim();
  const platform = $('cc-platform').value;
  const note = $('cc-note').value.trim();
  const hint = $('cc-hint');

  if (!name) { hint.textContent = '⚠ 请填写型号名称'; return; }
  if (!cpuz) { hint.textContent = '⚠ 请填写 CPU-Z 单核跑分'; return; }

  $('cc-save').disabled = true;
  hint.textContent = '正在保存…';
  try {
    const res = await fetch('/api/cpu/custom', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'add', name, cpuz, cores, platform, note }),
    });
    const data = await res.json();
    if (!data.ok) { hint.textContent = '⚠ ' + (data.error || '保存失败'); return; }

    OPTIONS.custom_cpu.list = data.list;
    // 把新型号并进下拉候选
    const item = data.spec;
    OPTIONS.cpu[item.platform === 'mobile' ? 'mobile' : 'desktop'].unshift({
      name: item.name, score: item.index, cpuz: item.cpuz, cores: item.cores,
      platform: item.platform, note: '自定义', custom: true,
    });
    buildCpuList();
    renderCustomCpuList();

    $('cc-name').value = '';
    $('cc-cpuz').value = '';
    $('cc-cores').value = '';
    $('cc-note').value = '';

    // 自动选用刚录入的型号并重算
    $('cpu').value = item.name;
    await refreshCooling(true);
    await calc();
    hint.textContent = `✅ 已保存「${item.name}」：CPU-Z 单核 ${item.cpuz} → 内部指数 ${item.index}`
                     + `（已自动选用并重算）`;
  } catch (err) {
    hint.textContent = '⚠ 保存请求失败：' + err;
  } finally {
    $('cc-save').disabled = false;
    await refreshCustomCpuFileNote();
  }
}

async function removeCustomCpu(name) {
  const hint = $('cc-hint');
  try {
    const res = await fetch('/api/cpu/custom', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'remove', name }),
    });
    const data = await res.json();
    if (!data.ok) { hint.textContent = '⚠ ' + (data.error || '删除失败'); return; }
    if (OPTIONS.custom_cpu) OPTIONS.custom_cpu.list = data.list;
    ['desktop', 'mobile'].forEach((p) => {
      OPTIONS.cpu[p] = OPTIONS.cpu[p].filter((x) => x.name !== name);
    });
    buildCpuList();
    renderCustomCpuList();
    hint.textContent = `已删除「${name}」`;
    if ($('cpu').value === name) { $('cpu').value = 'Ryzen 5 5600'; await calc(); }
  } catch (err) {
    hint.textContent = '⚠ 删除请求失败：' + err;
  }
}

async function refreshCustomCpuFileNote() {
  try {
    const res = await fetch('/api/cpu/custom');
    const data = await res.json();
    if (data.ok && OPTIONS.custom_cpu) {
      OPTIONS.custom_cpu.file = data.file;
      if (!data.list.length) return;
      $('cc-hint').textContent += `\n文件：${data.file}`;
    }
  } catch (err) { /* 只是补充提示，失败无所谓 */ }
}

function fillSelect(sel, values) {
  sel.innerHTML = values.map((v) => `<option value="${v}">${v}</option>`).join('');
}

function bindEvents() {
  $('calc').addEventListener('click', calc);
  $('reset').addEventListener('click', reset);
  $('copy').addEventListener('click', copyResult);
  $('speedtest').addEventListener('click', openSpeedtest);
  $('cc-save').addEventListener('click', saveCustomCpu);
  // 反馈收集
  $('fb-submit').addEventListener('click', submitFeedback);
  $('fb-clear').addEventListener('click', () => clearFeedbackForm());
  $('fb-summary').addEventListener('click', () => feedbackAction('summary'));
  $('fb-export-json').addEventListener('click', () => feedbackAction('export', 'json'));
  $('fb-export-csv').addEventListener('click', () => feedbackAction('export', 'csv'));
  $('fb-export-anchors').addEventListener('click', () => feedbackAction('export', 'anchors'));
  $('fb-export-agent').addEventListener('click', () => feedbackAction('export', 'agent'));
  $('fb-apply').addEventListener('click', () => feedbackAction('apply'));
  ['fb-cpu', 'fb-cpuz', 'fb-players', 'fb-tps', 'fb-mods'].forEach((id) => {
    $(id).addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); submitFeedback(); }
    });
  });
  $('cc-clear').addEventListener('click', () => {
    ['cc-name', 'cc-cpuz', 'cc-cores', 'cc-note'].forEach((id) => { $(id).value = ''; });
    $('cc-platform').value = '';
    $('cc-hint').textContent = '';
  });
  // 录入器里按回车就保存，不要触发整页重算
  ['cc-name', 'cc-cpuz', 'cc-cores', 'cc-note'].forEach((id) => {
    $(id).addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); saveCustomCpu(); }
    });
  });

  // CPU 一变：重新判定平台、刷新模具候选
  $('cpu').addEventListener('input', () => { clearTimeout(COOL_TIMER); COOL_TIMER = setTimeout(() => refreshCooling(), 220); });
  // 散热相关一变：只刷新提示
  ['platform', 'chassis', 'material', 'radiator', 'cooling_override'].forEach((id) => {
    $(id).addEventListener('change', () => refreshCooling());
    $(id).addEventListener('input', () => refreshCooling());
  });

  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' || e.target.tagName === 'BUTTON') return;
    // 自定义 CPU 录入器有自己的回车行为（保存），不要触发整页重算
    if (e.target.closest('#cpu-adder')) return;
    e.preventDefault();
    calc();
  });
}

/* ---------------- 测速网：交给本地服务调起默认浏览器 ---------------- */
async function openSpeedtest() {
  const url = (OPTIONS.speedtest && OPTIONS.speedtest.url) || '';
  const hint = $('speedtest-hint');
  if (!url) { hint.textContent = '未配置测速地址'; return; }

  $('speedtest').disabled = true;
  hint.textContent = '正在打开浏览器…';
  try {
    const res = await fetch('/api/open-url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (data.ok) {
      hint.textContent = '已在浏览器打开，测完把上行填到左边「上行 Mbps」';
    } else {
      // 服务端拒绝或启动失败时，退化为浏览器自己开新标签
      hint.textContent = '服务端未能打开，改为新标签页打开：' + url;
      window.open(url, '_blank', 'noopener');
    }
  } catch (err) {
    hint.textContent = '服务端未响应，改为新标签页打开：' + url;
    window.open(url, '_blank', 'noopener');
  } finally {
    $('speedtest').disabled = false;
    setTimeout(() => { hint.textContent = ''; }, 8000);
  }
}

function collect() {
  const data = {};
  FIELDS.forEach((k) => { data[k] = $(k).value; });
  return data;
}

/* ---------------- 散热联动 ---------------- */
async function refreshCooling(silent) {
  let payload;
  try {
    const res = await fetch('/api/cooling', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(collect()),
    });
    payload = await res.json();
  } catch (err) {
    if (!silent) $('cooling-note').textContent = '散热解析失败：' + err;
    return null;
  }
  if (!payload.ok) {
    if (!silent) $('cooling-note').textContent = payload.error || '散热解析失败';
    return null;
  }

  const mobile = payload.platform === 'mobile';
  $('row-radiator').classList.toggle('hidden', mobile);
  $('row-chassis').classList.toggle('hidden', !mobile);
  $('row-material').classList.toggle('hidden', !mobile);

  // 移动端：把模具候选收窄到该后缀的推荐档位（已选值不在候选里就切到推荐档）
  if (mobile && payload.chassis_options && payload.chassis_options.length) {
    const cur = $('chassis').value;
    fillSelect($('chassis'), payload.chassis_options);
    $('chassis').value = payload.chassis_options.includes(cur)
      ? cur : payload.chassis_options[0];
  }

  let note;
  if (mobile) {
    if (payload.override != null) {
      note = `已使用自定义总散热系数 ${payload.factor.toFixed(3)}（覆盖模具与导热）`;
    } else {
      note = `检测到移动端型号（后缀 ${payload.suffix || '未知'}）：`
           + `散热系数 = 模具 ${payload.chassis_coef.toFixed(3)} × 导热 ${payload.material_coef.toFixed(3)}`
           + ` = ${payload.factor.toFixed(3)}\n`
           + `笔记本实际性能还取决于温度墙与功耗墙，模具档位误差影响很大`;
    }
  } else if (payload.override != null) {
    note = `已使用自定义总散热系数 ${payload.factor.toFixed(3)}`;
  } else {
    note = `桌面端型号：散热系数 ${payload.factor.toFixed(3)}（${payload.radiator}）`;
  }
  if (payload.warnings && payload.warnings.length) note += '\n⚠ ' + payload.warnings[0];

  $('cooling-note').textContent = note;
  return payload;
}

/* ---------------- 计算与渲染 ---------------- */
async function calc() {
  $('calc').disabled = true;
  try {
    const res = await fetch('/api/calc', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(collect()),
    });
    const data = await res.json();
    if (!data.ok) {
      $('final').textContent = '输入有误';
      $('final').style.color = 'var(--bad)';
      $('detail').textContent = data.error || '计算失败';
      return;
    }
    render(data);
  } catch (err) {
    $('detail').textContent = '计算请求失败：' + err;
  } finally {
    $('calc').disabled = false;
  }
}

function render(d) {
  $('final').textContent = d.final_players + ' 人';
  $('final').style.color = 'var(--accent)';

  const binding = d.binding.map((b) => b.label).join('、') || '未识别到瓶颈';
  $('binding').textContent = '瓶颈：' + binding;
  $('tps').textContent = `估算 TPS ≈ ${d.tps_estimate}（目标 20）`;
  $('top-warning').textContent = d.warnings.length ? '⚠ ' + d.warnings[0] : '';

  const tbody = $('factor-table').querySelector('tbody');
  tbody.innerHTML = d.factors.map((f) => {
    const cls = f.is_bottleneck ? 'bottleneck' : (f.near_bottleneck ? 'near' : '');
    const load = f.load_pct == null ? '—' : f.load_pct + '%';
    return `<tr class="${cls}">
      <td class="label">${f.label}</td>
      <td>${f.ceiling} 人</td>
      <td>${load}</td>
      <td>${f.status}</td>
    </tr>`;
  }).join('');

  $('detail').textContent = d.report;
  LAST_SHORT = d.report_short;
  $('cooling-note').textContent = d.cooling && d.cooling.warnings.length
    ? $('cooling-note').textContent.replace(/\n⚠.*$/, '') + '\n⚠ ' + d.cooling.warnings[0]
    : $('cooling-note').textContent;
}

/* ---------------- 重置 / 复制 ---------------- */
async function reset() {
  $('mod_count').value = '0';
  $('cpu').value = 'Ryzen 5 5600';
  $('ram').value = '8G';
  $('network').value = OPTIONS.network_presets[2].name;
  $('bandwidth').value = '';
  $('download').value = '';
  $('latency').value = '';
  $('loss').value = '';
  $('behavior').value = OPTIONS.behaviors[0];
  $('player_sim').value = OPTIONS.player_sims[0];
  $('view_distance').value = '10';
  $('platform').value = '';
  $('modpack').value = '';
  $('radiator').value = OPTIONS.cooling.defaults.desktop;
  $('chassis').value = OPTIONS.cooling.defaults.chassis;
  $('material').value = OPTIONS.cooling.defaults.material;
  $('cooling_override').value = '';
  await refreshCooling(true);
  await calc();
}

async function copyResult() {
  if (!LAST_SHORT) return;
  try {
    await navigator.clipboard.writeText(LAST_SHORT);
    flash('已复制到剪贴板');
  } catch (err) {
    // 剪贴板 API 在非 https / 无权限时会失败，退回手动选择
    const ta = document.createElement('textarea');
    ta.value = LAST_SHORT;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
    flash('已复制到剪贴板');
  }
}

function flash(text) {
  const el = $('top-warning');
  const old = el.textContent;
  el.textContent = text;
  setTimeout(() => { el.textContent = old; }, 1600);
}

init();
