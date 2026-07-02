import sqlite3; conn = sqlite3.connect('.jarvis/memory.db'); cursor = conn.execute('SELECT name FROM sqlite_master'); print(cursor.fetchall())
