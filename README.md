# GTA Oculto AI — Web Dashboard

Painel web público do GTA Oculto AI. A camada web fica hospedada no Render; o motor pesado de produção (voz, visuais, FFmpeg e RTX 4060) será conectado posteriormente como agente local.

## Render
- Build: `pip install -r requirements.txt`
- Start: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120`
- Health: `/health`
