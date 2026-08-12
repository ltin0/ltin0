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
ALVOS = 9          # quantos dias campeões são alvejados por volta
DUR_VOO = 11.0     # segundos para a nave cruzar o ano
DUR_CICLO = 14.0   # duração total antes de reiniciar

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
    x_ini, x_fim = PAD_L - 26, PAD_L + grid_w + 26
    t_limpa = DUR_VOO + 1.0    # instante global em que as células devem apagar
    tiros, flashes, kf_acerto = [], [], []
    for i, (c, wd, _n) in enumerate(alvos(semanas, ALVOS)):
        x_alvo = PAD_L + c * PITCH + CELL / 2
        y_alvo = Y_GRID + wd * PITCH
        # instante em que a nave está sobre a coluna
        t = (x_alvo - x_ini) / (x_fim - x_ini) * DUR_VOO
        subida = y_lane - (y_alvo + CELL)
        tiros.append(
            f'<rect class="tiro" x="{x_alvo - 1:.1f}" y="{y_lane - 10:.1f}" '
            f'width="2" height="9" rx="1" fill="{GREEN}" '
            f'style="--sobe:{-subida:.1f}px;animation-delay:{t:.2f}s"/>')

        # ── a sutileza que quebra tudo ───────────────────────────────────────
        # As porcentagens de @keyframes são relativas ao ciclo PRÓPRIO do
        # elemento, que o animation-delay desloca — não ao relógio comum. Com
        # um único @keyframes compartilhado, a célula atingida aos 10s só
        # apagaria aos 21s, ou seja, continuaria acesa na volta seguinte.
        # Por isso cada alvo recebe o seu, com o ponto de apagar calculado a
        # partir do próprio delay.
        t_hit = t + 0.30
        p = max(2.0, (t_limpa - t_hit) / DUR_CICLO * 100)
        kf_acerto.append(f"""    @keyframes acerto{i} {{
      0%              {{ opacity: 0; }}
      0.1%            {{ opacity: .95; }}
      1.6%            {{ opacity: .5; }}
      {p:.2f}%        {{ opacity: .5; }}
      {p + 2.5:.2f}%, 100% {{ opacity: 0; }}
    }}
    .hit{i} {{ animation-name: acerto{i}; animation-delay: {t_hit:.2f}s; }}""")

        flashes.append(
            f'<rect class="hit hit{i}" x="{x_alvo - CELL / 2:.1f}" y="{y_alvo}" '
            f'width="{CELL}" height="{CELL}" rx="2.5" fill="{VIOLET}"/>')
        flashes.append(
            f'<circle class="boom" cx="{x_alvo:.1f}" cy="{y_alvo + CELL / 2}" '
            f'r="3" fill="none" stroke="{VIOLET}" stroke-width="1.5" '
            f'style="animation-delay:{t_hit:.2f}s"/>')

    fim_voo = DUR_VOO / DUR_CICLO * 100   # % do ciclo em que a nave chega ao fim
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
       Todos os elementos compartilham o mesmo ciclo de {DUR_CICLO}s, e cada tiro
       entra pelo seu próprio animation-delay, calculado a partir do instante em
       que a nave passa sobre a coluna alvo. */
    .nave {{ animation: voo {DUR_CICLO}s linear infinite; }}
    .tiro {{ opacity: 0; animation: disparo {DUR_CICLO}s linear infinite; }}
    /* .hit não declara animation-name aqui: cada alvo tem o seu, gerado abaixo. */
    .hit   {{ opacity: 0; animation-duration: {DUR_CICLO}s; animation-timing-function: linear;
             animation-iteration-count: infinite; }}
    .boom  {{ opacity: 0; animation: explosao {DUR_CICLO}s ease-out infinite; }}
    .chama {{ animation: motor .45s ease-in-out infinite alternate; }}
    .aura  {{ animation: respira 5s ease-in-out infinite alternate; }}

    @keyframes voo {{
      0%             {{ transform: translateX(0); }}
      {fim_voo:.1f}% {{ transform: translateX({x_fim - x_ini}px); }}
      100%           {{ transform: translateX({x_fim - x_ini}px); }}
    }}
    @keyframes disparo {{
      0%           {{ opacity: 0; transform: translateY(0); }}
      0.1%         {{ opacity: 1; transform: translateY(0); }}
      2.3%         {{ opacity: 1; transform: translateY(var(--sobe)); }}
      2.4%, 100%   {{ opacity: 0; transform: translateY(var(--sobe)); }}
    }}
{chr(10).join(kf_acerto)}
    @keyframes explosao {{
      0%    {{ opacity: 0;  transform: scale(.3); transform-origin: center; }}
      .1%   {{ opacity: .9; transform: scale(.3); transform-origin: center; }}
      2.5%  {{ opacity: 0;  transform: scale(2.6); transform-origin: center; }}
      100%  {{ opacity: 0;  transform: scale(2.6); transform-origin: center; }}
    }}
    @keyframes motor {{
      from {{ opacity: .35; }} to {{ opacity: 1; }}
    }}
    /* Pulso lento do halo. Amplitude baixa de propósito: a ideia é o card
       parecer vivo, não piscar. */
    @keyframes respira {{
      from {{ opacity: .38; }} to {{ opacity: .78; }}
    }}

    /* Quem pediu menos movimento no sistema vê o grid parado, com a nave
       no início da pista e sem tiros. O dado continua legível. */
    @media (prefers-reduced-motion: reduce) {{
      .nave, .tiro, .hit, .boom, .chama, .aura {{ animation: none; }}
      .tiro, .hit, .boom {{ opacity: 0; }}
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
  <rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14"
        fill="{BG}" stroke="url(#borda)" stroke-width="1.4"/>

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
