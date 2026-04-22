import os
import re
import webbrowser
from datetime import datetime

from flask import Flask, jsonify, render_template

from bcb_fetch import fetch_cambio_data, load_cached_data

app = Flask(__name__)

MONTH_MAP = {
    'jan': 1, 'fev': 2, 'mar': 3, 'abr': 4,
    'mai': 5, 'jun': 6, 'jul': 7, 'ago': 8,
    'set': 9, 'out': 10, 'nov': 11, 'dez': 12,
}

# Regex patterns
RE_ANNUAL  = re.compile(r'^(\d{4})(\s|$)')           # "2009", "2008 Set-dez"
RE_MONTHLY = re.compile(r'^([a-z]{3})-(\d{4})$')     # "jan-2026"
RE_DAILY   = re.compile(r'^\d{2}/\d{2}/(\d{4})$')    # "03/04/2026"
RE_DATE    = re.compile(r'^(\d{2})/(\d{2})/(\d{4})$')


def _get_date_month_year(label: str):
    """Return (month, year) from a daily label 'DD/MM/YYYY', or None."""
    m = RE_DATE.match(label)
    if m:
        return int(m.group(2)), int(m.group(3))
    return None


def _row_type(label: str) -> str:
    if RE_DATE.match(label):
        return "daily"
    if RE_MONTHLY.match(label):
        return "monthly"
    if RE_ANNUAL.match(label):
        return "annual"
    return ""


def filter_rows(rows: list) -> list:
    """Apply display rules and return annotated rows: {'type', 'cells'}."""
    now = datetime.now()
    cur_year  = now.year
    cur_month = now.month

    result = []
    for row in rows:
        label = row[0].strip()

        if label == 'Memo':
            break

        rtype     = _row_type(label)
        annual_m  = RE_ANNUAL.match(label)
        monthly_m = RE_MONTHLY.match(label)
        daily_m   = RE_DATE.match(label)

        if rtype == "annual":
            year = int(annual_m.group(1))
            if 2017 <= year < cur_year:
                result.append({"type": "annual", "cells": row})

        elif rtype == "monthly":
            year  = int(monthly_m.group(2))
            month = MONTH_MAP.get(monthly_m.group(1), 0)
            if year == cur_year and month <= cur_month:
                result.append({"type": "monthly", "cells": row})

        elif rtype == "daily":
            mon_m, yr_m = int(daily_m.group(2)), int(daily_m.group(3))
            if yr_m == cur_year and mon_m == cur_month:
                result.append({"type": "daily", "cells": row})

    return result


@app.route("/")
def index():
    data = load_cached_data()
    if data is None:
        data = {
            "header_cells": [], "n_cols": 11, "rows": [],
            "last_updated": None,
            "error": "Dados não carregados ainda. Clique em Atualizar.",
        }
    else:
        data = dict(data)
        data["rows"] = filter_rows(data["rows"])   # now list of {type, cells}
    return render_template("index.html", data=data)


@app.route("/refresh", methods=["POST"])
def refresh():
    try:
        data = fetch_cambio_data()
        return jsonify({"ok": True, "last_updated": data["last_updated"], "rows": len(data["rows"])})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/data")
def raw_data():
    data = load_cached_data()
    if data is None:
        return jsonify({"error": "Sem dados em cache"}), 404
    return jsonify(data)


if __name__ == "__main__":
    print("=" * 60)
    print("  Monitor de Cambio Contratado - BCB")
    print("=" * 60)
    print("  Servidor: http://localhost:5000")
    print()
    print("  Para agendar atualizacao automatica (quarta-feira 14h),")
    print("  crie uma tarefa no Agendador de Tarefas do Windows com:")
    print("    Programa : curl")
    print("    Argumentos: -X POST http://localhost:5000/refresh")
    print("    Gatilho  : Semanal, Quarta-feira, 14:00")
    print("=" * 60)
    import socket
    ip = socket.gethostbyname(socket.gethostname())
    print(f"  Acesso na rede: http://{ip}:5000")
    print("=" * 60)
    port = int(os.environ.get("PORT", 5000))
    if port == 5000:
        webbrowser.open("http://localhost:5000")
    app.run(host="0.0.0.0", debug=False, port=port)
