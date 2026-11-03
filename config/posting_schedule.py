"""Fonte única dos horários operacionais do scheduler.
Grade otimizada de alta conversão: 3 horários com espaçamento saudável (5h30 - 6h):
  - 06:30: Evangelho do Dia (Vídeo 9:16)
  - 12:00: Santo do Dia Oficial (Vídeo 9:16)
  - 18:00: Salmo Responsorial ou Grande Oração de Proteção (Vídeo 9:16)
  - 23:15: Analytics & Sincronização de Métricas
"""

MORNING = "06:30"
MIDDAY = "12:00"
EVENING = "18:00"
ANALYTICS = "23:15"

DAILY_JOBS = (
    (MORNING, "evangelho do dia matinal"),
    (MIDDAY, "santo do dia oficial"),
    (EVENING, "salmo ou oração de proteção"),
    (ANALYTICS, "sincronização de métricas"),
)
