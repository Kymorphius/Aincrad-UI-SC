"""Verify the two Regular TTF14 refinements against the immutable previous ZIP.

Run from the workspace or unpacked package. --report writes JSON; otherwise
stdout contains it. --baseline-zip selects the archived dense14-hexagrams ZIP.
Missing baseline returns ok=null/exit2 rather than claiming regression success.
This tool does not launch browsers or alter fonts, plans, or historical reports.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
import math
from pathlib import Path
import sys
from zipfile import ZipFile

import PIL
from PIL import ImageFont, features
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

import build_aincrad_font as build
from verify_aincrad_dense_hexagrams import (
    DEFAULT_PROJECT, digest, fixed_roi_white, geometry, line_metrics, raster,
    recording, sha,
)


BASELINE_NAME = 'Aincrad-UI-SC-v0.3-dense14-hexagrams.zip'
BASELINE_SHA = 'fbb334a39f97a16426198bda98242e5cde04a237b415184c7be15569cfe5fd1d'
TARGETS = '攥螣'
SIZES = (13, 14, 15, 28)
# Frozen OLD design-space boxes, before this plan; no box follows the new ink.
# Whole-frame boxes measure density at the previous location, not recognition.
ROIS = {
    '攥': [
        ('eye_frame', [387, 380, 886, 655], True, 'Old source contour8 eye-frame corners.'),
        ('eye_lower_counter', [446, 418, 824, 467], False, 'Old dense source contour5 bounds.'),
        ('eye_middle_counter', [446, 494, 824, 543], False, 'Old dense source contour6 bounds.'),
        ('eye_upper_counter', [446, 571, 824, 617], False, 'Old dense source contour7 bounds.'),
        ('bamboo_eye_neck', [470, 645, 840, 690], False, 'Frozen diagnosis window across the old bamboo/eye joint.'),
        ('eye_silk_neck', [450, 341, 850, 380], False, 'Frozen diagnosis window between old eye and lower component.'),
    ],
    '螣': [
        ('lower_dot_counter', [695, 22, 815, 107], True, 'Old source contour2 bounds; moving inner/right dot boundary.'),
        ('lower_dot_root', [630, -27, 880, 107], True, 'Frozen candidate-selection window around dot/root and lower stroke.'),
        ('central_stem_crown', [630, 388.6262, 695, 432], False, 'Old dense contour5 crown; retained to expose local tradeoffs.'),
        ('moon_lower_counter', [166, 329, 288, 493], False, 'Original source contour6 bounds; geometry unchanged this round.'),
        ('worm_left_counter', [517, 159, 630, 266], False, 'Original source contour3 bounds.'),
        ('worm_right_counter', [695, 159, 813, 266], False, 'Original source contour4 bounds; previous quantization-sensitive window.'),
    ],
}
HINT_TABLES = ('fpgm', 'prep', 'cvt ', 'gasp', 'LTSH', 'hdmx', 'VDMX')


def table_bytes(font, tag):
    return bytes(font.reader[tag])


def normalized_head(font):
    data = bytearray(table_bytes(font, 'head'))
    data[8:12] = bytes(4)       # file checksum depends on edited outlines
    data[20:36] = bytes(16)    # creation/modification timestamps are metadata
    return bytes(data)


def raw_recording(font, c):
    pen = RecordingPen()
    font.getGlyphSet()[font.getBestCmap()[ord(c)]].draw(pen)
    return pen


def verify(project, baseline_path):
    problems, diagnostics = [], []
    def check(ok, message):
        if not ok:
            problems.append(message)
        return bool(ok)
    def load(name):
        return json.loads((project / name).read_text(encoding='utf-8'))
    result = {
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'baseline': {'file': str(baseline_path), 'available': baseline_path.is_file(), 'expected_sha256': BASELINE_SHA},
        'scope': 'Exact six-font regression plus anchored local source geometry and default-TTF fixed old-ROI grayscale diagnostics.',
        'scope_limits': [
            'Gray whitespace is a local density diagnostic; movement changes occupancy of a frozen old window. It does not establish readability or blind recognition.',
            'Pillow/FreeType native physical pixels are distinct from browser CSS pixels, DirectWrite, Flutter and device rendering.',
            'Proper intersection checks use adaptive flattening at0.25UPM; endpoint touches and collinear overlap are not classified.',
            'Some unchanged-source regions can change raster coverage because runtime hint fitting is glyph-dependent. Negative ROI deltas remain in this report.',
        ],
        'environment': {'pillow': PIL.__version__, 'freetype': features.version_module('freetype2')},
        'input_hashes': {}, 'font_hashes': {}, 'formats': {}, 'source_plan_review': {},
        'target_geometry': {}, 'raster_diagnostics': {}, 'fixed_roi_samples': [],
        'controls': [], 'problems': problems, 'diagnostics': diagnostics,
    }
    if not baseline_path.is_file():
        return {**result, 'ok': None, 'status': 'baseline_unavailable', 'regression_performed': False}
    archive_data = baseline_path.read_bytes()
    check(sha(archive_data) == BASELINE_SHA, 'Baseline ZIP hash mismatch')
    result['baseline']['sha256'] = sha(archive_data)
    prov, charset = load('data/provenance.json'), load('data/charset.json')
    base_plan, dense, local = (load('data/' + name) for name in
                                ('refinements-v030.json', 'dense-refinements-v030.json', 'ttf14-refinements-v030.json'))
    names = ['data/charset.json', 'data/provenance.json', 'data/source-v030.json',
             'data/refinements-v030.json', 'data/dense-refinements-v030.json',
             'data/ttf14-refinements-v030.json', 'data/hexagrams.json', 'data/hexagram-outlines-v030.json']
    for name in names:
        result['input_hashes'][name] = sha((project / name).read_bytes())
    check(set(local['characters']) == set(TARGETS) and set(local['glyphs']) == set(TARGETS) and
          all(set(value) == {'issue', 'Regular'} for value in local['glyphs'].values()), 'Local plan scope is not exactly two Regular glyphs')
    check(local['prerequisite_plan']['file'] == 'data/dense-refinements-v030.json' and
          local['prerequisite_plan']['sha256'] == result['input_hashes']['data/dense-refinements-v030.json'], 'Prerequisite dense plan hash mismatch')
    check(prov['ttf14_refinements']['sha256'] == result['input_hashes']['data/ttf14-refinements-v030.json'], 'Local plan provenance hash mismatch')
    expected = set(map(ord, charset['characters']))
    check(len(expected) == 4041 and all(cp in expected for cp in range(0x4DC0, 0x4E00)), 'Frozen release charset differs from4041-character scope')
    with ZipFile(BytesIO(archive_data)) as archive:
        prefix = next(n for n in archive.namelist() if n.endswith('/data/charset.json')).removesuffix('data/charset.json')
        def old_json(name):
            return json.loads(archive.read(prefix + name).decode('utf-8'))
        check(old_json('data/charset.json')['characters'] == charset['characters'], 'Character set changed')
        unchanged_data = ['data/refinements-v030.json', 'data/dense-refinements-v030.json',
                          'data/hexagrams.json', 'data/hexagram-outlines-v030.json']
        result['preserved_plan_data'] = {}
        for name in unchanged_data:
            equal = check(archive.read(prefix + name) == (project / name).read_bytes(), name + ': historical data changed')
            result['preserved_plan_data'][name] = equal
        original = set(base_plan['glyphs'])
        check(len(original) == 161 and not original & set(TARGETS), 'Original161 scope invalid')
        preserved = sorted(original | set('羁黛') | set(map(chr, range(0x4DC0, 0x4E00))))
        for variant in ('Regular', 'Display'):
            result['formats'][variant] = {}
            for fmt in ('otf', 'ttf', 'woff2'):
                filename = f'AincradUISc-{variant}.{fmt}'
                payload = (project / 'fonts' / filename).read_bytes()
                old_payload = archive.read(prefix + 'fonts/' + filename)
                old, new = TTFont(BytesIO(old_payload)), TTFont(BytesIO(payload))
                result['font_hashes'][filename] = sha(payload)
                check(sha(payload) == prov['fonts'][filename]['sha256'] and len(payload) == prov['fonts'][filename]['bytes'], filename + ': provenance hash/size mismatch')
                om, nm = old.getBestCmap(), new.getBestCmap()
                cmap_equal = check(om == nm and set(nm) == expected and all(n != '.notdef' for n in nm.values()), filename + ': complete cmap mismatch')
                check(old.getGlyphOrder() == new.getGlyphOrder(), filename + ': glyph order changed')
                changed, old_records, new_records = [], [], []
                for name in old.getGlyphOrder():
                    a, b = recording(old, name, True), recording(new, name, True)
                    old_records.append([name, a]); new_records.append([name, b])
                    if a != b:
                        changed.append(name)
                allowed = {om[ord(c)] for c in TARGETS} if variant == 'Regular' else set()
                check(set(changed) == allowed, filename + ': outline changes differ from exactly permitted two Regular glyphs')
                metrics_equal = check(old['hmtx'].metrics == new['hmtx'].metrics, filename + ': complete hmtx changed')
                lines_equal = check(line_metrics(old) == line_metrics(new), filename + ': line metrics changed')
                subset_equal = check(all(recording(old, c) == recording(new, c) for c in preserved), filename + ': original161/羁黛/64hexagram output changed')
                raw_changed = [tag for tag in old.reader.keys() if tag not in new.reader or table_bytes(old, tag) != table_bytes(new, tag)]
                check(set(old.reader.keys()) == set(new.reader.keys()), filename + ': sfnt table repertoire changed')
                mutable = {'head', 'glyf', 'loca'} if fmt == 'ttf' else {'head', 'CFF '}
                check(set(raw_changed) <= mutable, filename + ': non-outline/global table bytes changed: ' + repr(set(raw_changed) - mutable))
                check(normalized_head(old) == normalized_head(new), filename + ': rendering-relevant head fields changed')
                fr = {'baseline_sha256': sha(old_payload), 'current_sha256': sha(payload),
                      'byte_identical': old_payload == payload, 'encoded_characters_compared': len(om),
                      'glyphs_compared_including_notdef': len(old.getGlyphOrder()),
                      'changed_glyph_names': changed, 'changed_characters': ''.join(c for c in TARGETS if om[ord(c)] in changed),
                      'unchanged_encoded_characters': len(om) - len(changed), 'cmap_exactly_equal': cmap_equal,
                      'complete_hmtx_exactly_equal': metrics_equal, 'hmtx_entries_compared': len(old['hmtx'].metrics),
                      'line_metrics_exactly_equal': lines_equal, 'line_metrics': line_metrics(new),
                      'preserved_original161_plus_羁黛_plus64_count': len(preserved), 'preserved_special_subset_equal': subset_equal,
                      'unchanged_outline_subset_old_sha256': digest([x for x in old_records if x[0] not in allowed]),
                      'unchanged_outline_subset_new_sha256': digest([x for x in new_records if x[0] not in allowed]),
                      'complete_hmtx_sha256': digest(sorted(new['hmtx'].metrics.items())),
                      'changed_raw_sfnt_tables': raw_changed, 'normalized_head_exactly_equal': normalized_head(old) == normalized_head(new),
                      'head_normalization': 'Exclude only checksumAdjustment and created/modified timestamps; retain all rendering fields.'}
                result['formats'][variant][fmt] = fr
                if variant == 'Display':
                    check(old_payload == payload, filename + ': Display must remain byte-identical')
                if fmt == 'ttf':
                    hint_presence = {tag: tag in new for tag in HINT_TABLES}
                    instruction_changes, old_bytes, new_bytes = [], 0, 0
                    for name in old.getGlyphOrder():
                        a, b = old['glyf'][name], new['glyf'][name]
                        a = bytes(a.program.getBytecode()) if hasattr(a, 'program') else b''
                        b = bytes(b.program.getBytecode()) if hasattr(b, 'program') else b''
                        old_bytes += len(a); new_bytes += len(b)
                        if a != b:
                            instruction_changes.append(name)
                    check(not instruction_changes and old_bytes == new_bytes == 0, filename + ': per-glyph hint instructions changed or introduced')
                    fr['hint_audit'] = {'hint_tables_present': hint_presence, 'old_glyph_instruction_bytes': old_bytes,
                                        'current_glyph_instruction_bytes': new_bytes, 'changed_instruction_glyphs': instruction_changes}
                else:
                    a, b = old['CFF '].cff, new['CFF '].cff
                    priv_old, priv_new = a.topDictIndex[0].Private.rawDict, b.topDictIndex[0].Private.rawDict
                    check(priv_old == priv_new, filename + ': CFF global Private hint dictionary changed')
                    check(len(a.GlobalSubrs) == len(b.GlobalSubrs) == 0, filename + ': unexpected global CFF subroutines')
                    fr['hint_audit'] = {'old_private_dict': priv_old, 'current_private_dict': priv_new,
                                        'global_subroutines': len(b.GlobalSubrs)}
                if variant == 'Regular':
                    result['target_geometry'][fmt] = {}
                    for c in TARGETS:
                        a, b = geometry(recording(old, c)), geometry(recording(new, c))
                        same = check(a['contour_count'] == b['contour_count'] and a['winding_signs'] == b['winding_signs'] and
                                     a['strict_self_crossings_by_contour'] == b['strict_self_crossings_by_contour'] and
                                     a['strict_cross_contour_crossings'] == b['strict_cross_contour_crossings'], filename + ': ' + c + ' geometry topology changed')
                        ratio = b['signed_ink_area'] / a['signed_ink_area']
                        check(.95 <= ratio <= 1.05, filename + ': ' + c + ' ink area outside reviewed local redistribution range')
                        result['target_geometry'][fmt][c] = {'baseline': a, 'current': b,
                            'winding_and_proper_crossings_preserved': same, 'ink_area_ratio': ratio}
                    if fmt == 'ttf':
                        old_engines = {size: ImageFont.truetype(BytesIO(old_payload), size, layout_engine=ImageFont.Layout.BASIC) for size in SIZES}
                        new_engines = {size: ImageFont.truetype(BytesIO(payload), size, layout_engine=ImageFont.Layout.BASIC) for size in SIZES}
                        for size in SIZES:
                            for c in TARGETS:
                                before, after = raster(old_engines[size], c, size), raster(new_engines[size], c, size)
                                for label, box, primary, origin in ROIS[c]:
                                    a = fixed_roi_white(*before[:2], box, size)
                                    b = fixed_roi_white(*after[:2], box, size)
                                    result['fixed_roi_samples'].append({'character': c, 'region': label, 'primary': primary,
                                        'source_box': box, 'source': origin, 'size_physical_px': size,
                                        'gray_white_mean_before': a, 'gray_white_mean_after': b,
                                        'gray_ink_mean_before': 1-a, 'gray_ink_mean_after': 1-b,
                                        'white_increase_percentage_points': (b-a)*100})
                                    if b < a:
                                        diagnostics.append({'kind': 'local_white_fraction_decreased', 'character': c, 'region': label,
                                            'size_physical_px': size, 'change_percentage_points': (b-a)*100})
                                a, b = before[2], after[2]
                                old_ink, new_ink = sum(a.tobytes()), sum(b.tobytes())
                                visible = bool(a.getbbox() and b.getbbox() and new_ink > 0 and new_ink == sum(after[0].tobytes()))
                                check(visible, f'{c}/{size}px: empty or cropped native raster')
                                box = b.getbbox()
                                actual = [after[3][0]+box[0], after[3][1]+box[1], after[3][0]+box[2], after[3][1]+box[3]]
                                lm, advance = line_metrics(new), new['hmtx'][nm[ord(c)]][0]
                                check(actual[0] >= -1 and actual[2] <= math.ceil(advance*size/lm[0])+1 and
                                      actual[1] >= -math.ceil(lm[1]*size/lm[0])-1 and actual[3] <= math.ceil(-lm[2]*size/lm[0])+1,
                                      f'{c}/{size}px: actual ink outside advance/line cell')
                                result['raster_diagnostics'].setdefault(c, []).append({'size_physical_px': size,
                                    'baseline_mask_offset': before[3], 'current_mask_offset': after[3],
                                    'baseline_gray_ink_sum': old_ink, 'current_gray_ink_sum': new_ink,
                                    'ink_coverage_ratio': new_ink/old_ink, 'current_ink_bounds_from_baseline': actual,
                                    'nonempty_unclipped': visible})
                            for text in ('羁黛', '命宫2026'):
                                a, b = old_engines[size].getmask2(text, mode='L', anchor='ls'), new_engines[size].getmask2(text, mode='L', anchor='ls')
                                equal = a[1] == b[1] and a[0].size == b[0].size and bytes(a[0]) == bytes(b[0])
                                check(equal, f'Unchanged control pixels differ: {text}/{size}px')
                                result['controls'].append({'text': text, 'size_physical_px': size, 'mask_and_offset_exactly_equal': equal})
        # Audit anchors in their declared coordinate space: AFTER original dense.
        source = prov['sources']['Regular']
        source_data = (project / source['file']).read_bytes()
        result['input_hashes'][source['file']] = sha(source_data)
        check(source_data == archive.read(prefix + source['file']) and sha(source_data) == local['source_sha256_by_weight']['Regular'], 'Regular source seed changed or local seed hash mismatch')
        seed = TTFont(BytesIO(source_data))
        for c in TARGETS:
            pen = raw_recording(seed, c)
            if c in base_plan['glyphs']:
                pen, _ = build.refine_source(pen, base_plan['glyphs'][c]['Regular'])
            pen, _ = build.refine_source(pen, dense['glyphs'][c]['Regular'])
            edit = local['glyphs'][c]['Regular']
            actual_anchor = sha(repr(pen.value).encode())
            check(actual_anchor == edit['source_outline_sha256'], c + ': post-dense source anchor mismatch')
            ns = build.get_contours(pen)
            check([len(nodes) for nodes, _ in ns] == edit['expected_contour_nodes'], c + ': source node topology mismatch')
            for entry in edit.get('node_deltas', []):
                check(all(0 <= i < len(ns[entry['contour']][0]) for i in entry['nodes']) and
                      all(math.isfinite(v) for v in entry['delta']), c + ': invalid node delta')
            for entry in edit.get('control_deltas', []):
                check(all(0 <= i < len(ns[entry['contour']][1][entry['edge']][1]) for i in entry['controls']) and
                      all(math.isfinite(v) for v in entry['delta']), c + ': invalid control delta')
            after, _ = build.refine_source(pen, edit)
            a, b = geometry(pen.value), geometry(after.value)
            safe = check(a['winding_signs'] == b['winding_signs'] and a['strict_self_crossings_by_contour'] == b['strict_self_crossings_by_contour'] and
                         a['strict_cross_contour_crossings'] == b['strict_cross_contour_crossings'], c + ': source geometry topology changed')
            review = {'declared_anchor': edit['source_outline_sha256'], 'actual_post_dense_anchor': actual_anchor,
                      'expected_node_counts': edit['expected_contour_nodes'], 'source_before': a, 'source_after': b,
                      'geometry_safe': safe, 'node_edits': len(edit.get('node_deltas', [])), 'control_edits': len(edit.get('control_deltas', []))}
            nodes_after = build.get_contours(after)
            if c == '攥':
                old_boxes, new_boxes = a['contour_bounds'], b['contour_bounds']
                stems = [new_boxes[6][1]-new_boxes[5][3], new_boxes[7][1]-new_boxes[6][3]]
                eye_height = nodes_after[8][0][6][1] - nodes_after[8][0][5][1]
                check(stems == [27,28] and eye_height == 305, '攥 reviewed stem/eye budget mismatch')
                review['eye_budget'] = {'inner_horizontal_thickness_upm': stems, 'eye_height_upm': eye_height,
                    'counter_height_increases_upm': [(new_boxes[i][3]-new_boxes[i][1])-(old_boxes[i][3]-old_boxes[i][1]) for i in (5,6,7)]}
            else:
                translated = []
                for ci, ei in ((2,3),(8,45)):
                    bn, be = ns[ci]; an, ae = nodes_after[ci]
                    before_points = [bn[ei], *be[ei][1], bn[(ei+1)%len(bn)]]
                    after_points = [an[ei], *ae[ei][1], an[(ei+1)%len(an)]]
                    ok = all(abs(q[0]-p[0]-16)<1e-7 and abs(q[1]-p[1])<1e-7 for p,q in zip(before_points,after_points))
                    check(ok, '螣 paired dot boundary curve did not translate rigidly16UPM')
                    translated.append({'contour':ci,'edge':ei,'all_curve_points_translated_exactly':[16,0],'verified':ok})
                review['dot_boundary_curve_checks'] = translated
                review['dot_cap_xmax_source_before_after'] = [max(ns[8][0][i][0] for i in (43,44,45,46)), max(nodes_after[8][0][i][0] for i in (43,44,45,46))]
            result['source_plan_review'][c] = review
        # The same source and old plans retain the original161 source instances.
        result['original_161_source_preservation'] = {}
        for variant in ('Regular','Display'):
            source = prov['sources'][variant]
            current = (project/source['file']).read_bytes()
            equal = check(current == archive.read(prefix+source['file']), variant+': source subset bytes changed')
            result['input_hashes'][source['file']] = sha(current)
            result['original_161_source_preservation'][variant] = {'source_subset_byte_identical':equal,'characters_preserved':161}
    for name, value in result['font_hashes'].items():
        check(sha((project/'fonts'/name).read_bytes()) == value, name+': font changed during review')
    for name, value in result['input_hashes'].items():
        check(sha((project/name).read_bytes()) == value, name+': input changed during review')
    result['fixed_roi_method'] = {'coordinate_space':'Frozen old post-dense source design coordinates; x=.88*x+10, y unchanged.',
        'sampling':'Pillow/FreeType default native grayscale, BASIC layout, common baseline; mean1-alpha/255 weighted by exact fractional pixel overlap. No resampling, filters, bbox-top alignment or moving/enlarging ROI.',
        'grayscale_threshold':None,'threshold_explanation':'Continuous alpha mean, not a binarized pass criterion.',
        'sizes_physical_px':list(SIZES),'unique_regions':sum(map(len,ROIS.values())), 'sample_count':len(result['fixed_roi_samples']),
        'monotonic_increase_required':False,'increased_samples':sum(x['white_increase_percentage_points']>0 for x in result['fixed_roi_samples']),
        'decreased_samples':sum(x['white_increase_percentage_points']<0 for x in result['fixed_roi_samples'])}
    result['primary_14px_results'] = [x for x in result['fixed_roi_samples'] if x['primary'] and x['size_physical_px']==14]
    result['regression_performed'] = True
    result['ok'] = not problems
    result['status'] = 'failed' if problems else 'passed_with_local_raster_diagnostics'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir',type=Path,default=DEFAULT_PROJECT)
    parser.add_argument('--baseline-zip',type=Path)
    parser.add_argument('--report',type=Path)
    args = parser.parse_args()
    report = verify(args.project_dir,args.baseline_zip or args.project_dir/BASELINE_NAME)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'ok':report['ok'],'status':report['status'],'problems':report['problems'],
                          'report':str(args.report),'primary_14px_results':report.get('primary_14px_results',[])},ensure_ascii=False))
    else:
        print(json.dumps(report,ensure_ascii=False,indent=2))
    return 1 if report['problems'] else 0 if report['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
