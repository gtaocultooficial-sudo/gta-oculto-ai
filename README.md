# GTA Oculto AI — Primeiro Short Qualidade V2

Versão de acabamento sobre a build que já gera MP4 no Render Free.

- mantém o processamento de baixo consumo de RAM;
- mantém 540x960 / 15 FPS para estabilidade;
- remove poluição visual de contador de cena no overlay;
- alterna vídeos reais e imagens;
- termina com um vídeo real em movimento para evitar quadro congelado no final;
- mantém mídia oficial da Rockstar e execução em nuvem.

## Deploy Render
Build: `pip install -r requirements.txt`
Start: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 300`
