# GTA OCULTO AI — V52 FULL AUTONOMY

Esta versão fecha a arquitetura de automação em camadas:

1. Radar → Editor-Chefe → roteiro → TTS → edição.
2. Auditor do MP4 real → reparos seguros → nova auditoria.
3. Auto-recuperação de produção: troca de pauta/estratégia quando a fonte falha.
4. Memória persistente de erros, estratégias e experimentos.
5. Publicação automática no YouTube (opcional, por OAuth).
6. Coleta periódica de analytics (opcional, por OAuth).
7. Módulo de deploy seguro para GitHub + Render, com auto-deploy desligado por padrão.
8. Backup/validação de código e quarentena para erros desconhecidos; o agente nunca deve reescrever código arbitrariamente sem testes.

## Infraestrutura recomendada para autonomia 24/7 no Render

A versão de produção usa Web Service pago + Persistent Disk para que jobs, memória e MP4 não desapareçam em reinícios. O Render informa que o filesystem normal é efêmero e que persistent disks preservam apenas o caminho montado; background workers são a opção recomendada para tarefas longas. Free Web Services também entram em sleep após 15 minutos sem tráfego. 

O `render.yaml` já está preparado com `plan: starter`, disco em `/var/data` e `GTA_WORKSPACE=/var/data/workspace`.

## Segredos

Nunca coloque tokens no código ou no chat. Configure no Environment do Render:

- `GITHUB_TOKEN`
- `RENDER_API_KEY`
- `RENDER_SERVICE_ID`
- `YOUTUBE_TOKEN_JSON`

Ative `GTA_AUTO_DEPLOY=1` apenas depois de validar os testes e o fluxo de rollback.

## YouTube

Faça primeiro um OAuth local e coloque o JSON autorizado em `YOUTUBE_TOKEN_JSON` (ou prefixe com `base64:`). Comece com `YOUTUBE_PRIVACY=private`. Depois de validar o pipeline, mude para `public` ou agendamento conforme sua estratégia.

## Testes locais

```bash
python -m py_compile app.py audit_engine.py autonomous_engine.py memory_store.py repair_engine.py deploy_manager.py youtube_publisher.py analytics_engine.py
```

## Importante

O sistema tem auto-recuperação real para falhas conhecidas e uma política de quarentena para falhas desconhecidas. Ele não recebe permissão para inventar um patch de código sem validação. A camada de deploy só atua quando explicitamente habilitada por variáveis de ambiente.



<!-- production verification trigger 2026-10-09b -->


<!-- production e2e verification 1791511136093 -->

<!-- encoder verification 1791511932071 -->

<!-- qa verification 1791512900950 -->

<!-- [produce] V62 verify production after Render Free QA optimization -->

<!-- [produce] V62.1 verify no visual re-render loop -->

<!-- [produce] V62.2 verify low-RAM final encoder -->

<!-- [produce] V63 single-encode end-to-end verification -->

<!-- [produce] V63.1 verify bounded keyframe QA -->

<!-- [produce] V63.2 isolated fast-QA end-to-end verification -->
