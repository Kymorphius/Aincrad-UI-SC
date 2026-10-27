#!/usr/bin/env python3
"""Build a small, reproducible OFL Chinese UI type specimen.

This is a Source Han Sans derivative. Version 0.3 expands the glyph set from a
categorized UI vocabulary and retains explicit local refinement plans.
"""
from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path

from fontTools import subset
from fontTools.fontBuilder import FontBuilder
from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = ROOT if (ROOT / 'specimen.html').is_file() else ROOT / 'design' / 'aincrad-ui-sc'
VERSION = '0.3.0'
FONT_VERSION = '0.300'
COPYRIGHT = (
    'Copyright 2014, 2015 Adobe Systems Incorporated (http://www.adobe.com/), '
    "with Reserved Font Name 'Source'. "
    'Aincrad UI SC specimen modifications, 2026. '
    'Derived from Source Han Sans SC; distributed under SIL Open Font License 1.1.'
)
LICENSE = (
    'This Font Software is licensed under the SIL Open Font License, Version 1.1. '
    'See the accompanying OFL.txt. This is an experimental modified font based '
    'on Source Han Sans, without endorsement by the original authors.'
)
VARIANTS = {
    'Regular': dict(family='Aincrad UI SC', source='Regular', han_scale=.88,
                    han_width=900, latin_scale=.79, radius=7, chamfer=0),
    'Display': dict(family='Aincrad UI SC Display', source='Medium', han_scale=.82,
                    han_width=850, latin_scale=.74, radius=8, chamfer=18),
}
WAO_CHARACTERS = '◆◇●■□▲▼▶◀‹«»─│┌┐└┘‥⟨⟩※†‖'
WAO_ORIGINAL_CHARACTERS = '─│┌┐└┘⟨⟩'


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


HAN_RANGES = (
    (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF),
    (0x20000, 0x2A6DF), (0x2A700, 0x2B73F), (0x2B740, 0x2B81F),
    (0x2B820, 0x2CEAF), (0x2CEB0, 0x2EE5F), (0x2F800, 0x2FA1F),
    (0x30000, 0x3347F),
)


def is_han(c: str) -> bool:
    return any(start <= ord(c) <= end for start, end in HAN_RANGES)


def source_extension(project: Path) -> tuple[Path | None, str]:
    for manifest, prefix in (
        ('wao-symbol-extension.json', 'AincradSeed-wao'),
        ('sourcehan-han-extension.json', 'AincradSeed-sourcehan'),
        ('gb2312-han-extension.json', 'AincradSeed-gb2312'),
    ):
        path = project / 'data' / manifest
        if path.is_file():
            return path, prefix
    return None, 'AincradSeed-v030'


def rename_seed(font: TTFont, weight: str) -> None:
    family = 'Aincrad Baseline SC' + (' Medium' if weight == 'Medium' else '')
    postscript = 'AincradBaselineSC-' + weight
    font['name'].names = []
    for name_id, value in {
        0: COPYRIGHT, 1: family, 2: 'Regular', 3: '1.004;' + postscript,
        4: family, 5: 'Version 1.004; Aincrad seed subset', 6: postscript,
        13: LICENSE, 14: 'https://openfontlicense.org/', 16: family, 17: 'Regular',
    }.items():
        font['name'].setName(value, name_id, 3, 1, 0x409)
    font['OS/2'].fsType = 0
    if 'CFF ' in font:
        cff = font['CFF '].cff
        cff.fontNames = [postscript]
        top = cff.topDictIndex[0]
        top.FamilyName = family
        top.FullName = family
        top.Notice = COPYRIGHT


def acquire_seed(project: Path, weight: str, characters: str, refresh: bool=False) -> tuple[TTFont, dict]:
    custom_symbols, _ = load_symbol_plan(project)
    source_characters = ''.join(c for c in characters if c not in custom_symbols)
    _manifest, seed_prefix = source_extension(project)
    path = project / 'sources' / f'{seed_prefix}-{weight}.otf'
    if path.exists() and not refresh:
        f = TTFont(path, recalcTimestamp=False)
        missing = set(map(ord, source_characters)) - set(f.getBestCmap())
        if missing:
            raise ValueError(f'Seed {weight} lacks new characters: {sorted(missing)}')
        return f, dict(file=path.relative_to(project).as_posix(), sha256=sha256(path))
    original = ROOT / 'collected-ui' / 'SAO-Utils-2-Progressive' / 'assets' / 'Fonts' / f'SourceHanSans-{weight}.ttc'
    if not original.is_file():
        raise FileNotFoundError(f'Seed and original source are both missing: {path}')
    f = TTFont(original, fontNumber=2, recalcTimestamp=False)
    original_info = dict(
        source_file=original.relative_to(ROOT).as_posix(), source_sha256=sha256(original),
        face_index=2, source_family=f['name'].getDebugName(1),
        source_version=f['name'].getDebugName(5),
        source_copyright=f['name'].getDebugName(0),
    )
    missing = set(map(ord, source_characters)) - set(f.getBestCmap())
    if missing:
        raise ValueError(f'Original source {weight} lacks codepoints: {sorted(missing)}')
    opts = subset.Options()
    opts.name_IDs = ['*']
    opts.name_legacy = True
    opts.name_languages = ['*']
    opts.notdef_outline = True
    opts.layout_features = []
    opts.recalc_timestamp = False
    opts.bidi_closure = False
    subsetter = subset.Subsetter(options=opts)
    subsetter.populate(unicodes=list(map(ord, source_characters)))
    subsetter.subset(f)
    # BASE and vertical metrics refer to the original full font's CIDs.
    for tag in ('BASE', 'VORG', 'vhea', 'vmtx', 'GSUB', 'GPOS'):
        if tag in f:
            del f[tag]
    rename_seed(f, weight)
    path.parent.mkdir(parents=True, exist_ok=True)
    f.save(path)
    return f, dict(file=path.relative_to(project).as_posix(), sha256=sha256(path), **original_info)


def reviewed_source_hash(project: Path, seed: TTFont, weight: str, info: dict) -> tuple[str, dict | None]:
    """Keep the reviewed seed immutable while extending its character coverage.

    Existing optical plans are anchored to the original source subset. An
    expanded subset can reuse them only when every old outline and advance is
    exactly identical; its own file/hash remains the actual build provenance.
    """
    path, seed_prefix = source_extension(project)
    if path is None:
        return info['sha256'], None
    manifest = json.loads(path.read_text(encoding='utf-8'))
    record = manifest['sources'][weight]
    expected_file = f'sources/{seed_prefix}-{weight}.otf'
    reviewed_file = f'sources/AincradSeed-v030-{weight}.otf'
    if (record['file'] != expected_file or record['reviewed_seed_file'] != reviewed_file
            or info['file'] != expected_file or info['sha256'] != record['sha256']
            or sha256(project / reviewed_file) != record['reviewed_seed_sha256']):
        raise ValueError('Expanded source or immutable reviewed source hash differs')
    compared = 0
    outline_digest = hashlib.sha256()
    with TTFont(project / reviewed_file, recalcTimestamp=False) as reviewed:
        old_map, new_map = reviewed.getBestCmap(), seed.getBestCmap()
        old_set, new_set = reviewed.getGlyphSet(), seed.getGlyphSet()
        for point, name in sorted(old_map.items()):
            if point not in new_map:
                raise ValueError('Expanded source removed an existing character')
            old, new = RecordingPen(), RecordingPen()
            old_set[name].draw(old)
            new_set[new_map[point]].draw(new)
            if (old.value != new.value or old_set[name].width != new_set[new_map[point]].width
                    or reviewed['hmtx'][name] != seed['hmtx'][new_map[point]]):
                raise ValueError(f'Expanded source changes reviewed outline/advance U+{point:04X}')
            outline_digest.update(repr((point, old_set[name].width, old.value)).encode('utf-8'))
            compared += 1
    review = dict(
        reviewed_seed_file=reviewed_file, reviewed_seed_sha256=record['reviewed_seed_sha256'],
        expanded_seed_file=expected_file, expanded_seed_sha256=info['sha256'],
        preserved_source_characters=compared, preserved_outline_advance_sha256=outline_digest.hexdigest(),
        all_reviewed_outlines_and_advances_identical=True)
    if seed_prefix in ('AincradSeed-sourcehan', 'AincradSeed-wao'):
        previous_file = f'sources/AincradSeed-gb2312-{weight}.otf'
        previous_record = json.loads((project / 'data' / 'gb2312-han-extension.json').read_text(encoding='utf-8'))['sources'][weight]
        if (record['previous_gb2312_seed_file'] != previous_file
                or record['previous_gb2312_seed_sha256'] != previous_record['sha256']
                or sha256(project / previous_file) != previous_record['sha256']):
            raise ValueError('Previous GB2312 source hash differs')
        digest, count = hashlib.sha256(), 0
        with TTFont(project / previous_file, recalcTimestamp=False) as previous:
            old_map, new_map = previous.getBestCmap(), seed.getBestCmap()
            old_set, new_set = previous.getGlyphSet(), seed.getGlyphSet()
            for point, name in sorted(old_map.items()):
                if point not in new_map:
                    raise ValueError('Source Han expansion removed a previous source character')
                old, new = RecordingPen(), RecordingPen()
                old_set[name].draw(old)
                new_set[new_map[point]].draw(new)
                metric = previous['hmtx'][name]
                if old.value != new.value or metric != seed['hmtx'][new_map[point]]:
                    raise ValueError(f'Source Han expansion changes previous source U+{point:04X}')
                digest.update(repr((point, metric, old.value)).encode('utf-8'))
                count += 1
        review.update(previous_gb2312_seed_file=previous_file,
                      previous_gb2312_seed_sha256=record['previous_gb2312_seed_sha256'],
                      preserved_previous_source_characters=count,
                      preserved_previous_outline_hmtx_sha256=digest.hexdigest(),
                      all_previous_outlines_and_horizontal_metrics_identical=True)
    if seed_prefix == 'AincradSeed-wao':
        previous_file = f'sources/AincradSeed-sourcehan-{weight}.otf'
        previous_record = json.loads((project / 'data' / 'sourcehan-han-extension.json').read_text(encoding='utf-8'))['sources'][weight]
        if (record['previous_sourcehan_seed_file'] != previous_file
                or record['previous_sourcehan_seed_sha256'] != previous_record['sha256']
                or sha256(project / previous_file) != previous_record['sha256']):
            raise ValueError('Previous full-Han source hash differs')
        digest, count = hashlib.sha256(), 0
        with TTFont(project / previous_file, recalcTimestamp=False) as previous:
            old_map, new_map = previous.getBestCmap(), seed.getBestCmap()
            old_set, new_set = previous.getGlyphSet(), seed.getGlyphSet()
            for point, name in sorted(old_map.items()):
                if point not in new_map:
                    raise ValueError('WAO expansion removed a previous source character')
                old, new = RecordingPen(), RecordingPen()
                old_set[name].draw(old)
                new_set[new_map[point]].draw(new)
                metric = previous['hmtx'][name]
                if old.value != new.value or metric != seed['hmtx'][new_map[point]]:
                    raise ValueError(f'WAO expansion changes previous source U+{point:04X}')
                digest.update(repr((point, metric, old.value)).encode('utf-8'))
                count += 1
        review.update(previous_sourcehan_seed_file=previous_file,
                      previous_sourcehan_seed_sha256=record['previous_sourcehan_seed_sha256'],
                      preserved_full_han_source_characters=count,
                      preserved_full_han_outline_hmtx_sha256=digest.hexdigest(),
                      all_full_han_source_outlines_and_horizontal_metrics_identical=True)
    return record['reviewed_seed_sha256'], review


def get_contours(recording: RecordingPen) -> list[tuple[list, list]]:
    """A closed contour is nodes plus outgoing (operator, control-points) edges."""
    contours = []
    nodes, edges = [], []
    for op, args in recording.value:
        if op == 'moveTo':
            nodes, edges = [args[0]], []
        elif op == 'lineTo':
            if args[0] != nodes[-1]:
                edges.append(('lineTo', ()))
                nodes.append(args[0])
        elif op == 'curveTo':
            if len(args) != 3:
                raise ValueError('Expected cubic CFF curves')
            edges.append(('curveTo', args[:-1]))
            nodes.append(args[-1])
        elif op == 'closePath':
            if len(nodes) > 1:
                if nodes[-1] == nodes[0]:
                    nodes.pop()
                else:
                    edges.append(('lineTo', ()))
                assert len(nodes) == len(edges)
                contours.append((nodes, edges))
        else:
            raise ValueError(f'Unsupported source outline command: {op}')
    return contours


def refine_source(recording: RecordingPen, plan: dict) -> tuple[RecordingPen, int]:
    """Replay local edits against original edge indices, before condensation.

    Node/control changes and full path replacements are gathered first. This
    prevents new chamfer nodes from shifting indices for later edits.
    """
    if plan.get('source_outline_sha256') and hashlib.sha256(repr(recording.value).encode()).hexdigest() != plan['source_outline_sha256']:
        raise ValueError('Local refinement source outline differs from its captured anchors')
    contours = get_contours(recording)
    expected = plan['expected_contour_nodes']
    if [len(nodes) for nodes, _edges in contours] != expected:
        raise ValueError('Refinement source contour topology differs from the reviewed seed')
    nodes = [[list(point) for point in ns] for ns, _es in contours]
    edges = [[(op,[list(point) for point in controls]) for op,controls in es] for _ns,es in contours]
    replacements = {}
    for edit in plan.get('edge_path_replacements', []):
        ci, ei = edit['contour'], edit['edge']
        original = contours[ci][0]
        if list(original[ei]) != edit['start'] or list(original[(ei+1)%len(original)]) != edit['end']:
            raise ValueError('Refinement edge anchors differ from reviewed coordinates')
        replacements[(ci,ei)] = edit['new_segments']
    for edit in plan.get('contour_translations', []):
        dx, dy = edit['delta']
        for ci in edit['contours']:
            for point in nodes[ci]:
                point[0] += dx
                point[1] += dy
            for _op, controls in edges[ci]:
                for point in controls:
                    point[0] += dx
                    point[1] += dy
    for edit in plan.get('node_deltas', []):
        dx, dy = edit['delta']
        for ni in edit['nodes']:
            point = nodes[edit['contour']][ni]
            point[0] += dx
            point[1] += dy
    for edit in plan.get('control_deltas', []):
        dx, dy = edit['delta']
        for control in edit['controls']:
            point = edges[edit['contour']][edit['edge']][1][control]
            point[0] += dx
            point[1] += dy
    for edit in plan.get('edge_replacements', []):
        ci, ei = edit['contour'], edit['edge']
        if edit['operator'] != 'lineTo':
            raise ValueError('Only reviewed straight edge replacements are supported')
        end = nodes[ci][(ei+1)%len(nodes[ci])]
        replacements[(ci,ei)] = [['lineTo', end]]
    result = RecordingPen()
    for ci, ns in enumerate(nodes):
        result.moveTo(tuple(ns[0]))
        for ei, (op, controls) in enumerate(edges[ci]):
            end = ns[(ei+1)%len(ns)]
            if (ci,ei) in replacements:
                segments = replacements[(ci,ei)]
                if list(segments[-1][-1]) != end:
                    raise ValueError('Replacement path does not rejoin the original contour')
                for operator, *points in segments:
                    getattr(result,operator)(*[tuple(point) for point in points])
            elif op == 'lineTo':
                result.lineTo(tuple(end))
            else:
                result.curveTo(*[tuple(point) for point in controls],tuple(end))
        result.closePath()
    operations = sum(len(plan.get(key, [])) for key in (
        'contour_translations','node_deltas','control_deltas','edge_replacements','edge_path_replacements'))
    return result, operations


def stylize(source: RecordingPen, radius: float, chamfer: float) -> tuple[RecordingPen, dict]:
    """Soften long convex orthogonal joins; chamfer selected upper-right corners.

    CFF source exterior contours are counterclockwise. Positive line-line turns
    are convex ink corners. No holes, curved joins or short stem joints are moved.
    The edit only removes a tiny corner of existing ink, so counters stay open.
    """
    result = RecordingPen()
    edits = dict(rounded=0, chamfered=0)
    for nodes, edges in get_contours(source):
        before = list(nodes)
        after = list(nodes)
        corner = [None] * len(nodes)
        for i, p in enumerate(nodes):
            if edges[i-1][0] != 'lineTo' or edges[i][0] != 'lineTo':
                continue
            prev, nxt = nodes[i-1], nodes[(i+1) % len(nodes)]
            a = (p[0]-prev[0], p[1]-prev[1])
            b = (nxt[0]-p[0], nxt[1]-p[1])
            la, lb = math.hypot(*a), math.hypot(*b)
            if min(la, lb) < 32:
                continue
            u, v = (a[0]/la, a[1]/la), (b[0]/lb, b[1]/lb)
            if abs(u[0]*v[0]+u[1]*v[1]) > .025:
                continue
            if u[0]*v[1]-u[1]*v[0] < .98:
                continue
            if min(abs(u[0]), abs(u[1])) > .012 or min(abs(v[0]), abs(v[1])) > .012:
                continue
            bevel = chamfer > 0 and u[1] > .98 and v[0] < -.98
            distance = min(chamfer if bevel else radius, la*.18, lb*.18)
            if distance < 2:
                continue
            before[i] = (p[0]-u[0]*distance, p[1]-u[1]*distance)
            after[i] = (p[0]+v[0]*distance, p[1]+v[1]*distance)
            corner[i] = 'chamfered' if bevel else 'rounded'
            edits[corner[i]] += 1
        result.moveTo(after[0])
        for i, (op, controls) in enumerate(edges):
            j = (i+1) % len(nodes)
            if op == 'lineTo':
                result.lineTo(before[j])
            else:
                result.curveTo(*controls, before[j])
            if corner[j] == 'rounded':
                # Quadratic corner represented by an exact cubic conversion.
                p = nodes[j]
                a, b = before[j], after[j]
                c1 = (a[0]+(p[0]-a[0])*2/3, a[1]+(p[1]-a[1])*2/3)
                c2 = (b[0]+(p[0]-b[0])*2/3, b[1]+(p[1]-b[1])*2/3)
                result.curveTo(c1, c2, b)
            elif corner[j] == 'chamfered':
                result.lineTo(after[j])
        result.closePath()
    return result, edits


def notdef_pen() -> RecordingPen:
    p = RecordingPen()
    for contour in [[(80,0),(580,0),(580,760),(80,760)],[(120,40),(120,720),(540,720),(540,40)]]:
        p.moveTo(contour[0])
        for node in contour[1:]:
            p.lineTo(node)
        p.closePath()
    return p


def glyph_name(c: str) -> str:
    return f'uni{ord(c):04X}'


def symbol_outline(plan: dict, weight: str) -> RecordingPen:
    pen = RecordingPen()
    methods = dict(moveTo=pen.moveTo, lineTo=pen.lineTo, curveTo=pen.curveTo, closePath=pen.closePath)
    for contour in plan['outlines'][weight]:
        for operator, points in contour:
            methods[operator](*[tuple(point) for point in points])
    return pen


def build_outlines(seed: TTFont, characters: str, config: dict, refinements: dict,
                   custom_symbols: dict, dense_refinements: dict | None = None,
                   ttf14_refinements: dict | None = None,
                   wao_symbols: dict | None = None) -> tuple[dict, dict, dict]:
    outlines = {'.notdef': notdef_pen()}
    metrics = {'.notdef': (660, 80)}
    changes = {}
    source_set = seed.getGlyphSet()
    cmap = seed.getBestCmap()
    # Compatibility codepoints can map to the same original glyph. Reuse an
    # existing glyph's captured plan so its newly included alias stays identical.
    # This introduces no new optical plan and leaves the reviewed glyph intact.
    plan_characters = (set(refinements['glyphs'])
                       | set((dense_refinements or {}).get('glyphs', {}))
                       | set((ttf14_refinements or {}).get('glyphs', {})))
    source_plans = {}
    for character in sorted(plan_characters, key=ord):
        if ord(character) in cmap:
            source_plans.setdefault(cmap[ord(character)], []).append(character)
    for c in characters:
        if c in (wao_symbols or {}):
            style = 'Regular' if config['source'] == 'Regular' else 'Display'
            plan = wao_symbols[c]['variants'][style]
            final = wao_outline(plan)
            bounds = BoundsPen(None)
            final.replay(bounds)
            name = glyph_name(c)
            outlines[name] = final
            metrics[name] = (plan['advance'], round(bounds.bounds[0]))
            changes[c] = dict(rounded=0, chamfered=0, refinement_operations=0, wao_symbol=1)
            continue
        original = RecordingPen()
        plan_character = c
        if c in custom_symbols:
            original = symbol_outline(custom_symbols[c], config['source'])
            width = custom_symbols[c]['source_advance']
        else:
            glyph = source_set[cmap[ord(c)]]
            glyph.draw(original)
            width = glyph.width
            aliases = source_plans.get(cmap[ord(c)], [])
            if c not in plan_characters and aliases:
                if len(aliases) != 1:
                    raise ValueError('Ambiguous existing plans for shared source glyph')
                plan_character = aliases[0]
        if is_han(c) or ord(c) > 0x2E7F or c in custom_symbols:
            sx = config['han_scale']
            advance = config['han_width']
            dx = (advance-width*sx)/2
        else:
            sx = config['latin_scale']
            advance = max(180, round(width*sx+12))
            dx = 6
        operations = 0
        if plan_character in refinements['glyphs']:
            original, operations = refine_source(original, refinements['glyphs'][plan_character][config['source']])
        dense_plan = (dense_refinements or {}).get('glyphs', {}).get(plan_character, {}).get(config['source'])
        if dense_plan:
            original, dense_operations = refine_source(original, dense_plan)
            operations += dense_operations
        ttf14_plan = (ttf14_refinements or {}).get('glyphs', {}).get(plan_character, {}).get(config['source'])
        if ttf14_plan:
            original, ttf14_operations = refine_source(original, ttf14_plan)
            operations += ttf14_operations
        raw = RecordingPen()
        original.replay(TransformPen(raw, Transform(sx, 0, 0, 1, dx, 0)))
        styled, edits = stylize(raw, config['radius'], config['chamfer'])
        edits['refinement_operations'] = operations
        if plan_character != c:
            edits['refinement_source_character'] = plan_character
        bounds = BoundsPen(None)
        styled.replay(bounds)
        name = glyph_name(c)
        outlines[name] = styled
        metrics[name] = (advance, round(bounds.bounds[0]) if bounds.bounds else 0)
        changes[c] = edits
    return outlines, metrics, changes


def make_font(outlines: dict, metrics: dict, characters: str, config: dict, truetype: bool,
              new_symbol_characters: str = '') -> TTFont:
    metrics = dict(metrics)
    family = config['family']
    postscript = family.replace(' ', '') + '-Regular'
    builder = FontBuilder(1000, isTTF=truetype)
    builder.setupGlyphOrder(list(outlines))
    builder.setupCharacterMap({ord(c): glyph_name(c) for c in characters})
    if truetype:
        glyphs = {}
        for name, recording in outlines.items():
            pen = TTGlyphPen(None)
            recording.replay(Cu2QuPen(pen, max_err=.6, reverse_direction=True))
            glyphs[name] = pen.glyph()
        builder.setupGlyf(glyphs)
        # TrueType xMin bounds include off-curve controls. For new symbols use
        # that bound as LSB, so glyphSet/FreeType do not shift the outline by
        # the difference from the CFF ink bound. Keep all old metrics intact.
        for character in new_symbol_characters:
            name = glyph_name(character)
            glyph = glyphs[name]
            if glyph.numberOfContours > 0:
                metrics[name] = (metrics[name][0], glyph.xMin)
    else:
        charstrings = {}
        for name, recording in outlines.items():
            pen = T2CharStringPen(metrics[name][0], None)
            recording.replay(pen)
            charstrings[name] = pen.getCharString()
        builder.setupCFF(postscript, dict(FullName=family, FamilyName=family, Weight='Regular',
                         version=FONT_VERSION, Notice=COPYRIGHT), charstrings, {})
    builder.setupHorizontalMetrics(metrics)
    # Includes the source's tall ASCII vertical bar and descending punctuation.
    builder.setupHorizontalHeader(ascent=1160, descent=-320, lineGap=0)
    builder.setupNameTable(dict(
        familyName=family, styleName='Regular', uniqueFontIdentifier=FONT_VERSION + ';' + postscript,
        fullName=family, psName=postscript, version='Version '+FONT_VERSION+'; common Chinese UI vocabulary',
        copyright=COPYRIGHT, licenseDescription=LICENSE,
        licenseInfoURL='https://openfontlicense.org/', typographicFamily=family,
        typographicSubfamily='Regular',
    ))
    builder.setupOS2(version=4, sTypoAscender=1160, sTypoDescender=-320, sTypoLineGap=0,
                     usWinAscent=1160, usWinDescent=320, usWeightClass=400,
                     usWidthClass=4, fsType=0, fsSelection=0xC0,
                     sCapHeight=733, sxHeight=543)
    builder.setupPost()
    builder.setupMaxp()
    builder.font['head'].fontRevision = float(FONT_VERSION)
    # Fixed specimen timestamp permits byte-identical rebuilds.
    builder.font['head'].created = 3875904000
    builder.font['head'].modified = 3875904000
    builder.font.recalcTimestamp = False
    return builder.font


def render_glyph_study(project: Path) -> None:
    """Render the real outlines at high resolution for a static comparison."""
    from PIL import Image, ImageDraw, ImageFont
    scale, width, height = 4, 1400, 720
    image = Image.new('RGB', (width*scale, height*scale), '#e3e8e5')
    draw = ImageDraw.Draw(image)
    # Use the supplied baseline also for labels: no machine-specific font needed.
    label_path = str(project / 'sources' / 'AincradSeed-v030-Regular.otf')
    label = ImageFont.truetype(label_path, 14*scale)
    title = ImageFont.truetype(label_path, 26*scale)
    draw.text((50*scale, 30*scale), 'AINCRAD UI SC / CHINESE TYPE STUDY',
              font=title, fill='#34454d')
    text = '系统设置  文件管理  网络连接'
    rows = [
        ('SOURCE HAN SANS SC / BASELINE', 'sources/AincradSeed-v030-Regular.otf', '#42545c', None),
        ('AINCRAD UI SC / REGULAR', 'fonts/AincradUISc-Regular.otf', '#42545c', None),
        ('AINCRAD UI SC / DISPLAY', 'fonts/AincradUISc-Display.otf', '#eef1e8', '#30444e'),
    ]
    for i, (name, path, ink, background) in enumerate(rows):
        y = (110+i*195)*scale
        if background:
            draw.rounded_rectangle((28*scale, y-13*scale, 1372*scale, y+155*scale),
                                   radius=3*scale, fill=background)
        draw.text((50*scale,y), name, font=label, fill='#b5c4c3' if background else '#75898e')
        font = ImageFont.truetype(str(project / path), 70*scale)
        draw.text((50*scale,y+30*scale), text, font=font, fill=ink, anchor='lt')
        draw.line((50*scale,y+164*scale,1350*scale,y+164*scale), fill='#a7b7b7', width=scale)
    image.resize((width,height), Image.Resampling.LANCZOS).save(project / 'glyph-study.png')


def render_refinement_study(project: Path) -> None:
    """Keep old/new pairs on the same background at identical scale and origins."""
    from PIL import Image, ImageDraw, ImageFont
    scale, width, height = 3, 1400, 1000
    image = Image.new('RGB', (width*scale,height*scale), '#e8ece8')
    draw = ImageDraw.Draw(image)
    label_path = str(project / 'sources' / 'AincradSeed-v030-Regular.otf')
    title = ImageFont.truetype(label_path,25*scale)
    label = ImageFont.truetype(label_path,14*scale)
    draw.text((60*scale,30*scale),'AINCRAD UI SC / COMMON UI REFINEMENT',font=title,fill='#34454d')
    draw.text((60*scale,80*scale),'SAME SIZE / SAME BACKGROUND / UNCHANGED ADVANCES',font=label,fill='#70838a')
    text = '设置 保存 取消 返回'
    for i,(style,version) in enumerate([('Regular','0.2'),('Regular','0.3'),('Display','0.2'),('Display','0.3')]):
        y=(142+i*206)*scale
        if version == '0.2':
            source = TTFont(project / 'fonts' / f'AincradUISc-v020-{style}.woff2')
            source.flavor = None
            buffer = BytesIO()
            source.save(buffer)
            source.close()
            buffer.seek(0)
            font = ImageFont.truetype(buffer,124*scale)
        else:
            font = ImageFont.truetype(str(project / 'fonts' / f'AincradUISc-{style}.otf'),124*scale)
        draw.text((60*scale,y),style.upper()+' / v'+version+(' BEFORE' if version=='0.2' else ' REFINED'),
                  font=label,fill='#70838a')
        draw.text((60*scale,y+36*scale),text,font=font,fill='#34454d',anchor='lt')
        draw.line((60*scale,y+182*scale,1340*scale,y+182*scale),fill='#c1cecb',width=scale)
    image.resize((width,height),Image.Resampling.LANCZOS).save(project / 'refinement-study.png')


def wao_outline(plan: dict) -> RecordingPen:
    """Replay one explicitly reviewed final-unit symbol without restyling it."""
    if type(plan.get('advance')) is not int or not 0 < plan['advance'] <= 2000:
        raise ValueError('Invalid WAO symbol advance')
    result = RecordingPen()
    arities = dict(moveTo=1, lineTo=1, curveTo=3, closePath=0)
    for operator, points in plan['outline']:
        if operator not in arities or len(points) != arities[operator]:
            raise ValueError('Invalid WAO symbol outline command')
        if any(len(point) != 2 or any(type(value) not in (int, float)
                                      or not math.isfinite(value) or abs(value) > 4000
                                      for value in point) for point in points):
            raise ValueError('Invalid WAO symbol coordinate')
        getattr(result, operator)(*[tuple(point) for point in points])
    if not get_contours(result):
        raise ValueError('WAO symbol must contain closed visible contours')
    bounds = BoundsPen(None)
    result.replay(bounds)
    if not bounds.bounds or bounds.bounds[2] <= bounds.bounds[0] or bounds.bounds[3] <= bounds.bounds[1]:
        raise ValueError('WAO symbol has no visible ink bounds')
    return result


def load_wao_symbols(project: Path) -> tuple[dict, dict | None]:
    extension_path = project / 'data' / 'wao-symbol-extension.json'
    if not extension_path.is_file():
        return {}, None
    extension = json.loads(extension_path.read_text(encoding='utf-8'))
    original = extension['original_characters']
    source = extension['source_characters']
    if (extension['characters'] != WAO_CHARACTERS
            or not isinstance(original, str) or len(original) != 8
            or set(original) != set(WAO_ORIGINAL_CHARACTERS)
            or not isinstance(source, str) or len(source) != 16
            or set(source) != set(WAO_CHARACTERS) - set(original)):
        raise ValueError('WAO extension must contain exactly the requested24/source16/original8 symbols')
    path = project / 'data' / 'wao-symbols-v030.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    if (data['version'] != VERSION or data['upm'] != 1000
            or data['license'] != 'SIL Open Font License 1.1'
            or set(data['glyphs']) != set(WAO_CHARACTERS)):
        raise ValueError('Invalid WAO outline plan, version, scope, UPM or license')
    for character, glyph in data['glyphs'].items():
        origin = 'original-geometry' if character in original else 'source-derived'
        if glyph['origin'] != origin or set(glyph['variants']) != set(VARIANTS):
            raise ValueError('WAO origin or variant declaration differs from its scope')
        for plan in glyph['variants'].values():
            wao_outline(plan)
    return data['glyphs'], dict(file=path.relative_to(project).as_posix(), sha256=sha256(path),
                               extension_file=extension_path.relative_to(project).as_posix(),
                               extension_sha256=sha256(extension_path), characters=WAO_CHARACTERS,
                               original_characters=original, source_characters=source,
                               upm=1000, license='SIL Open Font License 1.1')


def load_charset_extensions(project: Path) -> tuple[str, dict]:
    """Read explicit application additions from a reproducible project input."""
    path = project / 'data' / 'charset-extensions.json'
    extensions = json.loads(path.read_text(encoding='utf-8'))
    characters = extensions['characters']
    if (not isinstance(characters, str) or not characters
            or len(characters) != len(set(characters))
            or not all(is_han(c) for c in characters)):
        raise ValueError('Charset extensions must be distinct Han characters')
    symbol_path = project / 'data' / 'symbol-extensions.json'
    symbols = json.loads(symbol_path.read_text(encoding='utf-8'))['characters']
    if (not isinstance(symbols, str) or not symbols or len(symbols) != len(set(symbols))
            or any(is_han(c) or c.isspace() or ord(c) < 0x20 for c in symbols)):
        raise ValueError('Symbol extensions must be distinct visible non-Han characters')
    hexagram_path = project / 'data' / 'hexagrams.json'
    hexagrams = json.loads(hexagram_path.read_text(encoding='utf-8'))['records']
    if (len(hexagrams) != 64 or [entry['number'] for entry in hexagrams] != list(range(1, 65))
            or [ord(entry['character']) for entry in hexagrams] != list(range(0x4DC0, 0x4E00))):
        raise ValueError('Hexagrams must contain the 64 ordered Unicode Yijing symbols')
    hexagram_text = ''.join(entry['character'] + entry['name'] + entry['full_name']
                            + ''.join(entry.get('aliases', [])) for entry in hexagrams)
    gb_path = project / 'data' / 'gb2312-han-extension.json'
    gb_characters, gb_info = '', None
    if gb_path.is_file():
        gb_characters = json.loads(gb_path.read_text(encoding='utf-8'))['characters']
        if gb_characters != gb2312_han_characters():
            raise ValueError('GB2312 Han extension differs from the independently decoded two-level mapping')
        gb_info = dict(file=gb_path.relative_to(project).as_posix(), sha256=sha256(gb_path),
                       han_count=6763, level_one_han_count=3755, level_two_han_count=3008,
                       scope='Han characters only, not every GB2312 symbol or encoding requirement')
    sourcehan_path = project / 'data' / 'sourcehan-han-extension.json'
    sourcehan_characters, sourcehan_info = '', None
    if sourcehan_path.is_file():
        manifest = json.loads(sourcehan_path.read_text(encoding='utf-8'))
        sourcehan_characters = manifest['characters']
        coverage = json.loads((project / 'data' / 'source-font-coverage.json').read_text(encoding='utf-8'))
        if (not isinstance(sourcehan_characters, str) or not sourcehan_characters
                or sourcehan_characters != ''.join(sorted(set(sourcehan_characters), key=ord))
                or not all(is_han(c) for c in sourcehan_characters)
                or not set(gb_characters + characters) <= set(sourcehan_characters)):
            raise ValueError('Source Han extension must be sorted distinct Han including previous Han')
        for weight in ('Regular', 'Medium'):
            record = manifest['sources'][weight]
            expected_file = f'sources/AincradSeed-sourcehan-{weight}.otf'
            if record['file'] != expected_file or sha256(project / expected_file) != record['sha256']:
                raise ValueError('Source Han extension seed identity differs')
            with TTFont(project / expected_file, recalcTimestamp=False) as seed:
                actual_han = ''.join(chr(point) for point in sorted(seed.getBestCmap()) if is_han(chr(point)))
            if (sourcehan_characters != actual_han
                    or len(actual_han) != coverage['faces'][weight]['effective_han_codepoints']):
                raise ValueError('Source Han manifest differs from actual seed Han coverage')
        sourcehan_info = dict(file=sourcehan_path.relative_to(project).as_posix(),
                              sha256=sha256(sourcehan_path), han_count=len(sourcehan_characters),
                              coverage_file='data/source-font-coverage.json',
                              coverage_sha256=sha256(project / 'data' / 'source-font-coverage.json'),
                              scope='All unified and compatibility Han mapped by the local Source Han Sans SC v1.004 faces, including supplementary-plane characters')
    info = dict(file=path.relative_to(project).as_posix(),
        sha256=sha256(path), han_count=len(characters),
        symbols=dict(file=symbol_path.relative_to(project).as_posix(),
                     sha256=sha256(symbol_path), character_count=len(symbols)),
        hexagrams=dict(file=hexagram_path.relative_to(project).as_posix(),
                       sha256=sha256(hexagram_path), symbol_count=64))
    if gb_info:
        info['gb2312_han'] = gb_info
    if sourcehan_info:
        info['sourcehan_han'] = sourcehan_info
    _wao_glyphs, wao_info = load_wao_symbols(project)
    if wao_info:
        info['wao_symbols'] = wao_info
    return (characters + symbols + hexagram_text + gb_characters + sourcehan_characters
            + (wao_info['characters'] if wao_info else '')), info


def load_symbol_plan(project: Path) -> tuple[dict, dict]:
    path = project / 'data' / 'symbols-v030.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    glyphs = dict(manifest['glyphs'])
    requested = json.loads((project/'data'/'symbol-extensions.json').read_text(encoding='utf-8'))['characters']
    if manifest['upm'] != 1000 or not glyphs or not set(glyphs) <= set(requested):
        raise ValueError('Invalid custom symbol plan or symbols outside the request')
    hexagram_path = project / 'data' / 'hexagram-outlines-v030.json'
    hexagram_manifest = json.loads(hexagram_path.read_text(encoding='utf-8'))
    hexagram_glyphs = hexagram_manifest['glyphs']
    if (hexagram_manifest['upm'] != 1000 or set(map(ord, hexagram_glyphs)) != set(range(0x4DC0, 0x4E00))
            or set(glyphs) & set(hexagram_glyphs)):
        raise ValueError('Invalid or duplicate 64-hexagram outline plan')
    glyphs.update(hexagram_glyphs)
    for character, glyph in glyphs.items():
        if len(character) != 1 or glyph['source_advance'] != 1000 or glyph['layout'] != 'cjk-cell':
            raise ValueError('Invalid custom symbol character or cell')
        for weight in ('Regular', 'Medium'):
            symbol_outline(glyph, weight)
    characters = ''.join(sorted(glyphs, key=ord))
    info = dict(file=path.relative_to(project).as_posix(),sha256=sha256(path),
                characters=characters,count=len(glyphs),baseline_excluded_characters=characters,
                additional_manifests=[dict(file=hexagram_path.relative_to(project).as_posix(),
                                           sha256=sha256(hexagram_path), count=64)])
    wao_glyphs, wao_info = load_wao_symbols(project)
    if wao_info:
        glyphs.update({c:wao_glyphs[c] for c in wao_info['original_characters']})
    return glyphs, info


def vocabulary_characters(vocabulary: dict, previous: str, extensions: str = '') -> str:
    """Cover UI phrases, basic common Han, application additions, and old glyphs."""
    phrases = [phrase for category in vocabulary['categories'] for phrase in category['phrases']]
    return ''.join(sorted(set(previous + ''.join(phrases) + basic_han_characters() + extensions), key=ord))


def basic_han_characters() -> str:
    """Decode the reproducible GB2312 level-one region with Python's codec.

    This supplies ordinary grammar/name characters beyond the finite UI corpus.
    It is a coverage basis, not a claim that the font covers the complete GB2312.
    """
    result=set()
    for lead in range(0xB0,0xD8):
        for trail in range(0xA1,0xFF):
            try:character=bytes((lead,trail)).decode('gb2312')
            except UnicodeDecodeError:continue
            if is_han(character):result.add(character)
    if len(result)!=3755:raise ValueError('Unexpected basic common Han mapping')
    return ''.join(sorted(result,key=ord))


def gb2312_han_characters() -> str:
    """Return exactly the 6,763 Han in GB2312 levels one and two."""
    result = set()
    for lead in range(0xB0, 0xF8):
        for trail in range(0xA1, 0xFF):
            try:
                character = bytes((lead, trail)).decode('gb2312')
            except UnicodeDecodeError:
                continue
            if is_han(character):
                result.add(character)
    if len(result) != 6763:
        raise ValueError('Unexpected GB2312 two-level Han mapping')
    return ''.join(sorted(result, key=ord))


def render_coverage_sheets(project: Path, han: str) -> None:
    """Render every Han glyph without fallback and keep a compact review sheet."""
    from PIL import Image, ImageDraw, ImageFont
    columns, cell, margin = 32, 46, 28
    reports = {}
    for style in VARIANTS:
        font = ImageFont.truetype(str(project/'fonts'/f'AincradUISc-{style}.otf'),32)
        label = ImageFont.truetype(str(project/'sources'/'AincradSeed-v030-Regular.otf'),14)
        empty,pages=[],[]
        page_size=columns*32
        for start in range(0,len(han),page_size):
            part=han[start:start+page_size]
            page_index=start//page_size+1
            image=Image.new('RGB',(columns*cell+margin*2,math.ceil(len(part)/columns)*cell+95),'#edf1ed')
            draw=ImageDraw.Draw(image)
            draw.text((margin,18),f'AINCRAD UI SC v0.3 / {style.upper()} / PAGE {page_index} / {len(han)} HAN',font=label,fill='#34454d')
            for i,character in enumerate(part):
                if font.getmask(character).getbbox() is None:empty.append(character)
                draw.text((margin+(i%columns)*cell,63+(i//columns)*cell),character,font=font,fill='#34454d')
            filename=f'coverage-sheet-{style}'+('' if page_index==1 else f'-{page_index:02d}')+'.png'
            image.save(project/filename)
            pages.append(filename)
        reports[style] = dict(rendered_han_characters=len(han),empty_glyphs=''.join(empty),pages=pages)
        if empty:
            raise ValueError(f'Empty visible Han glyphs in {style}: {empty}')
    write_json(project/'data'/'raster-verification.json',dict(version=VERSION,font_size_px=32,variants=reports,ok=True))


def render_symbol_study(project: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont
    symbols = json.loads((project/'data'/'symbol-extensions.json').read_text(encoding='utf-8'))['characters']
    section_height = 60 + math.ceil(len(symbols)/16)*90
    image = Image.new('RGB', (1500, section_height*2+20), '#edf1ed')
    draw = ImageDraw.Draw(image)
    label = ImageFont.truetype(str(project/'fonts'/'AincradUISc-Regular.ttf'),16)
    for row, style in enumerate(VARIANTS):
        font = ImageFont.truetype(str(project/'fonts'/f'AincradUISc-{style}.ttf'),42)
        draw.text((24,14+row*section_height),style,font=label,fill='#34454d')
        for index, character in enumerate(symbols):
            x,y = 28+(index%16)*90,55+row*section_height+(index//16)*90
            draw.text((x,y),character,font=font,fill='#34454d')
            draw.text((x,y+53),f'{ord(character):04X}',font=label,fill='#71838c')
    image.save(project/'symbol-study.png')


def render_hexagram_study(project: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont
    records = json.loads((project/'data/hexagrams.json').read_text(encoding='utf-8'))['records']
    image = Image.new('RGB', (1440, 1450), '#edf1ed')
    draw = ImageDraw.Draw(image)
    for section, style in enumerate(VARIANTS):
        label = ImageFont.truetype(str(project/'fonts'/f'AincradUISc-{style}.ttf'), 16)
        symbol = ImageFont.truetype(str(project/'fonts'/f'AincradUISc-{style}.ttf'), 44)
        draw.text((25, section*720+12), style+' / 64 HEXAGRAMS', font=label, fill='#34454d')
        for index, entry in enumerate(records):
            x, y = 24+(index % 8)*178, section*720+50+(index//8)*82
            draw.text((x, y), entry['character'], font=symbol, fill='#34454d')
            draw.text((x+49, y+12), f"{entry['number']:02d} "+entry['name'], font=label, fill='#34454d')
            draw.text((x+49, y+36), entry['full_name'], font=label, fill='#71838c')
    image.save(project/'hexagram-study.png')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir', type=Path, default=DEFAULT_PROJECT)
    args = parser.parse_args()
    project = args.project_dir.resolve()
    for style in VARIANTS:
        reference = project / 'fonts' / f'AincradUISc-v020-{style}.woff2'
        if not reference.is_file():
            raise FileNotFoundError(f'v0.2 comparison font is required for v0.3: {reference}')
    refinements_path = project / 'data' / 'refinements-v030.json'
    refinements = json.loads(refinements_path.read_text(encoding='utf-8'))
    dense_path = project/'data/dense-refinements-v030.json'
    dense_refinements = json.loads(dense_path.read_text(encoding='utf-8'))
    if set(dense_refinements['glyphs']) != set('羁螣攥黛'):
        raise ValueError('Dense refinement scope must be the four reviewed characters')
    ttf14_path = project/'data/ttf14-refinements-v030.json'
    ttf14_refinements = json.loads(ttf14_path.read_text(encoding='utf-8'))
    if (set(ttf14_refinements['glyphs']) != set('攥螣')
            or ttf14_refinements['prerequisite_plan']['sha256'] != sha256(dense_path)
            or any(set(item) != {'issue', 'Regular'} for item in ttf14_refinements['glyphs'].values())):
        raise ValueError('TTF14 refinements must reference the captured dense plan and only two Regular glyphs')
    vocabulary = json.loads((project/'data'/'ui-vocabulary.json').read_text(encoding='utf-8'))
    extensions, extension_info = load_charset_extensions(project)
    custom_symbols, symbol_info = load_symbol_plan(project)
    wao_glyphs, wao_info = load_wao_symbols(project)
    symbol_characters = (json.loads((project/'data'/'symbol-extensions.json').read_text(encoding='utf-8'))['characters']
                         + ''.join(chr(point) for point in range(0x4DC0, 0x4E00))
                         + (wao_info['characters'] if wao_info else ''))
    with TTFont(project/'fonts'/'AincradUISc-v020-Regular.woff2') as previous:
        previous_characters = ''.join(map(chr,previous.getBestCmap()))
    fonts_dir = project / 'fonts'
    fonts_dir.mkdir(parents=True, exist_ok=True)
    characters = vocabulary_characters(vocabulary,previous_characters,extensions)
    han = ''.join(c for c in characters if is_han(c))
    new_refined = refinements['new_refined_characters']
    charset = dict(version=VERSION, characters=characters, han_characters=han,
                   han_count=len(han), character_count=len(characters),
                   description='Common UI vocabulary OFL derivative; arbitrary Chinese prose and names may require fallback.',
                   refined_characters=refinements['refined_characters'],
                   dense_refined_characters=dense_refinements['characters'],
                   ttf14_refined_characters=ttf14_refinements['characters'],
                   basis=dict(basic_common_han_count=len(basic_han_characters()),
                              vocabulary_han_count=len({c for category in vocabulary['categories'] for phrase in category['phrases'] for c in phrase if is_han(c)}),
                              application_extensions=extension_info,
                              note='Basic common Han plus actual UI vocabulary, explicit application additions and previous glyphs; not complete GB2312 or arbitrary Chinese prose.'),
                   expansion=dict(previous_version='0.2.0',previous_character_count=len(previous_characters),
                                  added_characters=''.join(c for c in characters if c not in previous_characters),
                                  refined_existing_characters=''.join(c for c in new_refined if c in previous_characters)))
    if 'gb2312_han' in extension_info:
        charset['basis']['gb2312_han_count'] = 6763
        charset['basis']['note'] = 'All GB2312 level-one and level-two Han plus retained UI/application characters; not every GB2312 symbol or arbitrary Chinese prose.'
    if 'sourcehan_han' in extension_info:
        charset['basis']['sourcehan_han_count'] = extension_info['sourcehan_han']['han_count']
        charset['basis']['note'] = 'All Han codepoints actually mapped by the local Source Han Sans SC v1.004 faces plus retained UI/application characters; includes unified, supplementary and compatibility ideographs, not every Unicode Han character.'
        charset['description'] = 'Source Han Sans SC v1.004 Han coverage with the existing Aincrad UI style and preserved UI/application symbols.'
    if wao_info:
        charset['wao_symbols'] = wao_info['characters']
    write_json(project / 'data' / 'charset.json', charset)
    (project/'data'/'font-catalog.js').write_text(
        'window.AINCRAD_CATALOG = '+json.dumps(dict(charset=charset,vocabulary=vocabulary),ensure_ascii=False,separators=(',',':'))+';\n',encoding='utf-8')
    source_records, font_records, source_reviews = {}, {}, {}
    for style, config in VARIANTS.items():
        seed, info = acquire_seed(project, config['source'], characters)
        reviewed_sha, source_review = reviewed_source_hash(project, seed, config['source'], info)
        if reviewed_sha != refinements['source_sha256_by_weight'][config['source']]:
            raise ValueError('Source seed hash differs from the reviewed refinement source')
        if config['source'] in dense_refinements['source_sha256_by_weight'] and reviewed_sha != dense_refinements['source_sha256_by_weight'][config['source']]:
            raise ValueError('Source seed hash differs from the dense refinement source')
        if config['source'] in ttf14_refinements['source_sha256_by_weight'] and reviewed_sha != ttf14_refinements['source_sha256_by_weight'][config['source']]:
            raise ValueError('Source seed hash differs from the TTF14 refinement source')
        if source_review:
            source_reviews[style] = source_review
        source_records[style] = info
        if style == 'Regular':
            # Same selection of unmodified source outlines for a fair visual comparison.
            baseline = TTFont(project / info['file'], recalcTimestamp=False)
            baseline.flavor = 'woff2'
            baseline.save(fonts_dir / 'SourceHanSansSC-Baseline.woff2')
            baseline.close()
        outlines, metrics, edits = build_outlines(seed, characters, config, refinements, custom_symbols,
                                                 dense_refinements, ttf14_refinements, wao_glyphs)
        prefix = 'AincradUISc-' + style
        for extension, ttf in [('otf',False), ('ttf',True), ('woff2',False)]:
            font = make_font(outlines, metrics, characters, config, ttf, symbol_characters)
            font.flavor = 'woff2' if extension == 'woff2' else None
            path = fonts_dir / (prefix + '.' + extension)
            font.save(path)
            font.close()
            font_records[path.name] = dict(bytes=path.stat().st_size, sha256=sha256(path))
        font_records[style] = dict(config=config, edited_glyphs=sum(any(x.values()) for x in edits.values()),
                                   rounded_corners=sum(x['rounded'] for x in edits.values()),
                                   chamfered_corners=sum(x['chamfered'] for x in edits.values()),
                                   refined_characters=''.join(c for c in characters if edits[c]['refinement_operations']),
                                    refinement_operations=sum(x['refinement_operations'] for x in edits.values()),
                                    inherited_source_glyph_refinements={c: edits[c]['refinement_source_character']
                                                                      for c in characters if 'refinement_source_character' in edits[c]})
        seed.close()
    provenance_path = project / 'data' / 'provenance.json'
    if provenance_path.exists():
        old = json.loads(provenance_path.read_text(encoding='utf-8'))
        for weight, info in source_records.items():
            if 'source_file' not in info:
                info.update({k:v for k,v in old.get('sources', {}).get(weight, {}).items()
                             if k not in ('sha256','file')})
    write_json(provenance_path, dict(
        version=VERSION, origin='Source Han Sans SC v1.004, local licensed TTC, SC face 2',
        license='SIL Open Font License 1.1', sources=source_records, fonts=font_records,
        design_note='UI-vocabulary expansion with local counter, component-gap and terminal refinements; v0.2 eight-glyph design retained.',
        refinement_plan=dict(file='data/refinements-v030.json', sha256=sha256(refinements_path)),
        vocabulary=dict(file='data/ui-vocabulary.json',sha256=sha256(project/'data'/'ui-vocabulary.json'),
                        categories=len(vocabulary['categories']),phrases=sum(len(c['phrases']) for c in vocabulary['categories'])),
        charset_extensions=extension_info,
        custom_symbols=symbol_info,
        **({'wao_symbols':wao_info} if wao_info else {}),
        dense_refinements=dict(file=dense_path.relative_to(project).as_posix(), sha256=sha256(dense_path),
                               characters=dense_refinements['characters'], variants=['Regular']),
        ttf14_refinements=dict(file=ttf14_path.relative_to(project).as_posix(), sha256=sha256(ttf14_path),
                               characters=ttf14_refinements['characters'], variants=['Regular'],
                               primary_validation_format='ttf', primary_size_px=14, primary_dpr=1),
        source_expansion_review=source_reviews,
        source_url='https://github.com/adobe-fonts/source-han-sans',
    ))
    render_glyph_study(project)
    render_refinement_study(project)
    render_coverage_sheets(project,han)
    render_symbol_study(project)
    render_hexagram_study(project)
    print(json.dumps(dict(project=str(project), han=len(han), total_characters=len(characters),
                          files={k:v for k,v in font_records.items() if '.' in k}), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
