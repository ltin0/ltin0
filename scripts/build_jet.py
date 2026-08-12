#!/usr/bin/env python3
"""
Gera assets/jet.svg — o grid de contribuições como um jogo de nave.

Uma nave percorre o ano da esquerda para a direita e dispara nos dias de maior
atividade. Cada tiro sobe da faixa da nave até a célula alvo, que explode e
apaga. Depois o ciclo reinicia.

    python scripts/build_jet.py            # usa GITHUB_TOKEN do ambiente
    GITHUB_TOKEN=ghp_xxx python scripts/build_jet.py

POR QUE ISSO EXISTE, EM VEZ DE UM SERVIÇO PRONTO
  Os geradores hospedados renderizam a cada visita ao perfil: no dia em que o
  serviço cai, some tudo. Já aconteceu duas vezes neste perfil
  (github-readme-stats: 503, github-profile-trophy: 402). Aqui o SVG é gerado
  por uma Action e commitado no próprio repositório — se este script parar de
  rodar, a última imagem continua no ar para sempre.

RESTRIÇÕES ATENDIDAS
  • Zero JavaScript — o GitHub não executa script em SVG de README
  • Animação em CSS @keyframes, que roda com o SVG carregado via <img>
  • Nenhuma fonte externa: só famílias genéricas
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ── o que você pode querer editar ────────────────────────────────────────────
GITHUB_USER = "ltin0"
TITULO = "Contribution Activity"
LEGENDA = "A nave percorre o ano e dispara nos dias de maior atividade."
ALVOS = 9           # quantos dias campeões são alvejados por volta
# A travessia É o ciclo inteiro: a nave nasce fora do card à esquerda e sai
# fora dele à direita, então o salto do fim para o início acontece com ela
# invisível. Sem isso o loop mostra a nave parada esperando e depois teleportando.
DUR_VOLTA = 13.0    # segundos de uma travessia completa
VIDA_ALVO = 3.2     # segundos que a célula atingida fica marcada
DUR_ORBITA = 7.0    # segundos para o facho dar uma volta na moldura

# ── identidade visual (mesma do resto do perfil) ─────────────────────────────
BG      = "#131317"
BORDER  = "#26262D"
GREEN   = "#4ADE80"
VIOLET  = "#A78BFA"
TEXT    = "#F4F4F5"
MUTED   = "#A1A1AA"
DIM     = "#71717A"
# escala do grid: nível 0 (vazio) até 4 (dia mais intenso)
NIVEIS = ["#1A1A20", "#14532D", "#166534", "#22C55E", GREEN]

SANS = ("ui-sans-serif,-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,"
        "Helvetica,Arial,sans-serif")

# ── geometria ────────────────────────────────────────────────────────────────
CELL, GAP = 11, 2
PITCH = CELL + GAP
PAD_L, PAD_R = 34, 18
# Folga em volta do card para o brilho não ser cortado pela borda do viewBox.
# Sem isso o filtro de blur é clipado e o halo aparece cortado em cima e embaixo.
MARGEM = 16
Y_TITULO, Y_MESES = 26, 58
Y_GRID = 66
LANE_OFF = 26      # distância da faixa da nave até a base do grid

MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
         "jul", "ago", "set", "out", "nov", "dez"]
DIAS = {1: "Seg", 3: "Qua", 5: "Sex"}

NIVEL_ENUM = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2,
              "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "jet.svg"
CACHE = ROOT / "assets" / ".contrib-cache.json"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          firstDay
          contributionDays { date weekday contributionCount contributionLevel }
        }
      }
    }
  }
}
"""


def token() -> str | None:
    for k in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(k):
            return os.environ[k]
    return None


def calendario() -> dict:
    """Busca o calendário; cai no cache se estiver sem rede ou sem token."""
    tk = token()
    if tk:
        body = json.dumps({"query": QUERY,
                           "variables": {"login": GITHUB_USER}}).encode()
        req = Request("https://api.github.com/graphql", data=body,
                      headers={"Authorization": f"bearer {tk}",
                               "Content-Type": "application/json",
                               "User-Agent": "build-jet"})
        try:
            data = json.loads(urlopen(req, timeout=30).read())
            if "errors" in data:
                raise RuntimeError(data["errors"][0].get("message", "erro GraphQL"))
            cal = (data["data"]["user"]["contributionsCollection"]
                       ["contributionCalendar"])
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(cal), encoding="utf-8")
            return cal
        except (HTTPError, URLError, RuntimeError, KeyError, TypeError) as e:
            print(f"aviso: falha na API ({e})", file=sys.stderr)
    else:
        print("aviso: sem GITHUB_TOKEN no ambiente", file=sys.stderr)

    if CACHE.exists():
        print(f"usando cache {CACHE.name}", file=sys.stderr)
        return json.loads(CACHE.read_text(encoding="utf-8"))
    raise SystemExit("sem token e sem cache — nao da para gerar")


def alvos(semanas: list, quantos: int) -> list[tuple[int, int, int]]:
    """Os dias mais intensos, no máximo um por coluna, espalhados pelo ano.

    Um alvo por coluna evita dois tiros simultâneos, que ficam confusos; e a
    ordenação por coluna no fim garante que a nave dispare na ordem em que
    passa, não na ordem de intensidade.
    """
    melhor: dict[int, tuple[int, int]] = {}
    for c, semana in enumerate(semanas):
        for dia in semana["contributionDays"]:
            n = dia["contributionCount"]
            if n <= 0:
                continue
            if c not in melhor or n > melhor[c][1]:
                melhor[c] = (dia["weekday"], n)
    ranking = sorted(melhor.items(), key=lambda kv: kv[1][1], reverse=True)
    escolhidos = ranking[:quantos]
    return sorted([(c, wd, n) for c, (wd, n) in escolhidos])


def build() -> str:
    cal = calendario()
    semanas = cal["weeks"]
    total = cal["totalContributions"]
    n_col = len(semanas)

    grid_w = n_col * PITCH - GAP
    W = PAD_L + grid_w + PAD_R          # dimensões do card
    y_base = Y_GRID + 7 * PITCH - GAP
    y_lane = y_base + LANE_OFF
    H = y_lane + 22
    W_TOTAL, H_TOTAL = W + 2 * MARGEM, H + 2 * MARGEM   # com a folga do brilho

    # ── células ──────────────────────────────────────────────────────────────
    celulas = []
    for c, semana in enumerate(semanas):
        for dia in semana["contributionDays"]:
            lvl = NIVEL_ENUM.get(dia["contributionLevel"], 0)
            x = PAD_L + c * PITCH
            y = Y_GRID + dia["weekday"] * PITCH
            celulas.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2.5" '
                f'fill="{NIVEIS[lvl]}"/>')

    # ── rótulos de mês: um por mudança de mês, sem repetir ───────────────────
    meses, visto = [], None
    for c, semana in enumerate(semanas):
        m = int(semana["firstDay"][5:7])
        if m != visto:
            visto = m
            x = PAD_L + c * PITCH
            if x < W - PAD_R - 18:
                meses.append(
                    f'<text x="{x}" y="{Y_MESES}" font-family="{SANS}" '
                    f'font-size="10" fill="{DIM}">{MESES[m - 1]}</text>')

    dias = [f'<text x="{PAD_L - 8}" y="{Y_GRID + wd * PITCH + 9}" '
            f'font-family="{SANS}" font-size="9" fill="{DIM}" '
            f'text-anchor="end">{rot}</text>' for wd, rot in DIAS.items()]

    # ── nave, tiros e explosões ──────────────────────────────────────────────
    # Vai e volta. A nave nasce fora do card à esquerda, sai fora dele à
    # direita e retorna — a inversão de sentido acontece com ela invisível,
    # então não se vê o "quique". Metade do ciclo para cada sentido.
    x_ini, x_fim = -30, W + 30
    meia = DUR_VOLTA / 2

    # Alvos alternados entre ida e volta: assim nenhuma célula pisca duas vezes
    # no mesmo ciclo e a ação se espalha melhor pelo ano.
    todos = alvos(semanas, ALVOS * 2)
    rota = [(alvo, "ida") for alvo in todos[0::2]] + \
           [(alvo, "volta") for alvo in todos[1::2]]

    tiros, flashes = [], []
    for (c, wd, _n), sentido in rota:
        x_alvo = PAD_L + c * PITCH + CELL / 2
        y_alvo = Y_GRID + wd * PITCH
        # instante em que a nave passa sobre a coluna, em cada sentido
        avanco = (x_alvo - x_ini) / (x_fim - x_ini)
        t = avanco * meia if sentido == "ida" else meia + (1 - avanco) * meia
        subida = y_lane - (y_alvo + CELL)
        tiros.append(
            f'<rect class="tiro" x="{x_alvo - 1:.1f}" y="{y_lane - 10:.1f}" '
            f'width="2" height="9" rx="1" fill="{GREEN}" '
            f'style="--sobe:{-subida:.1f}px;animation-delay:{t:.2f}s"/>')
        # ── por que agora basta um @keyframes para todos ─────────────────────
        # Porcentagem de @keyframes é relativa ao ciclo PRÓPRIO do elemento,
        # que o animation-delay desloca. Antes a célula precisava apagar num
        # instante global fixo, e cada alvo exigia a sua regra. Agora a vida do
        # alvo é contada A PARTIR DO TIRO ({VIDA_ALVO}s), que é exatamente o que
        # o ciclo deslocado já expressa — então a regra é uma só, e não existe
        # mais o momento de reset coletivo.
        flashes.append(
            f'<rect class="hit" x="{x_alvo - CELL / 2:.1f}" y="{y_alvo}" '
            f'width="{CELL}" height="{CELL}" rx="2.5" fill="{VIOLET}" '
            f'style="animation-delay:{t + 0.30:.2f}s"/>')
        flashes.append(
            f'<circle class="boom" cx="{x_alvo:.1f}" cy="{y_alvo + CELL / 2}" '
            f'r="3" fill="none" stroke="{VIOLET}" stroke-width="1.5" '
            f'style="animation-delay:{t + 0.30:.2f}s"/>')

    # ── facho que orbita a moldura ───────────────────────────────────────────
    # Um traço curto correndo o perímetro via stroke-dashoffset.
    #
    # NÃO calcular o perímetro à mão: a fórmula geométrica (2(W-2r) + 2(H-2r)
    # + 2πr) deu 1860, mas o getTotalLength do navegador mede 1855,4, porque
    # ele aproxima os arcos dos cantos por segmentos. Os 4,6px de diferença
    # viram um salto visível a cada volta, e o erro muda conforme o renderizador.
    # Com pathLength o comprimento passa a ser declarado por nós: dasharray e
    # dashoffset viram unidade normalizada e a volta fecha exata em qualquer
    # navegador.
    r_card = 14
    PATH_LEN = 1000
    facho = PATH_LEN * 0.16

    # Marcos do ciclo em porcentagem, derivados dos segundos acima. Deixar o
    # tempo em segundos nas constantes e converter aqui evita number mágico
    # espalhado pelo CSS.
    pct = lambda seg: seg / DUR_VOLTA * 100
    legenda_x = W - PAD_R - 132
    escala = "".join(
        f'<rect x="{legenda_x + 30 + i * 13}" y="{Y_TITULO - 9}" width="10" '
        f'height="10" rx="2" fill="{NIVEIS[i]}"/>' for i in range(5))

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W_TOTAL} {H_TOTAL}"
     width="{W_TOTAL}" height="{H_TOTAL}" role="img"
     aria-label="Grid de contribuições de {GITHUB_USER} no GitHub no último ano, com {total} contribuições, animado como um jogo de nave: uma nave percorre o ano e dispara nos dias de maior atividade.">
  <title>{TITULO} — {total} contribuições no último ano</title>

  <style>
    /* Animação 100% CSS: o GitHub não executa JavaScript em SVG de README.
       Todos os elementos compartilham o mesmo ciclo de {DUR_VOLTA}s, e cada tiro
       entra pelo seu próprio animation-delay, calculado a partir do instante em
       que a nave passa sobre a coluna alvo. */
    .nave   {{ animation: voo {DUR_VOLTA}s linear infinite; }}
    .tiro   {{ opacity: 0; animation: disparo {DUR_VOLTA}s linear infinite; }}
    .hit    {{ opacity: 0; animation: acerto {DUR_VOLTA}s linear infinite; }}
    .boom   {{ opacity: 0; animation: explosao {DUR_VOLTA}s ease-out infinite; }}
    .chama  {{ animation: motor .45s ease-in-out infinite alternate; }}
    .aura   {{ animation: respira 5s ease-in-out infinite alternate; }}
    .orbita {{ animation: orbita {DUR_ORBITA}s linear infinite; }}

    /* Vai e volta: ida em 50%, retorno nos outros 50%. Como as duas pontas
       ficam fora do card, a inversão de sentido acontece com a nave invisível
       — não se vê o "quique" nem o teleporte. Timing linear de propósito: os
       instantes de tiro são calculados linearmente, e um ease dessincronizaria
       o disparo da posição. */
    @keyframes voo {{
      0%   {{ transform: translateX(0); }}
      50%  {{ transform: translateX({x_fim - x_ini}px); }}
      100% {{ transform: translateX(0); }}
    }}
    @keyframes disparo {{
      0%                        {{ opacity: 0; transform: translateY(0); }}
      {pct(0.02):.2f}%          {{ opacity: 1; transform: translateY(0); }}
      {pct(0.32):.2f}%          {{ opacity: 1; transform: translateY(var(--sobe)); }}
      {pct(0.34):.2f}%, 100%    {{ opacity: 0; transform: translateY(var(--sobe)); }}
    }}
    /* Vida do alvo contada a partir do tiro, não de um instante global. */
    @keyframes acerto {{
      0%                            {{ opacity: 0; }}
      {pct(0.02):.2f}%              {{ opacity: .95; }}
      {pct(0.30):.2f}%              {{ opacity: .5; }}
      {pct(VIDA_ALVO):.2f}%         {{ opacity: .5; }}
      {pct(VIDA_ALVO + 0.8):.2f}%, 100% {{ opacity: 0; }}
    }}
    @keyframes explosao {{
      0%                     {{ opacity: 0;  transform: scale(.3); transform-origin: center; }}
      {pct(0.02):.2f}%       {{ opacity: .9; transform: scale(.3); transform-origin: center; }}
      {pct(0.45):.2f}%       {{ opacity: 0;  transform: scale(2.6); transform-origin: center; }}
      100%                   {{ opacity: 0;  transform: scale(2.6); transform-origin: center; }}
    }}
    @keyframes motor {{
      from {{ opacity: .35; }} to {{ opacity: 1; }}
    }}
    /* Pulso lento do halo. Amplitude baixa de propósito: a ideia é o card
       parecer vivo, não piscar. */
    @keyframes respira {{
      from {{ opacity: .38; }} to {{ opacity: .78; }}
    }}
    /* O facho percorre exatamente um perímetro por ciclo, então a emenda cai
       no mesmo ponto e a volta fecha sem salto. */
    @keyframes orbita {{
      from {{ stroke-dashoffset: 0; }}
      to   {{ stroke-dashoffset: -{PATH_LEN}; }}
    }}

    /* Quem pediu menos movimento no sistema vê o grid parado, com a nave
       no início da pista e sem tiros. O dado continua legível. */
    @media (prefers-reduced-motion: reduce) {{
      .nave, .tiro, .hit, .boom, .chama, .aura, .orbita {{ animation: none; }}
      .tiro, .hit, .boom, .orbita {{ opacity: 0; }}
      .aura {{ opacity: .6; }}
    }}
  </style>

  <defs>
    <linearGradient id="borda" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%"   stop-color="{GREEN}"/>
      <stop offset="55%"  stop-color="#34D399"/>
      <stop offset="100%" stop-color="{VIOLET}"/>
    </linearGradient>
    <filter id="halo" x="-25%" y="-45%" width="150%" height="190%">
      <feGaussianBlur stdDeviation="7"/>
    </filter>
  </defs>

  <g transform="translate({MARGEM}, {MARGEM})">

  <!-- Halo: mesma moldura borrada por trás do card. Duas camadas dão a queda
       suave do brilho; uma só fica com corte visível na borda. -->
  <rect class="aura" x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14"
        fill="none" stroke="url(#borda)" stroke-width="4" filter="url(#halo)"/>
  <rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="{r_card}"
        fill="{BG}" stroke="url(#borda)" stroke-width="1.4"/>
  <!-- Facho orbitando a moldura, para sempre. pathLength normaliza o
       comprimento, então a volta fecha exata em qualquer renderizador. -->
  <rect class="orbita" x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="{r_card}"
        pathLength="{PATH_LEN}" fill="none" stroke="{GREEN}" stroke-width="2.2"
        stroke-linecap="round"
        stroke-dasharray="{facho:.0f} {PATH_LEN - facho:.0f}" filter="url(#halo)"/>
  <rect class="orbita" x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="{r_card}"
        pathLength="{PATH_LEN}" fill="none" stroke="{TEXT}" stroke-width="1.2"
        stroke-linecap="round"
        stroke-dasharray="{facho * 0.4:.0f} {PATH_LEN - facho * 0.4:.0f}" opacity="0.9"/>

  <text x="{PAD_L - 8}" y="{Y_TITULO}" font-family="{SANS}" font-size="14"
        font-weight="700" fill="{TEXT}">{TITULO}</text>
  <text x="{PAD_L - 8}" y="{Y_TITULO + 17}" font-family="{SANS}" font-size="11"
        fill="{MUTED}">{total} contribuições no último ano</text>

  <text x="{legenda_x}" y="{Y_TITULO}" font-family="{SANS}" font-size="10"
        fill="{DIM}">Menos</text>
  {escala}
  <text x="{legenda_x + 30 + 5 * 13 + 4}" y="{Y_TITULO}" font-family="{SANS}"
        font-size="10" fill="{DIM}">Mais</text>

  {chr(10).join(meses)}
  {chr(10).join(dias)}

  <g>
{chr(10).join('    ' + c for c in celulas)}
  </g>

  <g>
{chr(10).join('    ' + f for f in flashes)}
  </g>

  <g>
{chr(10).join('    ' + t for t in tiros)}
  </g>

  <!-- a nave. Desenhada apontando para cima: ela voa na horizontal e atira
       para cima, então o bico segue a direção do tiro. -->
  <g class="nave">
    <g transform="translate({x_ini}, {y_lane})">
      <path d="M0,-9 L5.5,4 L0,1.5 L-5.5,4 Z" fill="{VIOLET}"/>
      <path d="M0,-9 L2.2,-2 L-2.2,-2 Z" fill="{TEXT}" opacity="0.9"/>
      <path class="chama" d="M0,2 L2.6,9 L0,7 L-2.6,9 Z" fill="{GREEN}"/>
    </g>
  </g>

  </g>
</svg>
"""


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    svg = build()
    OUT.write_text(svg, encoding="utf-8")
    print(f"gravado: {OUT.relative_to(ROOT)} ({len(svg)} bytes)")
