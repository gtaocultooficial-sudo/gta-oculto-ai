# GTA OCULTO — Ativação YouTube + Analytics

O motor V56 deve ser mantido congelado nesta etapa.
Este pacote não altera a renderização.

## Ordem

1. No Render, abra Environment.
2. Adicione:
   - `YOUTUBE_AUTO_PUBLISH=0`
   - `YOUTUBE_PRIVACY=private`
   - `YOUTUBE_ANALYTICS_ENABLED=1`
3. Configure as credenciais OAuth do YouTube na variável `YOUTUBE_TOKEN_JSON`.
4. Faça um primeiro upload privado.
5. Confira o vídeo e os metadados.
6. Só depois ative:
   - `YOUTUBE_AUTO_PUBLISH=1`
   - `YOUTUBE_PRIVACY=public`

## Objetivo

Fluxo final:

Radar → roteiro → narração → edição → Quality Gate → upload privado de teste
→ publicação → métricas → aprendizado.

## Segurança

Nunca coloque `client_secret`, `refresh_token` ou o JSON OAuth no GitHub.
Use apenas Environment Variables/Secrets do Render.
