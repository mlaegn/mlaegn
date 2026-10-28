"""Draw the README's header and footer waves as SVG, from wave physics.

Each line is a second-order Stokes wave of one period in water of one depth. Its
wavelength comes from the linear dispersion relation w^2 = g k tanh(k h), and it moves
at its phase speed in real time, so the long swell at the front overtakes the short
chop at the back exactly as it would at sea. A Stokes wave keeps its shape as it
travels, so each line is one path translated by one wavelength per period, and the
loop is seamless.

Usage:  python scripts/header.py
"""

import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
G = 9.81
DEPTH = 20.0    # m
PX_PER_M = 2.5  # horizontal scale: 1200 px is 480 m of sea
WIDTH = 1200

THEMES = {
    # name: (background or None, line colour). The README uses "band"; a theme without
    # a background suits a <picture> that switches with GitHub's light and dark modes.
    "band": (("#0E2F56", "#163F6E"), "#6FB8E6"),
}


def wavenumber(period, depth=DEPTH):
    """k from w^2 = g k tanh(k h), by Newton's method from the deep-water guess."""
    w = 2 * math.pi / period
    k = w * w / G
    for _ in range(50):
        f = G * k * math.tanh(k * depth) - w * w
        df = G * math.tanh(k * depth) + G * k * depth / math.cosh(k * depth) ** 2
        k -= f / df
    return k


def stokes(theta, a, k, depth=DEPTH):
    """Second-order Stokes surface elevation (m) at phase theta."""
    kh = k * depth
    b = k * a * a / 4 * math.cosh(kh) * (2 + math.cosh(2 * kh)) / math.sinh(kh) ** 3
    return a * math.cos(theta) + b * math.cos(2 * theta)


def line(period, height_m, y0, gain, stroke, opacity, colour, delay):
    k = wavenumber(period)
    wavelength = 2 * math.pi / k * PX_PER_M     # px
    a = height_m / 2
    step = 4
    pts = []
    x = -wavelength
    while x <= WIDTH + step:
        theta = k * (x / PX_PER_M)
        pts.append(f"{x:.0f},{y0 - gain * stokes(theta, a, k):.1f}")
        x += step
    d = "M" + " L".join(pts)
    return (
        f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="{stroke}" '
        f'stroke-opacity="{opacity}" stroke-linecap="round">'
        f'<animateTransform attributeName="transform" type="translate" '
        f'from="0 0" to="{wavelength:.2f} 0" dur="{period}s" begin="-{delay}s" '
        f'repeatCount="indefinite"/></path>'
    )


# (period s, wave height m, depth into the picture 0 = back .. 1 = front)
SEA = [(6.0, 0.8, 0.00), (8.0, 1.1, 0.25), (10.0, 1.4, 0.50),
       (12.0, 1.7, 0.75), (14.0, 2.0, 1.00)]


def svg(height, sea, theme):
    bg, colour = THEMES[theme]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
           f'viewBox="0 0 {WIDTH} {height}">']
    if bg:
        out.append('<defs><linearGradient id="bg" x1="0" x2="1">'
                   f'<stop offset="0" stop-color="{bg[0]}"/><stop offset="1" stop-color="{bg[1]}"/>'
                   '</linearGradient></defs>'
                   f'<rect width="{WIDTH}" height="{height}" rx="10" fill="url(#bg)"/>')
    top, bottom = height * 0.25, height * 0.80
    for i, (period, h, z) in enumerate(sea):
        y0 = top + (bottom - top) * z          # nearer lines sit lower
        gain = 2 + 6 * z                       # and look taller
        out.append(line(period, h, y0, gain, 0.6 + 1.0 * z, 0.25 + 0.6 * z, colour, i * 1.7))
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main():
    img = ROOT / "img"
    img.mkdir(exist_ok=True)
    for theme in THEMES:
        (img / f"header-{theme}.svg").write_text(svg(160, SEA, theme))
        (img / f"footer-{theme}.svg").write_text(svg(60, SEA[3:], theme))
    for period, _, _ in SEA:
        k = wavenumber(period)
        print(f"T={period:>4}s  L={2 * math.pi / k:6.1f} m  c={2 * math.pi / k / period:5.2f} m/s")


if __name__ == "__main__":
    main()
