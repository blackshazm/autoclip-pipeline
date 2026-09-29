import sqlite3

conn = sqlite3.connect(r'D:\Downloads\haker00\You1\data\pipeline.db')
cursor = conn.cursor()

tables = [row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print('Tables:', tables)

for t in tables:
    try:
        count = cursor.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"\nTable '{t}' has {count} rows:")
        cols = [d[0] for d in cursor.description] if cursor.description else []
        sample = cursor.execute(f"SELECT * FROM {t} LIMIT 5").fetchall()
        col_names = [d[0] for d in cursor.description]
        print("  Cols:", col_names)
        for s in sample:
            print("  Row:", s)
    except Exception as e:
        print(f"Error on {t}: {e}")
