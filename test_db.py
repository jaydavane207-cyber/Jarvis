import sqlite3; from contextlib import closing; import os; os.makedirs('test_dir', exist_ok=True); 
with closing(sqlite3.connect('test_dir/test.db')) as conn:
    with conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('''CREATE TABLE IF NOT EXISTS messages (id INTEGER)''')

