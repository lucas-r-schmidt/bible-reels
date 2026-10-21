# Guia Rápido: n8n + Buffer (Instagram Reels & TikTok)

## 1. Conectar as redes no Buffer (Gratuito)
1. Acesse [buffer.com](https://buffer.com) e crie sua conta grátis.
2. Em **Channels**, conecte seu perfil do **Instagram** e sua conta do **TikTok**.
3. Acesse **Settings ➔ Channels** para copiar o **ID** de cada canal conectado.
4. Gere ou pegue seu Access Token em [Buffer Developer Portal](https://buffer.com/developers/api) (ou use OAuth no n8n se preferir).

## 2. Importar o Workflow no n8n
1. Abra seu n8n local (`http://localhost:5678`).
2. Vá em **Workflows ➔ + Add Workflow**.
3. Clique nos 3 pontinhos no canto superior direito e selecione **Import from File...**
4. Escolha o arquivo: `data/n8n/bible_reels_buffer_workflow.json`.
5. Abra o nó **Publicar no Buffer (HTTP)** e:
   - Substitua `SEU_ACCESS_TOKEN_DO_BUFFER_AQUI` pelo seu token.
   - Substitua `ID_DO_SEU_CANAL_INSTAGRAM` pelo ID do canal do Instagram.
   - Substitua `ID_DO_SEU_CANAL_TIKTOK` pelo ID do canal do TikTok.
6. Clique em **Save** e ative o workflow (**Active: ON**).

## 3. Disparar pelo Bible Reels
- No arquivo `.env`:
  ```env
  WEBHOOK_URL=http://localhost:5678/webhook/bible-reels
  DEFAULT_PUBLISHER=webhook
  ```
- O Bible Reels envia o payload com a legenda formatada e a `video_url` direta do vídeo mp4.
- Você pode disparar pelo painel web (`run.bat`) ou pelo terminal.
