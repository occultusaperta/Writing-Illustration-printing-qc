from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class LABColor:
    l: float
    a: float
    b: float

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.l, self.a, self.b)


def clamp(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))


def chroma(lab: LABColor) -> float:
    return math.sqrt(lab.a * lab.a + lab.b * lab.b)


def hue_angle(lab: LABColor) -> float:
    return (math.degrees(math.atan2(lab.b, lab.a)) + 360.0) % 360.0


def temperature_proxy(lab: LABColor) -> float:
    return clamp((lab.b - lab.a * 0.1) / 128.0, -1.0, 1.0)


def _srgb_to_linear(x: float) -> float:
    return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(x: float) -> float:
    return 12.92 * x if x <= 0.0031308 else (1.055 * (x ** (1 / 2.4)) - 0.055)


def srgb_to_lab(rgb: Tuple[int, int, int]) -> LABColor:
    r, g, b = [_srgb_to_linear(clamp(c / 255.0, 0.0, 1.0)) for c in rgb]
    x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041
    xr, yr, zr = x / 0.95047, y / 1.00000, z / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t + 16 / 116)

    fx, fy, fz = f(xr), f(yr), f(zr)
    return LABColor(116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def lab_to_srgb(lab: LABColor) -> tuple[int, int, int]:
    fy = (lab.l + 16.0) / 116.0
    fx = lab.a / 500.0 + fy
    fz = fy - lab.b / 200.0

    def invf(t: float) -> float:
        c3 = t**3
        return c3 if c3 > 0.008856 else (t - 16 / 116) / 7.787

    xr, yr, zr = invf(fx), invf(fy), invf(fz)
    x, y, z = xr * 0.95047, yr * 1.0, zr * 1.08883
    rl = x * 3.2404542 + y * -1.5371385 + z * -0.4985314
    gl = x * -0.9692660 + y * 1.8760108 + z * 0.0415560
    bl = x * 0.0556434 + y * -0.2040259 + z * 1.0572252
    return tuple(int(round(clamp(_linear_to_srgb(clamp(c, 0.0, 1.0)), 0.0, 1.0) * 255)) for c in (rl, gl, bl))


def lab_from_lch(lightness: float, c: float, h_deg: float) -> LABColor:
    hr = math.radians(h_deg)
    return LABColor(lightness, c * math.cos(hr), c * math.sin(hr))


def hue_to_lab(hue: float, lightness: float, c: float) -> LABColor:
    return lab_from_lch(lightness, c, hue % 360.0)


def cie_de2000(l1: LABColor, l2: LABColor) -> float:
    l_bar = (l1.l + l2.l) / 2
    c1, c2 = chroma(l1), chroma(l2)
    c_bar = (c1 + c2) / 2
    g = 0.5 * (1 - math.sqrt((c_bar**7) / (c_bar**7 + 25**7 if c_bar else 25**7)))
    a1p, a2p = (1 + g) * l1.a, (1 + g) * l2.a
    c1p, c2p = math.sqrt(a1p**2 + l1.b**2), math.sqrt(a2p**2 + l2.b**2)

    def hp(ap: float, b: float) -> float:
        if ap == 0 and b == 0:
            return 0
        return (math.degrees(math.atan2(b, ap)) + 360) % 360

    h1p, h2p = hp(a1p, l1.b), hp(a2p, l2.b)
    dl = l2.l - l1.l
    dc = c2p - c1p
    dh = 0.0
    if c1p * c2p != 0:
        if abs(h2p - h1p) <= 180:
            dh = h2p - h1p
        elif h2p <= h1p:
            dh = h2p - h1p + 360
        else:
            dh = h2p - h1p - 360
    dhp = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dh / 2))

    lp_bar = (l1.l + l2.l) / 2
    cp_bar = (c1p + c2p) / 2
    hp_bar = h1p + h2p
    if c1p * c2p == 0:
        hp_bar = h1p + h2p
    elif abs(h1p - h2p) > 180:
        hp_bar = (h1p + h2p + 360) / 2 if (h1p + h2p) < 360 else (h1p + h2p - 360) / 2
    else:
        hp_bar = (h1p + h2p) / 2

    t = 1 - 0.17 * math.cos(math.radians(hp_bar - 30)) + 0.24 * math.cos(math.radians(2 * hp_bar)) + 0.32 * math.cos(math.radians(3 * hp_bar + 6)) - 0.20 * math.cos(math.radians(4 * hp_bar - 63))
    sl = 1 + ((0.015 * ((lp_bar - 50) ** 2)) / math.sqrt(20 + ((lp_bar - 50) ** 2)))
    sc = 1 + 0.045 * cp_bar
    sh = 1 + 0.015 * cp_bar * t
    delta_ro = 30 * math.exp(-(((hp_bar - 275) / 25) ** 2))
    rc = 2 * math.sqrt((cp_bar**7) / (cp_bar**7 + 25**7 if cp_bar else 25**7))
    rt = -math.sin(math.radians(2 * delta_ro)) * rc
    return math.sqrt((dl / sl) ** 2 + (dc / sc) ** 2 + (dhp / sh) ** 2 + rt * (dc / sc) * (dhp / sh))
