# GTA OCULTO AI — V42 RESTORE BASE

Esta versão restaura o **app.py V41.3 SELF-RESOLVER**, preservando o painel avançado, Radar, Editor-Chefe, roteiro, renderização e Auditor IA que já estavam funcionando.

A camada V42 autônoma fica separada para ser integrada de forma segura depois. Não substitua o motor de vídeo por um wrapper simplificado.

## Render
- Build: `pip install -r requirements.txt`
- Start: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120`

## Segurança
Faça um deploy e valide o painel/vídeo antes de ativar o Worker autônomo.
