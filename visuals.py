"""Offline visual direction and vector artwork. No models, network calls or SVG parser.

Only known geometry is generated: the same scene is painted with Pillow and exported
as an editable SVG. Narration influences design, never supplies invented chart data.
"""
from __future__ import annotations

import math
import re
import unicodedata
from html import escape


# Keywords in English, Arabic and Persian (Persian letters are folded onto the Arabic ones by normalize()).
TOPICS = {
    'solar': ('sun solar sunlight photovoltaic panel panels electricity battery renewable شمس شمسي شمسية الشمس الشمسية ألواح الألواح كهرباء الكهرباء بطارية خورشيد خورشيدي پنل پنلها برق باتري تجديدپذير', 'sunset'),
    'water': ('water ocean marine sea desalination irrigation rainfall مياه المياه ماء الماء بحر البحر تحلية ري أمطار آب اقیانوس دریا شیرینسازی آبیاری باران', 'ocean'),
    'biology': ('dna gene genes genetic genetics genome cell cells molecule molecular biology جين جينات الجينات وراثة وراثي خلية خلايا الخلايا جزيء أحياء ژن ژنها ژنتیک سلول سلولها مولکول زیستشناسی', 'forest'),
    'computing': ('computer computing software algorithm algorithms neural network networks machine data database digital ai حاسوب برمجة خوارزمية خوارزميات بيانات البيانات شبكة شبكات رقمي اصطناعي رایانه کامپیوتر نرمافزار الگوریتم داده دادهها شبکه دیجیتال', 'royal'),
    'health': ('health heart cardiac patient patients clinical medicine medical blood disease صحة الصحة قلب القلب مريض مرضى طبي طب دم الدم مرض سلامت قلب بیمار بیماران پزشکی خون بیماری', 'ocean'),
    'environment': ('plant plants tree trees forest climate environment ecosystem biodiversity carbon نبات نباتات شجرة أشجار غابة مناخ المناخ بيئة البيئة تنوع كربون گیاه گیاهان درخت درختان جنگل اقلیم محیطزیست بومسازگان کربن', 'forest'),
    'space': ('space planet planets orbit orbital astronomy satellite satellites فضاء الفضاء كوكب كواكب مدار فلك قمر أقمار فضا سیاره سیارهها مدار نجوم ماهواره', 'slate'),
    'research': ('research experiment experiments laboratory microscope evidence hypothesis بحث البحث تجربة تجارب مختبر المجهر دليل فرضية پژوهش تحقیق آزمایش آزمایشگاه میکروسکوپ شواهد فرضیه', 'desert'),
}

SUBJECTS = {
    'battery': ('solar', 'battery batteries بطارية بطاريات باتري باتریها'),
    'database': ('computing', 'database databases dataset datasets قاعدة قواعد پایگاه'),
    'cell': ('biology', 'cell cells cellular خلية خلايا خلوي سلول سلولها سلولی'),
}


def normalize(text: str) -> str:
    text = ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))
    # Persian yeh/kaf and Arabic alef maqsura are folded onto the Arabic letters so one keyword list serves Arabic and Farsi.
    return text.replace('ـ', '').replace('ى', 'ي').replace('ی', 'ي').replace('ک', 'ك')


def tokens(text: str) -> set[str]:
    words = set(re.findall(r'[^\W\d_]+', normalize(text), re.UNICODE))
    # Arabic conjunctions and the definite article are attached to the word.
    for word in tuple(words):
        if re.fullmatch(r'[\u0621-\u064a]+', word):
            if word.startswith('و') and len(word) > 3:
                words.add(word[1:])
            for form in (word, word[1:] if word.startswith('و') else word):
                if form.startswith('ال') and len(form) > 4:
                    words.add(form[2:])
    return words


def topic_for(title: str, bullets: list[str], narration: str, context: str = '') -> str:
    fields = [(tokens(title), 4), (tokens(' '.join(bullets)), 3), (tokens(narration), 2)]
    scores = {name: sum(len(words & tokens(spec[0])) * weight for words, weight in fields) for name, spec in TOPICS.items()}
    best = max(scores, key=scores.get)
    if scores[best]:
        return best
    background = tokens(context)
    scores = {name: len(background & tokens(spec[0])) for name, spec in TOPICS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else 'abstract'


def has_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    text = normalize(text)
    return any(re.search(r'(?<!\w)' + re.escape(normalize(p)) + r'(?!\w)', text) for p in phrases)


def analyze(slide: dict, context: str = '') -> dict:
    title, bullets = slide['title'], slide['bullets']
    narration = ' '.join(s['text'] for s in slide.get('segments', []))
    text = ' '.join([title, *bullets, narration])
    topic = topic_for(title, bullets, narration, context)
    fields = [(tokens(title), 4), (tokens(' '.join(bullets)), 3), (tokens(narration), 1)]
    scores = {name: sum(len(words & tokens(terms)) * weight for words, weight in fields) if parent == topic else 0
              for name, (parent, terms) in SUBJECTS.items()}
    subject = max(scores, key=scores.get)
    subject = subject if scores[subject] else topic
    intent, reason = 'explain', 'Illustrate the topic with the original slide points.'
    metric = None
    # Percentages are callouts, not charts: retain qualifiers, ranges and their full source sentence.
    for bullet in bullets:
        match = re.search(r'(?<![\w.,٫])(?:[<>≤≥~≈]\s*)?[\d]+(?:[.,٫]\d+)?(?:\s*[–—-]\s*\d+(?:[.,٫]\d+)?)?\s*[%٪]', bullet)
        if match:
            metric = {'value': match.group(0), 'text': bullet}
            break
    if len(bullets) == 2 and has_phrase(text, ('versus', 'vs', 'compared with', 'compared to', 'comparison', 'unlike', 'whereas', 'مقارنة', 'المقارنة', 'مقابل', 'بينما', 'بخلاف', 'مقایسه', 'در برابر', 'در مقابل', 'برخلاف', 'در حالی که')):
        intent, reason = 'compare', 'Two source points and explicit comparison language.'
    elif len(bullets) > 1 and (has_phrase(title, ('steps', 'stages', 'workflow', 'procedure', 'خطوات', 'الخطوات', 'مراحل', 'المراحل', 'گام', 'گامها', 'مرحله')) or
            (has_phrase(text, ('first', 'أولا', 'نخست', 'ابتدا')) and has_phrase(text, ('next', 'then', 'finally', 'ثانيا', 'ثم', 'أخيرا', 'سپس', 'در پایان', 'سرانجام')))):
        intent, reason = 'process', 'Explicit sequence language; preserve the source point order.'
    elif metric:
        intent, reason = 'metric', 'Emphasize a percentage already present in a slide point, with its context.'
    elif has_phrase(title, ('definition', 'means', 'what is', 'تعريف', 'ما هو', 'ما هي', 'تعریف', 'چیست')):
        intent, reason = 'definition', 'A definition benefits from a prominent statement.'
    return {'topic': topic, 'subject': subject, 'intent': intent, 'metric': metric, 'reason': reason}


def scene(topic: str, colors: list[str]) -> list[dict]:
    """A 400 x 400 symbolic illustration made exclusively of bounded primitives."""
    a, b, c = colors
    shapes = []

    def circle(x, y, r, fill=None, stroke=None, width=4):
        shapes.append(dict(kind='circle', cx=x, cy=y, r=r, fill=fill, stroke=stroke, width=width))

    def line(points, color=a, width=5):
        shapes.append(dict(kind='line', points=points, stroke=color, width=width))

    def rect(x, y, w, h, fill=None, stroke=None, radius=12):
        shapes.append(dict(kind='rect', x=x, y=y, w=w, h=h, fill=fill, stroke=stroke, width=4, radius=radius))

    if topic == 'battery':
        rect(80, 115, 240, 195, None, a, 22)
        rect(155, 85, 90, 25, b, radius=6)
        # Equal cells are decorative battery geometry, not a charge measurement.
        for x in (110, 175, 240):
            rect(x, 150, 40, 125, None, b, 6)
        line([(200, 165), (175, 210), (215, 210), (190, 255)], c, 9)
    elif topic == 'database':
        for y in (115, 195, 275):
            rect(80, y, 240, 65, None, a, 18)
            circle(112, y + 32, 8, c)
            line([(145, y + 32), (285, y + 32)], b, 5)
        line([(200, 65), (200, 100)], c, 5)
    elif topic == 'cell':
        circle(200, 200, 145, None, a, 8)
        circle(200, 200, 125, None, b, 2)
        circle(200, 195, 48, None, c, 7)
        circle(210, 190, 16, c)
        for x, y in ((120, 140), (275, 140), (130, 265), (265, 255)):
            rect(x - 16, y - 8, 32, 16, b, radius=8)
    elif topic == 'solar':
        circle(290, 100, 40, c)
        for k in range(8):
            t = k * math.pi / 4
            line([(290 + math.cos(t) * 53, 100 + math.sin(t) * 53), (290 + math.cos(t) * 67, 100 + math.sin(t) * 67)], c, 4)
        rect(45, 180, 285, 140, None, a)
        for x in (116, 187, 258):
            line([(x, 185), (x, 315)], b, 3)
        line([(50, 250), (325, 250)], b, 3)
        line([(150, 322), (140, 350), (240, 350), (230, 322)], a)
        line([(175, 92), (130, 135), (158, 135), (116, 174)], c, 7)
    elif topic == 'water':
        points = [(200, 55), (140, 155)] + [(200 + 78 * math.cos(t), 210 + 78 * math.sin(t)) for t in [math.pi - k * math.pi / 36 for k in range(37)]] + [(260, 155), (200, 55)]
        line(points, a, 7)
        for row in range(3):
            line([(35 + x, 310 + row * 24 + 9 * math.sin(x / 25)) for x in range(0, 331, 5)], b if row % 2 else c, 5)
        circle(220, 220, 14, c)
    elif topic == 'biology':
        for y in range(50, 351, 25):
            x = 200 + 80 * math.sin((y - 50) / 48)
            line([(x, y), (400 - x, y)], c, 3)
        for phase, col in ((0, a), (math.pi, b)):
            line([(200 + 80 * math.sin((y - 50) / 48 + phase), y) for y in range(50, 351, 3)], col, 9)
        for x, y in ((65, 90), (330, 285), (80, 310)):
            circle(x, y, 15, None, c, 3)
    elif topic == 'computing':
        layers = [[(70, y) for y in (110, 200, 290)], [(200, y) for y in (70, 155, 245, 330)], [(330, y) for y in (130, 270)]]
        for left, right in zip(layers, layers[1:]):
            for p in left:
                for q in right:
                    line([p, q], b, 2)
        for k, layer in enumerate(layers):
            for x, y in layer:
                circle(x, y, 19, colors[k])
    elif topic == 'health':
        rect(55, 85, 290, 230, None, b, 28)
        line([(75, 210), (125, 210), (150, 170), (180, 270), (215, 125), (245, 210), (325, 210)], a, 8)
        rect(280, 45, 12, 50, c, radius=3)
        rect(261, 64, 50, 12, c, radius=3)
    elif topic == 'environment':
        line([(200, 345), (200, 155)], a, 9)
        for x, y, col in ((135, 200, b), (265, 150, a), (140, 100, c)):
            line([(200, y + 60), (x, y)], a, 5)
            circle(x, y, 42, None, col, 7)
            line([(x - 20, y + 20), (x + 20, y - 20)], col, 4)
        line([(100, 350), (300, 350)], b, 6)
    elif topic == 'space':
        circle(200, 200, 68, a)
        circle(200, 200, 150, None, b, 3)
        circle(200, 200, 105, None, c, 3)
        circle(330, 125, 21, c)
        circle(98, 218, 12, b)
        for x, y in ((55, 60), (340, 310), (100, 340)):
            line([(x - 9, y), (x + 9, y)], c, 3)
            line([(x, y - 9), (x, y + 9)], c, 3)
    elif topic == 'research':
        line([(155, 60), (245, 60)], a, 7)
        line([(170, 65), (170, 160), (80, 310), (90, 340), (310, 340), (320, 310), (230, 160), (230, 65)], a, 7)
        line([(125, 260), (275, 260)], b, 7)
        for x, y, r in ((160, 300, 13), (225, 280, 9), (205, 210, 11), (195, 120, 6)):
            circle(x, y, r, c)
    else:
        # Neutral concept art, never a fabricated measurement or diagram of a claimed mechanism.
        circle(200, 200, 130, None, b, 3)
        circle(200, 200, 70, None, a, 12)
        for x, y, r, col in ((200, 70, 20, c), (88, 265, 15, a), (312, 265, 24, b)):
            circle(x, y, r, col)
        circle(200, 200, 16, c)
    return shapes


def paint(cv, shapes: list[dict], x: float, y: float, size: float) -> None:
    scale = size / 400
    for s in shapes:
        if s['kind'] == 'circle':
            cv.circle(x + s['cx'] * scale, y + s['cy'] * scale, s['r'] * scale, s['fill'], s['stroke'], s['width'] * scale)
        elif s['kind'] == 'rect':
            cv.rect(x + s['x'] * scale, y + s['y'] * scale, x + (s['x'] + s['w']) * scale, y + (s['y'] + s['h']) * scale,
                    s['fill'], s['radius'] * scale, s['stroke'], s['width'] * scale)
        else:
            cv.line([(x + px * scale, y + py * scale) for px, py in s['points']], s['stroke'], s['width'] * scale)


def svg(shapes: list[dict], title: str) -> str:
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" role="img">', '<title>' + escape(title) + '</title>']
    for s in shapes:
        attrs = f'fill="{s.get("fill") or "none"}" stroke="{s.get("stroke") or "none"}" stroke-width="{s["width"]}"'
        if s['kind'] == 'circle':
            parts.append(f'<circle cx="{s["cx"]}" cy="{s["cy"]}" r="{s["r"]}" {attrs}/>')
        elif s['kind'] == 'rect':
            parts.append(f'<rect x="{s["x"]}" y="{s["y"]}" width="{s["w"]}" height="{s["h"]}" rx="{s["radius"]}" {attrs}/>')
        else:
            points = ' '.join(f'{x:.2f},{y:.2f}' for x, y in s['points'])
            parts.append(f'<polyline points="{points}" {attrs} stroke-linecap="round" stroke-linejoin="round"/>')
    return '\n'.join(parts + ['</svg>'])
