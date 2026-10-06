# GTA Oculto AI — Cloud Video Real Stable

Correção final do produtor cloud:
- não baixa o ZIP de 9 vídeos da Rockstar;
- usa somente 12 segundos do Trailer 2 oficial via yt-dlp;
- cria 3 clipes reais em movimento + 3 imagens animadas;
- processamento em 360x640 durante a montagem e upscale final para 1080x1920;
- job persistido em `workspace/jobs.json`;
- jobs RUNNING antigos são recuperados após reinício;
- falha de vídeo não vira slideshow silencioso: registra ERRO.
