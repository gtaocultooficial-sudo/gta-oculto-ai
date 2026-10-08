# GTA OCULTO AI — V42 Autonomous Core

## O que esta versão entrega
- mantém o motor de renderização existente;
- adiciona Auditor IA pós-render;
- diagnóstico de vídeo com ffprobe;
- verificação de duração, verticalidade, FPS e áudio;
- verificação básica do roteiro contra metadados internos;
- memória persistente de experimentos em SQLite;
- biblioteca de reparos limitados e reversíveis;
- limite de tentativas para evitar loop infinito;
- worker separado para rodar sem você estar no site;
- endpoint `/api/autonomous` para status;
- endpoint `/api/autonomous/memory` para memória;
- preparação para deploy via Render API/Deploy Hook.

## Importante
Esta V42 NÃO faz alteração arbitrária de código-fonte em produção. O próximo nível de autoengenharia deve usar Git + testes + branch + rollback + Render API. Isso é proposital: evita que um erro de vídeo faça a IA destruir o próprio sistema.

## Render
Use dois serviços:
1. Web Service: `app_V42_AUTONOMOUS.py`
2. Background Worker: `worker.py`

Configure variáveis no Render, sem enviar segredos pelo chat:
- `GTA_MAX_REPAIR_ATTEMPTS=3`
- `GTA_MEMORY_DB=workspace/agent_memory.sqlite3`
- opcional: `RENDER_API_KEY`
- opcional: `RENDER_SERVICE_ID`
- opcional: `RENDER_DEPLOY_HOOK_URL`

Para memória realmente persistente entre deploys, use Postgres/Key Value ou um Persistent Disk. SQLite no filesystem padrão do Render é apenas memória local da instância e não deve ser tratado como armazenamento permanente.
