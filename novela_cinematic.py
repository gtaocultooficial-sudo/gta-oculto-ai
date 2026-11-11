"""Cinematic expansion pack for the first Vice City fan-fiction episode.

This is screenplay/storyboard metadata only. It does not create media, call a video
provider, enqueue a production job, or publish content.
"""
from copy import deepcopy
from datetime import datetime, timezone
import re

from novela_engine import SERIES_KEY


EPISODE_1_CINEMATIC = {
    "version": 2,
    "duration_target_seconds": 165,
    "format": "9:16",
    "spoken_word_target": "300-360",
    "scenes": [
        {
            "heading": "CENA 1 — EXT. MARINA DAS LEONIDA KEYS — FIM DE TARDE",
            "duration_seconds": 28,
            "action": (
                "Plano geral vertical dos píeres quase vazios. O vento empurra uma lona solta; "
                "cordas batem nos mastros. Jason observa o espaço vazio entre duas embarcações. "
                "Brian chega sem pressa, olha para os funcionários ao longe e entrega uma cópia "
                "amassada do manifesto. Jason não pega o papel imediatamente."
            ),
            "dialogue": [
                ("BRIAN HEDER", "O barco saiu às seis e quarenta. Tripulação e carga estavam registradas."),
                ("JASON DUVAL", "E depois?"),
                ("BRIAN HEDER", "O sistema diz que nunca saiu. O manifesto foi substituído."),
                ("JASON DUVAL", "Você entrega esse papel e espera que eu confie em você?"),
                ("BRIAN HEDER", "Meu nome aparece perto demais disso. Não vou esperar ser o culpado."),
                ("JASON DUVAL", "Então me diga quem abriu caminho."),
            ],
            "transition": "Corte seco no carimbo de horário do manifesto."
        },
        {
            "heading": "CENA 2 — INT. CASA DE JASON — COZINHA — NOITE",
            "duration_seconds": 32,
            "action": (
                "Luz fria sobre a mesa. Lucia coloca o manifesto sob uma luminária e fotografa "
                "o papel de lado para revelar a diferença de textura da tinta. Jason caminha "
                "de um lado para o outro. Ela segura o documento fora do alcance dele."
            ),
            "dialogue": [
                ("LUCIA CAMINOS", "Olha a tinta. O horário foi sobrescrito depois da assinatura."),
                ("JASON DUVAL", "Então alteraram a saída."),
                ("LUCIA CAMINOS", "O seis virou oito. A pressão da caneta prova que foi feito depois."),
                ("JASON DUVAL", "Brian jurou que era a cópia original."),
                ("LUCIA CAMINOS", "Talvez ele esteja dizendo a verdade sobre o papel e mentindo sobre o resto."),
                ("JASON DUVAL", "Você acha que ele está envolvido?"),
                ("LUCIA CAMINOS", "Acho que alguém quer que a gente culpe Brian antes de olhar para a marina."),
            ],
            "transition": "A câmera acompanha Lucia virando a folha; o carimbo de saída aparece no verso."
        },
        {
            "heading": "CENA 3 — INT. QUARTO DE CAL — NOITE",
            "duration_seconds": 30,
            "action": (
                "Monitores iluminam o quarto escuro. Cal compara o horário do manifesto com "
                "um registro de acesso da marina. Uma notificação antiga aparece e desaparece. "
                "Ele pausa, amplia o identificador da conta e chama Jason por vídeo."
            ),
            "dialogue": [
                ("CAL HAMPTON", "Encontrei o histórico. A alteração não apagou o acesso que a autorizou."),
                ("JASON DUVAL", "Quem fez?"),
                ("CAL HAMPTON", "Uma conta interna. O acesso veio da rede da marina."),
                ("LUCIA CAMINOS", "Qual terminal?"),
                ("CAL HAMPTON", "Escritório administrativo, estação quatro. Onze minutos depois da partida."),
                ("JASON DUVAL", "Alguém esperou o barco sair para apagar a saída."),
                ("CAL HAMPTON", "E o arquivo foi aberto outra vez ontem à noite."),
            ],
            "transition": "O cursor pisca sobre o horário da segunda abertura."
        },
        {
            "heading": "CENA 4 — EXT. MARINA — ESTACIONAMENTO — NOITE",
            "duration_seconds": 25,
            "action": (
                "Jason e Lucia observam o escritório administrativo do outro lado do pátio. "
                "As luzes estão apagadas, mas uma tela acende por um instante. Um segurança "
                "passa ao fundo. Lucia percebe que Jason está prestes a atravessar o estacionamento."
            ),
            "dialogue": [
                ("LUCIA CAMINOS", "A estação quatro fica naquele escritório."),
                ("JASON DUVAL", "A gente entra, pega o nome e sai."),
                ("LUCIA CAMINOS", "Se o arquivo foi aberto ontem, alguém ainda está cuidando dele."),
                ("JASON DUVAL", "Então esperamos essa pessoa aparecer."),
                ("LUCIA CAMINOS", "Você chama isso de plano?"),
                ("JASON DUVAL", "Chamo de não entrar numa armadilha sem saber quem está do outro lado."),
            ],
            "transition": "Um reflexo se move na janela do escritório; corte antes de revelar quem está lá."
        },
        {
            "heading": "CENA 5 — INT. CARRO DE JASON — ESTRADA À BEIRA-MAR — MADRUGADA",
            "duration_seconds": 26,
            "action": (
                "O carro está parado diante da água escura. Chuva fina começa a marcar o "
                "para-brisa. Lucia recebe uma mensagem de Cal: nenhum nome, apenas uma imagem "
                "de baixa resolução extraída de uma câmera externa. Jason aproxima o celular."
            ),
            "dialogue": [
                ("LUCIA CAMINOS", "Cal mandou uma imagem. É a câmera externa do píer."),
                ("JASON DUVAL", "Esse é o barco?"),
                ("LUCIA CAMINOS", "Olha o horário. Dez e quarenta e sete. Quatro horas depois do registro."),
                ("JASON DUVAL", "Então ele continuou navegando."),
                ("LUCIA CAMINOS", "Ou alguém preparou uma imagem para nos fazer acreditar nisso."),
                ("JASON DUVAL", "Você acha que é falsa?"),
                ("LUCIA CAMINOS", "Acho que quem mandou sabe exatamente o que estamos procurando."),
            ],
            "transition": "O celular vibra novamente; a imagem original chega como anexo."
        },
        {
            "heading": "CENA 6 — EXT. POSTO À BEIRA-MAR — MADRUGADA",
            "duration_seconds": 24,
            "action": (
                "Jason sai do carro e observa a fotografia ampliada sob a luz branca do posto. "
                "Ao fundo, o mar está quase invisível. No canto da imagem há uma marca de hora "
                "e um pequeno reflexo que parece vir de outra câmera. Lucia percebe que a foto "
                "foi enviada de uma conta ligada à rede interna da marina. O telefone de Jason "
                "mostra um número sem identificação."
            ),
            "dialogue": [
                ("JASON DUVAL", "A foto é posterior ao registro. Não é uma imagem antiga."),
                ("LUCIA CAMINOS", "No canto, o reflexo parece ser de outra câmera."),
                ("JASON DUVAL", "Quem enviou tinha acesso à rede da marina."),
                ("LUCIA CAMINOS", "Então está nos observando."),
                ("JASON DUVAL", "Talvez queira ajudar."),
                ("LUCIA CAMINOS", "Ninguém ajuda escondendo o próprio nome."),
                ("JASON DUVAL", "Então quer que a gente siga a pista. E quer ver até onde vamos."),
            ],
            "transition": "Close no telefone: chamada recebida de NÚMERO DESCONHECIDO. Corte para preto antes de Jason atender."
        }
    ],
    "shot_list": [
        {"id": "S01", "scene": 1, "duration_seconds": 5, "framing": "Plano geral vertical 9:16", "camera": "Dolly-in lento pelo píer", "visual": "Marina ao entardecer, água com pequenas ondas, espaço vazio no cais onde o barco deveria estar; atmosfera de suspense criminal."},
        {"id": "S02", "scene": 1, "duration_seconds": 4, "framing": "Plano médio de Jason", "camera": "Push-in discreto", "visual": "Jason imóvel observando o píer; expressão contida, vento mexendo a roupa; manter o mesmo modelo visual do personagem em todos os planos."},
        {"id": "S03", "scene": 1, "duration_seconds": 5, "framing": "Plano de dois personagens", "camera": "Pan lateral curto", "visual": "Brian entrega o manifesto a Jason; tensão silenciosa, funcionários desfocados ao fundo."},
        {"id": "S04", "scene": 2, "duration_seconds": 5, "framing": "Macro do documento", "camera": "Rack focus da tinta para a assinatura", "visual": "Tinta sobreposta, fibra do papel e carimbo de horário; mãos de Lucia apontam a alteração."},
        {"id": "S05", "scene": 2, "duration_seconds": 6, "framing": "Plano sobre o ombro de Lucia", "camera": "Arco lento em direção a Jason", "visual": "Lucia revela a alteração; Jason ao fundo inquieto; luz fria de cozinha, contraste íntimo."},
        {"id": "S06", "scene": 3, "duration_seconds": 5, "framing": "Plano geral do quarto de Cal", "camera": "Travelling curto entre monitores", "visual": "Quarto escuro iluminado por telas com mapa e logs abstratos, sem texto ilegível em destaque."},
        {"id": "S07", "scene": 3, "duration_seconds": 5, "framing": "Close na tela", "camera": "Push-in no horário e no terminal 04", "visual": "Linha de autorização interna aparece no monitor; evitar letras aleatórias, manter apenas elementos de interface simples."},
        {"id": "S08", "scene": 4, "duration_seconds": 6, "framing": "Plano geral por trás do casal", "camera": "Dolly lateral lento", "visual": "Jason e Lucia observam o escritório apagado do outro lado do estacionamento; uma luz acende brevemente."},
        {"id": "S09", "scene": 4, "duration_seconds": 4, "framing": "Close no reflexo da janela", "camera": "Rack focus para o interior", "visual": "Uma silhueta cruza a janela do escritório; não mostrar rosto nem revelar identidade."},
        {"id": "S10", "scene": 5, "duration_seconds": 6, "framing": "Plano interno do carro", "camera": "Câmera fixa com leve vibração de chuva", "visual": "Lucia mostra a imagem no celular; chuva fina no para-brisa, luzes distantes refletidas no vidro."},
        {"id": "S11", "scene": 6, "duration_seconds": 7, "framing": "Close no celular e no rosto de Jason", "camera": "Rack focus alternado", "visual": "Fotografia do barco com horário 22:47; reação de Jason; manter a fotografia consistente com o cais visto na cena 1."},
        {"id": "S12", "scene": 6, "duration_seconds": 5, "framing": "Extreme close-up do telefone", "camera": "Push-in e corte para preto", "visual": "Chamada de número desconhecido; tela ilumina a mão de Jason; terminar antes de atender."}
    ],
    "voice_direction": {
        "JASON DUVAL": "Voz masculina adulta, grave-média, controlada e econômica; fala pouco, segura a raiva, acelera discretamente quando se sente encurralado. Direção interpretativa original, sem imitar ator ou dublador.",
        "LUCIA CAMINOS": "Voz feminina adulta, firme e precisa; ritmo direto, inteligência emocional sob pressão; não elevar o volume para demonstrar autoridade.",
        "BRIAN HEDER": "Voz masculina adulta mais áspera e experiente; pausas longas, desconforto disfarçado por pragmatismo.",
        "CAL HAMPTON": "Voz masculina adulta, natural e observadora; ritmo um pouco mais rápido ao explicar detalhes técnicos, sem caricatura."
    },
    "audio_direction": {
        "music": "Trilha original minimalista de suspense urbano; baixo pulsante discreto, textura eletrônica e notas espaçadas. Crescer somente nas cenas 5 e 6.",
        "ambience": ["água batendo no píer", "cordas e mastros ao vento", "zumbido baixo de monitores", "chuva fina no para-brisa", "ruído distante de tráfego"],
        "mix": "Diálogo sempre inteligível e à frente; efeitos ambientes abaixo das vozes; silêncio breve antes do corte final."
    },
    "continuity_rules": [
        "Usar o mesmo modelo visual de Jason, Lucia, Brian e Cal em todas as cenas; não alterar rosto, cabelo, idade aparente ou proporções entre planos.",
        "O manifesto é o mesmo objeto físico em todas as cenas 1 e 2; manter as mesmas marcas de tinta e dobra.",
        "A embarcação deve ter pintura e silhueta idênticas sempre que aparecer em imagem ou reflexo.",
        "A foto recebida na cena 5 é a mesma ampliada na cena 6; o horário visível é 22:47.",
        "A autorização interna aponta para a estação administrativa 04; não revelar ainda o nome de quem a utilizou.",
        "A chamada desconhecida toca no final e Jason não atende neste episódio."
    ],
    "production_notes": [
        "Pacote pronto para storyboard e preparação de mídia, mas ainda sem arquivos de vídeo, imagens, vozes ou trilha renderizados.",
        "Usar captura do modelo/personagem autorizado ou referência de jogo escolhida pelo canal para preservar consistência; não gerar rostos diferentes a cada tomada.",
        "Não clonar vozes de atores ou dubladores; selecionar vozes licenciadas ou vozes sintéticas genéricas."
    ]
}


def expand_episode(engine, number):
    """Persist the deterministic cinematic version of an already-generated episode."""
    number = int(number)
    if number != 1:
        raise ValueError("EXPANSION_NOT_AVAILABLE: a expansão cinematográfica disponível nesta etapa é do episódio 1.")
    memory_lock = engine.memory.lock if engine.memory is not None else engine.lock
    with engine.lock:
        with memory_lock:
            root = engine._read_root()
            state = engine._load_series(root)
            episode = state.get("episodes", {}).get(str(number))
            if not episode:
                raise ValueError("EPISODE_NOT_FOUND: gere o roteiro do episódio antes de expandi-lo.")
            existing_scenes = episode.get("scenes") or []
            existing_dialogue_lines = sum(
                len(scene.get("dialogue") or [])
                for scene in existing_scenes
            )
            if (
                episode.get("cinematic", {}).get("version") == EPISODE_1_CINEMATIC["version"]
                and len(existing_scenes) >= 6
                and existing_dialogue_lines >= 35
                and episode.get("cinematic_ready")
            ):
                return deepcopy(episode)

            # A stale/partial v2 marker must not prevent repairing an older 4-scene draft.
            expanded = deepcopy(episode)
            cinematic = deepcopy(EPISODE_1_CINEMATIC)
            # Set a complete 165-second coverage plan: 12 key shots plus 9 dialogue/reaction cutaways.
            for shot in cinematic["shot_list"]:
                shot["duration_seconds"] = 7
            cinematic["shot_list"].extend([
                {"id": "S13", "scene": 2, "duration_seconds": 9, "framing": "Plano médio de Lucia", "camera": "Dolly-in lento", "visual": "Lucia percebe que Jason ainda protege a confiança antiga em Brian; tensão íntima, sem melodrama."},
                {"id": "S14", "scene": 3, "duration_seconds": 9, "framing": "Plano detalhe do terminal 04", "camera": "Pan curto até a linha do log", "visual": "A interface mostra uma conta interna e o acesso de ontem; preservar o identificador da estação administrativa quatro."},
                {"id": "S15", "scene": 4, "duration_seconds": 9, "framing": "Plano de reação de Jason", "camera": "Push-in suave", "visual": "Jason interrompe o movimento ao notar uma sombra atrás da janela; não revelar a identidade."},
                {"id": "S16", "scene": 5, "duration_seconds": 9, "framing": "Plano externo do carro", "camera": "Travelling lento acompanhando a chuva", "visual": "Carro parado na estrada à beira-mar; reflexos de luz no asfalto molhado, mar escuro ao fundo."},
                {"id": "S17", "scene": 5, "duration_seconds": 9, "framing": "Insert do celular de Lucia", "camera": "Rack focus da notificação para a fotografia", "visual": "Mensagem de Cal chega com a imagem capturada pela câmera externa da marina."},
                {"id": "S18", "scene": 5, "duration_seconds": 9, "framing": "Close alternado do casal", "camera": "Cortes de reação em ritmo crescente", "visual": "Lucia aponta o horário 22:47; Jason entende que o registro oficial não bate com a imagem."},
                {"id": "S19", "scene": 6, "duration_seconds": 9, "framing": "Plano geral sob a cobertura do posto", "camera": "Dolly-in lento", "visual": "Jason e Lucia isolados sob luz branca, com a estrada vazia e o mar escuro ao fundo."},
                {"id": "S20", "scene": 6, "duration_seconds": 9, "framing": "Macro do canto da fotografia", "camera": "Push-in no reflexo da câmera", "visual": "O reflexo de outra câmera aparece na fotografia; manter a composição e o horário já apresentados."},
                {"id": "S21", "scene": 6, "duration_seconds": 9, "framing": "Close do telefone na mão de Jason", "camera": "Push-in final e corte para preto", "visual": "Chamada de número desconhecido. Jason não atende; tela vibra uma vez e a imagem corta para preto."}
            ])
            expanded["scenes"] = cinematic["scenes"]
            lines = []
            for scene in cinematic["scenes"]:
                lines.extend([scene["heading"], scene["action"]])
                for character, line in scene["dialogue"]:
                    lines.append(f"{character}: {line}")
                lines.append("")
            expanded["script"] = "\n".join(lines).strip()
            expanded["word_count"] = len(re.findall(r"\b[\wÀ-ÿ'-]+\b", expanded["script"]))
            expanded["dialogue_word_count"] = sum(
                len(re.findall(r"\b[\wÀ-ÿ'-]+\b", line))
                for scene in cinematic["scenes"]
                for _, line in scene["dialogue"]
            )
            expanded["cinematic"] = cinematic
            expanded["cinematic_ready"] = True
            expanded["duration_target_seconds"] = cinematic["duration_target_seconds"]
            expanded["status"] = "CINEMATIC_SCRIPT_READY"
            expanded["updated_at"] = datetime.now(timezone.utc).isoformat()
            expanded["video_job_created"] = False
            state.setdefault("episodes", {})[str(number)] = expanded
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            root.setdefault("novelas", {})[SERIES_KEY] = state
            engine._write_root(root)
            return deepcopy(expanded)
