import os
import re
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


def _row_type(label):
    if RE_DATE.match(label):    return "daily"
    if RE_MONTHLY.match(label): return "monthly"
    if RE_ANNUAL.match(label):  return "annual"
    return ""


def filter_rows(rows):
    now = datetime.now()
    cur_year, cur_month = now.year, now.month
    result = []
    for row in rows:
        label = row[0].strip()
        if label == 'Memo':
            break
        rtype = _row_type(label)
        if rtype == "annual":
            year = int(RE_ANNUAL.match(label).group(1))
            if 2017 <= year < cur_year:
                result.append({"type": "annual", "cells": row})
        elif rtype == "monthly":
            m = RE_MONTHLY.match(label)
            year, month = int(m.group(2)), MONTH_MAP.get(m.group(1), 0)
            if year == cur_year and month <= cur_month:
                result.append({"type": "monthly", "cells": row})
        elif rtype == "daily":
            m = RE_DATE.match(label)
            mon_m, yr_m = int(m.group(2)), int(m.group(3))
            if yr_m == cur_year and mon_m == cur_month:
                result.append({"type": "daily", "cells": row})
    return result


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
    lines = []
    for row in rows:
        cells = "".join(f"<td>{c}</td>" for c in row["cells"])
        lines.append(f'<tr class="{row["type"]}">{cells}</tr>')
    return "\n".join(lines)


def _build_tfoot(n_cols):
    cells = "".join(
        f'<td id="sum-{i}">{"Soma" if i == 0 else ""}</td>'
        for i in range(n_cols)
    )
    return f'<tr id="sum-row">{cells}</tr>'


def generate_html(data):
    last_updated = data.get("last_updated", "")
    rows = data.get("rows", [])
    header_cells = data.get("header_cells", [])
    n_cols = data.get("n_cols", 11)

    if header_cells and rows:
        table_html = f"""
<table id="main-table">
  <thead>
    {_build_thead(header_cells)}
  </thead>
  <tbody id="tbody">
    {_build_tbody(rows)}
  </tbody>
  <tfoot>
    {_build_tfoot(n_cols)}
  </tfoot>
</table>"""
    else:
        table_html = '<div class="empty-msg">Nenhum dado disponível.</div>'

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Movimento de Câmbio Contratado — BCB</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f4f6f9; color: #222; padding: 24px; }}
    header {{ display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }}
    h1 {{ font-size: 1.2rem; font-weight: 600; color: #1a3a5c; }}
    .controls {{ display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }}
    .range-control {{ display: flex; align-items: center; gap: 8px; background: #fff; border: 1px solid #dde2ea; border-radius: 6px; padding: 6px 12px; font-size: 0.88rem; }}
    .range-control label {{ color: #555; }}
    .range-control input {{ width: 56px; border: 1px solid #bcc5d3; border-radius: 4px; padding: 3px 6px; font-size: 0.88rem; text-align: center; }}
    #status {{ font-size: 0.8rem; color: #666; }}
    .table-wrap {{ overflow-x: auto; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }}
    table {{ border-collapse: collapse; width: 100%; background: #fff; font-size: 0.82rem; }}
    thead th {{ background: #1a3a5c; color: #fff; padding: 5px 8px; text-align: center; white-space: nowrap; font-weight: 600; border: 1px solid #254e7a; position: sticky; top: 0; z-index: 2; }}
    td {{ padding: 4px 8px; border-bottom: 1px solid #e8ecf1; white-space: nowrap; }}
    td:first-child {{ text-align: left; min-width: 90px; }}
    td:not(:first-child) {{ text-align: right; min-width: 72px; max-width: 90px; }}
    tr.annual td {{ color: #333; }}
    tr.monthly td {{ font-weight: 700; background: #edf2f8; }}
    tr.monthly:hover td {{ background: #dce7f3; }}
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
  </style>
</head>
<body>

<header>
  <h1>Tabela 13 — Movimento de Câmbio Contratado (BCB)
    <span style="font-weight:400;font-size:0.85rem;color:#888;">&nbsp;US$ milhões</span>
  </h1>
  <div class="controls">
    <div class="range-control">
      <label for="range-input">Soma dos últimos</label>
      <input type="number" id="range-input" value="5" min="1" max="9999" />
      <span>dias</span>
    </div>
    <span id="status">{"Atualizado em " + last_updated if last_updated else ""}</span>
  </div>
</header>

<div class="table-wrap">
  {table_html}
</div>

<script>
  const rangeInput = document.getElementById('range-input');
  const DATE_RE = /^\\d{{2}}\\/\\d{{2}}\\/\\d{{4}}$/;
  const MONTHS  = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'];

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
</script>

</body>
</html>"""


def main():
    print("Baixando dados do BCB...")
    data = fetch_cambio_data()
    data = dict(data)
    data["rows"] = filter_rows(data["rows"])

    html = generate_html(data)

    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Gerado: docs/index.html ({len(data['rows'])} linhas)")


if __name__ == "__main__":
    main()
