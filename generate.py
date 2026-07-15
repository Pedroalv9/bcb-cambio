import json
import os
import re
import statistics
from datetime import datetime

from bcb_fetch import fetch_cambio_data

MONTH_MAP = {
    'jan': 1, 'fev': 2, 'mar': 3, 'abr': 4,
    'mai': 5, 'jun': 6, 'jul': 7, 'ago': 8,
    'set': 9, 'out': 10, 'nov': 11, 'dez': 12,
}

RE_ANNUAL  = re.compile(r'^(\d{4})(\s|$)')
RE_MONTHLY = re.compile(r'^([a-z]{3})-(\d{4})$')
RE_DATE    = re.compile(r'^(\d{2})/(\d{2})/(\d{4})$')

CHART_COLORS = {
    2023: '#2196F3',
    2024: '#4CAF50',
    2025: '#FF9800',
    2026: '#E53935',
}


def _row_type(label):
    if RE_DATE.match(label):    return "daily"
    if RE_MONTHLY.match(label): return "monthly"
    if RE_ANNUAL.match(label):  return "annual"
    return ""


def _parse_num(s):
    if not s or not s.strip():
        return None
    try:
        return float(s.strip().replace('.', ''))
    except ValueError:
        return None


def filter_rows(rows):
    now = datetime.now()
    cur_year, cur_month = now.year, now.month

    # Conta dias disponíveis no mês atual
    daily_cur = sum(
        1 for row in rows
        if (m := RE_DATE.match(row[0].strip())) and
           int(m.group(2)) == cur_month and int(m.group(3)) == cur_year
    )

    # Se < 5 dias no mês atual, mostra também os diários do mês anterior
    show_prev = daily_cur < 5
    if show_prev:
        prev_month = cur_month - 1 if cur_month > 1 else 12
        prev_year  = cur_year if cur_month > 1 else cur_year - 1
        # totais mensais fechados = meses antes do mês anterior
        monthly_max = prev_month + 1  # inclui o próprio mês anterior fechado
    else:
        monthly_max = cur_month

    result = []
    for row in rows:
        label = row[0].strip()
        if label == 'Memo':
            break
        rtype = _row_type(label)

        if rtype == "annual":
            year = int(RE_ANNUAL.match(label).group(1))
            if 2020 <= year < cur_year:
                result.append({"type": "annual", "cells": row})
            elif year == cur_year:
                result.append({"type": "annual-current", "cells": row})

        elif rtype == "monthly":
            m = RE_MONTHLY.match(label)
            year, month = int(m.group(2)), MONTH_MAP.get(m.group(1), 0)
            if year == cur_year and month <= cur_month:    # todos os meses disponíveis do ano atual
                mk = f"{year:04d}-{month:02d}"
                # abertos por padrão: mês atual (+ mês anterior quando ainda há poucos dias)
                open_default = (month == cur_month) or \
                    (show_prev and year == prev_year and month == prev_month)
                result.append({"type": "monthly", "cells": row,
                               "month_key": mk, "open": open_default})

        elif rtype == "daily":
            m = RE_DATE.match(label)
            mon_m, yr_m = int(m.group(2)), int(m.group(3))
            # diárias de todos os meses do ano atual (visibilidade controlada pela seta)
            if yr_m == cur_year and mon_m <= cur_month:
                mk = f"{yr_m:04d}-{mon_m:02d}"
                result.append({"type": "daily", "cells": row, "month_key": mk})

    return result


def get_chart_data(rows, start_year=2015):
    """Return {year: {month: saldo_value}} using col 10 (Saldo total)."""
    series = {}
    for row in rows:
        label = row[0].strip()
        if label == 'Memo':
            break
        m = RE_MONTHLY.match(label)
        if not m:
            continue
        month = MONTH_MAP.get(m.group(1), 0)
        year  = int(m.group(2))
        if year < start_year or month == 0 or len(row) <= 10:
            continue
        val = _parse_num(row[10])
        if val is not None:
            series.setdefault(year, {})[month] = val
    return series


def compute_monthly_stats(series, cur_year, n_years=10):
    """Compute mean, median, max, min per month over the last n_years complete years."""
    complete_years = sorted(y for y in series if y <= cur_year - 1)
    avg_years = complete_years[-n_years:]
    mean_d = {}; median_d = {}; max_d = {}; min_d = {}
    for month in range(1, 13):
        vals = [series[y][month] for y in avg_years if month in series[y]]
        if vals:
            mean_d[month]   = sum(vals) / len(vals)
            median_d[month] = statistics.median(vals)
            max_d[month]    = max(vals)
            min_d[month]    = min(vals)
    print(f"  Estatísticas: anos {avg_years[0]}–{avg_years[-1]} ({len(avg_years)} anos)")
    return mean_d, median_d, max_d, min_d, avg_years


def _build_thead(header_cells):
    rows_html = []
    for hrow in header_cells:
        cells_html = []
        for cell in hrow:
            attrs = ""
            if cell["colspan"] > 1:
                attrs += f' colspan="{cell["colspan"]}"'
            if cell["rowspan"] > 1:
                attrs += f' rowspan="{cell["rowspan"]}"'
            cells_html.append(f'<th{attrs}>{cell["text"]}</th>')
        rows_html.append("<tr>" + "".join(cells_html) + "</tr>")
    return "\n".join(rows_html)


def _build_tbody(rows):
    # meses que começam abertos
    open_months = {r["month_key"]: r.get("open", False)
                   for r in rows if r["type"] == "monthly"}
    lines = []
    for row in rows:
        rtype = row["type"]
        cells = row["cells"]
        if rtype == "monthly":
            mk = row.get("month_key", "")
            is_open = row.get("open", False)
            state = "open" if is_open else "collapsed"
            first = (
                '<td class="month-cell">'
                '<span class="month-toggle">▾</span>'
                f'<span class="month-label">{cells[0]}</span></td>'
            )
            rest = "".join(f"<td>{c}</td>" for c in cells[1:])
            lines.append(
                f'<tr class="monthly {state}" data-month="{mk}">{first}{rest}</tr>')
        elif rtype == "daily":
            mk = row.get("month_key", "")
            hidden = "" if open_months.get(mk, True) else " hidden-row"
            cells_html = "".join(f"<td>{c}</td>" for c in cells)
            lines.append(
                f'<tr class="daily{hidden}" data-month="{mk}">{cells_html}</tr>')
        else:
            cells_html = "".join(f"<td>{c}</td>" for c in cells)
            lines.append(f'<tr class="{rtype}">{cells_html}</tr>')
    return "\n".join(lines)


def _build_tfoot(n_cols):
    cells = "".join(
        f'<td id="sum-{i}">{"Soma" if i == 0 else ""}</td>'
        for i in range(n_cols)
    )
    return f'<tr id="sum-row">{cells}</tr>'


def _build_chart_datasets(chart_data, mean_d, median_d, max_d, min_d, avg_years, cur_year, display_from=2023):
    yr0, yr1 = avg_years[0], avg_years[-1]
    datasets = []
    extra_years = []          # anos antigos, ocultos por padrão (fora da legenda)
    prev_year = cur_year - 1  # ano atual e anterior ficam visíveis; os demais, ocultos

    for year in sorted(y for y in chart_data if y >= display_from):
        monthly  = chart_data[year]
        values   = [monthly.get(m) for m in range(1, 13)]
        color    = CHART_COLORS.get(year, '#607D8B')
        is_extra = year < prev_year
        datasets.append({
            "label":           str(year),
            "data":            values,
            "borderColor":     color,
            "backgroundColor": color + "22",
            "borderWidth":     2,
            "pointRadius":     4,
            "tension":         0.3,
            "spanGaps":        False,
            "hidden":          is_extra,
        })
        if is_extra:
            extra_years.append({"idx": len(datasets) - 1, "label": str(year)})

    def stat_dataset(label, data_d, color, dash, hidden=False):
        return {
            "label":           label,
            "data":            [data_d.get(m) for m in range(1, 13)],
            "borderColor":     color,
            "backgroundColor": "transparent",
            "borderWidth":     1.5,
            "borderDash":      dash,
            "pointRadius":     2,
            "tension":         0.3,
            "spanGaps":        True,
            "hidden":          hidden,
        }

    datasets.append(stat_dataset(f"Máximo {yr0}–{yr1}", max_d, "#EF9A9A", [3, 3]))
    datasets.append(stat_dataset(f"Mínimo {yr0}–{yr1}", min_d, "#A5D6A7", [3, 3]))
    datasets.append(stat_dataset(f"Média {yr0}–{yr1}",  mean_d,   "#90A4AE", [8, 4], hidden=True))
    datasets.append(stat_dataset(f"Mediana {yr0}–{yr1}", median_d, "#546E7A", [8, 4]))

    return json.dumps(datasets), json.dumps(extra_years)


def generate_html(data, chart_data):
    last_updated = data.get("last_updated", "")
    rows         = data.get("rows", [])
    header_cells = data.get("header_cells", [])
    n_cols       = data.get("n_cols", 11)

    if header_cells and rows:
        table_html = f"""<table id="main-table">
  <thead>{_build_thead(header_cells)}</thead>
  <tbody id="tbody">{_build_tbody(rows)}</tbody>
  <tfoot>{_build_tfoot(n_cols)}</tfoot>
</table>"""
    else:
        table_html = '<div class="empty-msg">Nenhum dado disponível.</div>'

    cur_year = datetime.now().year
    mean_d, median_d, max_d, min_d, avg_years = compute_monthly_stats(chart_data, cur_year)
    datasets_json, extra_years_json = _build_chart_datasets(
        chart_data, mean_d, median_d, max_d, min_d, avg_years, cur_year)

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Movimento de Câmbio Contratado — BCB</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
  <script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f4f6f9; color: #222; padding: 24px; }}
    header {{ display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }}
    h1 {{ font-size: 1.2rem; font-weight: 600; color: #1a3a5c; }}
    .controls {{ display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }}
    .range-control {{ display: flex; align-items: center; gap: 8px; background: #fff; border: 1px solid #dde2ea; border-radius: 6px; padding: 6px 12px; font-size: 0.88rem; }}
    .range-control label {{ color: #555; }}
    .range-control input {{ width: 56px; border: 1px solid #bcc5d3; border-radius: 4px; padding: 3px 6px; font-size: 0.88rem; text-align: center; }}
    #status {{ font-size: 0.8rem; color: #666; }}

    /* Tabs */
    .tab-bar {{ display: flex; gap: 4px; margin-bottom: 16px; }}
    .tab-btn {{
      padding: 7px 20px; font-size: 0.88rem; font-weight: 600; cursor: pointer;
      border: 1px solid #dde2ea; border-radius: 6px 6px 0 0; background: #e8ecf1; color: #555;
      transition: background 0.15s;
    }}
    .tab-btn.active {{ background: #1a3a5c; color: #fff; border-color: #1a3a5c; }}
    .tab-panel {{ display: none; }}
    .tab-panel.active {{ display: block; }}

    /* Chart */
    .chart-wrap {{ background: #fff; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); padding: 24px; }}

    /* Table */
    .table-wrap {{ overflow-x: auto; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); display: inline-block; max-width: 100%; }}
    .table-wrap.capturing {{ overflow: visible; box-shadow: none; }}
    .table-wrap.capturing thead th {{ position: static; }}
    table {{ border-collapse: collapse; width: auto; background: #fff; font-size: 0.86rem; }}
    thead th {{ background: #1a3a5c; color: #fff; padding: 5px 9px; text-align: center; white-space: nowrap; font-weight: 600; font-size: 0.8rem; border: 1px solid #254e7a; position: sticky; top: 0; z-index: 2; }}
    td {{ padding: 5px 9px; border-bottom: 1px solid #e8ecf1; white-space: nowrap; }}
    td:first-child {{ text-align: left; }}
    td:not(:first-child) {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .copy-bar {{ display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }}
    .copy-btn {{ padding: 7px 16px; font-size: 0.88rem; font-weight: 600; border: 1px solid #1a3a5c; border-radius: 6px; background: #1a3a5c; color: #fff; cursor: pointer; transition: background 0.15s; }}
    .copy-btn:hover {{ background: #254e7a; }}
    .copy-btn:disabled {{ opacity: 0.6; cursor: default; }}
    .copy-btn.secondary {{ background: #f0f3f7; color: #1a3a5c; border-color: #bcc5d3; }}
    .copy-btn.secondary:hover {{ background: #e2e8f0; }}
    .copy-status {{ font-size: 0.83rem; color: #666; }}
    .copy-status.ok {{ color: #27ae60; }}
    .copy-status.err {{ color: #c0392b; }}
    .tabela-layout {{ display: flex; gap: 18px; align-items: flex-start; flex-wrap: wrap; }}
    .tabela-layout .table-wrap {{ min-width: 0; }}
    .summary-card {{ flex: 0 0 250px; background: #fff; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); padding: 18px 20px; }}
    .summary-flow {{ font-size: 0.98rem; line-height: 1.45; color: #333; padding-bottom: 14px; margin-bottom: 14px; border-bottom: 1px solid #e8ecf1; }}
    .summary-flow .dir {{ font-weight: 700; }}
    .summary-flow strong {{ color: #1a3a5c; }}
    .summary-points {{ list-style: none; display: flex; flex-direction: column; gap: 11px; }}
    .summary-points li {{ display: flex; align-items: baseline; justify-content: space-between; gap: 12px; font-size: 0.9rem; }}
    .summary-points .pt-label {{ color: #666; }}
    .summary-points .val {{ font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap; }}
    .val.pos {{ color: #1e8e3e; }}
    .val.neg {{ color: #c0392b; }}
    .dir.pos {{ color: #1e8e3e; }}
    .dir.neg {{ color: #c0392b; }}
    .chart-controls {{ display: flex; align-items: center; gap: 20px; flex-wrap: wrap; margin-bottom: 16px; font-size: 0.85rem; color: #555; }}
    .stat-group {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
    .chart-copy {{ display: flex; align-items: center; gap: 12px; margin-left: auto; }}
    tr.annual td {{ color: #333; }}
    tr.annual-current td {{ color: #333; font-weight: 700; background: #fff; }}
    tr.monthly td {{ font-weight: 700; background: #edf2f8; }}
    tr.monthly:hover td {{ background: #dce7f3; }}
    tr.monthly .month-cell {{ cursor: pointer; user-select: none; white-space: nowrap; }}
    .month-toggle {{ display: inline-block; width: 0.85em; margin-right: 5px; color: #1a3a5c; font-size: 0.75em; transition: transform 0.15s; }}
    tr.monthly.collapsed .month-toggle {{ transform: rotate(-90deg); }}
    .month-toggle.empty {{ visibility: hidden; }}
    tr.daily.hidden-row {{ display: none; }}
    tr.daily td {{ font-style: italic; color: #444; }}
    tr.daily td:first-child {{ font-style: normal; color: #333; }}
    tr.daily:nth-child(even) td {{ background: #f7f9fc; }}
    tr.daily:hover td {{ background: #eaf2ff; }}
    tr.daily.in-range td {{ background: #fff8e1; font-style: italic; }}
    tr.daily.in-range td:first-child {{ font-style: normal; }}
    tr.daily.in-range:hover td {{ background: #fff0b3; }}
    tfoot tr {{ background: #1a3a5c !important; }}
    tfoot td {{ color: #fff; font-weight: 700; padding: 4px 8px; border: 1px solid #254e7a; white-space: nowrap; }}
    tfoot td:first-child {{ text-align: left; }}
    tfoot td:not(:first-child) {{ text-align: right; }}
    .empty-msg {{ text-align: center; padding: 48px; color: #888; font-size: 1rem; background: #fff; border-radius: 8px; }}
    .toggle-stat {{ padding: 4px 14px; font-size: 0.82rem; font-weight: 600; border: 1px solid #bcc5d3; border-radius: 4px; background: #f0f3f7; color: #555; cursor: pointer; }}
    .toggle-stat.active {{ background: #1a3a5c; color: #fff; border-color: #1a3a5c; }}
    #status.ok {{ color: #27ae60; }}
  </style>
</head>
<body>

<header>
  <h1>Tabela 13 — Movimento de Câmbio Contratado (BCB)
    <span style="font-weight:400;font-size:0.85rem;color:#888;">&nbsp;US$ milhões</span>
  </h1>
  <div class="controls">
    <div class="range-control" id="range-control">
      <label for="range-input">Soma dos últimos</label>
      <input type="number" id="range-input" value="5" min="1" max="9999" />
      <span>dias</span>
    </div>
    <span id="status">{"Atualizado em " + last_updated if last_updated else ""}</span>
  </div>
</header>

<div class="tab-bar">
  <button class="tab-btn active" data-tab="tabela">Tabela</button>
  <button class="tab-btn" data-tab="sazonalidade">Sazonalidade</button>
</div>

<div id="tab-tabela" class="tab-panel active">
  <div class="copy-bar">
    <button id="copy-msg-btn" class="copy-btn">📋 Copiar mensagem (imagem + texto)</button>
    <button id="copy-btn" class="copy-btn secondary">🖼️ Só imagem</button>
    <button id="copy-text-btn" class="copy-btn secondary">📝 Só texto</button>
    <span id="copy-status" class="copy-status"></span>
  </div>
  <div class="tabela-layout" id="tabela-capture">
    <div class="table-wrap">
      {table_html}
    </div>
    <aside class="summary-card">
      <div class="summary-flow" id="summary-flow">—</div>
      <ul class="summary-points">
        <li><span class="pt-label" id="pt-prev-label">Último mês</span><span class="val" id="pt-prev-val">—</span></li>
        <li><span class="pt-label" id="pt-cur-label">Mês atual</span><span class="val" id="pt-cur-val">—</span></li>
        <li><span class="pt-label" id="pt-year-label">Ano</span><span class="val" id="pt-year-val">—</span></li>
      </ul>
    </aside>
  </div>
</div>

<div id="tab-sazonalidade" class="tab-panel">
  <div class="chart-wrap">
    <div class="chart-controls">
      <div class="stat-group">
        <span>Tendência central:</span>
        <button class="toggle-stat active" data-stat="mediana">Mediana</button>
        <button class="toggle-stat" data-stat="media">Média</button>
      </div>
      <div class="stat-group" id="year-toggles"><span>Anos anteriores:</span></div>
      <div class="chart-copy">
        <button id="copy-chart-btn" class="copy-btn">📋 Copiar gráfico</button>
        <span id="copy-chart-status" class="copy-status"></span>
      </div>
    </div>
    <canvas id="seasonal-chart" height="100"></canvas>
  </div>
</div>

<script>
  // ── Copiar como imagem (helpers) ───────────────────────
  let currentSummaryText = '';  // preenchido por updateSummary()

  function setStatus(el, msg, cls) {{
    el.textContent = msg;
    el.className = 'copy-status' + (cls ? ' ' + cls : '');
  }}
  function escapeHtml(s) {{
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }}
  async function captureTableCanvas() {{
    const wrap = document.querySelector('.table-wrap');
    wrap.classList.add('capturing');
    try {{
      return await html2canvas(document.getElementById('main-table'), {{ backgroundColor: '#ffffff', scale: 2 }});
    }} finally {{
      wrap.classList.remove('capturing');
    }}
  }}

  async function copyOrDownload(blob, filename, statusEl, btn) {{
    try {{
      await navigator.clipboard.write([new ClipboardItem({{ 'image/png': blob }})]);
      setStatus(statusEl, '✓ Copiado! Cole na conversa com Ctrl+V.', 'ok');
    }} catch (err) {{
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      a.click();
      URL.revokeObjectURL(a.href);
      setStatus(statusEl, 'Cópia direta bloqueada — imagem baixada (' + filename + ').', 'err');
    }} finally {{
      if (btn) btn.disabled = false;
    }}
  }}

  const copyStatus  = document.getElementById('copy-status');

  // Só imagem (tabela)
  const copyBtn = document.getElementById('copy-btn');
  copyBtn.addEventListener('click', async () => {{
    copyBtn.disabled = true;
    setStatus(copyStatus, 'Gerando imagem…');
    try {{
      const canvas = await captureTableCanvas();
      canvas.toBlob(blob => copyOrDownload(blob, 'tabela-cambio.png', copyStatus, copyBtn), 'image/png');
    }} catch (e) {{
      copyBtn.disabled = false;
      setStatus(copyStatus, 'Erro ao gerar imagem: ' + e.message, 'err');
    }}
  }});

  // Só texto (resumo)
  const copyTextBtn = document.getElementById('copy-text-btn');
  copyTextBtn.addEventListener('click', async () => {{
    copyTextBtn.disabled = true;
    try {{
      await navigator.clipboard.writeText(currentSummaryText);
      setStatus(copyStatus, '✓ Texto copiado! Cole na conversa com Ctrl+V.', 'ok');
    }} catch (e) {{
      setStatus(copyStatus, 'Não foi possível copiar o texto: ' + e.message, 'err');
    }} finally {{
      copyTextBtn.disabled = false;
    }}
  }});

  // Mensagem pronta: uma imagem só (tabela + resumo desenhado embaixo)
  const copyMsgBtn = document.getElementById('copy-msg-btn');
  const IMG_SCALE  = 2;  // mesma escala do captureTableCanvas
  copyMsgBtn.addEventListener('click', async () => {{
    copyMsgBtn.disabled = true;
    setStatus(copyStatus, 'Gerando mensagem…');
    try {{
      const table = await captureTableCanvas();
      const pad   = 20 * IMG_SCALE;
      const fs    = 15 * IMG_SCALE;
      const lh    = Math.round(fs * 1.5);
      const font  = w => (w ? w + ' ' : '') + fs + 'px "Segoe UI", Arial, sans-serif';
      const lines = currentSummaryText.split('\\n');

      // mede a largura do texto para dimensionar o canvas
      const meas = document.createElement('canvas').getContext('2d');
      meas.font = font('600');
      let maxTextW = 0;
      lines.forEach(l => {{ maxTextW = Math.max(maxTextW, meas.measureText(l).width); }});

      const width  = Math.max(table.width, Math.ceil(maxTextW) + pad * 2);
      let textH = pad;  // respiro entre tabela e texto
      lines.forEach(l => {{ textH += (l === '' ? Math.round(lh * 0.5) : lh); }});
      textH += pad;     // respiro no rodapé
      const height = table.height + textH;

      const out = document.createElement('canvas');
      out.width = width; out.height = height;
      const ctx = out.getContext('2d');
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, width, height);
      ctx.drawImage(table, 0, 0);

      ctx.textBaseline = 'top';
      let y = table.height + pad;
      lines.forEach((l, i) => {{
        if (l === '') {{ y += Math.round(lh * 0.5); return; }}
        ctx.font = font(i === 0 ? '600' : '');
        ctx.fillStyle = i === 0 ? '#1a3a5c' : '#222222';
        ctx.fillText(l, pad, y);
        y += lh;
      }});

      out.toBlob(blob => copyOrDownload(blob, 'mensagem-cambio.png', copyStatus, copyMsgBtn), 'image/png');
    }} catch (e) {{
      copyMsgBtn.disabled = false;
      setStatus(copyStatus, 'Erro ao gerar mensagem: ' + e.message, 'err');
    }}
  }});

  // Copiar gráfico (compõe o canvas sobre fundo branco)
  const copyChartBtn    = document.getElementById('copy-chart-btn');
  const copyChartStatus = document.getElementById('copy-chart-status');
  copyChartBtn.addEventListener('click', () => {{
    const src = document.getElementById('seasonal-chart');
    copyChartBtn.disabled = true;
    setStatus(copyChartStatus, 'Gerando imagem…');
    const out = document.createElement('canvas');
    out.width  = src.width;
    out.height = src.height;
    const ctx = out.getContext('2d');
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, out.width, out.height);
    ctx.drawImage(src, 0, 0);
    out.toBlob(blob => copyOrDownload(blob, 'grafico-cambio.png', copyChartStatus, copyChartBtn), 'image/png');
  }});

  // ── Tab switching ──────────────────────────────────────
  const tabBtns  = document.querySelectorAll('.tab-btn');
  const rangeCtl = document.getElementById('range-control');

  tabBtns.forEach(btn => {{
    btn.addEventListener('click', () => {{
      tabBtns.forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
      rangeCtl.style.display = btn.dataset.tab === 'tabela' ? '' : 'none';
    }});
  }});

  // ── Abrir/fechar meses (setinha) ───────────────────────
  document.querySelectorAll('tr.monthly').forEach(row => {{
    const mk    = row.dataset.month;
    const days  = document.querySelectorAll('tr.daily[data-month="' + mk + '"]');
    const toggle = row.querySelector('.month-toggle');
    if (!days.length) {{           // mês sem diárias: seta some, sem clique
      if (toggle) toggle.classList.add('empty');
      return;
    }}
    row.querySelector('.month-cell').addEventListener('click', () => {{
      const collapsed = row.classList.toggle('collapsed');
      row.classList.toggle('open', !collapsed);
      days.forEach(d => d.classList.toggle('hidden-row', collapsed));
    }});
  }});

  // ── Soma (tabela) ──────────────────────────────────────
  const rangeInput = document.getElementById('range-input');
  const DATE_RE    = /^\\d{{2}}\\/\\d{{2}}\\/\\d{{4}}$/;
  const MONTHS     = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'];

  function parseNum(str) {{
    if (!str || str.trim() === '') return NaN;
    return parseFloat(str.replace(/\\./g, ''));
  }}
  function formatNum(n) {{
    if (isNaN(n)) return '';
    return Math.round(n).toLocaleString('pt-BR');
  }}
  function buildSumLabel(dailyRows) {{
    if (!dailyRows.length) return 'Soma';
    const first = dailyRows[0].querySelector('td').textContent.trim();
    const last  = dailyRows[dailyRows.length - 1].querySelector('td').textContent.trim();
    const [fd, fm] = first.split('/').map(Number);
    const [ld, lm] = last.split('/').map(Number);
    const lmon = MONTHS[lm - 1];
    if (first === last) return `Soma ${{ld}}${{lmon}}`;
    if (fm === lm)      return `Soma ${{fd}} - ${{ld}}${{lmon}}`;
    return `Soma ${{fd}}${{MONTHS[fm - 1]}} - ${{ld}}${{lmon}}`;
  }}
  function updateSums() {{
    const tbody = document.getElementById('tbody');
    if (!tbody) return;
    const allRows   = Array.from(tbody.querySelectorAll('tr'));
    const dailyRows = allRows.filter(r => DATE_RE.test(r.querySelector('td')?.textContent.trim() || ''));
    const n         = Math.max(1, parseInt(rangeInput.value, 10) || 5);
    const rangeRows = dailyRows.slice(-n);
    allRows.forEach(r => r.classList.remove('in-range'));
    rangeRows.forEach(r => r.classList.add('in-range'));
    const numCols = allRows[0] ? allRows[0].querySelectorAll('td').length : 0;
    const label   = buildSumLabel(rangeRows);
    for (let col = 0; col < numCols; col++) {{
      const sumCell = document.getElementById('sum-' + col);
      if (!sumCell) continue;
      if (col === 0) {{ sumCell.textContent = label; continue; }}
      const nums = rangeRows
        .map(r => parseNum((r.querySelectorAll('td')[col] || {{}}).textContent || ''))
        .filter(v => !isNaN(v));
      sumCell.textContent = nums.length ? formatNum(nums.reduce((a, b) => a + b, 0)) : '';
    }}
  }}
  rangeInput.addEventListener('input', updateSums);
  updateSums();

  // ── Resumo ao lado da tabela ───────────────────────────
  const MONTHS_EN = ['january','february','march','april','may','june',
                     'july','august','september','october','november','december'];
  const SALDO_COL = 10;  // coluna Saldo total (c = a+b)

  function bnParts(millions) {{
    const bn = millions / 1000;
    return {{ text: (bn >= 0 ? '+' : '-') + Math.abs(bn).toFixed(2) + 'bn', pos: bn >= 0 }};
  }}
  function saldoOf(row) {{
    return parseNum((row.querySelectorAll('td')[SALDO_COL] || {{}}).textContent || '');
  }}
  function setVal(el, millions) {{
    if (isNaN(millions)) {{ el.textContent = '—'; el.className = 'val'; return '—'; }}
    const p = bnParts(millions);
    el.textContent = p.text;
    el.className = 'val ' + (p.pos ? 'pos' : 'neg');
    return p.text;
  }}
  function updateSummary() {{
    const tbody = document.getElementById('tbody');
    if (!tbody) return;
    const allRows   = Array.from(tbody.querySelectorAll('tr'));
    const dailyRows = allRows.filter(r => DATE_RE.test(r.querySelector('td')?.textContent.trim() || ''));
    const n         = Math.max(1, parseInt(rangeInput.value, 10) || 5);
    const rangeRows = dailyRows.slice(-n);

    // Flow (saldo total) dos últimos N dias
    let flow = 0, has = false;
    rangeRows.forEach(r => {{ const v = saldoOf(r); if (!isNaN(v)) {{ flow += v; has = true; }} }});
    const flowEl = document.getElementById('summary-flow');
    let flowPlain = '—';
    if (has && rangeRows.length) {{
      const bn    = flow / 1000;
      const dir   = bn >= 0 ? 'Inflow' : 'Outflow';
      const cls   = bn >= 0 ? 'pos' : 'neg';
      const fmtD  = s => {{ const p = s.split('/'); return MONTHS_EN[(+p[1]) - 1] + ' ' + p[0]; }};
      const first = rangeRows[0].querySelector('td').textContent.trim();
      const last  = rangeRows[rangeRows.length - 1].querySelector('td').textContent.trim();
      const range = first === last ? fmtD(first) : fmtD(first) + ' - ' + fmtD(last);
      flowPlain   = `${{dir}} de $${{Math.abs(bn).toFixed(2)}} Bn em ${{range}}`;
      flowEl.innerHTML = `<span class="dir ${{cls}}">${{dir}}</span> de ` +
        `<strong>$${{Math.abs(bn).toFixed(2)}} Bn</strong> em ${{range}}`;
    }} else {{
      flowEl.textContent = '—';
    }}

    // Pontos fixos: último mês, mês atual, ano
    const monthly = allRows.filter(r => r.classList.contains('monthly'));
    const curM    = monthly[monthly.length - 1];
    const prevM   = monthly[monthly.length - 2];
    const yearR   = allRows.find(r => r.classList.contains('annual-current'));

    const monLabel  = r => {{
      const [mon, yr] = r.querySelector('td').textContent.trim().toLowerCase().split('-');
      return mon + (yr ? yr.slice(-2) : '');
    }};
    const yearLabel = r => (r.querySelector('td').textContent.trim().match(/\\d{{4}}/) || [''])[0];

    const prevLbl = 'Último mês' + (prevM ? ' (' + monLabel(prevM) + ')' : '');
    const curLbl  = 'Mês atual'  + (curM  ? ' (' + monLabel(curM)  + ')' : '');
    const yearLbl = 'Ano'        + (yearR ? ' (' + yearLabel(yearR) + ')' : '');
    document.getElementById('pt-prev-label').textContent = prevLbl;
    document.getElementById('pt-cur-label').textContent  = curLbl;
    document.getElementById('pt-year-label').textContent = yearLbl;
    const prevVal = setVal(document.getElementById('pt-prev-val'), prevM ? saldoOf(prevM) : NaN);
    const curVal  = setVal(document.getElementById('pt-cur-val'),  curM  ? saldoOf(curM)  : NaN);
    const yearVal = setVal(document.getElementById('pt-year-val'), yearR ? saldoOf(yearR) : NaN);

    currentSummaryText = [
      flowPlain, '',
      prevLbl + ': ' + prevVal,
      curLbl  + ': ' + curVal,
      yearLbl + ': ' + yearVal,
    ].join('\\n');
  }}
  rangeInput.addEventListener('input', updateSummary);
  updateSummary();

  // ── Toggle média / mediana ─────────────────────────────
  document.querySelectorAll('.toggle-stat[data-stat]').forEach(btn => {{
    btn.addEventListener('click', () => {{
      document.querySelectorAll('.toggle-stat[data-stat]').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const isMed = btn.dataset.stat === 'media';
      seasonalChart.setDatasetVisibility(IDX_MEDIA,   isMed);
      seasonalChart.setDatasetVisibility(IDX_MEDIANA, !isMed);
      seasonalChart.update();
    }});
  }});

  // ── Gráfico sazonal ────────────────────────────────────
  const datasets    = {datasets_json};
  const EXTRA_YEARS = {extra_years_json};  // anos ocultos por padrão
  const EXTRA_IDX   = new Set(EXTRA_YEARS.map(e => e.idx));
  // dataset indices: 0..n-1 = years, then Máximo, Mínimo, Média, Mediana
  const IDX_MEDIA   = datasets.length - 2;
  const IDX_MEDIANA = datasets.length - 1;

  const seasonalChart = new Chart(document.getElementById('seasonal-chart'), {{
    type: 'line',
    data: {{
      labels: ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'],
      datasets: datasets,
    }},
    options: {{
      responsive: true,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        title: {{
          display: true,
          text: 'Saldo de Câmbio Contratado — Evolução Mensal (US$ milhões)',
          font: {{ size: 14, weight: '600' }},
          color: '#1a3a5c',
          padding: {{ bottom: 16 }},
        }},
        legend: {{
          position: 'top',
          // anos antigos só entram na legenda quando reativados pelos botões
          labels: {{ filter: item => !(EXTRA_IDX.has(item.datasetIndex) && item.hidden) }},
        }},
        tooltip: {{
          callbacks: {{
            label: ctx => {{
              const v = ctx.raw;
              if (v === null || v === undefined) return null;
              return ctx.dataset.label + ': ' + Math.round(v).toLocaleString('pt-BR');
            }},
          }},
        }},
      }},
      scales: {{
        y: {{
          ticks: {{
            callback: v => Math.round(v).toLocaleString('pt-BR'),
          }},
        }},
      }},
    }},
  }});

  // ── Botões de anos anteriores (ocultos por padrão) ─────
  const yearToggles = document.getElementById('year-toggles');
  if (EXTRA_YEARS.length) {{
    EXTRA_YEARS.forEach(e => {{
      const b = document.createElement('button');
      b.className = 'toggle-stat';
      b.textContent = e.label;
      b.addEventListener('click', () => {{
        const vis = seasonalChart.isDatasetVisible(e.idx);
        seasonalChart.setDatasetVisibility(e.idx, !vis);
        b.classList.toggle('active', !vis);
        seasonalChart.update();
      }});
      yearToggles.appendChild(b);
    }});
  }} else {{
    yearToggles.style.display = 'none';
  }}
</script>

</body>
</html>"""


def main():
    print("Baixando dados do BCB...")
    data = fetch_cambio_data()
    raw_rows   = data["rows"]
    chart_data = get_chart_data(raw_rows)
    data = dict(data)
    data["rows"] = filter_rows(raw_rows)

    html = generate_html(data, chart_data)

    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    display_years = [y for y in chart_data if y >= 2023]
    print(f"Gerado: docs/index.html ({len(data['rows'])} linhas, anos no gráfico: {sorted(display_years)})")


if __name__ == "__main__":
    main()
