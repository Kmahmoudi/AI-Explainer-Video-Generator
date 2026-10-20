"""Local, content-aware slide direction, vector graphics and English/Arabic/Farsi drawing.

Meaning determines layout eligibility; a content seed breaks ties for visual variety.
The pure plan includes the reason for each choice and can be inspected without rendering.
"""
from __future__ import annotations

import random
import json
import zlib
from pathlib import Path

import visuals

THEMES = ('light', 'dark', 'vivid')
RTL = ('ar', 'fa')
TAGLINES = {'en': 'Learn · Connect · Understand', 'ar': 'تعلّم · اربط الأفكار · افهم', 'fa': 'یاد بگیر · ارتباط بده · درک کن'}
LAYOUTS = ('cards', 'split', 'steps', 'focus', 'rows', 'illustration', 'comparison', 'metric')
PALETTES = {
    'ocean': {'primary': '#1f3f94', 'secondary': '#0b7f8c', 'accent': '#f2a900', 'tint': '#e8f0fb', 'deep': '#0d2358'},
    'sunset': {'primary': '#c2410c', 'secondary': '#be185d', 'accent': '#f59e0b', 'tint': '#fff0e3', 'deep': '#4a1707'},
    'forest': {'primary': '#166534', 'secondary': '#0f766e', 'accent': '#d9a406', 'tint': '#e6f4ea', 'deep': '#0a3320'},
    'royal': {'primary': '#5b21b6', 'secondary': '#2563eb', 'accent': '#ec4899', 'tint': '#f0eafb', 'deep': '#26104f'},
    'slate': {'primary': '#334155', 'secondary': '#0e7490', 'accent': '#f43f5e', 'tint': '#edf1f6', 'deep': '#0f172a'},
    'desert': {'primary': '#92400e', 'secondary': '#0f766e', 'accent': '#d97706', 'tint': '#f8eedd', 'deep': '#3a1a08'},
}
TRANSITIONS = ('fade', 'slideleft', 'slideright', 'wipeleft', 'wiperight', 'circleopen', 'smoothleft', 'smoothright', 'dissolve', 'radial', 'zoomin', 'horzopen', 'vertopen', 'fadeblack', 'slideup', 'slidedown')
MIRROR = {'slideleft': 'slideright', 'slideright': 'slideleft', 'wipeleft': 'wiperight', 'wiperight': 'wipeleft', 'smoothleft': 'smoothright', 'smoothright': 'smoothleft'}
SURFACE_PREFS = {   # for the "vivid" theme: which surfaces suit a layout
    'cover': ('deep', 'bold'), 'cards': ('paper', 'tint'), 'split': ('paper', 'tint'), 'steps': ('tint', 'paper', 'deep'), 'focus': ('bold', 'deep'), 'rows': ('paper', 'tint', 'deep'), 'recap': ('tint', 'paper'),
    'illustration': ('paper', 'deep', 'tint'), 'comparison': ('paper', 'tint', 'deep'), 'metric': ('deep', 'bold', 'paper'),
}


class SlideError(ValueError):
    """A slide cannot be drawn (a word is wider than the slide, text does not fit)."""


def footer_text(sb: dict) -> str:
    """The line in the footer: the one the author chose, otherwise a short tagline in the language of the lesson."""
    return (sb.get('footer') or '').strip() or TAGLINES.get(sb.get('language'), TAGLINES['en'])


# --------------------------------------------------------------------------------------------------------------------------------- colours

def _rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip('#')
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def mix(a: str, b: str, t: float) -> str:
    """a moved towards b by t (0 = a, 1 = b)."""
    x, y = _rgb(a), _rgb(b)
    return '#%02x%02x%02x' % tuple(round(x[i] + (y[i] - x[i]) * t) for i in range(3))


def luminance(c: str) -> float:
    r, g, b = (v / 255 for v in _rgb(c))
    return .2126 * r + .7152 * g + .0722 * b


def on(color: str, light: str = '#ffffff', dark: str = '#10182f') -> str:
    """Readable text colour on a filled shape."""
    return dark if luminance(color) > .6 else light


def surface_colors(pal: dict, surface: str) -> dict:
    """Every colour a slide needs, for one surface of a palette."""
    p, s, a, tint, deep = pal['primary'], pal['secondary'], pal['accent'], pal['tint'], pal['deep']
    if surface == 'paper':
        c = {'bg': '#fbf8ef', 'ink': '#14203f', 'muted': '#5a6384', 'card': '#ffffff', 'line': '#e4e0d0', 'a': [p, s, a], 'panel': p, 'dark': False}
    elif surface == 'tint':
        c = {'bg': tint, 'ink': deep, 'muted': mix(deep, tint, .4), 'card': '#ffffff', 'line': mix(tint, p, .2), 'a': [p, s, a], 'panel': p, 'dark': False}
    elif surface == 'ink':
        d = mix(deep, '#000000', .35)
        c = {'bg': d, 'ink': '#f4f6fc', 'muted': mix('#f4f6fc', d, .38), 'card': mix(d, '#ffffff', .08), 'line': mix(d, '#ffffff', .16), 'a': [mix(p, '#ffffff', .5), mix(s, '#ffffff', .45), a], 'panel': p, 'dark': True}
    elif surface == 'deep':
        c = {'bg': deep, 'ink': '#f4f6fc', 'muted': mix('#f4f6fc', deep, .38), 'card': mix(deep, '#ffffff', .09), 'line': mix(deep, '#ffffff', .17), 'a': [mix(p, '#ffffff', .5), mix(s, '#ffffff', .45), a], 'panel': p, 'dark': True}
    else:   # bold
        c = {'bg': p, 'ink': '#ffffff', 'muted': mix('#ffffff', p, .25), 'card': mix(p, '#ffffff', .12), 'line': mix(p, '#ffffff', .3), 'a': [a, mix(s, '#ffffff', .55), '#ffffff'], 'panel': deep, 'dark': True}
    c['surface'] = surface
    return c


# ------------------------------------------------------------------------------------------------------------------------------------ plan

def pick_transitions(count: int, rtl: bool, rnd: random.Random) -> list[str]:
    """The transition after every slide but the last: all different from their neighbour, directional ones mirrored for right-to-left languages."""
    pool = list(TRANSITIONS)
    rnd.shuffle(pool)
    transitions, last = [], None
    for _ in range(count - 1):
        t = next((x for x in pool if x != last), pool[0])
        pool.remove(t)
        pool.append(t)
        last = t
        transitions.append(MIRROR.get(t, t) if rtl else t)
    return transitions


def motion_plan(sb: dict, seed: int | None = None) -> list[dict]:
    """Transition, zoom direction and drift for every slide of any template, so the classic single-layout templates move like the designed ones."""
    count = len(sb['slides'])
    rnd = random.Random(seed if seed is not None else zlib.crc32(json.dumps(sb, ensure_ascii=False, sort_keys=True).encode('utf-8')))
    transitions = pick_transitions(count, sb['language'] in RTL, rnd)
    return [{'transition': transitions[i] if i < count - 1 else None, 'zoom_in': i % 2 == 0, 'drift': (i * 37 % 100) / 100} for i in range(count)]


def plan(sb: dict, theme: str = 'vivid', palette: str = 'auto', seed: int | None = None) -> list[dict]:
    """The look of every slide: layout, surface, colours and the transition that follows it. Deterministic for the same script."""
    if theme not in THEMES:
        raise ValueError('Unknown theme.')
    count = len(sb['slides'])
    rnd = random.Random(seed if seed is not None else zlib.crc32(json.dumps(sb, ensure_ascii=False, sort_keys=True).encode('utf-8')))
    context = sb['title']
    content = [visuals.analyze(s, context) for s in sb['slides']]
    topic = visuals.topic_for(sb['title'], [s['title'] for s in sb['slides']],
                             ' '.join(g['text'] for s in sb['slides'] for g in s.get('segments', [])))
    name = palette if palette in PALETTES else (visuals.TOPICS[topic][1] if topic in visuals.TOPICS else rnd.choice(sorted(PALETTES)))
    pal = PALETTES[name]

    # Generic points must not acquire sequence arrows or a comparison just for variety.
    order = ['cards', 'split', 'focus', 'rows', 'illustration']
    rnd.shuffle(order)
    cursor, prev_layout, layouts = 0, None, []
    for i, slide in enumerate(sb['slides']):
        n = len(slide['bullets'])
        if i == 0:
            layouts.append('cover')
        elif i == count - 1:
            layouts.append('recap')
        else:
            semantic = {'compare': 'comparison', 'process': 'steps', 'metric': 'metric', 'definition': 'focus'}.get(content[i]['intent'])
            pick = semantic
            if not pick and content[i]['topic'] != 'abstract' and prev_layout != 'illustration':
                pick = 'illustration'
            for step in range(len(order)):
                if pick:
                    break
                cand = order[(cursor + step) % len(order)]
                if cand == prev_layout or (cand == 'cards' and n < 2):
                    continue
                pick, cursor = cand, cursor + step + 1
                break
            layouts.append(pick or 'rows')
        prev_layout = layouts[-1]

    surfaces, prev, before = [], None, None
    for i, layout in enumerate(layouts):
        if theme == 'light':
            s = {'cover': 'bold', 'focus': 'bold', 'recap': 'tint'}.get(layout) or ('paper' if i % 2 else 'tint')
        elif theme == 'dark':
            s = {'cover': 'deep', 'focus': 'bold', 'recap': 'deep'}.get(layout) or ('ink' if i % 2 else 'deep')
        else:
            prefs = [x for x in SURFACE_PREFS[layout] if x != prev and x != before] or [x for x in SURFACE_PREFS[layout] if x != prev] or list(SURFACE_PREFS[layout])
            s = rnd.choice(prefs)
        surfaces.append(s)
        before, prev = prev, s

    transitions = pick_transitions(count, sb['language'] in RTL, rnd)

    out = []
    for i in range(count):
        colors = surface_colors(pal, surfaces[i])
        k = i % 3
        colors['a'] = colors['a'][k:] + colors['a'][:k]      # the accent colours rotate from slide to slide
        out.append({'layout': layouts[i], 'surface': surfaces[i], 'palette': name, 'colors': colors, 'transition': transitions[i] if i < count - 1 else None, 'zoom_in': i % 2 == 0, 'drift': (i * 37 % 100) / 100,
                    'visual': content[i], 'design_version': 2})
    return out


# ---------------------------------------------------------------------------------------------------------------------------------- drawing

class Canvas:
    """A slide of 1280 x 720 design units (scaled for 1080p). Everything is given as for a left-to-right slide and is mirrored for Arabic."""

    def __init__(self, language: str, resolution: str, colors: dict, font_path):
        from PIL import Image, ImageDraw, features
        self.scale = 1.5 if resolution == '1080' else 1
        self.W, self.H = round(1280 * self.scale), round(720 * self.scale)
        self.c = colors
        self.image = Image.new('RGB', (self.W, self.H), colors['bg'])
        self.draw = ImageDraw.Draw(self.image)
        self.language = language
        self.rtl = language in RTL
        self.raqm = features.check_feature('raqm')
        self.font_path = font_path
        self._fonts: dict = {}

    # geometry
    def px(self, v: float) -> int:
        return round(v * self.scale)

    def box(self, x0, y0, x1, y1) -> tuple[int, int, int, int]:
        if self.rtl:
            x0, x1 = 1280 - x1, 1280 - x0
        return self.px(x0), self.px(y0), self.px(x1), self.px(y1)

    def rect(self, x0, y0, x1, y1, fill=None, radius=0, outline=None, width=1) -> None:
        b = self.box(x0, y0, x1, y1)
        if radius:
            self.draw.rounded_rectangle(b, radius=self.px(radius), fill=fill, outline=outline, width=max(1, self.px(width)) if outline else 0)
        else:
            self.draw.rectangle(b, fill=fill, outline=outline, width=max(1, self.px(width)) if outline else 0)

    def circle(self, cx, cy, r, fill=None, outline=None, width=1) -> None:
        x = 1280 - cx if self.rtl else cx
        self.draw.ellipse((self.px(x - r), self.px(cy - r), self.px(x + r), self.px(cy + r)), fill=fill, outline=outline, width=max(1, self.px(width)) if outline else 0)

    def poly(self, points, fill) -> None:
        self.draw.polygon([(self.px(1280 - x if self.rtl else x), self.px(y)) for x, y in points], fill=fill)

    def line(self, points, fill, width) -> None:
        pts = [(self.px(1280 - x if self.rtl else x), self.px(y)) for x, y in points]
        self.draw.line(pts, fill=fill, width=max(1, self.px(width)), joint='curve')

    def check(self, cx, cy, size, color, width) -> None:
        """A tick mark centred on (cx, cy); the place is mirrored for Arabic, the tick itself is not (a mirrored tick looks wrong)."""
        x = 1280 - cx if self.rtl else cx
        pts = [(x - .45 * size, cy + .05 * size), (x - .12 * size, cy + .38 * size), (x + .5 * size, cy - .32 * size)]
        self.draw.line([(self.px(a), self.px(b)) for a, b in pts], fill=color, width=max(1, self.px(width)), joint='curve')

    # text
    def font(self, size, bold=False):
        from PIL import ImageFont
        key = (round(size * self.scale), bold)
        if key not in self._fonts:
            self._fonts[key] = ImageFont.truetype(self.font_path(bold), key[0])
        return self._fonts[key]

    def visual(self, text: str) -> str:
        if self.rtl and not self.raqm:
            import arabic_reshaper
            from bidi.algorithm import get_display
            return get_display(arabic_reshaper.reshape(text))
        return text

    def measure(self, text: str, f) -> float:
        return self.draw.textlength(self.visual(text), font=f, **({'direction': 'rtl'} if self.rtl and self.raqm else {}))

    def wrap(self, text: str, f, max_width: float, index: int = 0) -> list[str]:
        lines, current = [], ''
        for word in text.split():
            candidate = (current + ' ' + word).strip()
            if current and self.measure(candidate, f) > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
            if self.measure(current, f) > max_width:
                raise SlideError(f'Slide {index}: a word is too wide for the slide.')
        if current:
            lines.append(current)
        return lines

    def put(self, text: str, x: float, y: float, f, color: str, anchor: str = 'start') -> None:
        """One line. anchor: start (left edge, right edge in Arabic), end, center - x is the LTR coordinate of that edge."""
        if anchor == 'center':
            ax, a = self.px(1280 - x if self.rtl else x), 'mt'
        else:
            left = (anchor == 'start')
            edge_is_left = left != self.rtl
            ax = self.px(1280 - x if self.rtl else x)
            a = ('l' if edge_is_left else 'r') + 't'
        self.draw.text((ax, self.px(y)), self.visual(text), font=f, fill=color, anchor=a, **({'direction': 'rtl', 'language': self.language} if self.rtl and self.raqm else {}))

    def block(self, text: str, x: float, y: float, w: float, h: float, size: int, color: str, bold=False, min_size=18, anchor='start', index=0, spacing=1.42, valign='top') -> float:
        """Text wrapped in a box and shrunk until it fits. Returns the y below it. x is the LTR left edge of the box."""
        f, lines = None, []
        for s in range(int(size), int(min_size) - 1, -1):
            f = self.font(s, bold)
            try:
                lines = self.wrap(text, f, w * self.scale, index)
            except SlideError:
                if s == int(min_size):
                    raise
                continue
            if len(lines) * s * spacing <= h:
                break
        else:
            raise SlideError(f'Slide {index}: the text does not fit.')
        used = int(s)
        if valign == 'middle':
            y += max(0.0, (h - len(lines) * used * spacing) / 2)
        for line in lines:
            ex = x if anchor == 'start' else (x + w if anchor == 'end' else x + w / 2)
            self.put(line, ex, y, f, color, anchor)
            y += used * spacing
        return y

    def text_width(self, text: str, size: int, bold=False) -> float:
        return self.measure(text, self.font(size, bold)) / self.scale

    def save(self, path) -> None:
        self.image.save(path)


def _decor(cv: Canvas, st: dict, idx: int) -> None:
    """Soft shapes in the corners, faint enough not to disturb the text."""
    c = st['colors']; a = c['a']
    soft = lambda col, t=.1: mix(c['bg'], col, t if not c['dark'] else t + .06)
    k = idx % 4
    if k == 0:
        cv.circle(1230, 690, 150, fill=soft(a[0])); cv.circle(1230, 690, 95, fill=soft(a[1], .13))
    elif k == 1:
        cv.circle(1260, 40, 130, outline=soft(a[1], .22), width=14); cv.circle(80, 720, 110, fill=soft(a[2], .12))
    elif k == 2:
        cv.poly([(1280, 420), (1280, 720), (980, 720)], soft(a[0], .12)); cv.circle(1120, 600, 40, fill=soft(a[2], .2))
    else:
        cv.circle(1200, 700, 200, outline=soft(a[0], .16), width=18); cv.circle(60, 40, 70, fill=soft(a[1], .1))
    # Locally generated topic artwork doubles as a quiet background watermark.
    visuals.paint(cv, visuals.scene(st.get('visual', {}).get('subject', 'abstract'), [soft(col, .07) for col in a]), 940, 85, 310)


def _furniture(cv: Canvas, sb: dict, st: dict, idx: int, count: int, left: float = 54) -> None:
    c = st['colors']
    cv.rect(left, 47, 1226, 52, c['line'])
    cv.rect(left, 47, left + (1226 - left) * idx / count, 52, c['a'][0])
    cv.block(footer_text(sb), left + 8, 657, 900, 35, 15, c['muted'], min_size=11, index=idx)
    cv.put(f'{idx} / {count}', 1218, 658, cv.font(15), c['muted'], 'end')


def _number_chip(cv: Canvas, st: dict, idx: int, x: float = 62, y: float = 76) -> None:
    c = st['colors']; w = 64
    cv.rect(x, y, x + w, y + 34, fill=c['a'][0], radius=17)
    cv.put(f'{idx:02}', x + w / 2, y + 5, cv.font(20, True), on(c['a'][0]), 'center')


def _title(cv: Canvas, st: dict, slide: dict, idx: int, y: float = 124, size: int = 50, w: float = 1100, h: float = 150, x: float = 62, anchor: str = 'start') -> float:
    return cv.block(slide['title'], x, y, w, h, size, st['colors']['ink'], True, 26, anchor, idx)


def layout_cover(cv, sb, slide, st, idx, count):
    c = st['colors']; a = c['a']
    # big rings and a band on the far side
    cv.circle(1040, 330, 330, outline=mix(c['bg'], a[0], .5 if not c['dark'] else .35), width=3)
    cv.circle(1040, 330, 240, outline=mix(c['bg'], a[1], .45), width=3)
    cv.circle(1040, 330, 205, fill=mix(c['bg'], '#ffffff', .07))
    _art(cv, st, 840, 130, 400)
    cv.circle(1180, 560, 28, fill=a[1]); cv.circle(870, 120, 16, fill=a[2])
    cv.poly([(0, 720), (0, 600), (360, 720)], mix(c['bg'], a[0], .35))
    cv.put(footer_text(sb).upper(), 80, 84, cv.font(20, True), a[0], 'start')
    cv.block(sb['title'], 80, 155, 700, 235, 60, c['ink'], True, 22, 'start', idx)
    cv.rect(80, 405, 220, 413, fill=a[0], radius=4)
    cv.block(slide['title'], 80, 435, 700, 70 if slide['bullets'] else 180, 29, c['ink'], False, 20, 'start', idx)
    for j, b in enumerate(slide['bullets']):
        y = 520 + j * 43
        cv.circle(87, y + 14, 4, fill=a[j % 3])
        cv.block(b, 106, y, 670, 42, 22, c['ink'], False, 14, 'start', idx, spacing=1.25)


def layout_cards(cv, sb, slide, st, idx, count):
    c = st['colors']; a = c['a']; n = len(slide['bullets'])
    _furniture(cv, sb, st, idx, count); _number_chip(cv, st, idx)
    _title(cv, st, slide, idx)
    w = (1156 - (n - 1) * 20) / n
    for j, b in enumerate(slide['bullets']):
        x = 62 + j * (w + 20); col = a[j % 3]
        cv.rect(x, 330, x + w, 612, fill=c['card'], radius=20, outline=c['line'])
        cv.rect(x + 24, 330, x + 24 + 70, 338, fill=col, radius=4)
        cv.circle(x + 24 + 24, 390, 24, fill=col)
        cv.put(str(j + 1), x + 24 + 24, 372, cv.font(26, True), on(col), 'center')
        cv.block(b, x + 24, 440, w - 48, 150, 30, c['ink'], False, 17, 'start', idx)


def layout_rows(cv, sb, slide, st, idx, count):
    c = st['colors']; a = c['a']; n = len(slide['bullets'])
    _furniture(cv, sb, st, idx, count); _number_chip(cv, st, idx)
    _title(cv, st, slide, idx, h=130)
    gap = 18; h = min(110, (330 - (n - 1) * gap) / n); y = 300
    for j, b in enumerate(slide['bullets']):
        col = a[j % 3]
        cv.rect(62, y, 1218, y + h, fill=c['card'], radius=18, outline=c['line'])
        cv.rect(62, y, 62 + 96, y + h, fill=col, radius=18); cv.rect(62 + 60, y, 62 + 96, y + h, fill=col)
        cv.put(str(j + 1), 62 + 48, y + h / 2 - 25, cv.font(40, True), on(col), 'center')
        cv.block(b, 190, y + 4, 1000, h - 8, 30, c['ink'], False, 17, 'start', idx, valign='middle')
        y += h + gap


def layout_split(cv, sb, slide, st, idx, count):
    c = st['colors']; a = c['a']; panel = c['panel']
    cv.rect(0, 0, 470, 720, fill=panel)
    cv.circle(60, 690, 190, fill=mix(panel, '#ffffff', .08)); cv.circle(440, 620, 90, outline=mix(panel, '#ffffff', .16), width=10)
    cv.put(f'{idx:02}', 56, 56, cv.font(120, True), mix(panel, '#ffffff', .2), 'start')
    y = cv.block(slide['title'], 56, 250, 372, 280, 46, on(panel), True, 24, 'start', idx)
    cv.rect(56, y + 14, 146, y + 22, fill=a[1] if on(panel) == '#ffffff' else a[0], radius=4)
    cv.rect(520, 47, 1226, 52, c['line']); cv.rect(520, 47, 520 + 706 * idx / count, 52, a[0])
    cv.block(footer_text(sb), 528, 657, 480, 35, 15, c['muted'], min_size=11, index=idx)
    cv.put(f'{idx} / {count}', 1218, 658, cv.font(15), c['muted'], 'end')
    n = len(slide['bullets']); gap = 26; h = min(150, (500 - (n - 1) * gap) / n); y = 110 + (500 - (n * h + (n - 1) * gap)) / 2
    for j, b in enumerate(slide['bullets']):
        col = a[j % 3]
        cv.rect(520, y, 530, y + h, fill=col, radius=5)
        cv.block(b, 560, y, 640, h, 34, c['ink'], False, 18, 'start', idx, valign='middle')
        y += h + gap


def layout_steps(cv, sb, slide, st, idx, count):
    c = st['colors']; a = c['a']; n = len(slide['bullets'])
    _furniture(cv, sb, st, idx, count); _number_chip(cv, st, idx)
    _title(cv, st, slide, idx, size=46, h=130)
    xs = [640] if n == 1 else [210 + 860 * k / (n - 1) for k in range(n)]
    cv.rect(xs[0], 357, xs[-1] if n > 1 else 640, 363, fill=c['line'], radius=3)
    for k, b in enumerate(slide['bullets']):
        col = a[k % 3]; x = xs[k]
        cv.circle(x, 360, 40, fill=c['bg'], outline=col, width=6)
        cv.circle(x, 360, 30, fill=col)
        cv.put(str(k + 1), x, 340, cv.font(32, True), on(col), 'center')
        w = 320 if n < 4 else 860 / (n - 1) - 24          # four steps sit closer together: narrower boxes so the texts do not touch
        cv.block(b, x - w / 2, 430, w, 190, 28, c['ink'], False, 17, 'center', idx)


def layout_focus(cv, sb, slide, st, idx, count):
    c = st['colors']; a = c['a']
    _furniture(cv, sb, st, idx, count)
    cv.put('“', 1000, 40, cv.font(320, True), mix(c['bg'], a[0], .2 if not c['dark'] else .28), 'start')
    cv.rect(96, 150, 96 + 8, 190, fill=a[0], radius=4)
    cv.block(slide['title'], 120, 156, 800, 40, 26, a[0], True, 16, 'start', idx)
    first = slide['bullets'][0]
    cv.block(first, 96, 220, 1000, 270, 62, c['ink'], True, 30, 'start', idx, spacing=1.3, valign='middle')
    y = 530
    for b in slide['bullets'][1:3]:
        cv.circle(106, y + 17, 7, fill=a[1])
        cv.block(b, 130, y, 1000, 40, 26, c['muted'] if not c['dark'] else c['ink'], False, 15, 'start', idx)
        y += 44


def layout_recap(cv, sb, slide, st, idx, count):
    c = st['colors']; a = c['a']; n = len(slide['bullets'])
    _furniture(cv, sb, st, idx, count)
    cv.circle(250, 400, 170, outline=a[0], width=18); cv.circle(250, 400, 120, fill=mix(c['bg'], a[1], .18 if not c['dark'] else .3))
    cv.check(250, 395, 150, a[2], 22)
    cv.block(slide['title'], 520, 110, 700, 150, 46, c['ink'], True, 26, 'start', idx)
    y = 290; gap = 20; h = min(96, (330 - (n - 1) * gap) / n)
    for j, b in enumerate(slide['bullets']):
        col = a[j % 3]
        cv.rect(520, y, 1218, y + h, fill=c['card'], radius=18, outline=c['line'])
        cv.circle(520 + 44, y + h / 2, 22, fill=col)
        cv.check(520 + 44, y + h / 2, 22, on(col), 5)
        cv.block(b, 590, y + 4, 600, h - 8, 28, c['ink'], False, 16, 'start', idx, valign='middle')
        y += h + gap


def _art(cv, st, x, y, size):
    visuals.paint(cv, visuals.scene(st.get('visual', {}).get('subject', 'abstract'), st['colors']['a']), x, y, size)


def layout_illustration(cv, sb, slide, st, idx, count):
    c = st['colors']
    _furniture(cv, sb, st, idx, count); _number_chip(cv, st, idx)
    _title(cv, st, slide, idx, size=44, h=130)
    cv.rect(62, 290, 530, 625, fill=c['card'], radius=28, outline=c['line'])
    _art(cv, st, 125, 285, 340)
    n = len(slide['bullets']); h = min(150, (330 - 18 * (n - 1)) / n)
    for j, b in enumerate(slide['bullets']):
        y = 290 + j * (h + 18)
        cv.rect(575, y + 4, 581, y + h - 4, fill=c['a'][j % 3], radius=3)
        cv.block(b, 608, y, 600, h, 30, c['ink'], min_size=18, index=idx, valign='middle')


def layout_comparison(cv, sb, slide, st, idx, count):
    if len(slide['bullets']) != 2:
        return layout_cards(cv, sb, slide, st, idx, count)
    c = st['colors']
    _furniture(cv, sb, st, idx, count); _number_chip(cv, st, idx)
    _title(cv, st, slide, idx, size=46, h=130)
    for j, b in enumerate(slide['bullets']):
        x = 62 + j * 600; col = c['a'][j]
        cv.rect(x, 300, x + 556, 620, fill=c['card'], radius=24, outline=c['line'])
        cv.rect(x + 26, 325, x + 110, 333, fill=col, radius=4)
        cv.block(b, x + 30, 370, 496, 214, 38, c['ink'], min_size=20, index=idx, valign='middle')
    cv.circle(640, 460, 26, fill=c['bg'], outline=c['line'], width=2)
    cv.circle(633, 460, 5, fill=c['a'][0])
    cv.circle(647, 460, 5, fill=c['a'][1])


def layout_metric(cv, sb, slide, st, idx, count):
    metric = st.get('visual', {}).get('metric')
    if not metric:
        return layout_illustration(cv, sb, slide, st, idx, count)
    c = st['colors']
    _furniture(cv, sb, st, idx, count); _number_chip(cv, st, idx)
    _title(cv, st, slide, idx, size=46, h=130)
    cv.rect(62, 300, 530, 620, fill=c['card'], radius=28, outline=c['line'])
    cv.block(metric['value'], 90, 345, 412, 220, 100, c['ink'], bold=True, min_size=36, anchor='center', index=idx, valign='middle')
    cv.rect(220, 580, 372, 586, fill=c['a'][0], radius=3)
    n = len(slide['bullets']); h = (320 - 16 * (n - 1)) / n
    for j, b in enumerate(slide['bullets']):
        cv.block(b, 580, 300 + j * (h + 16), 628, h, 32, c['ink'], bold=b == metric['text'], min_size=18, index=idx, valign='middle')


LAYOUT_FUNCS = {'cover': layout_cover, 'cards': layout_cards, 'rows': layout_rows, 'split': layout_split, 'steps': layout_steps, 'focus': layout_focus, 'recap': layout_recap,
                'illustration': layout_illustration, 'comparison': layout_comparison, 'metric': layout_metric}


def cover_image(title: str, subtitle: str, language: str, out_png, resolution: str, font_path, palette: str = 'auto', footer: str = '') -> dict:
    """A picture for a course (or any title): the cover layout of the videos with the title and a line below it. Returns the style that was used."""
    slide = {'title': subtitle[:150], 'bullets': [], 'segments': []}
    sb = {'title': title, 'language': language, 'footer': footer, 'slides': [slide, slide, slide]}
    style = plan(sb, 'vivid', palette)[0]
    draw_slide(sb, slide, 1, 3, out_png, style, resolution, font_path, export_art=False)
    return style


def draw_slide(sb: dict, slide: dict, index: int, count: int, path: Path, style: dict, resolution: str, font_path, export_art: bool = True) -> None:
    """Draws one planned slide (style is an item of plan())."""
    cv = Canvas(sb['language'], resolution, style['colors'], font_path)
    if style['layout'] != 'cover':
        _decor(cv, style, index)
    LAYOUT_FUNCS[style['layout']](cv, sb, slide, style, index, count)
    cv.save(path)
    # The graphic is exported from the same primitives used above; no external SVG is executed.
    if export_art:
        topic = style.get('visual', {}).get('subject', 'abstract')
        Path(path).with_suffix('.svg').write_text(visuals.svg(visuals.scene(topic, style['colors']['a']), slide['title']), encoding='utf-8')
