# GTA Oculto AI — Cloud Video Real — RAM 512 MB

Versão limpa do produtor cloud do GTA Oculto AI.

## Pipeline
- Pesquisa automática
- Análise e escolha de pauta
- Roteiro
- Narração
- Seleção de visuais
- Edição vertical 9:16
- Legendas
- Avaliação
- MP4 final

## Mídia oficial
- Usa os vídeos oficiais disponibilizados pela Rockstar Games.
- Não usa YouTube.
- Não usa yt-dlp.
- Não depende do PC do usuário.
- Para evitar o parser HTTP Range que apresentou falha no CDN, o produtor baixa o pacote oficial de vídeos da Rockstar em streaming para disco, extrai 3 clipes, normaliza os clipes com FFmpeg e remove o ZIP temporário.
- Os clipes normalizados ficam em cache para reutilização enquanto a instância do serviço mantiver o workspace.

## Deploy Render
Build:
`pip install -r requirements.txt`

Start:
`gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 300`

## Arquivos
- `app.py`
- `requirements.txt`
- `Procfile`
- `README.md`


### Otimização Render Free
- FFmpeg limitado a 1 thread e filtros limitados a 1 thread.
- Saída intermediária dos clipes reais em 320x568.
- Cenas de imagem preparadas em 720x1280 e upscale final para 1080x1920.
- Logs do FFmpeg não são acumulados na memória do Python.
- Downloads de imagens são feitos em streaming com limite por ativo.
- O objetivo é manter a produção dentro do limite de 512 MB do Render Free.
