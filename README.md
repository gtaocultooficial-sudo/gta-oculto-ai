# GTA Oculto AI — Cloud Final

Versão cloud-only. O painel e a produção rodam no servidor; **não depende do seu PC**.

## Pipeline
CRIAR SHORT → pesquisa oficial → decisão editorial → roteiro → visuais → narração PT-BR → edição 1080x1920 → avaliação → MP4 + capa + metadata.

## Render
Build: `pip install -r requirements.txt`
Start: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 180`

Não é necessário WORKER_TOKEN.

## Importante
O Render Free pode dormir por inatividade e o filesystem local não é armazenamento permanente após reinícios/deploys. Esta versão resolve a produção cloud, mas armazenamento permanente e publicação automática no YouTube são etapas separadas.

O conteúdo usa prioritariamente fontes oficiais da Rockstar. Copyright não é garantido; revise antes de publicar.
