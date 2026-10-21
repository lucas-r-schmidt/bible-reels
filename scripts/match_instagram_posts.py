import subprocess
import json
import base64
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.publisher.buffer_api import _load_env, get_post_status

_load_env()

# Script to run on remote to get all posts info
py_remote = """import sqlite3, json

conn = sqlite3.connect('/home/ubuntu/bible-reels/data/db/bible_reels.db')
c = conn.cursor()

c.execute('''
    SELECT p.id, p.status, p.created_at, p.published_at, v.reference, v.source, p.formatted_text, p.caption, p.video_path, p.image_path
    FROM posts p
    LEFT JOIN verses v ON v.id = p.verse_id
    ORDER BY p.id ASC
''')

cols = ['id', 'status', 'created_at', 'published_at', 'reference', 'source', 'formatted_text', 'caption', 'video_path', 'image_path']
posts = [dict(zip(cols, r)) for r in c.fetchall()]
print(json.dumps(posts))
"""

b64 = base64.b64encode(py_remote.encode('utf-8')).decode('ascii')
cmd = f"/home/ubuntu/bible-reels/.venv/bin/python -c \"import base64; exec(base64.b64decode('{b64}').decode('utf-8'))\""
res = subprocess.run(['ssh', 'oracle-social', cmd], capture_output=True, text=True, encoding='utf-8')
posts = json.loads(res.stdout)

# Now read log to map buffer id and due/sent to posts
log_res = subprocess.run(
    ["ssh", "oracle-social", "cat /home/ubuntu/bible-reels/logs/bible_reels.log"],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="ignore"
)

# Buffer post mappings
# Find where "Buffer (instagram): post ... criado id=..." appears along with post info or context
lines = log_res.stdout.splitlines()

# Also let's inspect the 17 links we found:
links_info = [
    ("2026-10-14 11:34:14", "6acf92db71d72ce5c0baa935", "https://www.instagram.com/p/Deem-5Mlsrt/"),
    ("2026-10-14 12:01:39", "6acf9949ad9763be98e5f554", "https://www.instagram.com/reel/DeeqIqmCOTk/"),
    ("2026-10-14 18:01:36", "6acfeda6ac16d08dd4db1450", "https://www.instagram.com/reel/DefTbVrgXxZ/"),
    ("2026-10-14 21:16:33", "6ad01b575ae624a5af9f6009", "https://www.instagram.com/p/DefpoK6kQZ_/"),
    ("2026-10-15 06:31:49", "6ad09d7a6e74276ac066f5a0", "https://www.instagram.com/reel/DegpI67DGJx/"),
    ("2026-10-15 12:01:58", "6ad0eadc0d345057f7d05607", "https://www.instagram.com/reel/DehPA2agr6L/"),
    ("2026-10-15 18:01:39", "6ad13f29c26e1a071758c0d1", "https://www.instagram.com/reel/Deh4KSNjcmm/"),
    ("2026-10-15 20:31:13", "6ad162369597cd1662593665", "https://www.instagram.com/p/DeiJO35CavV/"),
    ("2026-10-16 06:31:53", "6ad1eefffb64fffcf1c32393", "https://www.instagram.com/reel/DejN_huEriB/"),
    ("2026-10-16 12:02:38", "6ad23c84fd83dd559b9e44c2", "https://www.instagram.com/reel/Dejz42CDllM/"),
    ("2026-10-16 12:21:43", "6ad240fd45dfa13a7239b7ea", "https://www.instagram.com/reel/Dej2DTjDqG7/"),
    ("2026-10-16 18:02:48", "6ad290eec34368e4b09341f2", "https://www.instagram.com/reel/DekdDCXitRz/"),
    ("2026-10-16 20:32:19", "6ad2b3f91694d771d50f76be", "https://www.instagram.com/reel/DekuHwmiZ4W/"),
    ("2026-10-16 22:30:16", "6ad2cf9e87c4935770a74c8e", "https://www.instagram.com/reel/Dek7nlMjQp7/"),
    ("2026-10-16 22:30:43", "6ad2cfb98ac6cfe54425b2da", "https://www.instagram.com/reel/Dek7wZLDQfZ/"),
    ("2026-10-16 22:31:12", "6ad2cfd687c4935770a76f39", "https://www.instagram.com/reel/Dek7uoXGg5g/"),
    ("2026-10-16 22:31:40", "6ad2cff2c34368e4b0a074e0", "https://www.instagram.com/reel/Dek7x3SEg4J/"),
]

sys.stdout.reconfigure(encoding="utf-8")
print(f"{'Data Log':<20} | {'Buffer ID':<24} | {'Ref/Tema':<35} | Link Instagram")
print("-" * 120)

for dt, pid, link in links_info:
    # find line in lines and see what post id was being processed
    # search around this timestamp in lines
    matched_post = None
    # find line index
    for i, l in enumerate(lines):
        if pid in l:
            # search backwards for post id or reference
            for k in range(max(0, i-25), i):
                sub = lines[k]
                for p in posts:
                    if f"Post #{p['id']}" in sub or (p['reference'] and p['reference'] in sub):
                        matched_post = p
                        break
                if matched_post:
                    break
            break
    ref = matched_post['reference'] if matched_post else "Desconhecido"
    p_id = f"Post #{matched_post['id']}" if matched_post else ""
    desc = f"{p_id} {ref}".strip()
    print(f"{dt:<20} | {pid:<24} | {desc:<35} | {link}")
