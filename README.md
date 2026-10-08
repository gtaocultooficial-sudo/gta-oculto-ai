# GTA OCULTO AI — V42 FINAL

## Base preservada
`app.py` é o **V41.3 Self Resolver real**, preservando o painel, Radar, Editor-Chefe, source-lock, TTS, vídeos oficiais, timeline e auditoria que já estavam funcionando.

A V42 adiciona módulos separados para autonomia:
- `autonomous_engine.py` — ciclo do agente e limite de tentativas
- `audit_engine.py` — auditoria técnica pós-render
- `repair_engine.py` — biblioteca de estratégias seguras
- `memory_store.py` — memória de experimentos em SQLite
- `deploy_manager.py` — preparação para Render Deploy Hook/API
- `worker.py` — worker autônomo separado

## Deploy seguro
1. Faça backup/branch antes de substituir o `app.py`.
2. Substitua os arquivos pelos desta pasta.
3. Faça **um único commit**.
4. Aguarde o Web Service ficar Live.
5. Só depois configure o Worker.

## Importante sobre Render Free
O `render.yaml` usa `starter` porque Background Worker não está disponível no plano Free. Não altere seu plano automaticamente; se você estiver no Free, mantenha primeiro apenas o Web Service e valide o painel/motor. O Worker só entra quando o plano permitir.

## Segredos
Nunca coloque chaves no código. Para deploy automático, use Environment Variables no Render:
- `RENDER_API_KEY`
- `RENDER_SERVICE_ID`
- ou `RENDER_DEPLOY_HOOK_URL`

## Rollback
`app_legacy_V41_3.py` é uma cópia do núcleo V41.3 e deve ser mantida como backup. O agente V42 não deve editar código de produção arbitrariamente: alterações de código precisam passar por testes e rollback.
