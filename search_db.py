import sqlite3

def search_db(db_path, search_term):
    print(f"Searching in {db_path}...")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        for table_tuple in tables:
            table = table_tuple[0]
            try:
                cursor.execute(f"SELECT * FROM {table}")
                rows = cursor.fetchall()
                for row in rows:
                    if search_term.lower() in str(row).lower():
                        print(f"Found in {table}: {row}")
            except Exception as e:
                print(f"Error reading table {table}: {e}")
        conn.close()
    except Exception as e:
        print(f"Error with DB {db_path}: {e}")

search_db('.jarvis/memory.db', 'paybond')
search_db('personal.db', 'paybond')
search_db('test.db', 'paybond')
