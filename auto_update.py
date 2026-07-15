"""Baixa o fluxo cambial do BCB com retry por minuto e só regenera o HTML
quando aparece uma data nova (evita commit à toa por causa do timestamp).

Uso: python auto_update.py
Saída (exit code):
  0 -> dado novo encontrado; docs/index.html e data/cambio_data.json atualizados
  2 -> nenhum dado novo na janela de tentativas (nada a publicar)
  1 -> falha inesperada

Parâmetros por variável de ambiente:
  MAX_ATTEMPTS   nº de tentativas (padrão 6 -> 14:30:05 até 14:35:05)
  RETRY_INTERVAL segundos entre tentativas (padrão 60)
  INITIAL_DELAY  segundos antes da 1ª tentativa (padrão 5 -> o ":05")
"""
import json
import os
import re
import sys
import time

import bcb_fetch
import generate

RE_DATE = re.compile(r'^(\d{2})/(\d{2})/(\d{4})$')


def latest_daily(rows):
    """Maior data diária (ano, mês, dia) presente nas linhas; None se não houver."""
    best = None
    for r in rows:
        m = RE_DATE.match(r[0].strip())
        if m:
            d = (int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if best is None or d > best:
                best = d
    return best


def build_html(data):
    raw = data['rows']
    chart = generate.get_chart_data(raw)
    d = dict(data)
    d['rows'] = generate.filter_rows(raw)
    html = generate.generate_html(d, chart)
    os.makedirs('docs', exist_ok=True)
    with open('docs/index.html', 'w', encoding='utf-8') as f:
        f.write(html)


def save_data(data):
    os.makedirs(os.path.dirname(bcb_fetch.DATA_FILE), exist_ok=True)
    with open(bcb_fetch.DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    attempts = int(os.environ.get('MAX_ATTEMPTS', '6'))
    interval = int(os.environ.get('RETRY_INTERVAL', '60'))
    initial  = int(os.environ.get('INITIAL_DELAY', '5'))

    prev = bcb_fetch.load_cached_data()
    prev_max = latest_daily(prev['rows']) if prev else None
    print(f'Última data já publicada: {prev_max}', flush=True)

    if initial > 0:
        time.sleep(initial)

    for i in range(1, attempts + 1):
        print(f'Tentativa {i}/{attempts}...', flush=True)
        try:
            data = bcb_fetch._parse_sheet(bcb_fetch._download_excel())
        except Exception as e:
            print(f'  erro no download: {e}', flush=True)
            data = None

        if data is not None:
            new_max = latest_daily(data['rows'])
            print(f'  data mais recente no BCB: {new_max}', flush=True)
            if prev_max is None or (new_max is not None and new_max > prev_max):
                print('  -> dado novo! gerando e publicando.', flush=True)
                save_data(data)
                build_html(data)
                return 0
            print('  sem novidade ainda.', flush=True)

        if i < attempts:
            print(f'  aguardando {interval}s...', flush=True)
            time.sleep(interval)

    print('Nenhum dado novo na janela de tentativas.', flush=True)
    return 2


if __name__ == '__main__':
    sys.exit(main())
