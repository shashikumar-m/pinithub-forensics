import psycopg2

with open(".env") as f:
    for line in f:
        if line.startswith("DATABASE_URL="):
            url = line.split("=", 1)[1].strip().strip('"')

conn = psycopg2.connect(url)
cur = conn.cursor()
cur.execute("SELECT id, owner_id, status, original_filename, size_bytes FROM images LIMIT 10;")
rows = cur.fetchall()
print(f"Found {len(rows)} images:")
for r in rows:
    print(r)

cur.execute("SELECT id, email FROM users;")
users = cur.fetchall()
print(f"Found {len(users)} users:")
for u in users:
    print(u)

