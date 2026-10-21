import subprocess
import base64

py_code = """
import sqlite3
conn = sqlite3.connect('/home/ubuntu/bible-reels/data/db/bible_reels.db')
c = conn.cursor()
c.execute("SELECT id, reference, source, collected_at FROM verses WHERE source = 'saint' ORDER BY id DESC LIMIT 5")
print('SAINT VERSES:')
for r in c.fetchall():
    print(r)
print('--- UNUSED VERSES ---')
c.execute("SELECT v.id, v.reference, v.source FROM verses v LEFT JOIN posts p ON p.verse_id = v.id WHERE p.id IS NULL ORDER BY v.collected_at ASC LIMIT 10")
for r in c.fetchall():
    print(r)
print('--- RECENT POSTS ---')
c.execute("SELECT p.id, v.reference, v.source, p.status, p.created_at, p.published_at FROM posts p JOIN verses v ON p.verse_id = v.id ORDER BY p.id DESC LIMIT 8")
for r in c.fetchall():
    print(r)
"""

b64 = base64.b64encode(py_code.encode("utf-8")).decode("ascii")
cmd = f"/home/ubuntu/bible-reels/.venv/bin/python -c \"import base64; exec(base64.b64decode('{b64}').decode('utf-8'))\""
res = subprocess.run(["ssh", "oracle-social", cmd], capture_output=True, text=True, encoding="utf-8")
print(res.stdout)
if res.stderr:
    print("ERR:", res.stderr)
