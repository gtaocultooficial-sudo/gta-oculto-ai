# GTA Oculto AI — Render Free 512 MB

Versão final otimizada para o plano Free do Render.

## Pipeline
- Pesquisa automática
- Análise e escolha de pauta
- Roteiro
- Narração PT-BR
- Visuais oficiais
- 3 clipes reais oficiais da Rockstar
- Edição vertical 9:16
- Legendas
- Avaliação
- MP4 final

## Otimização de memória
- FFmpeg com 1 thread
- stderr do FFmpeg gravado em disco, não acumulado em RAM
- cenas intermediárias em 240x426
- 20 fps durante a montagem
- saída final 540x960 (9:16)
- temporários removidos após a edição
- sem YouTube e sem yt-dlp

## Render
Build: `pip install -r requirements.txt`
Start: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 1 --timeout 300`
