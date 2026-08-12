#!/usr/bin/env python3
"""
Gera assets/hero.svg — o card de hero do README.

Rode sempre que trocar a foto do perfil no GitHub:

    pip install pillow
    python scripts/build_hero.py

O retrato ASCII é gerado a partir do seu avatar real do GitHub. Fotos com
fundo escuro e sujeito iluminado (como a atual) rendem muito melhor que
fotos com fundo claro — se trocar por uma de fundo branco, inverta a rampa.

POR QUE UM SVG DESENHADO À MÃO, E NÃO UM SERVIÇO EXTERNO
  O README do GitHub descarta CSS, então cards com borda, tipografia grande
  e layout em duas colunas só existem dentro de uma imagem. Como o SVG é
  estático e mora no próprio repo, ele nunca cai — diferente dos geradores
  hospedados em Vercel, que já saíram do ar duas vezes neste perfil.
"""
from pathlib import Path
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape

from PIL import Image, ImageEnhance, ImageOps

# ── o que você pode querer editar ────────────────────────────────────────────
GITHUB_USER = "ltin0"
NOME = "Leonardo Tino"
CARGO = "Desenvolvedor Web Full Stack"
LOCAL = "São Paulo, Brasil"
STATUS = "ABERTO A OPORTUNIDADES · REMOTO"
TAGLINE = [
    "Desenvolvo experiências digitais rápidas, escaláveis",
    "e orientadas a resultados — do modelo de dados ao deploy.",
]
# (rótulo, largura da pill). Largura folgada de propósito — veja nota em pill().
STACK = [("TypeScript", 92), ("Next.js", 74), ("React", 66),
         ("PHP", 54), ("WordPress", 94), ("Docker", 72)]

# ── identidade visual ────────────────────────────────────────────────────────
BG, BORDER = "#131317", "#26262D"
GREEN, VIOLET = "#4ADE80", "#A78BFA"
TEXT, MUTED, PILL_BG = "#F4F4F5", "#A1A1AA", "#1A1A20"

# Só famílias genéricas: o GitHub serve o SVG via proxy e webfont não carrega.
SANS = ("ui-sans-serif,-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,"
        "Helvetica,Arial,sans-serif")
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,Liberation Mono,monospace"

RAMP = " .:-=+*#%@"          # do fundo (espaço) até a luz (@)
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "hero.svg"
CACHE = ROOT / "assets" / ".avatar-cache.png"


def avatar() -> Image.Image:
    """Baixa o avatar do GitHub; cai no cache local se estiver sem rede."""
    url = f"https://github.com/{GITHUB_USER}.png?size=460"
    try:
        req = Request(url, headers={"User-Agent": "build-hero"})
        data = urlopen(req, timeout=30).read()
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_bytes(data)
    except Exception as e:                                    # noqa: BLE001
        if not CACHE.exists():
            raise SystemExit(f"sem rede e sem cache em {CACHE}: {e}")
        print(f"aviso: usando cache ({e})")
    return Image.open(CACHE)


def ascii_portrait(cols=48, gamma=0.8, contrast=1.25, pad=6):
    im = avatar().convert("L")
    # o avatar tem muita margem preta — recorta na caixa do conteúdo
    lit = ImageEnhance.Brightness(im).enhance(2.2)
    b = lit.point(lambda v: 255 if v > 28 else 0).getbbox()
    im = im.crop((max(0, b[0] - pad), max(0, b[1] - pad),
                  min(im.width, b[2] + pad), min(im.height, b[3] + pad)))
    im = ImageOps.autocontrast(ImageEnhance.Contrast(im).enhance(contrast), cutoff=1)

    # caractere de terminal é ~2x mais alto que largo: comprime a altura
    rows_n = max(1, int(cols * im.height / im.width * 0.5))
    im = im.resize((cols, rows_n), Image.LANCZOS)

    n = len(RAMP) - 1
    rows = ["".join(RAMP[int((im.getpixel((x, y)) / 255.0) ** gamma * n + 0.5)]
                    for x in range(cols)).rstrip()
            for y in range(rows_n)]
    while rows and not rows[0].strip():
        rows.pop(0)
    while rows and not rows[-1].strip():
        rows.pop()
    return rows


def pill(x, y, w, h, label, color, size=12):
    """Pill de rótulo.

    A largura vem por parâmetro e é folgada de propósito: a fonte é genérica
    e a métrica muda por sistema operacional. Pill justa estoura o texto em
    quem não tem a mesma fonte.
    """
    return (f'  <g>\n'
            f'    <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h // 2}" '
            f'fill="{PILL_BG}" stroke="{BORDER}"/>\n'
            f'    <text x="{x + w / 2:.0f}" y="{y + h / 2 + size * 0.35:.1f}" '
            f'font-family="{SANS}" font-size="{size}" font-weight="500" '
            f'fill="{color}" text-anchor="middle">{escape(label)}</text>\n'
            f'  </g>')


def build() -> str:
    rows = ascii_portrait()
    fs = 11                     # corpo da fonte do ASCII
    adv = fs * 0.6              # avanço de um caractere monoespaçado
    lh = fs * 1.2

    W, H = 1000, 400
    art_x = 56
    art_y = (H - len(rows) * lh) / 2 + fs
    col = 420                   # início da coluna de texto

    # ── por que NBSP + textLength ───────────────────────────────────────────
    # O padrão de <text> em SVG é white-space:nowrap, que COLAPSA os espaços
    # à esquerda. Sem tratar, toda linha encosta na margem e o retrato vira um
    # borrão alinhado à esquerda. Duas travas:
    #   1. todo espaço vira U+00A0, que não colapsa
    #   2. toda linha é preenchida até a mesma largura e recebe o mesmo
    #      textLength — a grade de colunas fica travada mesmo se o
    #      renderizador cair numa fonte que não seja monoespaçada de verdade
    width_chars = max(len(r) for r in rows)
    span = width_chars * adv
    art = "\n".join(
        f'    <text x="{art_x}" y="{art_y + i * lh:.1f}" textLength="{span:.1f}" '
        f'lengthAdjust="spacing">'
        f'{escape(r.ljust(width_chars).replace(" ", chr(0xA0)))}</text>'
        for i, r in enumerate(rows) if r.strip())

    pills, px = [], col
    for label, w in STACK:
        pills.append(pill(px, 300, w, 30, label, MUTED))
        px += w + 9

    alt = (f"{NOME} — {CARGO} em {LOCAL}. Aberto a oportunidades remotas. "
           f"Stack: {', '.join(s for s, _ in STACK)}.")

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}"
     width="{W}" height="{H}" role="img" aria-label="{escape(alt)}">
  <title>{escape(NOME)} — {escape(CARGO)}</title>

  <defs>
    <linearGradient id="skin" x1="0" y1="0" x2="0.35" y2="1">
      <stop offset="0%"   stop-color="{GREEN}"/>
      <stop offset="55%"  stop-color="{GREEN}"/>
      <stop offset="100%" stop-color="{VIOLET}"/>
    </linearGradient>
    <radialGradient id="glow" cx="50%" cy="50%" r="50%">
      <stop offset="0%"   stop-color="{GREEN}"  stop-opacity="0.16"/>
      <stop offset="70%"  stop-color="{VIOLET}" stop-opacity="0.05"/>
      <stop offset="100%" stop-color="{VIOLET}" stop-opacity="0"/>
    </radialGradient>
  </defs>

  <rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="18" fill="{BG}" stroke="{BORDER}"/>
  <rect x="18" y="0.5" width="{W - 36}" height="1" fill="{GREEN}" opacity="0.35"/>

  <ellipse cx="{art_x + span / 2:.0f}" cy="{H / 2:.0f}" rx="210" ry="190" fill="url(#glow)"/>

  <g font-family="{MONO}" font-size="{fs}" fill="url(#skin)"
     xml:space="preserve" style="white-space:pre">
{art}
  </g>

  <g>
    <rect x="{col}" y="66" width="330" height="30" rx="15" fill="#0F2A1B" stroke="#1F6F42"/>
    <circle cx="{col + 18}" cy="81" r="4" fill="{GREEN}"/>
    <text x="{col + 32}" y="86" font-family="{SANS}" font-size="12.5" font-weight="600"
          letter-spacing="0.6" fill="{GREEN}">{escape(STATUS)}</text>
  </g>

  <text x="{col}" y="164" font-family="{SANS}" font-size="52" font-weight="700"
        fill="{GREEN}">{escape(NOME)}</text>

  <text x="{col}" y="200" font-family="{SANS}" font-size="19" font-weight="600" fill="{TEXT}">
    {escape(CARGO)}<tspan fill="{MUTED}" font-weight="400"> · {escape(LOCAL)}</tspan>
  </text>

  <text x="{col}" y="240" font-family="{SANS}" font-size="15" fill="{MUTED}">{escape(TAGLINE[0])}</text>
  <text x="{col}" y="262" font-family="{SANS}" font-size="15" fill="{MUTED}">{escape(TAGLINE[1])}</text>

{chr(10).join(pills)}
</svg>
"""


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    svg = build()
    OUT.write_text(svg, encoding="utf-8")
    print(f"gravado: {OUT.relative_to(ROOT)} ({len(svg)} bytes)")
