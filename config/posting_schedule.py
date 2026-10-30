"""Fonte única dos horários operacionais do scheduler."""

MORNING = "06:30"
SAINT_CAROUSEL = "08:30"
GOSPEL_CAROUSEL = "10:00"
MIDDAY = "12:00"
NOVENA = "15:00"
EVENING = "18:00"
EVENING_CAROUSEL = "19:15"
SAINT_VIDEO = "20:30"
ANALYTICS = "23:15"

DAILY_JOBS = (
    (MORNING, "devocional ou evangelho matinal"),
    (SAINT_CAROUSEL, "carrossel do santo do dia"),
    (GOSPEL_CAROUSEL, "carrossel do evangelho"),
    (MIDDAY, "palavra bíblica do meio-dia"),
    (NOVENA, "novena ativa"),
    (EVENING, "salmo ou oração clássica"),
    (EVENING_CAROUSEL, "carrossel complementar de oração ou salmo"),
    (SAINT_VIDEO, "vídeo do santo da véspera"),
    (ANALYTICS, "sincronização de métricas"),
)
