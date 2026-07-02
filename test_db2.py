import sqlite3; from contextlib import closing; import os; os.makedirs('test_dir2', exist_ok=True);
with closing(sqlite3.connect('test_dir2/test.db')) as conn:
    with conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('''CREATE TABLE IF NOT EXISTS messages (id INTEGER)''')
print(os.path.getsize('test_dir2/test.db'))

