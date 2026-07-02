import sqlite3; conn = sqlite3.connect('test_dir/test.db'); print(conn.execute('SELECT name FROM sqlite_master').fetchall())
