import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT / "data" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

TRACKS = [
    {
        "filename": "worship_bondade_de_deus.mp3",
        "search": "ytsearch1:bondade de deus piano instrumental worship oracao",
    },
    {
        "filename": "worship_acaso_nao_sabeis.mp3",
        "search": "ytsearch1:acaso nao sabeis instrumental piano suave",
    },
    {
        "filename": "worship_oceans.mp3",
        "search": "ytsearch1:oceans hillsong piano instrumental peaceful",
    },
    {
        "filename": "worship_ninguem_te_ama.mp3",
        "search": "ytsearch1:ninguem te ama como eu instrumental piano suave",
    },
]

def download_track(track):
    out_path = AUDIO_DIR / track["filename"]
    if out_path.is_file() and out_path.stat().st_size > 500_000:
        print(f"[ALREADY EXISTS] {out_path.name} ({out_path.stat().st_size // 1024} KB)")
        return True

    print(f"\n[DOWNLOADING] {track['filename']} via query: {track['search']}")
    temp_tmpl = str(AUDIO_DIR / f"temp_{track['filename'].replace('.mp3', '')}.%(ext)s")
    
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--no-playlist",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "192k",
        "--postprocessor-args", "ffmpeg:-t 180",  # limit to 3 minutes
        "-o", temp_tmpl,
        track["search"]
    ]
    
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if res.returncode != 0:
        print(f"[ERROR] Failed to download {track['filename']}:")
        print(res.stdout[-500:])
        return False
        
    # Find generated mp3
    temp_mp3 = AUDIO_DIR / f"temp_{track['filename'].replace('.mp3', '')}.mp3"
    if temp_mp3.is_file():
        temp_mp3.replace(out_path)
        print(f"[SUCCESS] Saved {out_path.name} ({out_path.stat().st_size // 1024} KB)")
        return True
    else:
        # Check if another name was generated
        for p in AUDIO_DIR.glob(f"temp_{track['filename'].replace('.mp3', '')}*"):
            if p.suffix.lower() == ".mp3":
                p.replace(out_path)
                print(f"[SUCCESS] Saved {out_path.name}")
                return True
        print(f"[ERROR] Output file not found for {track['filename']}")
        return False

def main():
    print(f"Target directory: {AUDIO_DIR}")
    success_count = 0
    for t in TRACKS:
        if download_track(t):
            success_count += 1
    print(f"\nCompleted: {success_count}/{len(TRACKS)} tracks ready in data/audio/")

if __name__ == "__main__":
    main()
