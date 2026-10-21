import subprocess
import base64
import sys

py_code = """import os, glob, subprocess
import numpy as np

def get_pcm(path, is_video=False):
    cmd = ['ffmpeg', '-v', 'error', '-i', path]
    if is_video:
        cmd.extend(['-vn'])
    cmd.extend(['-t', '15', '-ss', '1', '-ac', '1', '-ar', '8000', '-f', 's16le', '-'])
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return np.frombuffer(res.stdout, dtype=np.int16).astype(np.float32)

tracks = glob.glob('/home/ubuntu/bible-reels/data/audio/*.mp3')
tracks = [t for t in tracks if not os.path.basename(t).startswith(('temp_', 'teste_'))]

track_pcms = {}
for t in tracks:
    pcm = get_pcm(t)
    if len(pcm) > 0:
        track_pcms[os.path.basename(t)] = pcm

videos = sorted(glob.glob('/home/ubuntu/bible-reels/output/videos/post_00*.mp4'), key=os.path.getmtime)[-15:]
for v in videos:
    vpcm = get_pcm(v, is_video=True)
    if len(vpcm) == 0:
        continue
    best_name = 'Unknown'
    best_corr = -1
    for t_name, tpcm in track_pcms.items():
        min_l = min(len(vpcm), len(tpcm))
        if min_l < 4000: continue
        v_sub = vpcm[:min_l] - np.mean(vpcm[:min_l])
        t_sub = tpcm[:min_l] - np.mean(tpcm[:min_l])
        v_norm = np.linalg.norm(v_sub)
        t_norm = np.linalg.norm(t_sub)
        if v_norm > 0 and t_norm > 0:
            corr = np.dot(v_sub, t_sub) / (v_norm * t_norm)
            if corr > best_corr:
                best_corr = corr
                best_name = t_name
    print(f"{os.path.basename(v)} -> {best_name} (score: {best_corr:.2f})")
"""

b64 = base64.b64encode(py_code.encode("utf-8")).decode("ascii")
cmd = f"/home/ubuntu/bible-reels/.venv/bin/python -c \"import base64; exec(base64.b64decode('{b64}').decode('utf-8'))\""
res = subprocess.run(["ssh", "oracle-social", cmd], capture_output=True, text=True, encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
print(res.stdout)
if res.stderr:
    print("ERR:", res.stderr)
