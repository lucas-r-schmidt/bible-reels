"""
src/integrations/videoflow_client.py
------------------------------------
Cliente para comunicação entre o Bible-Reels e o VideoFlow.
Permite solicitar cortes inteligentes (nicho bíblico/The Chosen),
acompanhar o status e baixar/importar os vídeos gerados para a fila do Bible-Reels.
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional
import httpx

from config.settings import VIDEOFLOW_URL, VIDEOFLOW_API_TOKEN, OUTPUT_VIDEOS
from src.processor.db_manager import DBManager
from src.utils.logger import get_logger

log = get_logger("videoflow_client")


class VideoFlowClient:
    def __init__(
        self,
        base_url: str = VIDEOFLOW_URL,
        api_token: str = VIDEOFLOW_API_TOKEN,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.timeout = timeout

    @property
    def headers(self) -> dict[str, str]:
        headers = {}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def is_online(self) -> bool:
        """Verifica se o serviço VideoFlow está acessível."""
        try:
            r = httpx.get(f"{self.base_url}/api/v1/jobs", headers=self.headers, timeout=5.0)
            return r.status_code in (200, 401, 403, 404, 405)
        except Exception:
            return False

    def request_cuts(
        self,
        source_url: str,
        cut_mode: str = "highlights",
        niche_preset: str = "biblico",
        max_clips: int = 3,
        max_clip_duration: int = 60,
        aspect_mode: str = "blur",
        subtitle_style: str = "karaoke",
        publish_mode: str = "draft",
        requires_approval: bool = False,
        enable_bgm: bool = True,
        speed_boost: float = 1.03,
        enable_headline: bool = True,
    ) -> dict[str, Any]:
        """
        Dispara um job de corte inteligente no VideoFlow com preset bíblico/fé.
        """
        payload = {
            "source_type": "youtube",
            "source_url": source_url,
            "cut_mode": cut_mode,
            "part_duration": max_clip_duration,
            "max_clip_duration": max_clip_duration,
            "max_clips": max_clips,
            "platforms": ["instagram", "tiktok"],
            "subtitle_style": subtitle_style,
            "aspect_mode": aspect_mode,
            "niche_preset": niche_preset,
            "enable_hook": True,
            "publish_mode": publish_mode,
            "requires_approval": requires_approval,
            "enable_bgm": enable_bgm,
            "speed_boost": speed_boost,
            "enable_headline": enable_headline,
            "watermark_text": "The Chosen • thechosen.tv" if ("chosen" in niche_preset.lower() or "biblico" in niche_preset.lower() or "chosen" in source_url.lower()) else None,
        }

        url = f"{self.base_url}/api/v1/jobs"
        log.info(f"Enviando pedido de corte para VideoFlow: {url} | URL: {source_url} | Preset: {niche_preset}")

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, json=payload, headers=self.headers)
            if resp.status_code >= 400:
                try:
                    err_json = resp.json()
                    detail = err_json.get("detail")
                    if detail:
                        raise RuntimeError(str(detail))
                except (ValueError, KeyError):
                    pass
                resp.raise_for_status()
            data = resp.json()
            log.info(f"Job criado com sucesso no VideoFlow! ID: {data.get('job_id')} | Status: {data.get('status')}")
            return data

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        """Consulta o status atual de um job no VideoFlow."""
        url = f"{self.base_url}/api/v1/jobs/{job_id}"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(url, headers=self.headers)
            resp.raise_for_status()
            return resp.json()

    def wait_for_job(
        self,
        job_id: str,
        timeout_seconds: int = 900,
        poll_interval: int = 10,
    ) -> dict[str, Any]:
        """
        Aguarda a finalização do processamento do job no VideoFlow.
        """
        start = time.time()
        log.info(f"Acompanhando processamento do job {job_id} (timeout: {timeout_seconds}s)...")

        while (time.time() - start) < timeout_seconds:
            status_data = self.get_job_status(job_id)
            status = status_data.get("status")
            log.info(f"Job {job_id}: status={status}")

            if status in ("completed", "done", "ready"):
                log.info(f"Job {job_id} concluído com sucesso!")
                return status_data
            elif status in ("failed", "error"):
                err = status_data.get("error_message") or "Erro desconhecido no VideoFlow"
                raise RuntimeError(f"VideoFlow job {job_id} falhou: {err}")

            time.sleep(poll_interval)

        raise TimeoutError(f"Tempo limite excedido aguardando job {job_id}")

    def download_file(self, remote_path_or_url: str, dest_path: Path) -> Path:
        """Baixa o vídeo gerado pelo VideoFlow para armazenamento local."""
        if remote_path_or_url.startswith("http://") or remote_path_or_url.startswith("https://"):
            dl_url = remote_path_or_url
        else:
            rel = remote_path_or_url if remote_path_or_url.startswith("/") else f"/{remote_path_or_url}"
            dl_url = f"{self.base_url}{rel}"

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        log.info(f"Baixando vídeo de {dl_url} para {dest_path}...")

        with httpx.Client(timeout=120.0) as client:
            with client.stream("GET", dl_url, headers=self.headers) as resp:
                resp.raise_for_status()
                with open(dest_path, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=65536):
                        f.write(chunk)

        log.info(f"Vídeo salvo com sucesso: {dest_path} ({dest_path.stat().st_size // 1024} KB)")
        return dest_path

    def import_to_bible_reels(
        self,
        job_data: dict[str, Any],
        db: DBManager,
        custom_theme: str = "cena_biblica",
    ) -> list[int]:
        """
        Registra os vídeos gerados pelo VideoFlow no SQLite do Bible-Reels.
        Baixa o vídeo se remoto e salva na tabela 'posts' para postagem.
        """
        output_files = job_data.get("output_files") or []
        job_id = job_data.get("job_id", "vf_job")
        title = job_data.get("generated_title") or "Cena Bíblica de Impacto"
        caption = job_data.get("generated_caption") or (
            "Uma mensagem de fé e reflexão que toca a alma. 🙏✝️\n\n"
            "#jesus #thechosen #fe #reflexaobiblica #deus #shorts"
        )
        hook_text = job_data.get("hook_text") or "PRESTE ATENÇÃO NISSO 🙏"

        credit_line = "🎬 Cena da série The Chosen — Assista completo no app oficial The Chosen (thechosen.tv)"
        if credit_line not in caption:
            if "#" in caption:
                p_text, p_tags = caption.split("#", 1)
                caption = f"{p_text.rstrip()}\n\n{credit_line}\n\n#{p_tags}"
            else:
                caption = f"{caption}\n\n{credit_line}"

        created_post_ids: list[int] = []

        if not output_files:
            log.warning(f"Nenhum arquivo de saída encontrado no job {job_id}")
            return created_post_ids

        for idx, file_str in enumerate(output_files, start=1):
            local_name = f"{job_id}_clip{idx}.mp4"
            local_target = OUTPUT_VIDEOS / local_name

            # Se for caminho remoto (/outputs/... ou http...), baixa localmente
            if file_str.startswith("/") or file_str.startswith("http"):
                try:
                    resolved_vid = str(self.download_file(file_str, local_target).resolve())
                except Exception as dl_err:
                    log.error(f"Erro ao baixar vídeo {file_str}: {dl_err}")
                    resolved_vid = file_str
            else:
                vid_path = Path(file_str)
                resolved_vid = str(vid_path.resolve()) if vid_path.exists() else file_str

            # Hash para deduplicação
            content_hash = hashlib.sha256(f"{job_id}_{idx}_{local_name}".encode()).hexdigest()

            if db.verse_exists(content_hash):
                log.info(f"Clipe já registrado anteriormente (hash={content_hash[:8]}). Pulando.")
                continue

            ref_title = f"{title} (Parte {idx})" if len(output_files) > 1 else title

            # Insere no verses como fonte externa de corte
            v_id = db.insert_verse(
                source="videoflow_cut",
                reference=ref_title,
                text=caption,
                content_hash=content_hash,
                translation="N/A",
            )

            # Insere no posts com o caminho do vídeo pronto
            post_id = db.insert_post(
                verse_id=v_id,
                formatted_text=caption,
                hashtags=["#jesus", "#thechosen", "#fe", "#deus", "#reflexaobiblica", "#cristao"],
                visual_prompt="Videoflow AI Cut",
                image_path="",
                video_path=resolved_vid,
                caption=caption,
                hook_title=hook_text,
            )

            created_post_ids.append(post_id)
            log.info(f"Clipe {idx} importado com sucesso para Bible-Reels! Post ID: {post_id} | Vídeo: {resolved_vid}")

        return created_post_ids
