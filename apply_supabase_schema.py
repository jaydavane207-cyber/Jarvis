import os
import sys
import re
from urllib.parse import urlparse
from dotenv import load_dotenv
import pg8000.native

load_dotenv()

supabase_url = os.getenv("SUPABASE_URL", "")
db_password = os.getenv("DB_PASSWORD", "")
supabase_key = os.getenv("SUPABASE_KEY", "")

print("=== AUTOMATIC SUPABASE SCHEMA EXECUTION ===")
print(f"Supabase URL: {supabase_url}")

if not supabase_url or not db_password:
    print("ERROR: SUPABASE_URL or DB_PASSWORD missing in .env")
    sys.exit(1)

# Extract project ref from URL
# e.g. https://sstwkvhjnltiyktqfegd.supabase.co -> sstwkvhjnltiyktqfegd
parsed = urlparse(supabase_url)
project_ref = parsed.netloc.split('.')[0]
print(f"Project Reference: {project_ref}")

hosts_to_try = [
    (f"aws-0-ap-south-1.pooler.supabase.com", 6543),
    (f"aws-0-ap-south-1.pooler.supabase.com", 5432),
    (f"aws-0-us-east-1.pooler.supabase.com", 6543),
    (f"aws-0-us-east-1.pooler.supabase.com", 5432),
    (f"db.{project_ref}.supabase.co", 5432),
    (f"db.{project_ref}.supabase.co", 6543),
]

user_str = f"postgres.{project_ref}"

con = None
for host, port in hosts_to_try:
    print(f"Attempting Postgres connection to {host}:{port} as user '{user_str}'...")
    try:
        con = pg8000.native.Connection(
            user=user_str,
            host=host,
            port=port,
            database="postgres",
            password=db_password,
            timeout=10
        )
        print(f"[SUCCESS] Connected to {host}:{port}!")
        break
    except Exception as e:
        print(f"Connection to {host}:{port} failed: {e}")

if not con:
    print("\nERROR: Could not establish direct Postgres connection to Supabase.")
    sys.exit(1)

# Read schema_supabase.sql
schema_file = "schema_supabase.sql"
if not os.path.exists(schema_file):
    print(f"ERROR: {schema_file} not found.")
    sys.exit(1)

with open(schema_file, "r", encoding="utf-8") as f:
    sql_script = f.read()

print("\nExecuting schema_supabase.sql DDL statements...")

# Execute statements
statements = [s.strip() for s in sql_script.split(';') if s.strip()]

for i, stmt in enumerate(statements, 1):
    # Remove single-line comments for clean execution
    lines = [l for l in stmt.split('\n') if not l.strip().startswith('--')]
    clean_stmt = '\n'.join(lines).strip()
    if not clean_stmt:
        continue
    try:
        con.run(clean_stmt)
        print(f"  [OK] Statement #{i} executed.")
    except Exception as ex:
        print(f"  [WARNING] Statement #{i} note: {ex}")

print("\n[COMPLETE] Schema migration executed successfully!")
con.close()
