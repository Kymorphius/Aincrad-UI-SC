"""Verify the additive GB2312 two-level Han extension without rebuilding fonts.

The codec oracle is independently enumerated here. --report writes JSON;
otherwise stdout contains the report. Run in the workspace or unpacked package.
Without the immutable previous release ZIP, current/source checks still run,
but the old six-font regression is unavailable (ok=null, exit2). A real failure
exits1. This tool does not launch browsers or modify fonts, plans or old reports.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import math
import os
from pathlib import Path
import sys
from zipfile import ZipFile

import PIL
from PIL import ImageFont, features
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

from verify_aincrad_font import (
    CURRENT_FONT_VERSION, FORMATS, VARIANTS, baseline_source_scope, inspect_font,
    is_han, label,
)
from verify_aincrad_dense_hexagrams import (
    DEFAULT_PROJECT, digest, font_bytes_for_pillow, line_metrics, recording, sha,
)


BASELINE_NAME = 'Aincrad-UI-SC-v0.3-ttf14-round2.zip'
BASELINE_SHA = '1149aab3b8f95a3c3d3335f0afde88e06397f3e283e0f4df31e9c445df49d650'
MANIFEST = 'data/gb2312-han-extension.json'
OLD_SOURCE_SHA = {
    'Regular':'b1be5fc6e992d3f773f4104919da48b9ea086eb38b6e31096b7b509664bbad7b',
    'Medium':'63abfdf6ff6e5f5f70dff10ff969732f2d2a3ce9d7424db87757a04f37908727',
}
OLD_PLANS = ('data/refinements-v030.json', 'data/dense-refinements-v030.json',
             'data/ttf14-refinements-v030.json')
HINT_TABLES = ('fpgm','prep','cvt ','gasp','LTSH','hdmx','VDMX')
RASTER_PX = 32
OLD_CONTROL = '角色装备技能确认羁螣攥黛2026☰䷀䷿'


def codec_han():
    """Decode only the two Han row ranges; reject unassigned byte pairs."""
    groups = []
    for start,stop in ((0xB0,0xD7),(0xD8,0xF7)):
        values = {}
        for high in range(start,stop+1):
            for low in range(0xA1,0xFF):
                encoded = bytes((high,low))
                try:
                    character = encoded.decode('gb2312')
                except UnicodeDecodeError:
                    continue
                if len(character) != 1 or not is_han(character):
                    raise ValueError('The GB2312 Han-zone oracle returned a non-Han value')
                values[character] = encoded.hex().upper()
        groups.append(values)
    if len(groups[0]) != 3755 or len(groups[1]) != 3008 or set(groups[0]) & set(groups[1]):
        raise ValueError('Unexpected Python gb2312 two-level Han mapping')
    return groups


def tt_coordinates(font,name):
    glyph = font['glyf'][name]
    points,ends,flags = glyph.getCoordinates(font['glyf'])
    return [list(points),list(ends),list(flags),glyph.numberOfContours]


def outline_hash(font,character_or_name,by_name=False):
    return sha(repr(recording(font,character_or_name,by_name)).encode())


def native_raster(engine,character,line,advance):
    """Read the real native mask; compare its nonzero ink to the line cell."""
    mask,offset = engine.getmask2(character,mode='L',anchor='ls')
    values = bytes(mask)
    nonzero = [i for i,value in enumerate(values) if value]
    if not nonzero or not mask.size[0]:
        return {'nonempty':False,'inside_line_cell':False,'gray_ink_sum':0}
    width = mask.size[0]
    xs,ys = [i%width for i in nonzero],[i//width for i in nonzero]
    box = [offset[0]+min(xs),offset[1]+min(ys),offset[0]+max(xs)+1,offset[1]+max(ys)+1]
    upm,ascent,descent = line[:3]
    inside = (box[0] >= -1 and box[2] <= math.ceil(advance*RASTER_PX/upm)+1 and
              box[1] >= -math.ceil(ascent*RASTER_PX/upm)-1 and
              box[3] <= math.ceil(-descent*RASTER_PX/upm)+1)
    return {'nonempty':True,'inside_line_cell':inside,'gray_ink_sum':sum(values),
            'mask_offset':offset,'ink_bounds_from_baseline':box}


def verify(project,baseline_path):
    project,baseline_path = project.resolve(),baseline_path.resolve()
    failures = []
    def check(ok,message):
        if not ok:
            failures.append(message)
        return bool(ok)
    result = {
        'timestamp_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'Add GB2312 two-level Han characters while retaining the old4041 release glyphs and metrics in both styles and all three formats.',
        'scope_limits':[
            'The Python codec Han-zone enumeration verifies the declared character scope; this is not full GB2312 non-Han, GBK or unrestricted Unicode coverage.',
            'One native32px grayscale raster per added glyph/form checks visible renderability and the line cell, not small-size readability or manual design quality.',
            'Pillow FreeType rendering differs from browser, DirectWrite, Flutter and device rendering.',
            'No old-font regression success is claimed without the hash-verified immutable previous ZIP.',
        ],
        'baseline':{'file':str(baseline_path),'available':baseline_path.is_file(),'expected_sha256':BASELINE_SHA},
        'environment':{'pillow':PIL.__version__,'freetype':features.version_module('freetype2')},
        'input_hashes':{},'formats':{},'sources':{},'cross_format':{},'failures':failures,
    }
    required = [MANIFEST,'data/charset.json','data/provenance.json',*OLD_PLANS,
                'data/symbols-v030.json','data/hexagram-outlines-v030.json']
    missing_files = [name for name in required if not (project/name).is_file()]
    if missing_files:
        return {**result,'ok':None,'status':'extension_inputs_unavailable','unavailable_artifacts':missing_files,'regression_performed':False}
    def payload(name):
        data = (project/name).read_bytes()
        result['input_hashes'][name] = sha(data)
        return data
    def load(name):
        return json.loads(payload(name).decode('utf-8-sig'))
    manifest,charset,provenance = load(MANIFEST),load('data/charset.json'),load('data/provenance.json')
    previous_plans = [load(name) for name in OLD_PLANS]
    symbols,hexagrams = load('data/symbols-v030.json'),load('data/hexagram-outlines-v030.json')
    custom = set(symbols['glyphs']) | set(hexagrams['glyphs'])
    check(len(custom) == 78 and not any(is_han(c) for c in custom), 'Original-symbol exclusion differs from the reviewed78 non-Han characters')
    first,second = codec_han()
    gb = set(first)|set(second)
    archive,archive_prefix = None,None
    if baseline_path.is_file():
        archive_bytes = baseline_path.read_bytes()
        result['baseline']['sha256'] = sha(archive_bytes)
        if check(sha(archive_bytes) == BASELINE_SHA,'Immutable previous release ZIP hash differs'):
            archive = ZipFile(BytesIO(archive_bytes))
            names = [name for name in archive.namelist() if name.endswith('/data/charset.json') or name=='data/charset.json']
            if len(names) != 1:
                raise ValueError('Expected one previous project root in the baseline ZIP')
            archive_prefix = names[0].removesuffix('data/charset.json')
    def archived(name):
        return archive.read(archive_prefix+name)
    old_regular_path = 'sources/AincradSeed-v030-Regular.otf'
    old_regular_bytes = payload(old_regular_path)
    check(sha(old_regular_bytes) == OLD_SOURCE_SHA['Regular'],'Immutable old Regular seed hash differs')
    with TTFont(BytesIO(old_regular_bytes)) as old_seed:
        inferred_previous = set(map(chr,old_seed.getBestCmap()))|custom
    if archive is not None:
        old_charset = json.loads(archived('data/charset.json').decode('utf-8'))
        previous = set(old_charset['characters'])
        check(previous == inferred_previous,'Archived4041 charset differs from reviewed source plus original symbols')
    else:
        previous = inferred_previous
    added,expected = gb-previous,gb|previous
    previous_han = {c for c in previous if is_han(c)}
    expected_han = {c for c in expected if is_han(c)}
    current_text = charset['characters']
    current = set(current_text)
    declared_han = charset['han_characters']
    check(len(previous) == 4041 and len(previous_han) == 3814,'Previous release scope differs from4041/3814')
    check(len(added) == 2953 and all(is_han(c) for c in added),'Independent codec difference is not exactly2953 additional Han characters')
    check(current == expected and len(current_text) == len(current),'Current charset differs from the old release plus independent GB2312 Han union')
    check(set(declared_han) == expected_han and len(declared_han) == len(expected_han),'Declared Han charset differs from the actual union')
    check(len(expected) == 6994 and len(expected_han) == 6767,'Computed union differs from6994 total/6767 Han')
    check(set(manifest['characters']) == gb and len(manifest['characters']) == len(gb),'Extension manifest is not exactly the independently decoded6763 Han set')
    check(set(manifest['added_characters']) == added and len(manifest['added_characters']) == len(added),'Manifest added characters differ from the independent2953-character difference')
    extras = previous_han-gb
    check(set(manifest['retained_extra_han_characters']) == extras and len(manifest['retained_extra_han_characters']) == len(extras),'Retained non-GB2312 Han declaration differs')
    check(charset['basis']['gb2312_han_count'] == len(gb),'Charset basis GB2312 Han count differs')
    declaration = charset['basis']['application_extensions']['gb2312_han']
    check(declaration['file'] == MANIFEST and declaration['sha256'] == result['input_hashes'][MANIFEST] and
          declaration['han_count'] == len(gb) and declaration['level_one_han_count'] == len(first) and
          declaration['level_two_han_count'] == len(second),'Charset extension manifest file/hash/count differs')
    for key,independent in (('level1',first),('level2',second)):
        group = manifest[key]
        check(set(group['characters']) == set(independent) and len(group['characters']) == len(independent) and
              group['count'] == len(independent),'Manifest '+key+' differs from the independent codec enumeration')
    for key,computed in (('han_count',len(gb)),('added_han_count',len(added))):
        if key in manifest:
            check(manifest[key] == computed,'Manifest '+key+' metadata differs from actual sets')
    for key,computed in (('character_count',len(current)),('han_count',len(expected_han))):
        if key in charset:
            check(charset[key] == computed,'Charset '+key+' metadata differs from actual coverage')
    for group,counts in (
        ('baseline',{'character_count':len(previous),'han_count':len(previous_han),'source_character_count':len(previous-custom)}),
        ('target',{'character_count':len(expected),'han_count':len(expected_han),'source_character_count':len(expected-custom),'custom_symbol_count':len(custom)}),
    ):
        for key,value in counts.items():
            if key in manifest.get(group,{}):
                check(manifest[group][key] == value,'Manifest '+group+'.'+key+' metadata differs from computed scope')
    if archive is not None and 'charset_sha256' in manifest.get('baseline',{}):
        check(manifest['baseline']['charset_sha256'] == sha(archived('data/charset.json')),'Manifest previous charset hash differs from the immutable archive')
    result['character_scope'] = {
        'codec':'Python gb2312; only B0-D7/D8-F7 rows x A1-FE columns, invalid byte pairs skipped',
        'level1_count':len(first),'level2_count':len(second),'gb2312_han_count':len(gb),
        'independent_gb2312_han_sha256':digest(sorted(gb)),
        'previous_total':len(previous),'previous_han':len(previous_han),
        'added_han_count':len(added),'added_han_sha256':digest(sorted(added)),
        'expected_total':len(expected),'expected_han':len(expected_han),
        'retained_extra_han_characters':''.join(sorted(extras)),
        'unexpected_characters':''.join(sorted(current-expected)),
        'missing_characters':''.join(sorted(expected-current)),
        'removed_previous_characters':''.join(sorted(previous-current)),
    }
    preserved = set(previous_plans[0]['glyphs']) | set('羁螣攥黛') | set(map(chr,range(0x4DC0,0x4E00)))
    check(len(previous_plans[0]['glyphs']) == 161,'Original local-refinement161 scope differs')
    if archive is not None:
        result['historical_preservation'] = {}
        for name in [*OLD_PLANS,'data/symbols-v030.json','data/hexagram-outlines-v030.json','data/hexagrams.json',
                     'data/charset-extensions.json','data/symbol-extensions.json']:
            result['historical_preservation'][name] = check(payload(name) == archived(name),name+': reviewed historical plan/input bytes changed')
    # Review both expanded source subsets before checking their derived fonts.
    expected_source = expected-custom
    previous_source = previous-custom
    check(len(expected_source) == 6916 and len(previous_source) == 3963,'Source-scope counts differ from6916/3963')
    for weight,variant in (('Regular','Regular'),('Medium','Display')):
        declaration = manifest['sources'][weight]
        old_name,new_name = f'sources/AincradSeed-v030-{weight}.otf',f'sources/AincradSeed-gb2312-{weight}.otf'
        old_data,new_data = payload(old_name),payload(new_name)
        check(sha(old_data) == OLD_SOURCE_SHA[weight],weight+': immutable old source seed hash differs')
        check(declaration['file'] == new_name and declaration['reviewed_seed_file'] == old_name and
              declaration['sha256'] == sha(new_data) and declaration['reviewed_seed_sha256'] == sha(old_data),weight+': manifest source paths/hashes differ')
        check(provenance['sources'][variant]['file'] == new_name and provenance['sources'][variant]['sha256'] == sha(new_data),variant+': actual build source provenance differs')
        old_archive_equal = check(old_data == archived(old_name),weight+': old seed bytes differ from baseline') if archive is not None else None
        with TTFont(BytesIO(old_data)) as old,TTFont(BytesIO(new_data)) as new:
            om,nm = old.getBestCmap(),new.getBestCmap()
            check(set(map(chr,om)) == previous_source and set(map(chr,nm)) == expected_source,weight+': source cmap scope differs')
            check(all(name != '.notdef' for name in nm.values()),weight+': expanded source contains a .notdef cmap mapping')
            changed_outlines,changed_metrics,empty = [],[],[]
            combined = hashlib.sha256()
            old_set,new_set = old.getGlyphSet(),new.getGlyphSet()
            for point,name in sorted(om.items()):
                character = chr(point)
                if point not in nm:
                    changed_outlines.append(character);changed_metrics.append(character);continue
                a,b = recording(old,character),recording(new,character)
                if a != b:
                    changed_outlines.append(character)
                if old['hmtx'][name] != new['hmtx'][nm[point]]:
                    changed_metrics.append(character)
                combined.update(repr((point,old_set[name].width,a)).encode('utf-8'))
            for character in sorted(added):
                name = nm.get(ord(character))
                if not name or name == '.notdef':
                    empty.append(character);continue
                pen = BoundsPen(new_set);new_set[name].draw(pen)
                if pen.bounds is None or pen.bounds[0] >= pen.bounds[2] or pen.bounds[1] >= pen.bounds[3]:
                    empty.append(character)
            check(not changed_outlines and not changed_metrics,weight+': expanded source changes an old outline or horizontal metric')
            check(not empty,weight+': added source glyphs lack visible nonempty outlines')
            review = provenance['source_expansion_review'][variant]
            review_matches = check(review['reviewed_seed_file'] == old_name and review['expanded_seed_file'] == new_name and
                review['reviewed_seed_sha256'] == sha(old_data) and review['expanded_seed_sha256'] == sha(new_data) and
                review['preserved_source_characters'] == len(om) and review['preserved_outline_advance_sha256'] == combined.hexdigest() and
                review['all_reviewed_outlines_and_advances_identical'] is True,variant+': source expansion review binding differs')
            result['sources'][weight] = {'old_file':old_name,'expanded_file':new_name,'old_sha256':sha(old_data),'expanded_sha256':sha(new_data),
                'old_seed_byte_identical_to_archive':old_archive_equal,'previous_source_characters':len(om),'expanded_source_characters':len(nm),
                'old_outline_changes':''.join(changed_outlines),'old_hmtx_changes':''.join(changed_metrics),
                'added_source_glyphs_checked':len(added),'empty_added_source_characters':''.join(empty),
                'preserved_outline_advance_sha256':combined.hexdigest(),'build_review_binding_matches':review_matches}
    comparisons = {}
    for variant,(stem,family) in VARIANTS.items():
        comparisons[variant],result['formats'][variant] = {},{}
        for extension in FORMATS:
            name = f'fonts/{stem}.{extension}'
            data = payload(name)
            summary,comp = inspect_font(project/name,sorted(expected),family,failures,expected_version=CURRENT_FONT_VERSION)
            comparisons[variant][extension] = comp
            result['formats'][variant][extension] = summary
            if not comp:
                continue
            check(comp['cmap'] == set(map(ord,expected)),name+': final cmap is not exactly the6994-character union')
            check(sum(is_han(chr(cp)) for cp in comp['cmap']) == len(expected_han),name+': final Han coverage differs')
            check(set(map(ord,gb)) <= comp['usable_characters'],name+': some independently enumerated GB2312 Han glyphs are unusable')
            check(provenance['fonts'][Path(name).name]['sha256'] == sha(data) and provenance['fonts'][Path(name).name]['bytes'] == len(data),name+': final font provenance hash/size differs')
            digits = {str(i):comp['advances'].get(ord(str(i))) for i in range(10)}
            expected_digit_width = 450 if variant=='Regular' else 434
            check(set(digits.values()) == {expected_digit_width},name+': digit advances differ from the preserved tabular width')
            summary['tabular_digits'] = {'advances':digits,'expected_preserved_width':expected_digit_width}
            with TTFont(BytesIO(data)) as new:
                old_data = archived(name) if archive is not None else None
                old = TTFont(BytesIO(old_data)) if old_data is not None else None
                if old is not None:
                    om,nm = old.getBestCmap(),new.getBestCmap()
                    outline_changes,metric_changes,mapping_changes,coordinate_changes = [],[],[],[]
                    old_outline_fingerprint,new_outline_fingerprint,metric_fingerprint = [],[],[]
                    for point,glyph_name in sorted(om.items()):
                        character = chr(point)
                        old_hash,new_hash = outline_hash(old,character),comp['outlines'].get(point)
                        old_outline_fingerprint.append([point,old_hash]);new_outline_fingerprint.append([point,new_hash])
                        if old_hash != new_hash: outline_changes.append(character)
                        if glyph_name != nm.get(point): mapping_changes.append(character)
                        metric = new['hmtx'][nm[point]] if point in nm else None
                        metric_fingerprint.append([point,metric])
                        if old['hmtx'][glyph_name] != metric: metric_changes.append(character)
                        if extension=='ttf' and point in nm and tt_coordinates(old,glyph_name) != tt_coordinates(new,nm[point]):
                            coordinate_changes.append(character)
                    check(not outline_changes and not metric_changes and not mapping_changes and not coordinate_changes,name+': old4041 outline/mapping/hmtx/point regression failed')
                    line_equal = check(line_metrics(old) == line_metrics(new),name+': old line metrics changed')
                    notdef_equal = check(outline_hash(old,'.notdef',True) == outline_hash(new,'.notdef',True) and old['hmtx']['.notdef'] == new['hmtx']['.notdef'],name+': .notdef changed')
                    hint_changes = [tag for tag in HINT_TABLES if (tag in old)!=(tag in new) or (tag in old and bytes(old.reader[tag])!=bytes(new.reader[tag]))]
                    check(not hint_changes,name+': global hint/render tables changed')
                    hint_instruction_changes = []
                    if extension=='ttf':
                        for point,glyph_name in om.items():
                            a,b = old['glyf'][glyph_name],new['glyf'][nm[point]]
                            ai = bytes(a.program.getBytecode()) if hasattr(a,'program') else b''
                            bi = bytes(b.program.getBytecode()) if hasattr(b,'program') else b''
                            if ai != bi:hint_instruction_changes.append(chr(point))
                        check(not hint_instruction_changes,name+': old per-glyph hint instructions changed')
                    subset_equal = check(all(c not in outline_changes and c not in metric_changes for c in preserved),name+': original161/dense4/ttf14/64hexagram subset changed')
                    summary['previous_release_regression'] = {'encoded_characters_compared':len(om),
                        'added_characters':len(set(nm)-set(om)),'removed_characters':''.join(chr(cp) for cp in sorted(set(om)-set(nm))),
                        'old_outline_changes':''.join(outline_changes),'old_hmtx_changes':''.join(metric_changes),
                        'old_mapping_changes':''.join(mapping_changes),'old_quadratic_point_flag_endpoint_changes':''.join(coordinate_changes),
                        'old_outline_sha256':digest(old_outline_fingerprint),'preserved_outline_sha256':digest(new_outline_fingerprint),
                        'old_character_hmtx_sha256':digest(metric_fingerprint),'line_metrics_equal':line_equal,'.notdef_preserved':notdef_equal,
                        'preserved_special_subset_count':len(preserved),'preserved_special_subset_equal':subset_equal,
                        'global_hint_table_changes':hint_changes,'old_glyph_hint_changes':''.join(hint_instruction_changes)}
                    check(set(map(chr,set(nm)-set(om))) == added and not set(om)-set(nm),name+': added/removed font characters differ from the independent extension')
                # Exactly one necessary physical size for every new glyph.
                engine = ImageFont.truetype(BytesIO(font_bytes_for_pillow(data)),RASTER_PX,layout_engine=ImageFont.Layout.BASIC)
                raster_empty,raster_outside = [],[]
                ink_sums = []
                for character in sorted(added):
                    point = ord(character)
                    if point not in comp['advances']:
                        raster_empty.append(character);continue
                    sample = native_raster(engine,character,line_metrics(new),comp['advances'][point])
                    if not sample['nonempty']:raster_empty.append(character)
                    if not sample['inside_line_cell']:raster_outside.append(character)
                    ink_sums.append([point,sample['gray_ink_sum']])
                check(not raster_empty and not raster_outside,name+': added glyph native32px raster is empty or outside the line cell')
                summary['added_glyph_raster'] = {'size_physical_px':RASTER_PX,'glyphs_checked':len(added),
                    'empty_characters':''.join(raster_empty),'outside_line_characters':''.join(raster_outside),
                    'gray_ink_sums_sha256':digest(ink_sums),'minimum_gray_ink_sum':min((n for _,n in ink_sums),default=None),
                    'method':'Actual declared font, native FreeType BASIC L alpha mask, anchor=ls; no fallback, scaling or postprocessing.'}
                if old is not None:
                    old_engine = ImageFont.truetype(BytesIO(font_bytes_for_pillow(old_data)),RASTER_PX,layout_engine=ImageFont.Layout.BASIC)
                    a,b = old_engine.getmask2(OLD_CONTROL,mode='L',anchor='ls'),engine.getmask2(OLD_CONTROL,mode='L',anchor='ls')
                    equal = check(a[1] == b[1] and a[0].size == b[0].size and bytes(a[0]) == bytes(b[0]),name+': old control native32px pixels changed')
                    summary['old_control_raster'] = {'text':OLD_CONTROL,'size_physical_px':RASTER_PX,'mask_and_offset_identical':equal}
                    old.close()
        reference = comparisons[variant].get('otf',{})
        result['cross_format'][variant] = {}
        for extension in ('ttf','woff2'):
            candidate = comparisons[variant].get(extension,{})
            equal_fields = {key:reference.get(key)==candidate.get(key) for key in ('upm','cmap','advances','line_metrics')}
            check(all(equal_fields.values()),variant+'/'+extension+': OTF/other-format mappings, widths or lines differ')
            bad_bounds = []
            for point,bounds in reference.get('bounds',{}).items():
                other = candidate.get('bounds',{}).get(point)
                if (bounds is None)!=(other is None) or (bounds is not None and other is not None and any(abs(a-b)>3 for a,b in zip(bounds,other))):
                    bad_bounds.append(chr(point))
            check(not bad_bounds,variant+'/'+extension+': ink bounds differ from OTF by more than3UPM')
            result['cross_format'][variant][extension] = {**equal_fields,'ink_bounds_tolerance_upm':3,'out_of_tolerance_characters':''.join(bad_bounds)}
    baseline_expected,source_scope = baseline_source_scope(project,sorted(expected),charset,comparisons,failures)
    check(set(baseline_expected) == expected_source and source_scope['excluded_count'] == 78,'Source baseline exclusion differs from the explicit original78-symbol scope')
    baseline_name = 'fonts/SourceHanSansSC-Baseline.woff2'
    payload(baseline_name)
    summary,comparison = inspect_font(project/baseline_name,baseline_expected,None,failures)
    check(comparison.get('cmap') == set(map(ord,expected_source)), 'Source Han baseline cmap is not exactly6916 genuine source characters')
    with TTFont(project/manifest['sources']['Regular']['file']) as source:
        different = [chr(point) for point,value in comparison.get('outlines',{}).items() if value != outline_hash(source,chr(point))]
        check(not different,'Source Han comparison baseline differs from the expanded Regular source outlines')
    result['source_baseline'] = {'inspection':summary,'scope':source_scope,'outline_mismatch_characters':''.join(different)}
    result['variant_distinction'] = {'han_outline_differences':sum(
        comparisons['Regular'].get('otf',{}).get('outlines',{}).get(ord(c)) != comparisons['Display'].get('otf',{}).get('outlines',{}).get(ord(c)) for c in expected_han)}
    check(result['variant_distinction']['han_outline_differences']>0,'Regular and Display Han outlines are identical')
    if os.name=='nt':
        import ctypes
        gdi = ctypes.WinDLL('gdi32',use_last_error=True)
        gdi.AddFontResourceExW.argtypes = [ctypes.c_wchar_p,ctypes.c_uint,ctypes.c_void_p]
        gdi.AddFontResourceExW.restype = ctypes.c_int
        gdi.RemoveFontResourceExW.argtypes = [ctypes.c_wchar_p,ctypes.c_uint,ctypes.c_void_p]
        gdi.RemoveFontResourceExW.restype = ctypes.c_int
        result['windows_private_loading'] = []
        for stem,_family in VARIANTS.values():
            for extension in ('otf','ttf'):
                name = f'fonts/{stem}.{extension}'
                loaded,removed = 0,0
                try:
                    loaded = gdi.AddFontResourceExW(str((project/name).resolve()),0x30,None)
                finally:
                    if loaded:removed = gdi.RemoveFontResourceExW(str((project/name).resolve()),0x30,None)
                check(loaded>0 and removed!=0,name+': private Windows font load/release failed')
                result['windows_private_loading'].append({'file':name,'faces_loaded':loaded,'released':bool(removed)})
    for name,expected_hash in result['input_hashes'].items():
        check(sha((project/name).read_bytes()) == expected_hash,name+': input changed during review')
    regression = archive is not None
    if archive is not None:
        archive.close()
        check(sha(baseline_path.read_bytes()) == BASELINE_SHA,'Baseline ZIP changed during review')
    result['regression_performed'] = regression
    result['ok'] = False if failures else True if regression else None
    result['status'] = 'failed' if failures else 'passed' if regression else 'current_checks_passed_baseline_unavailable'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir',type=Path,default=DEFAULT_PROJECT)
    parser.add_argument('--baseline-zip',type=Path)
    parser.add_argument('--report',type=Path)
    args = parser.parse_args()
    result = verify(args.project_dir,args.baseline_zip or args.project_dir/BASELINE_NAME)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'ok':result['ok'],'status':result['status'],'regression_performed':result['regression_performed'],
                          'failures':result['failures'],'report':str(args.report),'character_scope':result.get('character_scope')},ensure_ascii=False))
    else:
        print(json.dumps(result,ensure_ascii=False,indent=2))
    return 1 if result['failures'] else 0 if result['ok'] else 2


if __name__=='__main__':
    sys.exit(main())
