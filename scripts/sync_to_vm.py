import os
import subprocess
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def sync_to_vm():
    print("=== [1/3] Empacotando arquivos do projeto ===")
    include_dirs = ["src", "config", "deploy", "scripts", "data/audio", "data/fonts", "data/saints", "data/quotes"]
    include_files = ["main.py", "web_server.py", "requirements.txt", "AGENTS.md"]

    tar_path = ROOT / "deploy_bundle.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        for d in include_dirs:
            p_dir = ROOT / d
            if p_dir.is_dir():
                for item in p_dir.rglob("*"):
                    if "__pycache__" in item.parts or ".pytest_cache" in item.parts:
                        continue
                    arcname = item.relative_to(ROOT).as_posix()
                    tar.add(item, arcname=arcname)
                    
        for f in include_files:
            p_file = ROOT / f
            if p_file.is_file():
                tar.add(p_file, arcname=f)

    size_mb = tar_path.stat().st_size / (1024 * 1024)
    print(f"Pacote criado: {tar_path.name} ({size_mb:.2f} MB)")

    print("=== [2/3] Transferindo pacote para oracle-social ===")
    scp_cmd = ["scp", str(tar_path), "oracle-social:/home/ubuntu/bible-reels/deploy_bundle.tar.gz"]
    res = subprocess.run(scp_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("Erro no scp:", res.stderr)
        tar_path.unlink(missing_ok=True)
        return False
    print("Upload concluido!")

    print("=== [3/3] Descompactando no servidor e atualizando serviços ===")
    remote_unpack = (
        "cd /home/ubuntu/bible-reels && "
        "tar -xzf deploy_bundle.tar.gz && "
        "rm -f deploy_bundle.tar.gz && "
        "sudo systemctl restart bible-reels-web bible-reels-scheduler && "
        "echo 'Arquivos extraídos e serviços reiniciados com sucesso na VM!'"
    )
    res_ssh = subprocess.run(["ssh", "oracle-social", remote_unpack], capture_output=True, text=True)
    print(res_ssh.stdout)
    if res_ssh.stderr:
        print("Avisos/Erros SSH:", res_ssh.stderr)

    tar_path.unlink(missing_ok=True)
    return True

if __name__ == "__main__":
    ok = sync_to_vm()
    if ok:
        print("Deploy de arquivos na VM finalizado com sucesso!")
    else:
        print("Falha no deploy!")
