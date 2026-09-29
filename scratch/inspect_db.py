import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import sqlite3
import os
import json

db_path = r"d:\Downloads\haker00\You1\data\pipeline.db"
print("=== VERIFICANDO BANCO DE DADOS:", db_path)

if not os.path.exists(db_path):
    print("Banco de dados nao encontrado.")
    exit(0)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

tables = [t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
print(f"Tabelas encontradas ({len(tables)}): {tables}\n")

for t in tables:
    count = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"[*] Tabela '{t}': {count} registros")
    cols = [col[1] for col in cur.execute(f"PRAGMA table_info({t})").fetchall()]
    print(f"    Colunas: {cols}")
    if count > 0:
        rows = cur.execute(f"SELECT * FROM {t} ORDER BY rowid DESC LIMIT 5").fetchall()
        for i, r in enumerate(rows):
            d = dict(r)
            # Truncate large texts for readability
            for k, v in d.items():
                if isinstance(v, str) and len(v) > 80:
                    d[k] = v[:80] + "..."
            print(f"    Registro {i+1}: {d}")
    print()

conn.close()
