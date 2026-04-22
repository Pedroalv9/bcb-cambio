import json
import os
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


def fetch_cambio_data() -> dict:
    content = _download_excel()
    data = _parse_sheet(content)
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
