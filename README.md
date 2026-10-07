# GTA Oculto AI — Primeiro Short Qualidade FINAL

Versão de acabamento do produtor cloud do GTA Oculto AI.

## Pipeline
- Pesquisa automática
- Análise e escolha de pauta
- Roteiro
- Narração PT-BR
- Visuais
- Edição vertical 9:16
- Legendas únicas e limpas
- Avaliação
- MP4 final

## Mídia oficial
- Usa vídeos oficiais disponibilizados pela Rockstar Games.
- Não usa YouTube.
- Não usa yt-dlp.
- Não depende do PC do usuário.
- Processa a mídia sequencialmente para respeitar o limite de memória do Render Free.
- Usa até 6 clipes oficiais reais por Short, alternados com 3 visuais preparados.
- Os clipes intermediários são preparados em baixa resolução e a montagem final é feita em 540x960/15 FPS para manter estabilidade no Render Free.
- O vídeo final usa compressão melhorada sem aumentar o número de processos concorrentes.

## Render
Build:
`pip install -r requirements.txt`

Start:
`gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 300`

## Arquivos
- app.py
- requirements.txt
- Procfile
- README.md
