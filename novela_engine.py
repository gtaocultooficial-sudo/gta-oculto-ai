"""Persistent, non-repeating fan-fiction episode engine for GTA Oculto AI.

This module manages the story bible and screenplay drafts only. It deliberately
does not enqueue or render videos; production must be an explicit, separate step.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import re
import threading
from pathlib import Path


SERIES_KEY = "vice_city_preco_neon"
CHARACTERS = [
    {"name": "Jason Duval", "role": "protagonista", "profile": "Pragmático, dividido entre lealdade, dinheiro e a vida que tenta construir."},
    {"name": "Lucia Caminos", "role": "protagonista", "profile": "Perspicaz e determinada; não aceita ser conduzida por decisões alheias."},
    {"name": "Cal Hampton", "role": "apoio", "profile": "Observador, atento a sinais, transmissões e padrões que os outros ignoram."},
    {"name": "Brian Heder", "role": "apoio", "profile": "Contrabandista experiente, ligado ao passado de Jason."},
    {"name": "Boobie Ike", "role": "apoio", "profile": "Empresário influente, preocupado em proteger seus negócios e reputação."},
    {"name": "Dre'Quan Priest", "role": "apoio", "profile": "Empreendedor musical tentando consolidar a Only Raw Records."},
    {"name": "Bae-Luxe", "role": "apoio", "profile": "Metade de Real Dimez; carismática e atenta às oportunidades."},
    {"name": "Roxy", "role": "apoio", "profile": "Metade de Real Dimez; espontânea, perspicaz e difícil de intimidar."},
    {"name": "Raul Bautista", "role": "apoio", "profile": "Criminoso ambicioso, sedutor e calculista."},
]

# Each episode has a distinct dramatic engine, setting, revelation and cliffhanger.
# This is an original fan-fiction storyline, not official GTA VI canon.
EPISODE_CATALOG = [
    {
        "number": 1, "title": "A CARGA FANTASMA", "location": "Marina das Leonida Keys",
        "conflict": "Uma embarcação desaparece e o manifesto de carga foi alterado depois da partida.",
        "revelation": "O registro de saída mostra que alguém usou uma autorização válida de dentro da própria marina.",
        "cliffhanger": "Jason recebe uma foto da embarcação tirada depois do horário em que ela deveria estar no mar.",
        "novelty_keys": ["manifesto-alterado", "barco-desaparecido", "autorizacao-interna"],
        "scenes": [
            {"heading": "CENA 1 — EXT. MARINA — FIM DE TARDE", "action": "O píer está quase vazio. Jason observa o espaço deixado pela embarcação. Brian entrega a ele uma cópia amassada do manifesto.", "dialogue": [
                ("BRIAN HEDER", "O barco saiu daqui. O problema é que ninguém admite ter visto."),
                ("JASON DUVAL", "Barco não some. Alguém abre caminho ou alguém fecha a boca.")
            ]},
            {"heading": "CENA 2 — INT. CASA DE JASON — NOITE", "action": "Lucia compara os horários anotados no papel. Um horário foi escrito por cima de outro.", "dialogue": [
                ("LUCIA CAMINOS", "Olha a tinta. Mudaram isso depois que a embarcação saiu."),
                ("JASON DUVAL", "Brian disse que o documento era original."),
                ("LUCIA CAMINOS", "Então alguém teve acesso ao original.")
            ]},
            {"heading": "CENA 3 — INT. QUARTO DE CAL — NOITE", "action": "Cal amplia o registro digital da marina e encontra uma autorização emitida por uma conta interna.", "dialogue": [
                ("CAL HAMPTON", "A autorização não veio de fora. Foi criada aqui dentro."),
                ("JASON DUVAL", "Você consegue descobrir quem abriu a porta?"),
                ("CAL HAMPTON", "Consigo descobrir qual conta. Não quem estava sentado na cadeira.")
            ]},
            {"heading": "CENA 4 — EXT. POSTO À BEIRA-MAR — MADRUGADA", "action": "O celular de Jason vibra. Uma fotografia mostra a embarcação ainda navegando horas depois do registro de desaparecimento.", "dialogue": [
                ("LUCIA CAMINOS", "Isso prova que alguém mentiu sobre o horário."),
                ("JASON DUVAL", "Não. Prova que alguém quer que a gente veja essa foto.")
            ]}
        ]
    },
    {
        "number": 2, "title": "FREQUÊNCIA MORTA", "location": "Estação meteorológica abandonada",
        "conflict": "Cal tenta identificar uma transmissão que surge apenas durante alguns segundos e muda de frequência a cada tentativa.",
        "revelation": "A mensagem contém coordenadas de uma estação meteorológica desativada, não da rota do barco.",
        "cliffhanger": "Dentro da estação, Lucia encontra um gravador ainda ligado com a voz de Jason.",
        "novelty_keys": ["radio-frequencia", "coordenadas-falsas", "gravador-voz-jason"],
        "scenes": [
            {"heading": "CENA 1 — INT. QUARTO DE CAL — MADRUGADA", "action": "O rádio chia. Cal marca no mapa os saltos de frequência enquanto uma tempestade se aproxima.", "dialogue": [
                ("CAL HAMPTON", "Não é interferência. A mensagem está pulando de canal de propósito."),
                ("LUCIA CAMINOS", "Então alguém sabe que estamos ouvindo."),
                ("CAL HAMPTON", "Ou quer ter certeza de que vamos continuar.")
            ]},
            {"heading": "CENA 2 — EXT. ESTRADA ALAGADA — NOITE", "action": "Jason dirige devagar pela estrada cercada de água. Lucia acompanha as coordenadas no telefone.", "dialogue": [
                ("JASON DUVAL", "A gente veio atrás de uma transmissão e acabou no meio do nada."),
                ("LUCIA CAMINOS", "É exatamente por isso que alguém escolheu esse lugar.")
            ]},
            {"heading": "CENA 3 — INT. ESTAÇÃO METEOROLÓGICA — NOITE", "action": "Painéis enferrujados cobrem as paredes. Um rádio portátil transmite uma mensagem gravada.", "dialogue": [
                ("CAL HAMPTON", "Essa estação está oficialmente desligada há anos."),
                ("JASON DUVAL", "Oficialmente é uma palavra muito conveniente.")
            ]},
            {"heading": "CENA 4 — INT. SALA DE EQUIPAMENTOS — NOITE", "action": "Lucia encontra um gravador no fundo de uma gaveta. Ao apertar PLAY, ouve a voz de Jason dizendo seu próprio nome.", "dialogue": [
                ("GRAVAÇÃO DE JASON", "Lucia, não confie no que ele vai oferecer."),
                ("LUCIA CAMINOS", "Jason... essa gravação é sua?")
            ]}
        ]
    },
    {
        "number": 3, "title": "VIRAL", "location": "Estúdio da Only Raw Records",
        "conflict": "Um vídeo de Real Dimez ganha milhares de visualizações e expõe, sem querer, uma conversa privada refletida em um espelho do estúdio.",
        "revelation": "A conversa mostra o nome de uma empresa de fachada ligada ao pagamento da marina.",
        "cliffhanger": "Uma pessoa desconhecida oferece comprar o arquivo original antes que a dupla o entregue à polícia.",
        "novelty_keys": ["video-viral", "reflexo-espelho", "empresa-fachada"],
        "scenes": [
            {"heading": "CENA 1 — INT. ESTÚDIO — TARDE", "action": "Bae-Luxe e Roxy assistem à repercussão do vídeo. Dre'Quan tenta comemorar, mas percebe um detalhe ao fundo.", "dialogue": [
                ("DRE'QUAN PRIEST", "O vídeo está explodindo. Só precisamos manter o foco na música."),
                ("ROXY", "Então explica por que tem gente pausando o vídeo no segundo vinte e três."),
                ("BAE-LUXE", "Tem uma conversa no espelho. E não parece ser sobre música.")
            ]},
            {"heading": "CENA 2 — INT. ESCRITÓRIO DO ESTÚDIO — TARDE", "action": "Dre'Quan fecha a porta e pede que o vídeo não seja apagado até entender o que aparece nele.", "dialogue": [
                ("DRE'QUAN PRIEST", "Não apaguem nada. Primeiro precisamos saber quem aparece."),
                ("ROXY", "Engraçado. Ontem você queria que todo mundo assistisse.")
            ]},
            {"heading": "CENA 3 — INT. APARTAMENTO DE LUCIA — NOITE", "action": "Lucia congela o reflexo do espelho e lê o nome de uma empresa de fachada no papel sobre a mesa.", "dialogue": [
                ("LUCIA CAMINOS", "Essa empresa aparece no registro da marina."),
                ("JASON DUVAL", "Então o vídeo acabou de transformar uma pista em problema.")
            ]},
            {"heading": "CENA 4 — EXT. ESTACIONAMENTO DO ESTÚDIO — NOITE", "action": "Uma mulher de óculos escuros entrega a Bae-Luxe um cartão sem identificação.", "dialogue": [
                ("DESCONHECIDA", "O arquivo original vale mais do que vocês imaginam."),
                ("BAE-LUXE", "E por que você acha que a gente quer vender?"),
                ("DESCONHECIDA", "Porque amanhã alguém vai oferecer o dobro.")
            ]}
        ]
    },
    {
        "number": 4, "title": "LINHA DE CRÉDITO", "location": "Clube de Boobie Ike em Vice City",
        "conflict": "Uma auditoria inesperada ameaça congelar as contas de um dos negócios de Boobie.",
        "revelation": "As movimentações suspeitas foram lançadas como despesas de um evento que nunca aconteceu.",
        "cliffhanger": "Boobie recebe a confirmação de que alguém usou sua assinatura digital.",
        "novelty_keys": ["auditoria-financeira", "evento-fantasma", "assinatura-digital"],
        "scenes": [
            {"heading": "CENA 1 — INT. CLUBE — MANHÃ", "action": "O clube está vazio. Boobie encara uma pilha de documentos enquanto funcionários recolhem caixas.", "dialogue": [
                ("BOOBIE IKE", "Eu sei quanto entra, quanto sai e quem recebe. Esse número não pertence à minha casa."),
                ("JASON DUVAL", "Alguém está usando seu negócio como cobertura.")
            ]},
            {"heading": "CENA 2 — INT. ESCRITÓRIO — MANHÃ", "action": "Lucia encontra notas de um evento com data futura e lista de fornecedores inexistentes.", "dialogue": [
                ("LUCIA CAMINOS", "O evento não aconteceu. Nem estava marcado."),
                ("BOOBIE IKE", "Mas pagaram por ele. E agora querem que eu explique o dinheiro.")
            ]},
            {"heading": "CENA 3 — INT. SALA VIP — TARDE", "action": "Dre'Quan reconhece um dos fornecedores fictícios como uma empresa que tentou patrocinar a gravadora.", "dialogue": [
                ("DRE'QUAN PRIEST", "Eles procuraram a gravadora há duas semanas."),
                ("BOOBIE IKE", "E você assinou alguma coisa?"),
                ("DRE'QUAN PRIEST", "Não. Mas alguém levou nossos dados.")
            ]},
            {"heading": "CENA 4 — INT. ESCRITÓRIO — NOITE", "action": "Boobie abre um alerta no celular: uma nova operação foi aprovada com sua assinatura digital.", "dialogue": [
                ("BOOBIE IKE", "Eu não aprovei isso."),
                ("LUCIA CAMINOS", "Então não estão só escondendo dinheiro. Estão falando em seu nome.")
            ]}
        ]
    },
    {
        "number": 5, "title": "A DÍVIDA DE RAUL", "location": "Hotel de beira de estrada em Leonida",
        "conflict": "Raul procura Jason com uma proposta que promete resolver os prejuízos, mas exige que ele entregue uma pessoa, não uma carga.",
        "revelation": "O alvo é o contador que pode provar quem falsificou os registros financeiros.",
        "cliffhanger": "Lucia descobre que Jason marcou um encontro com Raul sem contar a ela.",
        "novelty_keys": ["proposta-raul", "contador-testemunha", "encontro-escondido"],
        "scenes": [
            {"heading": "CENA 1 — INT. HOTEL — NOITE", "action": "Raul está sentado perto da janela, sem tocar no café. Jason entra e percebe que a saída está bloqueada por dois homens.", "dialogue": [
                ("RAUL BAUTISTA", "Você perdeu tempo procurando um barco. Eu posso mostrar quem recebeu o dinheiro."),
                ("JASON DUVAL", "E o que você quer em troca?"),
                ("RAUL BAUTISTA", "Uma pessoa que sabe demais.")
            ]},
            {"heading": "CENA 2 — EXT. ESTACIONAMENTO — NOITE", "action": "Raul entrega um envelope com a foto de um contador e vai embora sem explicar mais nada.", "dialogue": [
                ("JASON DUVAL", "Você quer que eu entregue um homem."),
                ("RAUL BAUTISTA", "Quero que você escolha de que lado prefere ficar.")
            ]},
            {"heading": "CENA 3 — INT. CASA DE LUCIA — MADRUGADA", "action": "Lucia encontra o envelope escondido sob o banco do carro e reconhece o nome do contador.", "dialogue": [
                ("LUCIA CAMINOS", "Você não ia me contar."),
                ("JASON DUVAL", "Eu ainda não aceitei nada."),
                ("LUCIA CAMINOS", "O problema é que você já começou a decidir sozinho.")
            ]},
            {"heading": "CENA 4 — EXT. ESTRADA — MADRUGADA", "action": "Jason recebe a localização do encontro. Lucia observa de longe quando ele entra no carro.", "dialogue": [
                ("LUCIA CAMINOS", "Se você for até ele, eu vou descobrir por quê."),
                ("JASON DUVAL", "Então talvez seja melhor você não me seguir.")
            ]}
        ]
    },
    {
        "number": 6, "title": "O ARQUIVO DE BRIAN", "location": "Armazém antigo no porto",
        "conflict": "Um arquivo físico desaparece antes de ser entregue ao contador e Jason precisa decidir se confronta Brian.",
        "revelation": "Brian guardava uma cópia do manifesto original para se proteger de alguém acima dele.",
        "cliffhanger": "A cópia contém uma segunda assinatura: a de uma pessoa que Jason conhece desde antes de Lucia.",
        "novelty_keys": ["arquivo-fisico", "manifesto-original", "segunda-assinatura"],
        "scenes": [
            {"heading": "CENA 1 — EXT. PORTO — AMANHECER", "action": "Jason encontra o armazém aberto e marcas recentes no chão. O arquivo que deveria estar em um armário sumiu.", "dialogue": [
                ("JASON DUVAL", "Alguém chegou antes de nós."),
                ("LUCIA CAMINOS", "Ou alguém sabia exatamente quando a gente viria.")
            ]},
            {"heading": "CENA 2 — INT. ARMAZÉM — AMANHECER", "action": "Brian aparece com uma chave antiga e admite que manteve uma cópia do manifesto.", "dialogue": [
                ("BRIAN HEDER", "Eu guardo cópias porque aprendi a não confiar em ninguém."),
                ("JASON DUVAL", "E resolveu contar isso agora?"),
                ("BRIAN HEDER", "Agora é quando você ainda pode sair dessa.")
            ]},
            {"heading": "CENA 3 — INT. SALA DOS FUNDOS — MANHÃ", "action": "Lucia compara duas assinaturas no documento. Uma delas pertence a alguém conhecido de Jason.", "dialogue": [
                ("LUCIA CAMINOS", "Essa segunda assinatura não é de um funcionário da marina."),
                ("JASON DUVAL", "Eu conheço esse nome.")
            ]},
            {"heading": "CENA 4 — EXT. PORTO — MANHÃ", "action": "Jason dobra a cópia e guarda no bolso. Um carro passa devagar e não reduz a velocidade.", "dialogue": [
                ("BRIAN HEDER", "Quando souber quem assinou, vai entender por que fiquei calado."),
                ("JASON DUVAL", "Não. Vou entender por que você me deixou no escuro.")
            ]}
        ]
    },
    {
        "number": 7, "title": "NOITE DE MÁSCARAS", "location": "Gala beneficente em Vice City",
        "conflict": "Jason e Lucia entram em uma gala para localizar a pessoa ligada à segunda assinatura, enquanto Real Dimez se apresenta no evento.",
        "revelation": "A assinatura pertence a um intermediário que trabalha publicamente como consultor de eventos.",
        "cliffhanger": "As portas são trancadas e uma voz anuncia que a polícia recebeu uma denúncia anônima contra Jason.",
        "novelty_keys": ["gala-infiltracao", "consultor-intermediario", "denuncia-anonima"],
        "scenes": [
            {"heading": "CENA 1 — INT. SALÃO DA GALA — NOITE", "action": "Luzes douradas, câmeras e convidados. Real Dimez se prepara para entrar no palco. Jason e Lucia circulam separados.", "dialogue": [
                ("LUCIA CAMINOS", "Você olha para as saídas. Eu procuro o consultor."),
                ("JASON DUVAL", "E se ele estiver procurando a gente?"),
                ("LUCIA CAMINOS", "Então não vamos facilitar.")
            ]},
            {"heading": "CENA 2 — INT. CORREDOR DOS CAMARINS — NOITE", "action": "Dre'Quan tenta manter a apresentação no horário enquanto um produtor recebe uma ligação urgente.", "dialogue": [
                ("DRE'QUAN PRIEST", "Ninguém cancela o show por um boato."),
                ("ROXY", "Não é boato. Alguém acabou de perguntar pelo Jason.")
            ]},
            {"heading": "CENA 3 — INT. SALA PRIVATIVA — NOITE", "action": "Lucia reconhece o consultor em uma foto de evento e o confronta com a cópia da assinatura.", "dialogue": [
                ("LUCIA CAMINOS", "Você assinou o documento da marina."),
                ("CONSULTOR", "Eu assino dezenas de contratos por semana."),
                ("LUCIA CAMINOS", "Esse é o problema. Você acha que ninguém lê.")
            ]},
            {"heading": "CENA 4 — INT. SALÃO DA GALA — NOITE", "action": "As portas se fecham. Os celulares dos convidados recebem a mesma mensagem de alerta.", "dialogue": [
                ("VOZ NO SISTEMA", "A polícia foi informada de uma ocorrência envolvendo Jason Duval."),
                ("JASON DUVAL", "Lucia, isso não veio de você, veio?"),
                ("LUCIA CAMINOS", "Você ainda está fazendo essa pergunta?")
            ]}
        ]
    },
    {
        "number": 8, "title": "O PREÇO DO NEON", "location": "Terminal de contêineres de Vice City",
        "conflict": "Com Jason procurado e a rede prestes a desaparecer, Lucia propõe uma troca pública de provas no terminal.",
        "revelation": "Raul e o consultor trabalharam juntos, mas a ordem para alterar o manifesto veio de alguém que usou a identidade de Brian.",
        "cliffhanger": "Jason recebe uma chamada de um número desconhecido. Do outro lado, a voz de Brian diz: 'Você devia ter deixado isso quieto'.",
        "novelty_keys": ["troca-publica-provas", "identidade-clonada-brian", "telefonema-final"],
        "scenes": [
            {"heading": "CENA 1 — EXT. TERMINAL — NOITE", "action": "Contêineres formam corredores estreitos. Lucia prepara a troca de documentos enquanto Cal monitora o canal aberto.", "dialogue": [
                ("LUCIA CAMINOS", "A prova vai sair daqui com ou sem a gente."),
                ("CAL HAMPTON", "O canal está aberto. Se alguém se aproximar, eu vou ouvir."),
                ("JASON DUVAL", "E se a pessoa que vier for alguém que a gente conhece?")
            ]},
            {"heading": "CENA 2 — INT. CABINE DE CONTROLE — NOITE", "action": "Cal encontra dois registros incompatíveis: um acesso autorizado por Brian e outro feito com uma cópia digital da identidade dele.", "dialogue": [
                ("CAL HAMPTON", "Tem duas autorizações. Uma é real. A outra imita a assinatura de Brian."),
                ("LUCIA CAMINOS", "Então alguém queria que Jason culpasse a pessoa errada.")
            ]},
            {"heading": "CENA 3 — EXT. PÁTIO DE CONTÊINERES — NOITE", "action": "Raul aparece acompanhado do consultor. Jason coloca o manifesto original sobre o capô de um carro.", "dialogue": [
                ("RAUL BAUTISTA", "Você trouxe papel velho para uma negociação nova."),
                ("JASON DUVAL", "Trouxe a única coisa que você não consegue comprar."),
                ("RAUL BAUTISTA", "Todo mundo tem um preço.")
            ]},
            {"heading": "CENA 4 — EXT. ACESSO AO TERMINAL — MADRUGADA", "action": "A troca é interrompida por sirenes distantes. Lucia e Jason escapam por lados diferentes. O telefone de Jason toca.", "dialogue": [
                ("BRIAN HEDER — TELEFONE", "Você devia ter deixado isso quieto, garoto."),
                ("JASON DUVAL", "Você está me ameaçando ou tentando me avisar?"),
                ("BRIAN HEDER — TELEFONE", "Na próxima vez, talvez você não tenha tempo de perguntar.")
            ]}
        ]
    }
]


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9áéíóúãõç]+", " ", str(text or "").lower())).strip()


def _fresh_state():
    return {
        "schema_version": 1,
        "series": {
            "id": SERIES_KEY,
            "title": "VICE CITY: O PREÇO DO NEON",
            "subtitle": "Uma história original de fã no universo GTA VI",
            "genre": ["crime", "drama", "romance", "ação", "suspense"],
            "format": "vertical_9_16",
            "target_minutes": 2.5,
            "canon_note": "Fanfiction não oficial; não altera nem representa a história oficial do jogo."
        },
        "characters": deepcopy(CHARACTERS),
        "season": {"number": 1, "title": "O PREÇO DO NEON", "episode_count": len(EPISODE_CATALOG)},
        "episodes": {},
        "created_at": _utc_now(),
        "updated_at": _utc_now()
    }


class NovelaEngine:
    """Stores a season bible and idempotent episode scripts in TrendBrain memory."""

    def __init__(self, trend_brain=None, workspace=None):
        self.memory = trend_brain
        self.root = Path(workspace or "workspace")
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "novela_memory.json"
        self.lock = threading.RLock()

    def _read_root(self):
        if self.memory is not None:
            value = self.memory._read()
            return value if isinstance(value, dict) else {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def _write_root(self, data):
        if self.memory is not None:
            self.memory._write(data)
            return
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def _load_series(self, root):
        novels = root.setdefault("novelas", {})
        state = novels.get(SERIES_KEY)
        if not isinstance(state, dict):
            state = _fresh_state()
            novels[SERIES_KEY] = state
            self._write_root(root)
        return state

    def state(self):
        with self.lock:
            if self.memory is not None:
                with self.memory.lock:
                    root = self._read_root()
                    data = deepcopy(self._load_series(root))
            else:
                root = self._read_root()
                data = deepcopy(self._load_series(root))
            generated = sorted(
                (self._episode_summary(v) for v in data.get("episodes", {}).values()),
                key=lambda item: item["number"]
            )
            numbers = {int(item["number"]) for item in generated}
            next_number = next((n for n in range(1, len(EPISODE_CATALOG) + 1) if n not in numbers), None)
            persistence = "supabase" if self.memory is not None and self.memory.status().get("persistent_storage", {}).get("connected") else "local"
            return {
                "ok": True,
                "series": data["series"],
                "season": data["season"],
                "characters": data["characters"],
                "episodes": generated,
                "generated_count": len(generated),
                "next_episode_number": next_number,
                "season_complete": next_number is None,
                "persistence": persistence,
                "video_generation_enabled": False,
                "message": "Roteiros são salvos na memória da série. Nenhum vídeo é iniciado automaticamente."
            }

    @staticmethod
    def _episode_summary(episode):
        return {
            "number": int(episode["number"]),
            "episode_id": episode["episode_id"],
            "title": episode["title"],
            "location": episode["location"],
            "status": episode.get("status", "SCRIPT_READY"),
            "word_count": episode.get("word_count", 0),
            "created_at": episode.get("created_at"),
            "cliffhanger": episode["cliffhanger"],
            "cinematic_ready": bool(episode.get("cinematic_ready")),
            "duration_target_seconds": episode.get("duration_target_seconds"),
            "dialogue_word_count": episode.get("dialogue_word_count", 0)
        }

    def _validate_novelty(self, state, plan):
        used = []
        used_lines = set()
        for old in state.get("episodes", {}).values():
            used.extend(old.get("novelty_keys", []))
            for scene in old.get("scenes", []):
                for character, line in scene.get("dialogue", []):
                    used_lines.add(_norm(line))
        overlap = set(plan["novelty_keys"]) & set(used)
        if overlap:
            raise ValueError("NOVELTY_GUARD: conflito ou reviravolta já utilizado: " + ", ".join(sorted(overlap)))
        new_lines = []
        for scene in plan["scenes"]:
            for character, line in scene.get("dialogue", []):
                normalized = _norm(line)
                if normalized in used_lines or normalized in new_lines:
                    raise ValueError("NOVELTY_GUARD: diálogo repetido detectado.")
                new_lines.append(normalized)

    def generate_episode(self, number):
        try:
            number = int(number)
        except (TypeError, ValueError):
            raise ValueError("Número de episódio inválido.")
        if number < 1 or number > len(EPISODE_CATALOG):
            raise ValueError("Esta temporada possui 8 episódios planejados.")
        with self.lock:
            memory_lock = self.memory.lock if self.memory is not None else self.lock
            with memory_lock:
                root = self._read_root()
                state = self._load_series(root)
                key = str(number)
                # Retry is idempotent: it returns the same saved script, never creates a duplicate.
                if key in state.get("episodes", {}):
                    return deepcopy(state["episodes"][key])
                generated_numbers = {int(k) for k in state.get("episodes", {})}
                expected = next((n for n in range(1, len(EPISODE_CATALOG) + 1) if n not in generated_numbers), None)
                if number != expected:
                    raise ValueError(f"CONTINUITY_GUARD: o próximo roteiro é o episódio {expected}.")
                plan = deepcopy(EPISODE_CATALOG[number - 1])
                self._validate_novelty(state, plan)
                scene_lines = []
                for scene in plan["scenes"]:
                    scene_lines.append(scene["heading"])
                    scene_lines.append(scene["action"])
                    for character, line in scene["dialogue"]:
                        scene_lines.append(f"{character}: {line}")
                    scene_lines.append("")
                script_text = "\n".join(scene_lines).strip()
                word_count = len(re.findall(r"\b[\wÀ-ÿ'-]+\b", script_text))
                episode = {
                    **plan,
                    "episode_id": f"s01e{number:02d}",
                    "status": "SCRIPT_READY",
                    "script": script_text,
                    "word_count": word_count,
                    "created_at": _utc_now(),
                    "video_job_created": False
                }
                state.setdefault("episodes", {})[key] = episode
                state["updated_at"] = _utc_now()
                root.setdefault("novelas", {})[SERIES_KEY] = state
                self._write_root(root)
                return deepcopy(episode)

    def get_episode(self, number):
        with self.lock:
            root = self._read_root()
            state = root.get("novelas", {}).get(SERIES_KEY, {})
            value = state.get("episodes", {}).get(str(int(number)))
            return deepcopy(value) if value else None


NOVELA_PAGE = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Novelas | GTA Oculto AI</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#080c12;color:#e8edf5;font-family:Inter,Segoe UI,Arial,sans-serif}
.wrap{max-width:1120px;margin:auto;padding:26px 20px 70px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:26px}.brand{font-weight:1000;letter-spacing:2px}.brand span{color:#a36cff}.back{color:#bd9aff;text-decoration:none;font-weight:800;font-size:13px}
.hero{border:1px solid #392e53;border-radius:20px;padding:28px;background:radial-gradient(circle at 85% 0%,#4a226d 0,#20172f 32%,#111923 75%);display:flex;justify-content:space-between;gap:24px;align-items:center}
.kicker{color:#d1a9ff;font-size:10px;font-weight:900;letter-spacing:2px}h1{font-size:clamp(28px,5vw,46px);line-height:1.04;margin:10px 0}.sub{color:#b8c1d0;max-width:680px;line-height:1.55;font-size:14px}.pill{display:inline-block;border:1px solid #51406e;border-radius:30px;padding:6px 10px;color:#d7c4f6;font-size:10px;font-weight:900;margin:4px 4px 0 0}
.btn{background:#8b4ee8;border:0;border-radius:10px;color:#fff;padding:13px 17px;font-weight:950;cursor:pointer;white-space:nowrap}.btn:disabled{opacity:.4;cursor:not-allowed}.panel{background:#101720;border:1px solid #263244;border-radius:16px;padding:20px;margin-top:18px}.panel h2{font-size:15px;letter-spacing:1px;margin:0 0 14px}.muted{color:#94a1b3;font-size:12px}.cast{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:9px}.person{background:#151f2c;border:1px solid #29384d;border-radius:10px;padding:11px}.person b{display:block;font-size:12px}.person span{font-size:10px;color:#a7b2c2;line-height:1.4}
.episode{display:grid;grid-template-columns:48px minmax(0,1fr) auto;gap:12px;align-items:center;padding:13px 0;border-bottom:1px solid #263244}.episode:last-child{border:0}.epnum{font-weight:1000;color:#b48aff;font-size:18px}.epname{font-weight:900;font-size:13px}.epdesc{font-size:11px;color:#95a2b4;margin-top:4px}.status{font-size:9px;color:#82dfb5;margin-top:5px;font-weight:900}.small{padding:8px 11px;font-size:10px}.scene{padding:14px 0;border-bottom:1px solid #273244}.scene h3{margin:0 0 7px;color:#d8baff;font-size:12px}.scene p{color:#aab5c4;font-size:12px;line-height:1.5}.line{font-size:12px;line-height:1.6;margin:5px 0}.line b{color:#f0d6ff}.notice{color:#aeb9c8;font-size:11px;line-height:1.5;background:#151e2a;border-radius:10px;padding:12px;margin-top:12px}.scripthead{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap}.error{color:#ff9d9d}.good{color:#87e8b8}@media(max-width:650px){.hero{display:block}.hero .btn{margin-top:18px;width:100%}.episode{grid-template-columns:32px minmax(0,1fr)}.episode button{grid-column:2;justify-self:start}}
</style></head>
<body><div class="wrap">
<div class="top"><div class="brand">GTA <span>OCULTO</span> AI · NOVELAS</div><a class="back" href="/">← VOLTAR AO RADAR</a></div>
<section class="hero"><div><div class="kicker">SÉRIE ORIGINAL DE FÃ · UNIVERSO GTA VI</div><h1>VICE CITY:<br>O PREÇO DO NEON</h1><div class="sub">Uma temporada criminal com Jason, Lucia e personagens do universo GTA VI. Cada episódio avança a trama, muda as relações e deixa consequências para o próximo.</div><span class="pill">8 EPISÓDIOS</span><span class="pill">DRAMA + CRIME + ROMANCE + AÇÃO</span><span class="pill">VERTICAL 9:16</span></div><button class="btn" id="nextBtn" onclick="generateNext()">✍️ GERAR PRÓXIMO ROTEIRO</button></section>
<div class="notice">A série é uma fanfiction não oficial. A memória da temporada registra acontecimentos, conflitos, revelações, diálogos e ganchos já utilizados. Gerar um roteiro não inicia renderização nem publicação de vídeo.</div>
<section class="panel"><div class="scripthead"><h2>ELENCO RECORRENTE</h2><span id="storage" class="muted">Memória carregando…</span></div><div id="cast" class="cast"></div></section>
<section class="panel"><div class="scripthead"><h2>PRIMEIRA TEMPORADA</h2><span id="progress" class="muted">0/8 roteiros criados</span></div><div id="episodes" class="muted">Carregando episódios…</div></section>
<section class="panel" id="preview" hidden><div class="scripthead"><h2 id="previewTitle">ROTEIRO</h2><span id="wordCount" class="muted"></span></div><div id="scriptBody"></div></section>
<div id="message" class="notice">A novela mantém sua própria memória, independente do Radar de notícias.</div>
</div>
<script>
let state=null;
function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
async function loadState(){const r=await fetch('/api/novelas/state',{cache:'no-store'});const d=await r.json();if(!r.ok||!d.ok)throw new Error(d.error||'Não foi possível carregar a novela.');state=d;render();}
function render(){document.getElementById('storage').textContent='Memória: '+(state.persistence==='supabase'?'persistente (Supabase)':'local')+' · Vídeo automático: desligado';
document.getElementById('progress').textContent=state.generated_count+'/8 roteiros criados';
document.getElementById('cast').innerHTML=state.characters.map(p=>'<div class="person"><b>'+esc(p.name)+'</b><span>'+esc(p.profile)+'</span></div>').join('');
const generated=new Map(state.episodes.map(e=>[e.number,e]));
document.getElementById('episodes').innerHTML=Array.from({length:8},(_,i)=>{let n=i+1,e=generated.get(n),titles=['A CARGA FANTASMA','FREQUÊNCIA MORTA','VIRAL','LINHA DE CRÉDITO','A DÍVIDA DE RAUL','O ARQUIVO DE BRIAN','NOITE DE MÁSCARAS','O PREÇO DO NEON'],places=['Marina das Leonida Keys','Estação meteorológica abandonada','Estúdio da Only Raw Records','Clube de Boobie Ike','Hotel de beira de estrada','Armazém antigo no porto','Gala beneficente em Vice City','Terminal de contêineres'];return '<div class="episode"><div class="epnum">'+String(n).padStart(2,'0')+'</div><div><div class="epname">'+titles[i]+'</div><div class="epdesc">'+places[i]+'</div><div class="status">'+(e?'✓ ROTEIRO SALVO':'○ AINDA NÃO GERADO')+'</div></div>'+(e?'<div style="display:flex;gap:6px;flex-wrap:wrap"><button class="btn small" onclick="openEpisode('+n+')">ABRIR ROTEIRO</button>'+(e.cinematic_ready?'<span class="pill">STORYBOARD PRONTO</span>':'<button class="btn small" onclick="cinematizeEpisode('+n+')">CINEMATIZAR</button>')+'</div>':(state.next_episode_number===n?'<button class="btn small" onclick="generateNext()">CRIAR ROTEIRO</button>':'<span class="muted">Aguardando episódio anterior</span>'))+'</div>'}).join('');
const b=document.getElementById('nextBtn');b.disabled=state.season_complete;b.textContent=state.season_complete?'✓ TEMPORADA COMPLETA':'✍️ GERAR EPISÓDIO '+String(state.next_episode_number).padStart(2,'0');
}
function showEpisode(e){
document.getElementById('preview').hidden=false;
document.getElementById('previewTitle').textContent='EPISÓDIO '+String(e.number).padStart(2,'0')+' — '+e.title;
document.getElementById('wordCount').textContent=e.word_count+' palavras · '+e.location+(e.cinematic_ready?' · '+e.dialogue_word_count+' palavras faladas · '+Math.round((e.duration_target_seconds||0)/60)+' min alvo':'');
const c=e.cinematic||{};
const shots=Array.isArray(c.shot_list)?c.shot_list:[];
const voices=c.voice_direction||{};
const continuity=c.continuity_rules||[];
const audio=c.audio_direction||{};
const cinematicPanel=e.cinematic_ready?'<div class="notice"><b>STORYBOARD CINEMATOGRÁFICO</b><br>Duração-alvo: '+Math.floor((c.duration_target_seconds||0)/60)+'m '+String((c.duration_target_seconds||0)%60).padStart(2,'0')+'s · Formato '+esc(c.format||'9:16')+' · '+shots.length+' planos<br><b>Áudio de referência:</b> '+esc(audio.music||'')+'<br><b>Mixagem planejada:</b> '+esc(audio.mix||'')+'</div><div class="scene"><h3>PLANOS DE CÂMERA</h3>'+shots.map(s=>'<div class="line"><b>'+esc(s.id)+' · Cena '+esc(s.scene)+' · '+esc(s.duration_seconds)+'s — '+esc(s.framing)+'</b><br><span class="muted">Câmera: '+esc(s.camera)+'</span><br>'+esc(s.visual)+'</div>').join('')+'</div><div class="scene"><h3>DIREÇÃO DE VOZ</h3>'+Object.keys(voices).map(k=>'<div class="line"><b>'+esc(k)+':</b> '+esc(voices[k])+'</div>').join('')+'</div><div class="scene"><h3>REGRAS DE CONTINUIDADE</h3>'+continuity.map(v=>'<div class="line">• '+esc(v)+'</div>').join('')+'</div>':'<div class="notice"><b>PRÓXIMO PASSO:</b> expandir este roteiro para cenas cinematográficas, planos, direção de voz e continuidade.'+(e.number===1?' <button class="btn small" onclick="cinematizeEpisode(1)">CINEMATIZAR EPISÓDIO 01</button>':'')+'</div>';
const voicePanel=e.number===1?'<div class="scene"><h3>REFAZER DIÁLOGOS COM VOZES NEURAIS</h3><p>Envie o MP4 atual do episódio. O GTA Oculto vai substituir a faixa de áudio por quatro vozes neurais brasileiras diferentes, sincronizadas às seis cenas. A faixa robótica antiga será descartada; não haverá fallback para eSpeak.</p><p class="muted">Jason · voz masculina grave | Lucia · voz feminina | Brian · voz masculina madura | Cal · voz masculina mais jovem. Nenhuma voz de ator será clonada.</p><div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center"><input id="voiceSourceVideo" type="file" accept="video/mp4,.mp4" style="max-width:100%;color:#dbe4f0"><button class="btn" id="voiceRemixBtn" onclick="startVoiceRemix()">GERAR NOVA VERSÃO COM VOZES NEURAIS</button></div><div id="voiceRemixStatus" class="notice" style="margin-top:10px">Selecione o MP4 que você recebeu e inicie a substituição da narração.</div></div>':'';
document.getElementById('scriptBody').innerHTML='<div class="notice"><b>CONFLITO:</b> '+esc(e.conflict)+'<br><b>REVELAÇÃO:</b> '+esc(e.revelation)+'<br><b>GANCHO FINAL:</b> '+esc(e.cliffhanger)+'</div>'+cinematicPanel+voicePanel+e.scenes.map(s=>'<div class="scene"><h3>'+esc(s.heading)+(s.duration_seconds?' · '+esc(s.duration_seconds)+'s':'')+'</h3><p>'+esc(s.action)+'</p>'+s.dialogue.map(d=>'<div class="line"><b>'+esc(d[0])+':</b> '+esc(d[1])+'</div>').join('')+'</div>').join('');
document.getElementById('preview').scrollIntoView({behavior:'smooth',block:'start'});
}
async function cinematizeEpisode(n){
const m=document.getElementById('message');m.textContent='Expandindo o roteiro, detalhando planos e gravando a continuidade na memória…';
try{const r=await fetch('/api/novelas/episodes/'+n+'/cinematic',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})});const d=await r.json();if(!r.ok)throw new Error(d.error||'Falha na expansão cinematográfica.');await loadState();showEpisode(d);m.innerHTML='<span class="good">Roteiro cinematográfico e storyboard salvos na memória persistente. Nenhum vídeo foi iniciado.</span>';}
catch(e){m.innerHTML='<span class="error">'+esc(e.message)+'</span>';}
}
async function startVoiceRemix(){
const input=document.getElementById('voiceSourceVideo');
const button=document.getElementById('voiceRemixBtn');
const status=document.getElementById('voiceRemixStatus');
const file=input&&input.files?input.files[0]:null;
if(!file){status.innerHTML='<span class="error">Selecione o MP4 do episódio 01 primeiro.</span>';return;}
if(!file.name.toLowerCase().endsWith('.mp4')){status.innerHTML='<span class="error">O arquivo precisa ser MP4.</span>';return;}
const form=new FormData();form.append('video',file,file.name);
button.disabled=true;status.textContent='Enviando o MP4 para o servidor…';
try{
 const r=await fetch('/api/novelas/episodes/1/voice-remix',{method:'POST',body:form});
 const d=await r.json();if(!r.ok)throw new Error(d.error||'Não foi possível iniciar a dublagem neural.');
 status.textContent='Dublagem iniciada. O servidor está sintetizando cada fala separadamente…';
 pollVoiceRemix(d.job_id);
}catch(e){status.innerHTML='<span class="error">'+esc(e.message)+'</span>';button.disabled=false;}
}
async function pollVoiceRemix(jobId){
const status=document.getElementById('voiceRemixStatus');
const button=document.getElementById('voiceRemixBtn');
try{
 const r=await fetch('/api/novelas/voice-remix/'+jobId,{cache:'no-store'});
 const d=await r.json();if(!r.ok)throw new Error(d.error||'Não foi possível consultar o trabalho.');
 if(d.status==='COMPLETED'){
   const voices=d.result&&d.result.voices?Object.keys(d.result.voices).map(k=>'<div class="line"><b>'+esc(k)+':</b> '+esc(d.result.voices[k])+'</div>').join(''):'';
   status.innerHTML='<span class="good"><b>MP4 COM VOZES NEURAIS PRONTO.</b></span><br>'+esc(d.result.spoken_lines)+' falas · '+esc(d.result.spoken_words)+' palavras · '+esc(d.result.duration_seconds)+'s<br><div class="scene">'+voices+'</div><a class="btn" href="'+esc(d.download_url)+'">BAIXAR VÍDEO COM NOVAS VOZES</a> <a class="btn small" href="'+esc(d.subtitles_url)+'">BAIXAR LEGENDAS SRT</a>';
   button.disabled=false;return;
 }
 if(d.status==='ERROR'){throw new Error(d.error||d.message||'A síntese neural falhou. O áudio original não foi alterado.');}
 status.textContent=(d.stage||'PROCESSANDO')+' · '+(d.progress||0)+'% — '+(d.message||'Gerando vozes neurais…');
 setTimeout(()=>pollVoiceRemix(jobId),2500);
}catch(e){status.innerHTML='<span class="error">'+esc(e.message)+'</span>';button.disabled=false;}
}
async function openEpisode(n){const r=await fetch('/api/novelas/episodes/'+n);const d=await r.json();if(!r.ok){document.getElementById('message').textContent=d.error||'Roteiro não encontrado.';return;}showEpisode(d);}
async function generateNext(){if(!state||!state.next_episode_number)return;const n=state.next_episode_number,b=document.getElementById('nextBtn'),m=document.getElementById('message');b.disabled=true;m.textContent='Montando roteiro e verificando continuidade…';
try{const r=await fetch('/api/novelas/episodes/'+n+'/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})});const d=await r.json();if(!r.ok)throw new Error(d.error||'Falha ao gerar roteiro.');await loadState();showEpisode(d);m.innerHTML='<span class="good">Roteiro salvo na memória da temporada. Nenhum vídeo foi iniciado.</span>';}catch(e){m.innerHTML='<span class="error">'+esc(e.message)+'</span>';b.disabled=false;}}
loadState().catch(e=>document.getElementById('message').textContent=e.message);
</script></body></html>"""
