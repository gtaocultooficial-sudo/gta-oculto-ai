# GTA OCULTO AI V42 FIXED

Esta versão corrige a regressão da V42 inicial. O núcleo de renderização usado como base é o `app_current.py` mais recente fornecido pelo projeto, preservando o pipeline de vídeo que já estava funcionando.

A V42 envolve esse núcleo com fila/autonomia/auditoria, sem substituir o renderizador por uma versão antiga.

## Deploy
- mantenha `app.py` como entrada do Web Service
- `app_legacy_V41_LATEST.py` é o núcleo de produção preservado
- configure o Worker separado quando o plano Render permitir
- não dependa de alterações locais em `app.py` para persistência; use Git/Deploy Hook/API para auto-deploy
