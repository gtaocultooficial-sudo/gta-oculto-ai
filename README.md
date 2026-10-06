# GTA Oculto AI — Cloud Multimedia Producer

Versão cloud-only. O painel e a produção rodam no servidor; não depende do PC do usuário.

## Pipeline
CRIAR SHORT → pesquisa oficial → decisão editorial → roteiro → seleção multimídia → narração PT-BR → edição → avaliação → MP4.

## Editor multimídia
- Prioriza clipes de vídeo oficiais da Rockstar quando disponíveis.
- Usa screenshots oficiais como complemento.
- Faz cortes curtos de vídeo em 9:16.
- Aplica zoom/movimento em imagens.
- Usa transições crossfade cinematográficas curtas entre cenas.
- Mantém fallback para imagens quando o pacote oficial de vídeos não estiver disponível.
- Render final em 1080x1920 / 24 FPS.

A versão usa o pacote oficial de 9 clipes disponibilizado pela Rockstar na página de mídia de GTA VI. O download é feito sob demanda e fica em cache durante a vida do servidor.

## Render
Build: `pip install -r requirements.txt`
Start: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 300`

## Observação
O Render Free pode dormir por inatividade e tem recursos limitados. A montagem multimídia foi mantida em resolução intermediária durante a composição para reduzir memória/CPU e o arquivo final é entregue em 1080x1920.
