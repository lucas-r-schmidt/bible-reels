# Regras de publicação

O daemon de publicação está configurado em `main.py` e os horários são centralizados em `config/posting_schedule.py`. O serviço systemd mantém o daemon ativo; ele não define os horários diretamente.

## Agenda diária

| Horário | Conteúdo | Mídia |
|---|---|---|
| 06:30 | Evangelho; domingo usa bênção semanal | Vídeo vertical 9:16 |
| 08:30 | Santo do dia | Carrossel no Instagram; Photo Mode no TikTok |
| 10:00 | Evangelho | Carrossel 4:5 |
| 12:00 | Palavra bíblica do meio-dia | Vídeo vertical 9:16 |
| 15:00 | Novena ativa | Vídeo/carrossel, somente quando houver novena |
| 18:00 | Salmo ou oração clássica, alternados pelo dia | Vídeo vertical 9:16 |
| 19:15 | Oração ou salmo complementar | Carrossel |
| 20:30 | Santo da véspera | Vídeo vertical 9:16 |
| 23:15 | Métricas | Sem postagem |

## Mídia por plataforma

- Instagram: vídeo Reel prioritariamente; carrosseis nos horários de feed definidos.
- TikTok: vídeo vertical prioritariamente; Photo Mode para jobs explícitos de carrossel.
- YouTube: vídeo vertical MP4.

## Estado da fila

O fluxo esperado é:

`created → media_ready → queued → sent → published`

O despacho não deve substituir a etapa de geração. Um post sem mídia é registrado como falha e deve ser processado novamente pela etapa de mídia antes do envio.

## Santo da véspera

O Santo para o dia seguinte é gerado às 20:30 da véspera. TikTok e YouTube são enviados imediatamente pela regra do Buffer; Instagram é agendado para 06:00 do dia do Santo, quando o horário ainda não tiver passado.

## Operação

Execute manualmente o daemon em Linux com:

```bash
.venv/bin/python main.py --daemon --video --publisher buffer
```

Mantenha os horários em `config/posting_schedule.py`. Não mantenha textos de horários duplicados em documentação, serviços ou scripts de publicação.
