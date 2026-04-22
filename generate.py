import os
import re
from datetime import datetime

from jinja2 import Environment, FileSystemLoader

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


def main():
    print("Baixando dados do BCB...")
    data = fetch_cambio_data()
    data = dict(data)
    data["rows"] = filter_rows(data["rows"])

    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("index.html")
    html = template.render(data=data)

    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Gerado: docs/index.html ({len(data['rows'])} linhas)")


if __name__ == "__main__":
    main()
