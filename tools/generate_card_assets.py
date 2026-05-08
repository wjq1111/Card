from __future__ import annotations

import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "assets" / "images" / "cards"

CARD_WIDTH = 360
CARD_HEIGHT = 540
CORNER_RADIUS = 28

RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUITS = [
    ("spades", "S", "#1A1E2A", "\u2660"),
    ("hearts", "H", "#B22A2A", "\u2665"),
    ("clubs", "C", "#1F2B22", "\u2663"),
    ("diamonds", "D", "#C4452D", "\u2666"),
]

RANK_LABELS = {
    "A": "ACE",
    "J": "JACK",
    "Q": "QUEEN",
    "K": "KING",
}

PIP_LAYOUTS: dict[str, list[tuple[float, float]]] = {
    "2": [(0.5, 0.18), (0.5, 0.82)],
    "3": [(0.5, 0.18), (0.5, 0.5), (0.5, 0.82)],
    "4": [(0.32, 0.2), (0.68, 0.2), (0.32, 0.8), (0.68, 0.8)],
    "5": [(0.32, 0.2), (0.68, 0.2), (0.5, 0.5), (0.32, 0.8), (0.68, 0.8)],
    "6": [
        (0.32, 0.2),
        (0.68, 0.2),
        (0.32, 0.5),
        (0.68, 0.5),
        (0.32, 0.8),
        (0.68, 0.8),
    ],
    "7": [
        (0.32, 0.2),
        (0.68, 0.2),
        (0.5, 0.33),
        (0.32, 0.5),
        (0.68, 0.5),
        (0.32, 0.8),
        (0.68, 0.8),
    ],
    "8": [
        (0.32, 0.18),
        (0.68, 0.18),
        (0.32, 0.38),
        (0.68, 0.38),
        (0.32, 0.62),
        (0.68, 0.62),
        (0.32, 0.82),
        (0.68, 0.82),
    ],
    "9": [
        (0.32, 0.16),
        (0.68, 0.16),
        (0.32, 0.34),
        (0.68, 0.34),
        (0.5, 0.5),
        (0.32, 0.66),
        (0.68, 0.66),
        (0.32, 0.84),
        (0.68, 0.84),
    ],
    "10": [
        (0.32, 0.14),
        (0.68, 0.14),
        (0.32, 0.3),
        (0.68, 0.3),
        (0.32, 0.46),
        (0.68, 0.46),
        (0.32, 0.62),
        (0.68, 0.62),
        (0.32, 0.78),
        (0.68, 0.78),
    ],
}


def svg_document(content: str, defs: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_WIDTH}" height="{CARD_HEIGHT}" '
        f'viewBox="0 0 {CARD_WIDTH} {CARD_HEIGHT}">'
        f"{defs}{content}</svg>"
    )


def card_defs(accent: str) -> str:
    return f"""
    <defs>
      <linearGradient id="cardBg" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#fffdf8" />
        <stop offset="100%" stop-color="#f3eee3" />
      </linearGradient>
      <linearGradient id="edgeGlow" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#f8e6af" />
        <stop offset="100%" stop-color="{accent}" />
      </linearGradient>
      <linearGradient id="medallion" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#fff7d0" />
        <stop offset="100%" stop-color="#d8ba66" />
      </linearGradient>
      <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
        <feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="#000000" flood-opacity="0.18" />
      </filter>
    </defs>
    """


def base_card_shell() -> str:
    return f"""
    <rect x="14" y="14" width="{CARD_WIDTH - 28}" height="{CARD_HEIGHT - 28}" rx="{CORNER_RADIUS}" fill="#000000" opacity="0.08" />
    <rect x="8" y="8" width="{CARD_WIDTH - 16}" height="{CARD_HEIGHT - 16}" rx="{CORNER_RADIUS}" fill="url(#cardBg)" stroke="url(#edgeGlow)" stroke-width="4" filter="url(#shadow)" />
    <rect x="24" y="24" width="{CARD_WIDTH - 48}" height="{CARD_HEIGHT - 48}" rx="22" fill="none" stroke="#d3c6a3" stroke-width="2" />
    """


def corner_index(rank: str, suit_symbol: str, color: str, flipped: bool = False) -> str:
    x = 38
    y = 66
    transform = ""
    if flipped:
        transform = f' transform="rotate(180 {CARD_WIDTH / 2} {CARD_HEIGHT / 2})"'
    return f"""
    <g{transform}>
      <text x="{x}" y="{y}" text-anchor="middle" font-size="42" font-weight="700" fill="{color}" font-family="Georgia, 'Times New Roman', serif">{rank}</text>
      <text x="{x}" y="{y + 34}" text-anchor="middle" font-size="30" fill="{color}" font-family="'Segoe UI Symbol', 'DejaVu Sans', serif">{suit_symbol}</text>
    </g>
    """


def decorative_frame(color: str) -> str:
    return f"""
    <path d="M82 88 C118 64, 154 64, 180 98 C206 64, 242 64, 278 88" fill="none" stroke="{color}" stroke-width="3" opacity="0.35" />
    <path d="M82 452 C118 476, 154 476, 180 442 C206 476, 242 476, 278 452" fill="none" stroke="{color}" stroke-width="3" opacity="0.35" />
    <circle cx="180" cy="270" r="118" fill="none" stroke="{color}" stroke-width="2" opacity="0.16" />
    <circle cx="180" cy="270" r="98" fill="none" stroke="{color}" stroke-width="1.5" opacity="0.12" />
    """


def pip_text(x_ratio: float, y_ratio: float, size: int, color: str, suit_symbol: str, rotate: bool) -> str:
    x = CARD_WIDTH * x_ratio
    y = CARD_HEIGHT * y_ratio
    transform = ""
    if rotate:
        transform = f' transform="rotate(180 {x} {y})"'
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" dominant-baseline="middle" '
        f'font-size="{size}" fill="{color}" font-family="\'Segoe UI Symbol\', \'DejaVu Sans\', serif"{transform}>{suit_symbol}</text>'
    )


def number_card_art(rank: str, suit_symbol: str, color: str) -> str:
    if rank == "A":
        return f"""
        <circle cx="180" cy="270" r="104" fill="{color}" opacity="0.08" />
        <text x="180" y="255" text-anchor="middle" font-size="188" fill="{color}" font-family="'Segoe UI Symbol', 'DejaVu Sans', serif">{suit_symbol}</text>
        <text x="180" y="348" text-anchor="middle" font-size="26" letter-spacing="6" fill="{color}" opacity="0.78" font-family="Georgia, serif">SIGNATURE ACE</text>
        """
    layout = PIP_LAYOUTS[rank]
    pieces: list[str] = []
    for x_ratio, y_ratio in layout:
        pieces.append(pip_text(x_ratio, y_ratio, 58, color, suit_symbol, y_ratio > 0.5))
    return "".join(pieces)


def face_card_art(rank: str, suit_symbol: str, color: str) -> str:
    label = RANK_LABELS[rank]
    crown_points = []
    for index in range(8):
        angle = math.radians(-90 + index * 45)
        outer = 108 if index % 2 == 0 else 84
        x = 180 + math.cos(angle) * outer
        y = 270 + math.sin(angle) * outer
        crown_points.append(f"{x:.1f},{y:.1f}")
    crown = " ".join(crown_points)
    return f"""
    <polygon points="{crown}" fill="{color}" opacity="0.08" />
    <circle cx="180" cy="270" r="92" fill="url(#medallion)" stroke="{color}" stroke-width="3" opacity="0.96" />
    <circle cx="180" cy="270" r="72" fill="#fffaf0" stroke="{color}" stroke-width="1.5" opacity="0.85" />
    <text x="180" y="230" text-anchor="middle" font-size="30" font-weight="700" letter-spacing="4" fill="{color}" font-family="Georgia, serif">{label}</text>
    <text x="180" y="305" text-anchor="middle" font-size="132" fill="{color}" font-family="Georgia, serif">{rank}</text>
    <text x="180" y="356" text-anchor="middle" font-size="42" fill="{color}" font-family="'Segoe UI Symbol', 'DejaVu Sans', serif">{suit_symbol} {suit_symbol} {suit_symbol}</text>
    <path d="M108 158 C138 128, 222 128, 252 158" fill="none" stroke="{color}" stroke-width="4" opacity="0.42" />
    <path d="M108 382 C138 412, 222 412, 252 382" fill="none" stroke="{color}" stroke-width="4" opacity="0.42" />
    """


def create_face_svg(rank: str, suit_name: str, suit_symbol: str, suit_color: str) -> str:
    accent = "#d1a94f" if suit_name in {"spades", "clubs"} else "#d8a05b"
    center_art = face_card_art(rank, suit_symbol, suit_color) if rank in {"J", "Q", "K"} else number_card_art(rank, suit_symbol, suit_color)
    content = f"""
    {base_card_shell()}
    {corner_index(rank, suit_symbol, suit_color)}
    {corner_index(rank, suit_symbol, suit_color, flipped=True)}
    {decorative_frame(suit_color)}
    {center_art}
    """
    return svg_document(content, card_defs(accent))


def create_back_svg() -> str:
    defs = """
    <defs>
      <linearGradient id="backBg" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#13233f" />
        <stop offset="100%" stop-color="#6b1320" />
      </linearGradient>
      <linearGradient id="backEdge" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#f6dd9f" />
        <stop offset="100%" stop-color="#f0b65d" />
      </linearGradient>
      <pattern id="diamondGrid" width="36" height="36" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <rect width="36" height="36" fill="none" />
        <path d="M18 0 L36 18 L18 36 L0 18 Z" fill="none" stroke="#f7e7b1" stroke-width="1.4" opacity="0.18" />
      </pattern>
      <filter id="backShadow" x="-20%" y="-20%" width="140%" height="140%">
        <feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="#000000" flood-opacity="0.22" />
      </filter>
    </defs>
    """
    rosettes = []
    for x, y, radius in [(180, 160, 56), (180, 380, 56), (110, 270, 42), (250, 270, 42), (180, 270, 74)]:
        rosettes.append(
            f'<circle cx="{x}" cy="{y}" r="{radius}" fill="none" stroke="#f6dd9f" stroke-width="2" opacity="0.78" />'
        )
        rosettes.append(
            f'<circle cx="{x}" cy="{y}" r="{radius - 12}" fill="none" stroke="#f6dd9f" stroke-width="1" opacity="0.48" />'
        )
    lattice = []
    for offset in range(0, 8):
        inset = 52 + offset * 12
        lattice.append(
            f'<rect x="{inset}" y="{inset * 1.25:.1f}" width="{CARD_WIDTH - 2 * inset}" height="{CARD_HEIGHT - 2 * inset * 1.25:.1f}" rx="18" fill="none" stroke="#f7e7b1" stroke-width="0.9" opacity="{0.16 + offset * 0.05:.2f}" />'
        )
    content = f"""
    <rect x="14" y="14" width="{CARD_WIDTH - 28}" height="{CARD_HEIGHT - 28}" rx="{CORNER_RADIUS}" fill="#000000" opacity="0.10" />
    <rect x="8" y="8" width="{CARD_WIDTH - 16}" height="{CARD_HEIGHT - 16}" rx="{CORNER_RADIUS}" fill="url(#backBg)" stroke="url(#backEdge)" stroke-width="4" filter="url(#backShadow)" />
    <rect x="22" y="22" width="{CARD_WIDTH - 44}" height="{CARD_HEIGHT - 44}" rx="24" fill="url(#diamondGrid)" stroke="#f7e7b1" stroke-width="1.8" opacity="0.94" />
    <rect x="34" y="34" width="{CARD_WIDTH - 68}" height="{CARD_HEIGHT - 68}" rx="18" fill="none" stroke="#f7e7b1" stroke-width="1.4" opacity="0.72" />
    {''.join(lattice)}
    {''.join(rosettes)}
    <path d="M90 120 C128 158, 232 158, 270 120 C232 82, 128 82, 90 120 Z" fill="none" stroke="#f6dd9f" stroke-width="2.2" opacity="0.84" />
    <path d="M90 420 C128 382, 232 382, 270 420 C232 458, 128 458, 90 420 Z" fill="none" stroke="#f6dd9f" stroke-width="2.2" opacity="0.84" />
    <path d="M106 270 C132 228, 228 228, 254 270 C228 312, 132 312, 106 270 Z" fill="none" stroke="#f6dd9f" stroke-width="2.8" opacity="0.9" />
    <text x="180" y="278" text-anchor="middle" font-size="56" fill="#f8e8bb" font-family="'Segoe UI Symbol', 'DejaVu Sans', serif" opacity="0.94">\u2660 \u2665 \u2663 \u2666</text>
    """
    return svg_document(content, defs)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for suit_name, short_name, suit_color, suit_symbol in SUITS:
        for rank in RANKS:
            file_name = f"{rank.lower()}_{suit_name}.svg"
            svg = create_face_svg(rank, suit_name, suit_symbol, suit_color)
            (OUTPUT_DIR / file_name).write_text(svg, encoding="utf-8")
    (OUTPUT_DIR / "card_back.svg").write_text(create_back_svg(), encoding="utf-8")
    print(f"Generated 53 card assets in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
