# GTA Oculto AI — Render Free 512 MB

Versão otimizada para o limite de 512 MB do Render Free.

- Pesquisa, análise, roteiro e narração em nuvem.
- Usa mídia oficial da Rockstar; não usa YouTube/yt-dlp.
- FFmpeg em 1 thread e intermediários 320x568.
- Imagens baixadas em streaming com limite de 8 MB.
- Cenas intermediárias são removidas após a montagem.
- Saída final continua 1080x1920.

## Render
Build: `pip install -r requirements.txt`
Start: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 300`
