"""Independent v0.3 dense-glyph/hexagram review; does not launch a browser.

Use --report PATH to save JSON, and optionally --baseline-zip PATH. In a portable
package without the previous symbols ZIP, current checks still run, but the
result is explicitly partial (ok=null, exit 2); legacy preservation and A/B ROI
claims are never fabricated. Exit 1 means a real check failed; exit 0 means the
stated current and baseline checks passed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import sys
from zipfile import ZipFile

from fontTools.pens.areaPen import AreaPen
from fontTools.pens.basePen import BasePen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = ROOT if (ROOT / 'fonts').is_dir() else ROOT / 'design/aincrad-ui-sc'
BASELINE_NAME = 'Aincrad-UI-SC-v0.3-xingpan-symbols.zip'
BASELINE_SHA = 'fc81120aac3a657a39d0adda9a41ba2b0533e355f2ec29c03f49f68f75a2b968'
DENSE = '羁螣攥黛'
ADDED = {ord('遯'), *range(0x4DC0, 0x4E00)}
TRIGRAM_ORDER = '乾兑离震巽坎艮坤'
TRIGRAM_BITS = dict(zip(TRIGRAM_ORDER, ('111', '011', '101', '001', '110', '010', '100', '000')))
ELEMENTS = dict(zip(TRIGRAM_ORDER, '天泽火雷风水山地'))
# Independent reference transcription: rows are LOWER trigrams, columns UPPER.
# https://zh.wikisource.org/wiki/周易, 六十四卦速查表, checked 2026-10-27.
# This oracle is deliberately not derived from the project's hexagrams.json.
REFERENCE_MATRIX = (
    '䷀䷪䷍䷡䷈䷄䷙䷊', '䷉䷹䷥䷵䷼䷻䷨䷒',
    '䷌䷰䷝䷶䷤䷾䷕䷣', '䷘䷐䷔䷲䷩䷂䷚䷗',
    '䷫䷛䷱䷟䷸䷯䷑䷭', '䷅䷮䷿䷧䷺䷜䷃䷆',
    '䷠䷞䷷䷽䷴䷦䷳䷎', '䷋䷬䷢䷏䷓䷇䷖䷁',
)
REFERENCE_NAMES = (
    '乾 坤 屯 蒙 需 讼 师 比 小畜 履 泰 否 同人 大有 谦 豫 随 蛊 临 观 '
    '噬嗑 贲 剥 复 无妄 大畜 颐 大过 坎 离 咸 恒 遯 大壮 晋 明夷 家人 睽 蹇 解 '
    '损 益 夬 姤 萃 升 困 井 革 鼎 震 艮 渐 归妹 丰 旅 巽 兑 涣 节 中孚 小过 既济 未济'
).split()
REFERENCE_URLS = [
    'https://www.unicode.org/charts/PDF/U4DC0.pdf',
    'https://zh.wikisource.org/wiki/周易',
    'https://zh.wikisource.org/wiki/易傳/說卦',
    'https://zh.wikisource.org/wiki/周易正義/04遯',
    'https://zh.wikisource.org/wiki/周易正義/03坎',
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(value):
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())


def recording(font, character_or_name, by_name=False):
    gs = getattr(font, '_dense_review_glyph_set', None)
    if gs is None:
        gs = font.getGlyphSet()
        font._dense_review_glyph_set = gs
    name = character_or_name if by_name else font.getBestCmap()[ord(character_or_name)]
    pen = DecomposingRecordingPen(gs)
    gs[name].draw(pen)
    return pen.value


def contours(commands):
    result, current = [], []
    for command in commands:
        current.append(command)
        if command[0] in ('closePath', 'endPath'):
            result.append(current)
            current = []
    if current:
        raise ValueError('Unclosed contour recording')
    return result


class FlattenPen(BasePen):
    def __init__(self):
        super().__init__(None)
        self.polygons = []
        self.points = []

    def _moveTo(self, pt):
        self.points = [pt]

    def _lineTo(self, pt):
        self.points.append(pt)

    def _curveToOne(self, b, c, d):
        self._cubic(self._getCurrentPoint(), b, c, d)

    def _qCurveToOne(self, q, d):
        a = self._getCurrentPoint()
        b = tuple(x + 2 * (y - x) / 3 for x, y in zip(a, q))
        c = tuple(x + 2 * (y - x) / 3 for x, y in zip(d, q))
        self._cubic(a, b, c, d)

    def _cubic(self, a, b, c, d, level=0):
        vx, vy = d[0] - a[0], d[1] - a[1]
        length = math.hypot(vx, vy)
        deviation = max(abs(vy * (q[0] - a[0]) - vx * (q[1] - a[1])) / length
                        if length else math.dist(q, a) for q in (b, c))
        if deviation <= .25 or level >= 14:
            self.points.append(d)
            return
        def mid(p, q):
            return tuple((x + y) / 2 for x, y in zip(p, q))
        ab, bc, cd = mid(a, b), mid(b, c), mid(c, d)
        abc, bcd = mid(ab, bc), mid(bc, cd)
        center = mid(abc, bcd)
        self._cubic(a, ab, abc, center, level + 1)
        self._cubic(center, bcd, cd, d, level + 1)

    def _closePath(self):
        if self.points[-1] != self.points[0]:
            self.points.append(self.points[0])
        self.polygons.append(self.points)

    def _endPath(self):
        raise ValueError('Open glyph contour')


def proper_intersection(a, b, c, d):
    if any(max(min(a[k], b[k]), min(c[k], d[k])) >
           min(max(a[k], b[k]), max(c[k], d[k])) for k in (0, 1)):
        return False
    def cross(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return cross(a, b, c) * cross(a, b, d) < -1e-8 and cross(c, d, a) * cross(c, d, b) < -1e-8


def geometry(commands):
    areas, boxes, flattened = [], [], []
    for contour in contours(commands):
        area, bounds, flat = AreaPen(), BoundsPen(None), FlattenPen()
        for op, args in contour:
            for pen in (area, bounds, flat):
                getattr(pen, op)(*args)
        areas.append(area.value)
        boxes.append(bounds.bounds)
        flattened.append([(a, b) for a, b in zip(flat.polygons[0], flat.polygons[0][1:]) if a != b])
    self_crossings, cross_contour = [], []
    for ci, segments in enumerate(flattened):
        count = sum(proper_intersection(*segments[i], *segments[j])
                    for i in range(len(segments)) for j in range(i + 2, len(segments))
                    if not (i == 0 and j == len(segments) - 1))
        self_crossings.append(count)
        for cj in range(ci):
            count = sum(proper_intersection(*a, *b) for a in segments for b in flattened[cj])
            if count:
                cross_contour.append([cj, ci, count])
    return {'contour_count': len(areas), 'contour_signed_areas': areas,
            'winding_signs': [1 if a > 0 else -1 if a < 0 else 0 for a in areas],
            'signed_ink_area': sum(areas), 'strict_self_crossings_by_contour': self_crossings,
            'strict_cross_contour_crossings': cross_contour, 'contour_bounds': boxes}


def line_metrics(font):
    h, o = font['hhea'], font['OS/2']
    return [font['head'].unitsPerEm, h.ascent, h.descent, h.lineGap, o.sTypoAscender,
            o.sTypoDescender, o.sTypoLineGap, o.usWinAscent, o.usWinDescent]


def font_bytes_for_pillow(data):
    f = TTFont(BytesIO(data))
    if not f.flavor:
        return data
    f.flavor = None
    stream = BytesIO()
    f.save(stream)
    return stream.getvalue()


def raster(engine, c, size):
    mask, offset = engine.getmask2(c, mode='L', anchor='ls')
    image = Image.frombytes('L', mask.size, bytes(mask))
    canvas = Image.new('L', (size * 2, size * 2))
    origin = (size // 2, math.ceil(size * 1.2))
    canvas.paste(image, (origin[0] + offset[0], origin[1] + offset[1]))
    return canvas, origin, image, offset


def fixed_roi_white(canvas, origin, source_box, size):
    # Original, frozen source coordinates: x condensation .88 and +10 UPM.
    # Fractional pixel overlap prevents a rounded crop or enlarged ROI bias.
    x0, y0, x1, y1 = source_box
    x0, x1 = [(x * .88 + 10) * size / 1000 + origin[0] for x in (x0, x1)]
    top, bottom = origin[1] - y1 * size / 1000, origin[1] - y0 * size / 1000
    white = 0
    for y in range(math.floor(top), math.ceil(bottom)):
        for x in range(math.floor(x0), math.ceil(x1)):
            weight = max(0, min(x + 1, x1) - max(x, x0)) * max(0, min(y + 1, bottom) - max(y, top))
            white += weight * (1 - canvas.getpixel((x, y)) / 255)
    return white / ((x1 - x0) * (bottom - top))


def segment_count(values):
    threshold = max(values) * .4
    active = [value > threshold and value > 0 for value in values]
    return sum(value and (i == 0 or not active[i - 1]) for i, value in enumerate(active))


def run(project, baseline_path):
    problems = []
    def check(condition, message):
        if not condition:
            problems.append(message)
        return bool(condition)
    def load(name):
        return json.loads((project / name).read_text(encoding='utf-8'))
    charset, prov = load('data/charset.json'), load('data/provenance.json')
    dense, plan = load('data/dense-refinements-v030.json'), load('data/refinements-v030.json')
    hexagrams, manifest = load('data/hexagrams.json'), load('data/hexagram-outlines-v030.json')
    original_symbols = load('data/symbols-v030.json')
    expected = set(map(ord, charset['characters']))
    custom = set(original_symbols['glyphs']) | set(manifest['glyphs'])
    report = {'timestamp_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'Independent incremental font regression, exact winding, 0.25 UPM flattened proper crossings, fixed local grayscale ROIs and six-line symbol semantics.',
              'scope_limits': ['Local grayscale white fractions are diagnostics, not universal readability acceptance.',
                               'No browser, Flutter, Android/iOS device, OS font scaling or professional hinting acceptance.',
                               'Strict proper crossings exclude endpoint touches and collinear overlap; flattening is numerical, not exact algebraic curve intersection.',
                               'Current-only portable checks cannot prove preservation or baseline-relative whitespace gains.'],
              'baseline': {'file': str(baseline_path), 'available': baseline_path.is_file(), 'expected_sha256': BASELINE_SHA},
              'input_hashes': {}, 'font_hashes': {}, 'formats': {}, 'dense_geometry': {},
              'fixed_roi_grayscale': {}, 'original_161_preservation': {}, 'problems': problems,
              'diagnostics': []}
    input_names = ['data/charset.json', 'data/provenance.json', 'data/refinements-v030.json',
                   'data/dense-refinements-v030.json', 'data/hexagrams.json', 'data/hexagram-outlines-v030.json',
                   'data/symbols-v030.json', 'data/source-v030.json']
    for name in input_names:
        report['input_hashes'][name] = sha((project / name).read_bytes())
    check(set(dense['glyphs']) == set(DENSE) and all(set(v) == {'issue', 'Regular'} for v in dense['glyphs'].values()),
          'Dense plan must contain only the four declared Regular plans')
    check(len(expected) == 4041 and len(charset['han_characters']) == 3814, 'Current charset does not match the frozen 4041/3814 release scope')
    for key in ('refinement_plan', 'dense_refinements', 'custom_symbols'):
        d = prov[key]
        check(sha((project / d['file']).read_bytes()) == d['sha256'], key + ': provenance hash mismatch')
    for d in prov['custom_symbols'].get('additional_manifests', []):
        check(sha((project / d['file']).read_bytes()) == d['sha256'], 'Additional manifest hash mismatch')
    hdecl = prov['charset_extensions']['hexagrams']
    check(hdecl['sha256'] == report['input_hashes']['data/hexagrams.json'] and hdecl['symbol_count'] == 64, 'Hexagram data provenance mismatch')
    check(set(map(ord, manifest['glyphs'])) == set(range(0x4DC0, 0x4E00)), 'Hexagram outline manifest character scope mismatch')
    check(len(custom) == 78 and set(prov['custom_symbols']['characters']) == custom and
          set(prov['custom_symbols']['baseline_excluded_characters']) == custom and prov['custom_symbols']['count'] == 78,
          'Source exclusions are not exactly the 78 declared original symbols')
    source_scope = expected - set(map(ord, custom))
    source_baseline = TTFont(project / 'fonts/SourceHanSansSC-Baseline.woff2')
    check(set(source_baseline.getBestCmap()) == source_scope, 'Source comparison font coverage mismatch')
    report['baseline_source_scope'] = {'source_character_count': len(source_scope), 'excluded_original_count': len(custom),
                                      'exact_source_cmap_matches': set(source_baseline.getBestCmap()) == source_scope}
    oracle = {}
    for lower, row in zip(TRIGRAM_ORDER, REFERENCE_MATRIX):
        for upper, c in zip(TRIGRAM_ORDER, row):
            oracle[c] = (upper, lower, list(map(int, TRIGRAM_BITS[upper] + TRIGRAM_BITS[lower])))
    semantic_data = []
    check(len(hexagrams['records']) == 64, 'Hexagram record count is not 64')
    for index, entry in enumerate(hexagrams['records']):
        c = chr(0x4DC0 + index)
        upper, lower, bits = oracle[c]
        name = REFERENCE_NAMES[index]
        full_name = name + '为' + ELEMENTS[upper] if upper == lower else ELEMENTS[upper] + ELEMENTS[lower] + name
        ok = check(entry['number'] == index + 1 and entry['character'] == c and entry['codepoint'] == f'U+{ord(c):04X}' and
                   entry['name'] == name and entry['full_name'] == full_name and entry['upper_trigram'] == upper and
                   entry['lower_trigram'] == lower and entry['lines_top_to_bottom'] == bits,
                   f'{c}: received order/name/upper-lower/six-line data mismatch')
        check(manifest['glyphs'][c]['lines_top_to_bottom'] == bits, c + ': manifest pattern differs from independent oracle')
        semantic_data.append({'number': index + 1, 'character': c, 'name': name, 'full_name': full_name,
                              'upper_trigram': upper, 'lower_trigram': lower, 'expected_top_to_bottom': bits, 'data_matches': ok})
    aliases_29 = '习坎' in hexagrams['records'][28]['aliases']
    aliases_33 = {'遁', '天山遁'} <= set(hexagrams['records'][32]['aliases'])
    check(aliases_29 and aliases_33, 'Required traditional-name aliases missing')
    report['hexagram_semantics'] = {'oracle': 'Independent published lower-row / upper-column matrix and received-order names; not generated from project JSON.',
                                   'reference_urls': REFERENCE_URLS, 'references_checked_utc': '2026-10-27',
                                   'records': semantic_data, 'alias_checks': {'29_习坎': aliases_29, '33_遯_with_遁_天山遁': aliases_33},
                                   'vector_cases': 0, 'raster_cases': 0, 'raster_sizes_px': [14, 28, 128], 'failures': []}
    report['hexagram_row_separation'] = {
        'method': 'Actual native grayscale image row-alpha sum; count separated occupied bands above 25% of the strongest image row. No expected line centers are supplied to this measurement.',
        'sizes_physical_px': [14, 18, 28], 'threshold_fraction': .25,
        'cases': [], 'interpretation': 'Six detectable bands is a raster separation check, not subjective recognition or universal readability acceptance.'}
    baseline = ZipFile(baseline_path) if baseline_path.is_file() else None
    if baseline:
        baseline_sha = sha(baseline_path.read_bytes())
        report['baseline']['sha256'] = baseline_sha
        check(baseline_sha == BASELINE_SHA, 'Immutable symbols baseline ZIP hash mismatch')
        prefix = next(n for n in baseline.namelist() if n.endswith('/data/charset.json')).removesuffix('data/charset.json')
        def old_json(name):
            return json.loads(baseline.read(prefix + name).decode('utf-8'))
        old_expected = set(map(ord, old_json('data/charset.json')['characters']))
        check(len(old_expected) == 3976 and expected - old_expected == ADDED and old_expected <= expected,
              'Charset delta must be exactly 遯 plus U+4DC0..U+4DFF')
        old_plan = old_json('data/refinements-v030.json')
        check(old_plan['glyphs'] == plan['glyphs'] and len(plan['glyphs']) == 161, 'Original 161 local plans changed')
    raster_count = 0
    roi_count = 0
    for variant, weight in (('Regular', 'Regular'), ('Display', 'Medium')):
        report['formats'][variant] = {}
        report['dense_geometry'][variant] = {}
        refined_output_equal = True
        for fmt in ('otf', 'ttf', 'woff2'):
            filename = f'AincradUISc-{variant}.{fmt}'
            data = (project / 'fonts' / filename).read_bytes()
            font = TTFont(BytesIO(data))
            cmap = font.getBestCmap()
            report['font_hashes'][filename] = sha(data)
            check(sha(data) == prov['fonts'][filename]['sha256'], filename + ': provenance font hash mismatch')
            check(set(cmap) == expected and all(n != '.notdef' for n in cmap.values()), filename + ': full real-glyph coverage mismatch')
            text = ''.join(e['name'] + e['full_name'] + ''.join(e.get('aliases', [])) for e in hexagrams['records'])
            names_covered = check(set(map(ord, text)) <= set(cmap), filename + ': hexagram names/aliases not fully covered')
            old = TTFont(BytesIO(baseline.read(prefix + 'fonts/' + filename))) if baseline else None
            fr = {'coverage': len(cmap), 'name_alias_coverage': names_covered, 'new_characters': ''.join(map(chr, sorted(ADDED))),
                  'old_regression_available': bool(old)}
            report['formats'][variant][fmt] = fr
            if old:
                om = old.getBestCmap()
                changed, before, after = [], [], []
                for name in old.getGlyphOrder():
                    a, b = recording(old, name, True), recording(font, name, True)
                    before.append([name, a]); after.append([name, b])
                    if a != b:
                        changed.append(name)
                allowed = {om[ord(c)] for c in DENSE} if variant == 'Regular' else set()
                metric_changes = [n for n, m in old['hmtx'].metrics.items() if font['hmtx'].metrics.get(n) != m]
                check(set(changed) == allowed, filename + ': old outline changes differ from exactly permitted four Regular / zero Display')
                check(not metric_changes and line_metrics(old) == line_metrics(font), filename + ': old hmtx or line metrics changed')
                check(set(cmap) - set(om) == ADDED and set(om) <= set(cmap) and
                      all(cmap[cp] == om[cp] for cp in om), filename + ': added/retained cmap mismatch')
                refined_output_equal &= all(recording(old, c) == recording(font, c) for c in plan['glyphs'])
                fr.update(previous_characters_compared=len(om), previous_glyphs_compared=len(old.getGlyphOrder()),
                          changed_old_glyph_names=changed, changed_old_characters=''.join(c for c in DENSE if om[ord(c)] in changed),
                          changed_old_hmtx_glyphs=metric_changes, previous_hmtx_entries_compared=len(old['hmtx'].metrics),
                          line_metrics_preserved=line_metrics(old) == line_metrics(font),
                          old_complete_outline_sha256=digest(before), current_old_complete_outline_sha256=digest(after),
                          unchanged_glyph_subset_old_sha256=digest([v for v in before if v[0] not in allowed]),
                          unchanged_glyph_subset_new_sha256=digest([v for v in after if v[0] not in allowed]),
                          old_hmtx_sha256=digest(sorted(old['hmtx'].metrics.items())),
                          current_old_hmtx_sha256=digest([(n, font['hmtx'].metrics[n]) for n in sorted(old['hmtx'].metrics)]))
            digits = [font['hmtx'][cmap[ord(c)]][0] for c in '0123456789']
            check(len(set(digits)) == 1 and digits[0] > 0, filename + ': digits not tabular')
            fr['tabular_digits_advance_upm'] = digits[0] if len(set(digits)) == 1 else digits
            engines = {s: ImageFont.truetype(BytesIO(font_bytes_for_pillow(data)), s, layout_engine=ImageFont.Layout.BASIC)
                       for s in (11, 12, 13, 14, 18, 28, 128)}
            for c in DENSE:
                g = geometry(recording(font, c))
                review = {'current': g}
                if old:
                    previous = geometry(recording(old, c))
                    review['baseline'] = previous
                    ratio = g['signed_ink_area'] / previous['signed_ink_area']
                    review['ink_area_ratio'] = ratio
                    check(g['contour_count'] == previous['contour_count'] and g['winding_signs'] == previous['winding_signs'],
                          filename + ': ' + c + ' contour count or winding changed')
                    check(g['strict_self_crossings_by_contour'] == previous['strict_self_crossings_by_contour'] and
                          g['strict_cross_contour_crossings'] == previous['strict_cross_contour_crossings'],
                          filename + ': ' + c + ' crossing topology changed')
                    check(.9 <= ratio <= 1.001, filename + ': ' + c + ' unreasonable ink-area change')
                    if variant == 'Regular':
                        area_changes = []
                        for region in dense['glyphs'][c]['Regular']['counter_expansions']:
                            ci = region['contour']
                            a, b = abs(previous['contour_signed_areas'][ci]), abs(g['contour_signed_areas'][ci])
                            enlarged = check(b > a, filename + ': selected vector counter did not enlarge: ' + c + '/' + str(ci))
                            area_changes.append({'contour': ci, 'area_before_upm2': a, 'area_after_upm2': b,
                                                 'area_ratio': b / a, 'vector_counter_enlarged': enlarged})
                        review['selected_vector_counter_expansions'] = area_changes
                else:
                    check(not any(g['strict_self_crossings_by_contour']) and not g['strict_cross_contour_crossings'],
                          filename + ': ' + c + ' proper intersections found')
                if c == '攥' and variant == 'Regular':
                    b = g['contour_bounds']
                    thicknesses = [b[6][1] - b[5][3], b[7][1] - b[6][3]]
                    review['eye_inner_horizontal_thickness_upm'] = thicknesses
                    check(min(thicknesses) >= 27, filename + ': 攥 inner bar below reviewed 27 UPM minimum')
                report['dense_geometry'][variant].setdefault(c, {})[fmt] = review
            for cp in sorted(ADDED):
                c = chr(cp)
                g = geometry(recording(font, c))
                all_bounds = g['contour_bounds']
                check(bool(all_bounds) and abs(g['signed_ink_area']) > 0, filename + ': new glyph empty: ' + c)
                advance = font['hmtx'][cmap[cp]][0]
                lm = line_metrics(font)
                check(all(0 <= b[0] <= b[2] <= advance and lm[2] <= b[1] <= b[3] <= lm[1] for b in all_bounds),
                      filename + ': new glyph outside font cell: ' + c)
                for size in (11, 12, 13, 14):
                    canvas, origin, image, offset = raster(engines[size], c, size)
                    box = image.getbbox()
                    coverage = sum(image.tobytes())
                    visible = bool(box and coverage > 0 and coverage == sum(canvas.tobytes()))
                    if box:
                        x0, y0, x1, y1 = offset[0] + box[0], offset[1] + box[1], offset[0] + box[2], offset[1] + box[3]
                        visible &= x0 >= -1 and x1 <= math.ceil(advance * size / lm[0]) + 1 and y0 >= -math.ceil(lm[1] * size / lm[0]) - 1 and y1 <= math.ceil(-lm[2] * size / lm[0]) + 1
                    check(visible, f'{filename}: {c} is empty or clipped at {size}px')
                    raster_count += 1
                if cp < 0x4DC0 or cp > 0x4DFF:
                    continue
                groups = {}
                for bounds in all_bounds:
                    center = round((bounds[1] + bounds[3]) / 2, 3)
                    groups.setdefault(center, []).append(bounds)
                centers = sorted(groups, reverse=True)
                expected_segments = [1 if bit else 2 for bit in oracle[c][2]]
                actual_segments = [len(groups[y]) for y in centers]
                check(len(centers) == 6 and actual_segments == expected_segments,
                      filename + ': six-line vector identity mismatch: ' + c)
                check(not any(g['strict_self_crossings_by_contour']) and not g['strict_cross_contour_crossings'],
                      filename + ': hexagram geometry intersections: ' + c)
                report['hexagram_semantics']['vector_cases'] += 1
                for size in (14, 18, 28):
                    _, _, native, _ = raster(engines[size], c, size)
                    pixels, width = native.tobytes(), native.width
                    row_sums = [sum(pixels[y * width:(y + 1) * width]) for y in range(native.height)]
                    threshold = max(row_sums) * .25
                    active = [value > threshold for value in row_sums]
                    bands = sum(value and (i == 0 or not active[i - 1]) for i, value in enumerate(active))
                    report['hexagram_row_separation']['cases'].append({
                        'font': filename, 'character': c, 'size_physical_px': size,
                        'occupied_bands': bands, 'six_bands_separated': bands == 6,
                        'normalized_row_alpha_sums': [round(v / max(row_sums), 5) for v in row_sums]})
                    if size == 14:
                        check(bands == 6, filename + ': native 14px hexagram does not resolve six occupied row bands: ' + c)
                for size in (14, 28, 128):
                    canvas, origin, _, _ = raster(engines[size], c, size)
                    counts = [segment_count([canvas.getpixel((x, math.floor(origin[1] - center * size / lm[0])))
                                             for x in range(canvas.width)]) for center in centers]
                    ok = len(centers) == 6 and counts == expected_segments
                    if not ok:
                        report['hexagram_semantics']['failures'].append({'font': filename, 'character': c, 'size_px': size,
                                                                       'expected': expected_segments, 'observed': counts})
                    check(ok, f'{filename}: six-line raster identity mismatch for {c} at {size}px')
                    report['hexagram_semantics']['raster_cases'] += 1
            if variant == 'Regular' and old:
                old_data = baseline.read(prefix + 'fonts/' + filename)
                roi_entries = []
                for size in (14, 28):
                    old_engine = ImageFont.truetype(BytesIO(font_bytes_for_pillow(old_data)), size, layout_engine=ImageFont.Layout.BASIC)
                    for c in DENSE:
                        old_raster, new_raster = raster(old_engine, c, size), raster(engines[size], c, size)
                        for region in dense['glyphs'][c]['Regular']['counter_expansions']:
                            box = region['source_node_bounds']
                            before = fixed_roi_white(*old_raster[:2], box, size)
                            after = fixed_roi_white(*new_raster[:2], box, size)
                            if after < before:
                                report['diagnostics'].append({
                                    'code': 'local_gray_counter_white_coverage_decreased',
                                    'font': filename, 'character': c, 'contour': region['contour'],
                                    'physical_size_px': size,
                                    'increase_percentage_points': (after - before) * 100,
                                    'interpretation': 'Local curve/pixel quantization can differ by format and size. This measured exception is retained; not every ROI is claimed to improve. It is separate from vector counter expansion, geometry and readability acceptance.'})
                            roi_entries.append({'character': c, 'contour': region['contour'], 'source_roi': box, 'physical_size_px': size,
                                                'white_fraction_before': before, 'white_fraction_after': after,
                                                'increase_percentage_points': (after - before) * 100})
                            roi_count += 1
                report['fixed_roi_grayscale'][fmt] = roi_entries
        source = prov['sources'][variant]
        seed_data = (project / source['file']).read_bytes()
        report['input_hashes'][source['file']] = sha(seed_data)
        seed = TTFont(BytesIO(seed_data))
        check(sha(seed_data) == source['sha256'] == plan['source_sha256_by_weight'][weight], variant + ': seed/plan/provenance hash mismatch')
        check(set(seed.getBestCmap()) == source_scope, variant + ': source seed scope mismatch')
        if variant == 'Regular':
            check(sha(seed_data) == dense['source_sha256_by_weight']['Regular'], 'Dense plan source seed hash mismatch')
            anchors = {c: sha(repr(recording(seed, c)).encode()) == dense['glyphs'][c]['Regular']['source_outline_sha256'] for c in DENSE}
            check(all(anchors.values()), 'Dense source outline anchors mismatch')
            report['dense_source_anchors'] = anchors
        if baseline:
            old_seed = TTFont(BytesIO(baseline.read(prefix + source['file'])))
            before = [[c, recording(old_seed, c)] for c in plan['glyphs']]
            after = [[c, recording(seed, c)] for c in plan['glyphs']]
            source_equal = before == after
            check(source_equal and refined_output_equal, variant + ': original 161 source/output outlines changed')
            report['original_161_preservation'][variant] = {'characters_compared': len(plan['glyphs']),
                'plans_exactly_equal': old_plan['glyphs'] == plan['glyphs'], 'sources_exactly_equal': source_equal,
                'output_outlines_equal_all_three_formats': refined_output_equal,
                'old_source_subset_sha256': digest(before), 'current_source_subset_sha256': digest(after)}
    report['fixed_roi_method'] = {'unique_fixed_source_regions': sum(len(dense['glyphs'][c]['Regular']['counter_expansions']) for c in DENSE),
        'cases_compared': roi_count, 'sizes_physical_px': [14, 28],
        'measurement': 'Mean 1-alpha/255 over exactly the original source ROI, transformed x=.88*x+10, y unchanged; fractional pixel overlap weighting, identical baseline/origin, no resampling or ROI expansion.',
        'diagnostic_only': True,
        'increased_cases': sum(entry['increase_percentage_points'] > 0 for entries in report['fixed_roi_grayscale'].values() for entry in entries),
        'decreased_cases': sum(entry['increase_percentage_points'] < 0 for entries in report['fixed_roi_grayscale'].values() for entry in entries),
        'interpretation': 'Only local white-coverage change; not a claim that every internal slit is visually resolved or that the word is readable.'}
    for name, value in report['input_hashes'].items():
        check(sha((project / name).read_bytes()) == value, name + ': input changed during review')
    for name, value in report['font_hashes'].items():
        check(sha((project / 'fonts' / name).read_bytes()) == value, name + ': font changed during review')
    report['new_glyph_rasterizations'] = raster_count
    report['hexagram_row_separation']['summary'] = [
        {'font': filename, 'size_physical_px': size, 'cases': len(cases),
         'six_bands_separated': sum(item['six_bands_separated'] for item in cases)}
        for filename in report['font_hashes'] for size in (14, 18, 28)
        for cases in [[item for item in report['hexagram_row_separation']['cases']
                       if item['font'] == filename and item['size_physical_px'] == size]]]
    report['current_checks_passed'] = not problems
    report['ok'] = not problems if baseline else False if problems else None
    report['status'] = ('failed' if problems else 'partial_baseline_unavailable' if not baseline
                        else 'passed_with_local_raster_diagnostics' if report['diagnostics']
                        else 'passed_within_stated_scope')
    if baseline:
        baseline.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir', type=Path, default=DEFAULT_PROJECT)
    parser.add_argument('--baseline-zip', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    baseline_path = args.baseline_zip or args.project_dir / BASELINE_NAME
    report = run(args.project_dir, baseline_path)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'ok': report['ok'], 'status': report['status'], 'problems': report['problems'],
                          'report': str(args.report), 'hexagram_raster_cases': report['hexagram_semantics']['raster_cases'],
                          'roi_cases': report['fixed_roi_method']['cases_compared']}, ensure_ascii=False))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report['problems'] else 0 if report['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
