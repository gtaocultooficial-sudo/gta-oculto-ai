# GTA Oculto AI — Cloud Multimídia Estável

Versão cloud do produtor automático do GTA Oculto.

## Pipeline
Pesquisa → análise → roteiro → visuais → narração → edição multimídia → avaliação → MP4.

## Editor multimídia
- Prioriza vídeos oficiais do canal Rockstar Games no YouTube.
- Baixa apenas trechos curtos (não o vídeo inteiro).
- Usa até 3 trechos de vídeo + até 3 imagens.
- Intercala vídeo e imagem na timeline.
- Aplica movimento nas imagens.
- Usa crossfade cinematográfico curto entre cenas.
- Renderiza as cenas em 540x960 para manter o Render Free leve e faz a saída final em 1080x1920 / 24 FPS.
- Se o download de vídeo falhar, continua automaticamente com imagens e não trava a produção.

## Fontes oficiais de vídeo usadas nesta versão
- Rockstar Games — GTA VI Trailer 2: https://www.youtube.com/watch?v=VQRLujxTm3c
- Rockstar Games — GTA VI: An Extended Look: https://www.youtube.com/watch?v=tJbzMqJGH4k

## Deploy
- Python 3
- `pip install -r requirements.txt`
- `gunicorn app:APP --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 180`
- Sem dependência do PC do usuário.
