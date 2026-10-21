import asyncio
import subprocess
from pathlib import Path
import edge_tts

async def gen(text, out_path):
    comm = edge_tts.Communicate(text, "pt-BR-AntonioNeural")
    await comm.save(str(out_path))

async def main():
    p_verse = Path("data/audio/temp_test_verse.mp3")
    p_cta = Path("data/audio/temp_test_cta.mp3")
    p_merged = Path("data/audio/temp_test_merged.mp3")

    verse_text = "Em tudo dai graças; porque esta é a vontade de Deus em Cristo Jesus para convosco. Primeiro Tessalonicenses, capítulo 5, versículo 18."
    cta_text = "Se essa mensagem falou ao seu coração, curta, salve para lembrar e compartilhe com quem precisa. Siga para receber a Palavra diária."

    print("Gerando narração do versículo...")
    await gen(verse_text, p_verse)
    print("Gerando narração do CTA...")
    await gen(cta_text, p_cta)

    # Concatena via ffmpeg com 1.5s de silêncio entre eles
    print("Mesclando com 1.5s de pausa no meio...")
    filter_complex = (
        "aevalsrc=0:d=1.5:s=24000:c=mono[silence];"
        "[0:a][silence][1:a]concat=n=3:v=0:a=1[aout]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(p_verse),
        "-i", str(p_cta),
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-c:a", "libmp3lame", "-b:a", "192k",
        str(p_merged)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        # Pega duração do arquivo resultante
        cmd_dur = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(p_merged)]
        r_dur = subprocess.run(cmd_dur, capture_output=True, text=True)
        print(f"Sucesso! Duração total: {float(r_dur.stdout.strip()):.2f}s")
    else:
        print("Erro FFmpeg:", res.stderr)

    p_verse.unlink(missing_ok=True)
    p_cta.unlink(missing_ok=True)
    p_merged.unlink(missing_ok=True)

if __name__ == "__main__":
    asyncio.run(main())
