# GTA Oculto AI — V4

Arquitetura: Render hospeda somente painel/fila/API. O PC local executa pesquisa, visuais, narração e FFmpeg.

## Render
Crie a variável de ambiente `WORKER_TOKEN` com uma senha forte sua.

## PC produtor
Instale Python 3.11+ e rode:

Windows CMD:
```
set GTA_OCULTO_SERVER=https://gta-oculto-ai.onrender.com
set GTA_OCULTO_TOKEN=COLE_A_MESMA_SENHA_DO_RENDER
python -m pip install -r worker_requirements.txt
python worker.py
```

O worker fica aguardando tarefas. Se o PC estiver desligado, a tarefa fica na fila até ele voltar.
