import json
import os
import re
from datetime import datetime
from io import BytesIO

import pandas as pd
import requests

BCB_URL = "https://www.bcb.gov.br/content/indeco/indicadoresselecionados/ies-13.xlsx"
DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "cambio_data.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bcb.gov.br/estatisticas/indicadoresselecionados",
}

DATA_START_ROW = 12
N_COLS = 11

# Header structure — verified col counts:
# Row 0: 1 + 6 + 3 + 1(rs2) = 11 cols
# Row 1: 1 + 4 + 1 + 1 + 1(rs2) + 1(rs2) + 1 = 10 (+1 covered by Saldo rs2 = 11)
# Row 2: 9 explicit cells for cols 0-6, 9, 10 (cols 7,8 covered by Compras/Vendas rs2)
HEADER_CELLS = [
    [  # Row 0
        {"text": "",             "colspan": 1, "rowspan": 1},   # col 0: vazio
        {"text": "Comercial",    "colspan": 6, "rowspan": 1},   # cols 1-6
        {"text": "Financeiro³/", "colspan": 3, "rowspan": 1},   # cols 7-9
        {"text": "Saldo",        "colspan": 1, "rowspan": 2},   # col 10 (cobre row 0-1)
    ],
    [  # Row 1 — col 10 coberto por Saldo acima
        {"text": "",                   "colspan": 1, "rowspan": 1},  # col 0: vazio
        {"text": "Exportação de bens", "colspan": 4, "rowspan": 1},  # cols 1-4
        {"text": "Importação",         "colspan": 1, "rowspan": 1},  # col 5
        {"text": "Saldo",              "colspan": 1, "rowspan": 1},  # col 6
        {"text": "Compras",            "colspan": 1, "rowspan": 2},  # col 7 (cobre rows 1-2)
        {"text": "Vendas",             "colspan": 1, "rowspan": 2},  # col 8 (cobre rows 1-2)
        {"text": "Saldo",              "colspan": 1, "rowspan": 1},  # col 9
    ],
    [  # Row 2 — cols 7, 8 cobertos por Compras/Vendas acima
        {"text": "Período",   "colspan": 1, "rowspan": 1},  # col 0
        {"text": "Total",     "colspan": 1, "rowspan": 1},  # col 1
        {"text": "ACC",       "colspan": 1, "rowspan": 1},  # col 2
        {"text": "PA",        "colspan": 1, "rowspan": 1},  # col 3
        {"text": "Demais",    "colspan": 1, "rowspan": 1},  # col 4
        {"text": "de bens",   "colspan": 1, "rowspan": 1},  # col 5
        {"text": "(a)",       "colspan": 1, "rowspan": 1},  # col 6
        # cols 7, 8 cobertos — browser pula automaticamente
        {"text": "(b)",       "colspan": 1, "rowspan": 1},  # col 9
        {"text": "c = (a+b)", "colspan": 1, "rowspan": 1},  # col 10
    ],
]


def _download_excel() -> bytes:
    resp = requests.get(BCB_URL, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.content


def _format_cell(val) -> str:
    if pd.isna(val):
        return ""
    if isinstance(val, datetime):
        return val.strftime("%d/%m/%Y")
    if isinstance(val, (int, float)):
        formatted = f"{round(val):,}"
        return formatted.replace(",", ".")
    return str(val).strip()


def _is_footnote(val) -> bool:
    if pd.isna(val):
        return False
    s = str(val).strip()
    return s.startswith("1/") or s.startswith("2/") or s.startswith("3/") or s.startswith("    ")


def _parse_sheet(content: bytes) -> dict:
    raw = pd.read_excel(BytesIO(content), sheet_name=0, header=None, engine="openpyxl")

    rows = []
    for row_idx in range(DATA_START_ROW, len(raw)):
        row = raw.iloc[row_idx]
        first_val = row.iloc[0]

        if _is_footnote(first_val):
            break
        if row.isna().all():
            continue

        cells = [_format_cell(v) for v in row]
        rows.append(cells)

    return {
        "header_cells": HEADER_CELLS,
        "n_cols": N_COLS,
        "rows": rows,
        "last_updated": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    }


# ── Validação ──────────────────────────────────────────────
# Protege contra mudança silenciosa de layout da planilha: em vez de publicar
# número errado, levanta ValueError (o Action fica vermelho e você é avisado).

_RE_DATE_V    = re.compile(r'^(\d{2})/(\d{2})/(\d{4})$')
_RE_MONTHLY_V = re.compile(r'^[a-z]{3}-\d{4}$')
_RE_ANNUAL_V  = re.compile(r'^\d{4}(\s|$)')


def _num_v(s):
    s = (s or "").strip()
    if s == "":
        return None
    try:
        return float(s.replace(".", ""))
    except ValueError:
        return None


def validate_parsed(data, max_age_days=60, tol=5.0):
    """Confere estrutura e identidades contábeis. Levanta ValueError se algo
    estiver fora do esperado. Retorna um dicionário-resumo se passar."""
    rows = data.get("rows", [])
    if not rows:
        raise ValueError("Validação BCB: nenhuma linha de dados extraída da planilha.")

    # 1) largura das colunas
    bad = [i for i, r in enumerate(rows) if len(r) != N_COLS]
    if bad:
        raise ValueError(
            f"Validação BCB: {len(bad)} linha(s) com nº de colunas != {N_COLS} "
            f"(ex.: índice {bad[0]} tem {len(rows[bad[0]])}). Layout pode ter mudado.")

    # 2) tipos de linha presentes (anual, mensal, diária)
    labels  = [r[0].strip() for r in rows]
    daily_m = [_RE_DATE_V.match(l) for l in labels]
    n_annual = sum(1 for l in labels if _RE_ANNUAL_V.match(l))
    n_month  = sum(1 for l in labels if _RE_MONTHLY_V.match(l))
    n_daily  = sum(1 for m in daily_m if m)
    if not (n_annual and n_month and n_daily):
        raise ValueError(
            f"Validação BCB: estrutura inesperada (anuais={n_annual}, "
            f"mensais={n_month}, diárias={n_daily}); esperado ≥1 de cada.")

    # 3) recência: a diária mais recente não pode estar velha demais
    latest = None
    for m in daily_m:
        if m:
            d = (int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if latest is None or d > latest:
                latest = d
    latest_date = datetime(latest[0], latest[1], latest[2])
    age = (datetime.now() - latest_date).days
    if age > max_age_days:
        raise ValueError(
            f"Validação BCB: diária mais recente é {latest_date:%d/%m/%Y} "
            f"({age} dias atrás > limite {max_age_days}). Dado velho ou parsing errado.")

    # 4) identidades contábeis — pegam deslocamento/troca de coluna na hora:
    #    Total = ACC+PA+Demais | Saldo com. = Export−Import | Saldo fin. = Compras−Vendas | c = a+b
    checked = fails = 0
    for r in rows:
        v = [_num_v(x) for x in r]
        if any(v[i] is None for i in range(1, 11)):
            continue
        checked += 1
        ok = (abs(v[1] - (v[2] + v[3] + v[4])) <= tol and
              abs(v[6] - (v[1] - v[5]))        <= tol and
              abs(v[9] - (v[7] - v[8]))        <= tol and
              abs(v[10] - (v[6] + v[9]))       <= tol)
        if not ok:
            fails += 1
    if checked < 10:
        raise ValueError(
            f"Validação BCB: poucas linhas numéricas para checar ({checked}).")
    if fails / checked > 0.05:
        raise ValueError(
            f"Validação BCB: {fails}/{checked} linhas ({fails/checked:.0%}) violam as "
            "identidades contábeis (Total=ACC+PA+Demais, c=a+b, etc). "
            "Provável troca/deslocamento de colunas na planilha.")

    return {
        "linhas": len(rows), "anuais": n_annual, "mensais": n_month,
        "diarias": n_daily, "ultima_diaria": f"{latest_date:%d/%m/%Y}",
        "identidades_ok": f"{checked - fails}/{checked}",
    }


def fetch_cambio_data() -> dict:
    content = _download_excel()
    data = _parse_sheet(content)
    report = validate_parsed(data)          # levanta ValueError se algo estiver estranho
    print(f"  Validação OK: {report}")
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def load_cached_data() -> dict | None:
    if not os.path.exists(DATA_FILE):
        return None
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    print("Baixando dados do BCB...")
    data = fetch_cambio_data()
    print(f"OK - {len(data['rows'])} linhas")
