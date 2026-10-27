"""Independent additive local-Source-Han coverage and old-release verification.

Run in the workspace or unpacked package. --report writes a new JSON report.
The immutable GB2312 ZIP and both original TTCs are needed for a full verdict.
Missing external inputs produce a partial report, ok=null and exit2, rather
than a fabricated old-regression/source-oracle success. --source-root locates
the workspace containing the original TTC relative paths in the manifest.
No fonts, manifests, historical reports or browser pages are modified.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gc
import hashlib
from io import BytesIO
from itertools import combinations
import json
import math
import os
from pathlib import Path
import sys
from zipfile import ZipFile

import PIL
from PIL import Image, ImageFont, features
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.teePen import TeePen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables.ttProgram import Program

from verify_aincrad_font import (
    CURRENT_FONT_VERSION, FORMATS, VARIANTS, baseline_source_scope, name_text,
    visible,
)
from verify_aincrad_dense_hexagrams import (
    DEFAULT_PROJECT, digest, font_bytes_for_pillow, line_metrics, sha,
)


ROOT = Path(__file__).resolve().parents[1]
BASELINE_NAME = 'Aincrad-UI-SC-v0.3-gb2312-han.zip'
BASELINE_SHA = 'afff0461aa0fcfa5d106e15f85f340d4169f2cc87a9d04f4a3d2787b3b80a3d1'
MANIFEST = 'data/sourcehan-han-extension.json'
OLD_PLANS = ('data/refinements-v030.json','data/dense-refinements-v030.json',
             'data/ttf14-refinements-v030.json')
OLD_SOURCE_SHA = {
    'Regular':'b1be5fc6e992d3f773f4104919da48b9ea086eb38b6e31096b7b509664bbad7b',
    'Medium':'63abfdf6ff6e5f5f70dff10ff969732f2d2a3ce9d7424db87757a04f37908727',
}
GB_SOURCE_SHA = {
    'Regular':'66c3e8774b8419d4deb69bcd357edb3968c2354dffda642da40c75d03ddf2e1b',
    'Medium':'d3002691a4829c1599ecd9e66bd227f1e35b84a58baa0aac4c5d732d3fc66aa9',
}
TTC_SHA = {
    'Regular':'f31d0a98b09380c11c72754bb85b74be488d0c5f1d3dbdf056f408c24cc50da3',
    'Medium':'28e9a792a7d57327c903e4cb70164c4fd093e5d9543265f819d505a6cfc049d5',
}
HINT_TABLES = ('fpgm','prep','cvt ','gasp','LTSH','hdmx','VDMX')
RASTER_PX = 32
OLD_CONTROL = '角色装备技能确认羁螣攥黛更2026☰䷀䷿'
EXPECTED_INHERITED = {'更':'更'}
# Explicit disjoint ideograph blocks, independent of the build's Han predicate.
# The local v1.004 source has no characters in the later unified blocks.
HAN_BLOCKS = (
    ('basic',0x4E00,0x9FFF),('extension_A',0x3400,0x4DBF),
    ('extension_B',0x20000,0x2A6DF),('extension_C',0x2A700,0x2B73F),
    ('extension_D',0x2B740,0x2B81F),('extension_E',0x2B820,0x2CEAF),
    ('extension_F',0x2CEB0,0x2EBEF),('extension_I',0x2EBF0,0x2EE5F),
    ('extension_G',0x30000,0x3134F),('extension_H',0x31350,0x323AF),
    ('extension_J',0x323B0,0x3347F),
    ('compatibility',0xF900,0xFAFF),('compatibility_supplement',0x2F800,0x2FA1F),
)


def han(point):
    return any(low <= point <= high for _name,low,high in HAN_BLOCKS)


def compatibility(point):
    return 0xF900 <= point <= 0xFAFF or 0x2F800 <= point <= 0x2FA1F


def alias_groups(mapping,points):
    groups = defaultdict(list)
    for point in sorted(points):
        if point in mapping:
            groups[mapping[point]].append(point)
    return sorted(tuple(group) for group in groups.values() if len(group)>1)


def cmap_audit(font,check,label):
    best = font.getBestCmap() or {}
    reports,twelve,windows = [],0,False
    for table in font['cmap'].tables:
        if not table.isUnicode() or table.format not in (4,12):
            continue
        expected = best if table.format==12 else {cp:name for cp,name in best.items() if cp<=0xFFFF}
        exact = check(table.cmap == expected,label+': Unicode cmap subtable disagrees with the best cmap')
        reports.append({'platform':table.platformID,'encoding':table.platEncID,'format':table.format,
                        'entries':len(table.cmap),'mapping_exactly_matches_expected_scope':exact})
        if table.format==12:
            twelve += 1
            windows |= (table.platformID,table.platEncID)==(3,10)
    non_bmp = {cp for cp in best if cp>0xFFFF}
    if non_bmp:
        check(twelve>0 and windows,label+': supplementary mappings lack Windows Unicode-full format12')
    return {'subtables':reports,'non_bmp_codepoints':len(non_bmp),
            'format12_tables':twelve,'windows_3_10_format12_present':windows}


def scan(font,points,check,label,family=None,reviewed_points=None):
    """Decode each requested outline once, teeing commands to hash and bounds."""
    cmap,gs = font.getBestCmap() or {},font.getGlyphSet()
    missing = sorted(cp for cp in points if cp not in cmap or cmap[cp]=='.notdef')
    check(not missing,label+': missing or .notdef mappings')
    out,metrics,bounds = {},{},{}
    empty,clipped,bad_width = [],[],[]
    lm = line_metrics(font)
    combined = hashlib.sha256()
    for cp in sorted(set(points)&set(cmap)):
        name = cmap[cp]
        if name=='.notdef':
            continue
        pen,box = DecomposingRecordingPen(gs),BoundsPen(gs)
        gs[name].draw(TeePen(pen,box))
        out[cp] = sha(repr(pen.value).encode())
        bounds[cp],metrics[cp] = box.bounds,tuple(font['hmtx'][name])
        if reviewed_points is not None and cp in reviewed_points:
            combined.update(repr((cp,gs[name].width,pen.value)).encode('utf-8'))
        if visible(chr(cp)) and (box.bounds is None or box.bounds[0]>=box.bounds[2] or box.bounds[1]>=box.bounds[3]):
            empty.append(cp)
        if box.bounds is not None and (box.bounds[1]<lm[2]-2 or box.bounds[3]>lm[1]+2 or
                                      box.bounds[1]<-lm[8]-2 or box.bounds[3]>lm[7]+2):
            clipped.append(cp)
        if metrics[cp][0]<0 or metrics[cp][0]>lm[0]*3 or (visible(chr(cp)) and metrics[cp][0]==0):
            bad_width.append(cp)
    check(not empty and not clipped and not bad_width,label+': empty outlines, clipped ink or invalid advances')
    check(lm[0]==1000 and lm[1]>0 and lm[2]<0 and lm[3]>=0,label+': unreasonable UPM/line metrics')
    if family is not None:
        families = {n.toUnicode() for n in font['name'].names if n.nameID in (1,16)}
        check(family in families and all('source' not in n.lower() for n in families),label+': derivative family differs or uses the reserved Source name')
        check('adobe' in name_text(font,0).lower() and 'open font license' in name_text(font,13).lower() and
              '1.1' in name_text(font,13),label+': Adobe attribution or OFL1.1 is missing')
        check(font['OS/2'].fsType==0,label+': embedding restrictions introduced')
        check(CURRENT_FONT_VERSION in name_text(font,5),label+': font name version differs')
    summary = {'mapped_characters':len(cmap),'requested_characters':len(points),
        'han_characters':sum(han(cp) for cp in cmap),'glyphs':len(font.getGlyphOrder()),
        'family':name_text(font,1),'version':name_text(font,5),'line_metrics':lm,
        'missing_codepoints':missing,'empty_codepoints':empty,'outside_line_codepoints':clipped,
        'invalid_advance_codepoints':bad_width,'fsType':font['OS/2'].fsType,
        'cmap_audit':cmap_audit(font,check,label)}
    return summary,{'cmap':set(cmap),'cmap_mapping':cmap,'outlines':out,'horizontal_metrics':metrics,
                    'advances':{cp:value[0] for cp,value in metrics.items()},'bounds':bounds,
                    'upm':lm[0],'line_metrics':lm,'reviewed_outline_advance_sha256':combined.hexdigest()}


def outlines_only(font,point):
    gs=font.getGlyphSet()
    pen=DecomposingRecordingPen(gs)
    gs[font.getBestCmap()[point]].draw(pen)
    return sha(repr(pen.value).encode())


def coordinates(font,name):
    glyph=font['glyf'][name]
    points,ends,flags=glyph.getCoordinates(font['glyf'])
    return [list(points),list(ends),list(flags),glyph.numberOfContours]


def raster_added(engine,points,comp):
    missing,outside,samples=[],[],[]
    lm=comp['line_metrics']
    for cp in sorted(points):
        mask,offset=engine.getmask2(chr(cp),mode='L',anchor='ls')
        image=Image.frombytes('L',mask.size,bytes(mask))
        box=image.getbbox()
        if box is None:
            missing.append(cp);continue
        ink=sum(image.tobytes())
        actual=[offset[0]+box[0],offset[1]+box[1],offset[0]+box[2],offset[1]+box[3]]
        advance=comp['advances'].get(cp,0)
        if not (actual[0]>=-1 and actual[2]<=math.ceil(advance*RASTER_PX/lm[0])+1 and
                actual[1]>=-math.ceil(lm[1]*RASTER_PX/lm[0])-1 and actual[3]<=math.ceil(-lm[2]*RASTER_PX/lm[0])+1):
            outside.append(cp)
        samples.append([cp,ink,actual])
    return {'size_physical_px':RASTER_PX,'glyphs_checked':len(points),'empty_codepoints':missing,
            'outside_line_cell_codepoints':outside,'raster_ink_and_bounds_sha256':digest(samples),
            'minimum_gray_ink_sum':min((r[1] for r in samples),default=None),
            'method':'Every added codepoint in this actual font; native FreeType BASIC L mask at one32px size, anchor=ls; no fallback/resampling/filter.'}


def mask_image(engine,text):
    mask,offset=engine.getmask2(text,mode='L',anchor='ls')
    image=Image.frombytes('L',mask.size,bytes(mask))
    box=image.getbbox()
    bounds=[offset[0]+box[0],offset[1]+box[1],offset[0]+box[2],offset[1]+box[3]] if box else None
    return image,offset,bounds


def compare_masks(before,after,text):
    a,oa,ba=mask_image(before,text);b,ob,bb=mask_image(after,text)
    x0,y0=min(oa[0],ob[0]),min(oa[1],ob[1])
    x1,y1=max(oa[0]+a.width,ob[0]+b.width),max(oa[1]+a.height,ob[1]+b.height)
    ca,cb=Image.new('L',(x1-x0,y1-y0)),Image.new('L',(x1-x0,y1-y0))
    ca.paste(a,(oa[0]-x0,oa[1]-y0));cb.paste(b,(ob[0]-x0,ob[1]-y0))
    va,vb=ca.tobytes(),cb.tobytes()
    differences=[abs(x-y) for x,y in zip(va,vb)]
    return {'changed_pixels':sum(v>0 for v in differences),'absolute_gray_difference_sum':sum(differences),
        'maximum_alpha_change':max(differences,default=0),'old_gray_ink_sum':sum(va),'new_gray_ink_sum':sum(vb),
        'old_nonzero_pixels':sum(v>0 for v in va),'new_nonzero_pixels':sum(v>0 for v in vb),
        'old_ink_bbox':ba,'new_ink_bbox':bb,'old_mask_offset':oa,'new_mask_offset':ob,
        'old_mask_size':a.size,'new_mask_size':b.size,'old_advance':before.getlength(text),'new_advance':after.getlength(text),
        'threshold64_crossings':sum((x>=64)!=(y>=64) for x,y in zip(va,vb)),
        'threshold128_crossings':sum((x>=128)!=(y>=128) for x,y in zip(va,vb)),
        'mask_and_offset_equal':oa==ob and a.size==b.size and a.tobytes()==b.tobytes()}


def ttf_control_diagnostics(old_bytes,new_bytes,variant):
    samples=[]
    for size in (11,12,13,14,32):
        old=ImageFont.truetype(BytesIO(old_bytes),size,layout_engine=ImageFont.Layout.BASIC)
        new=ImageFont.truetype(BytesIO(new_bytes),size,layout_engine=ImageFont.Layout.BASIC)
        affected=[]
        for character in dict.fromkeys(OLD_CONTROL):
            difference=compare_masks(old,new,character)
            if difference['changed_pixels']:
                affected.append({'character':character,'codepoint':ord(character),**difference})
        samples.append({'variant':variant,'size_physical_px':size,'control_text':OLD_CONTROL,
            'whole_control':compare_masks(old,new,OLD_CONTROL),'affected_characters':affected,
            'angle_U89D2':compare_masks(old,new,'角')})
    return samples


def cmap_autohint_probe(old_bytes,new_bytes):
    """Diagnostic-only BytesIO fonts. No modified probe can become an output."""
    def signature(data):
        engine=ImageFont.truetype(BytesIO(data),32,layout_engine=ImageFont.Layout.BASIC)
        image,offset,bounds=mask_image(engine,'角')
        return {'mask_alpha_sha256':sha(image.tobytes()),'mask_size':image.size,'mask_offset':offset,
            'ink_bbox':bounds,'gray_ink_sum':sum(image.tobytes()),'advance':engine.getlength('角')}
    def same(a,b):
        return all(a[key]==b[key] for key in ('mask_alpha_sha256','mask_size','mask_offset','advance'))
    groups={'head_bbox':('head',('xMin','yMin','xMax','yMax')),
        'hhea_extents':('hhea',('advanceWidthMax','minLeftSideBearing','minRightSideBearing','xMaxExtent')),
        'unicode_ranges':('OS/2',('ulUnicodeRange1','ulUnicodeRange2','ulUnicodeRange3','ulUnicodeRange4')),
        'first_last_char':('OS/2',('usFirstCharIndex','usLastCharIndex'))}
    old_sig,new_sig=signature(old_bytes),signature(new_bytes)
    with TTFont(BytesIO(old_bytes)) as old,TTFont(BytesIO(new_bytes)) as new:
        previous=set(old.getBestCmap());all_points=set(new.getBestCmap());added=all_points-previous
        old_fields={key:{field:getattr(old[tag],field) for field in fields} for key,(tag,fields) in groups.items()}
        new_fields={key:{field:getattr(new[tag],field) for field in fields} for key,(tag,fields) in groups.items()}
        core={tag:sha(bytes(new.reader[tag])) for tag in ('glyf','loca','hmtx','maxp','post')}
        maxp={key:[getattr(old['maxp'],key),getattr(new['maxp'],key)] for key in
              ('numGlyphs','maxPoints','maxContours','maxSizeOfInstructions','maxStackElements')}
    cases=[]
    def variant(label,allowed=None,restore=(),dummy=False,base=new_bytes):
        with TTFont(BytesIO(base),recalcBBoxes=False,recalcTimestamp=False) as font:
            # fontTools otherwise silently rewrites first/lastCharIndex during
            # OS/2.compile, confounding both metadata and cmap-only experiments.
            font['OS/2'].updateFirstAndLastCharIndex=lambda _font:None
            if allowed is not None:
                for table in font['cmap'].tables:
                    if table.isUnicode() and hasattr(table,'cmap'):
                        table.cmap={cp:name for cp,name in table.cmap.items() if cp in allowed}
            for key in restore:
                tag,_fields=groups[key]
                for field,value in old_fields[key].items():setattr(font[tag],field,value)
            if dummy:
                table=newTable('fpgm');table.program=Program()
                table.program.fromBytecode([0xB0,0,0x21]);font['fpgm']=table
            stream=BytesIO();font.save(stream);data=stream.getvalue()
        with TTFont(BytesIO(data)) as parsed:
            preserved=all(sha(bytes(parsed.reader[tag]))==value for tag,value in core.items()) if base is new_bytes else None
            count=parsed['maxp'].numGlyphs
            effective={key:{field:getattr(parsed[tag],field) for field in fields} for key,(tag,fields) in groups.items()}
            wanted={key:(old_fields[key] if key in restore or base is old_bytes else new_fields[key]) for key in groups}
        value=signature(data)
        row={'case':label,'signature':value,'equals_old_default_mask':same(value,old_sig),
            'equals_new_default_mask':same(value,new_sig),'new_glyf_loca_hmtx_maxp_post_bytes_preserved':preserved,'numGlyphs':count,
            'effective_metadata_fields':effective,'requested_metadata_fields_verified_after_serialization':effective==wanted}
        cases.append(row)
        return row
    variant('new_memory_roundtrip')
    for key in groups:variant('restore_old_'+key,restore=(key,))
    variant('restore_all_old_metadata',restore=tuple(groups))
    old_only=variant('new_glyphs_old_cmap_only',allowed=previous)
    variant('drop_only_added_nonBMP',allowed=all_points-{cp for cp in added if cp>0xFFFF})
    variant('drop_only_added_compatibility',allowed=all_points-{cp for cp in added if compatibility(cp)})
    trio=tuple(map(ord,'進過還'))
    combination_rows=[]
    for count in range(4):
        for subset in combinations(trio,count):
            row=variant('old_cmap_plus_'+(''.join(map(chr,subset)) or 'none'),allowed=previous|set(subset))
            combination_rows.append({'added_codepoints':list(subset),'equals_old':row['equals_old_default_mask'],'equals_new':row['equals_new_default_mask']})
    drop_three=variant('full_cmap_drop_進過還',allowed=all_points-set(trio))
    for cp in trio:variant('full_cmap_drop_only_'+chr(cp),allowed=all_points-{cp})
    dummy_old=variant('old_plus_balanced_dummy_fpgm',dummy=True,base=old_bytes)
    dummy_new=variant('new_plus_balanced_dummy_fpgm',dummy=True)
    sufficient=all(row['equals_old'] if len(row['added_codepoints'])<3 else row['equals_new'] for row in combination_rows)
    observed=not same(old_sig,new_sig)
    confirmed=observed and old_only['equals_old_default_mask'] and drop_three['equals_old_default_mask'] and sufficient
    return {'scope':'Display TTF angle U89D2 at32px; every modified font exists only in BytesIO and is discarded.',
        'old_default':old_sig,'new_default':new_sig,'metadata_before':old_fields,'metadata_after':new_fields,
        'maxp_before_after':maxp,'cases':cases,'minimal_sufficient_subset_with_old_cmap':{'characters':'進過還','codepoints':list(trio),'all_eight_subsets':combination_rows},
        'coverage_change_causally_isolated':confirmed,'default_difference_observed':observed,
        'dummy_old_new_masks_equal':same(dummy_old['signature'],dummy_new['signature']),
        'maxp_restoration_not_attempted':'Actual new glyph maxima and numGlyphs are retained; reducing them would contradict real outlines. The cmap-only restoration already keeps these fields unchanged.',
        'interpretation':'On this measured FreeType build, changing only mapped character coverage can restore the old mask. 進過還 is a sufficient minimal combination on top of the old cmap; none of the three is individually necessary within the full new cmap. Official CJK-bottom sampling data contains these characters. Exact internal blue-zone values were not instrumented.',
        'not_a_delivery_change':'Dropping requested mappings would defeat coverage. Dummy fpgm changes the renderer path and offset/size; it is diagnostic only and is never written to a font file.'}


def verify(project,baseline_path,source_root):
    project,baseline_path,source_root=project.resolve(),baseline_path.resolve(),source_root.resolve()
    failures,unavailable=[],[]
    def check(ok,message):
        if not ok:failures.append(message)
        return bool(ok)
    def progress(message):
        print(message,file=sys.stderr,flush=True)
    result={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'edition':'local-sourcehan-all-han',
        'scope':'Add all Han codepoints actually mapped by the pinned local Source Han Sans SC v1.004 face2, retaining the previous6994-character release.',
        'scope_limits':[
            'Han means the declared disjoint unified and compatibility ideograph blocks. Radicals, ideographic marks, IVS sequences and other source glyph variants are outside this count.',
            'Coverage belongs to these exact local v1.004 TTC snapshots, not the latest upstream release or every Unicode Han character.',
            'Compatibility codepoints follow the source cmap/glyph identity. No NFKC normalization is used; distinct regional source outlines remain distinct.',
            'Each added glyph/form receives one actual native32px raster check. This proves visible renderability, not11-14px readability or manual design acceptance.',
            'Full source-oracle and previous-release conclusions require the original TTCs and the hash-verified GB ZIP; missing inputs yield a partial/null result.',
        ],'environment':{'pillow':PIL.__version__,'freetype':features.version_module('freetype2')},
        'baseline':{'file':str(baseline_path),'expected_sha256':BASELINE_SHA,'available':baseline_path.is_file()},
        'checker':{'file':'scripts/verify_aincrad_sourcehan.py','sha256':sha(Path(__file__).read_bytes())},
        'input_hashes':{},'external_sources':{},'source_subsets':{},'formats':{},'cross_format':{},
        'failures':failures,'unavailable_inputs':unavailable}
    def payload(name):
        value=(project/name).read_bytes();result['input_hashes'][name]=sha(value);return value
    def load(name):return json.loads(payload(name).decode('utf-8-sig'))
    if not (project/MANIFEST).is_file():
        return {**result,'ok':None,'status':'sourcehan_inputs_unavailable','regression_performed':False,'external_ttc_oracle_performed':False}
    manifest,charset,provenance=load(MANIFEST),load('data/charset.json'),load('data/provenance.json')
    plans=[load(name) for name in OLD_PLANS]
    glyphs=load('data/symbols-v030.json')['glyphs']|load('data/hexagram-outlines-v030.json')['glyphs']
    custom=set(map(ord,glyphs))
    declared=set(map(ord,manifest['characters']))
    check(len(declared)==len(manifest['characters'])==30186 and all(han(cp) for cp in declared),'Manifest Han set is not30186 distinct ideographs')
    check(len(custom)==78 and not any(han(cp) for cp in custom),'Original-symbol exclusion is not the reviewed78 non-Han codepoints')
    archive,prefix=None,None
    if baseline_path.is_file():
        data=baseline_path.read_bytes();result['baseline']['sha256']=sha(data)
        if check(sha(data)==BASELINE_SHA,'Immutable GB2312 release ZIP hash differs'):
            archive=ZipFile(BytesIO(data))
            roots=[n.removesuffix('data/charset.json') for n in archive.namelist() if n.endswith('/data/charset.json') or n=='data/charset.json']
            if len(roots)!=1:raise ValueError('Expected one project root in the baseline ZIP')
            prefix=roots[0]
    else:unavailable.append('immutable_previous_gb2312_release_zip')
    def old_payload(name):return archive.read(prefix+name)
    with TTFont(BytesIO(payload('sources/AincradSeed-gb2312-Regular.otf'))) as previous_seed:
        inferred_previous=set(previous_seed.getBestCmap())|custom
    previous=set(map(ord,json.loads(old_payload('data/charset.json').decode('utf-8'))['characters'])) if archive is not None else inferred_previous
    check(previous==inferred_previous and len(previous)==6994,'Previous6994 charset differs from the immutable GB source plus original symbols')
    non_han={cp for cp in previous if not han(cp)}
    added=declared-previous
    expected=declared|non_han
    current=set(map(ord,charset['characters']))
    check(len(non_han)==227 and len(added)==23419 and len(expected)==30413,'Independent union/addition counts differ from227/23419/30413')
    check({cp for cp in previous if han(cp)}<=declared,'The local full-Han set removes a previous Han character')
    check(current==expected and len(charset['characters'])==len(expected),'Current charset differs from full source Han plus exactly the old227 non-Han characters')
    check(set(map(ord,charset['han_characters']))==declared and len(charset['han_characters'])==len(declared),'Declared Han charset differs from source scope')
    check(set(map(ord,manifest['added_characters']))==added and len(manifest['added_characters'])==len(added),'Manifest addition differs from the independent old/new difference')
    check(manifest['han_count']==len(declared) and manifest['added_han_count']==len(added) and
          charset['han_count']==len(declared) and charset['character_count']==len(expected),
          'Manifest or charset count metadata differs from the actual sets')
    compat={cp for cp in declared if compatibility(cp)}
    supplementary={cp for cp in declared if cp>0xFFFF}
    check(len(compat)==421 and len(supplementary)==2293,'Compatibility or non-BMP counts differ from421/2293')
    declaration=charset['basis']['application_extensions']['sourcehan_han']
    check(declaration['file']==MANIFEST and declaration['sha256']==result['input_hashes'][MANIFEST] and
          declaration['han_count']==len(declared),'Charset full-source declaration file/hash/count differs')
    if 'sourcehan_han_count' in charset['basis']:
        check(charset['basis']['sourcehan_han_count']==len(declared),'Charset source Han basis count differs')
    result['character_scope']={'previous_total':len(previous),'previous_han':sum(han(cp) for cp in previous),
        'han_count':len(declared),'total_character_count':len(expected),'added_han_count':len(added),
        'retained_non_han_count':len(non_han),'compatibility_han_count':len(compat),'non_bmp_han_count':len(supplementary),
        'han_codepoint_set_sha256':digest(sorted(declared)),'added_codepoint_set_sha256':digest(sorted(added)),
        'han_by_block':{name:sum(low<=cp<=high for cp in declared) for name,low,high in HAN_BLOCKS},
        'removed_previous_codepoints':sorted(previous-current),'unexpected_codepoints':sorted(current-expected),'missing_codepoints':sorted(expected-current)}
    for group,counts in (('baseline',{'han_count':sum(han(cp) for cp in previous),'character_count':len(previous),'source_character_count':len(previous-custom)}),
        ('target',{'han_count':len(declared),'character_count':len(expected),'source_character_count':len(expected-custom),
                   'custom_symbol_count':len(custom),'retained_non_han_character_count':len(non_han),
                   'non_bmp_han_count':len(supplementary),'compatibility_han_count':len(compat)})):
        for key,value in counts.items():
            if key in manifest.get(group,{}):check(manifest[group][key]==value,'Manifest '+group+'.'+key+' differs from independently counted scope')
    reference=manifest.get('coverage_reference')
    if reference:
        check(sha(payload(reference['file']))==reference['sha256'],'Source coverage reference hash differs')
    if archive is not None:
        check(manifest['baseline']['charset_sha256']==sha(old_payload('data/charset.json')),'Manifest previous charset hash differs from the GB archive')
        result['historical_preservation']={}
        for name in [*OLD_PLANS,'data/gb2312-han-extension.json','data/symbols-v030.json','data/hexagram-outlines-v030.json',
                     'data/hexagrams.json','data/charset-extensions.json','data/symbol-extensions.json']:
            result['historical_preservation'][name]=check(payload(name)==old_payload(name),name+': historical input bytes changed')
    expected_source=expected-custom
    check(len(expected_source)==30335,'Derived source scope differs from30335')
    oracle_groups,source_data={},{}
    ttc_hash_snapshots={}
    for weight,variant in (('Regular','Regular'),('Medium','Display')):
        progress('Checking original/expanded source '+weight)
        record=manifest['sources'][weight]
        new_name=f'sources/AincradSeed-sourcehan-{weight}.otf'
        gb_name=f'sources/AincradSeed-gb2312-{weight}.otf'
        reviewed_name=f'sources/AincradSeed-v030-{weight}.otf'
        new_bytes,gb_bytes,reviewed_bytes=payload(new_name),payload(gb_name),payload(reviewed_name)
        check(record['file']==new_name and record['sha256']==sha(new_bytes) and record['reviewed_seed_file']==reviewed_name and
              record['reviewed_seed_sha256']==sha(reviewed_bytes)==OLD_SOURCE_SHA[weight] and sha(gb_bytes)==GB_SOURCE_SHA[weight],weight+': source manifest paths or pinned seed hashes differ')
        if 'previous_gb2312_seed_file' in record:
            check(record['previous_gb2312_seed_file']==gb_name and record['previous_gb2312_seed_sha256']==sha(gb_bytes),weight+': previous GB source declaration differs')
        check(provenance['sources'][variant]['file']==new_name and provenance['sources'][variant]['sha256']==sha(new_bytes),variant+': actual source provenance differs')
        preserved_bytes=None
        if archive is not None:
            preserved_bytes=check(gb_bytes==old_payload(gb_name) and reviewed_bytes==old_payload(reviewed_name),weight+': previous source bytes changed')
        with TTFont(BytesIO(reviewed_bytes)) as reviewed:
            reviewed_points=set(reviewed.getBestCmap())
        with TTFont(BytesIO(new_bytes)) as new:
            summary,data=scan(new,expected_source,check,new_name,reviewed_points=reviewed_points)
            source_data[weight]=data
            check(data['cmap']==expected_source,new_name+': source cmap is not exactly30335 required characters')
            groups=alias_groups(data['cmap_mapping'],declared)
            with TTFont(BytesIO(gb_bytes)) as old:
                om=old.getBestCmap();oldgs=old.getGlyphSet()
                old_outline_changes,old_metric_changes=[],[]
                gb_combined=hashlib.sha256()
                for cp,name in sorted(om.items()):
                    pen=DecomposingRecordingPen(oldgs);oldgs[name].draw(pen)
                    gb_combined.update(repr((cp,old['hmtx'][name],pen.value)).encode('utf-8'))
                    if sha(repr(pen.value).encode())!=data['outlines'].get(cp):old_outline_changes.append(cp)
                    if tuple(old['hmtx'][name])!=data['horizontal_metrics'].get(cp):old_metric_changes.append(cp)
                check(len(om)==6916 and not old_outline_changes and not old_metric_changes,weight+': an old6916 source outline/hmtx changed')
            review=provenance['source_expansion_review'][variant]
            check(review['reviewed_seed_file']==reviewed_name and review['reviewed_seed_sha256']==sha(reviewed_bytes) and
                  review['expanded_seed_file']==new_name and review['expanded_seed_sha256']==sha(new_bytes) and
                  review['preserved_source_characters']==len(reviewed_points)==3963 and
                  review['preserved_outline_advance_sha256']==data['reviewed_outline_advance_sha256'] and
                  review['all_reviewed_outlines_and_advances_identical'] is True,variant+': reviewed3963 source proof binding differs')
            check(review['previous_gb2312_seed_file']==gb_name and review['previous_gb2312_seed_sha256']==sha(gb_bytes) and
                  review['preserved_previous_source_characters']==len(om)==6916 and
                  review['preserved_previous_outline_hmtx_sha256']==gb_combined.hexdigest() and
                  review['all_previous_outlines_and_horizontal_metrics_identical'] is True,
                  variant+': previous6916 source proof binding differs')
            summary.update({'sha256':sha(new_bytes),'bytes':len(new_bytes),'old_seed_bytes_equal_archive':preserved_bytes,
                'old_gb_source_characters_compared':len(om),'old_source_outline_changes':old_outline_changes,
                'old_source_hmtx_changes':old_metric_changes,'reviewed_outline_advance_sha256':data['reviewed_outline_advance_sha256'],
                'previous_outline_hmtx_sha256':gb_combined.hexdigest(),
                'source_alias_groups':len(groups),'source_alias_codepoints':sum(map(len,groups))})
            result['source_subsets'][weight]=summary
        ttc_path=source_root/record['source_ttc_file']
        external={'file':str(ttc_path),'available':ttc_path.is_file(),'expected_sha256':TTC_SHA[weight],'face_index':2}
        result['external_sources'][weight]=external
        if ttc_path.is_file():
            original_bytes=ttc_path.read_bytes();actual_hash=sha(original_bytes)
            ttc_hash_snapshots[str(ttc_path)]=actual_hash
            check(actual_hash==TTC_SHA[weight]==record['source_ttc_sha256'] and record['face_index']==2,weight+': original TTC hash or face index differs')
            with TTFont(BytesIO(original_bytes),fontNumber=2) as original:
                actual_han={cp for cp,name in original.getBestCmap().items() if han(cp) and name!='.notdef'}
                check(actual_han==declared,weight+': actual original TTC Han cmap differs from manifest')
                original_groups=alias_groups(original.getBestCmap(),actual_han)
                oracle_groups[variant]=original_groups
                check(groups==original_groups and len(groups)==94 and sum(map(len,groups))==189,weight+': expanded source lost an original shared-glyph relation')
                original_summary,original_data=scan(original,expected_source,check,weight+' original face2')
                differences=[cp for cp in expected_source if original_data['outlines'].get(cp)!=data['outlines'].get(cp) or
                             original_data['horizontal_metrics'].get(cp)!=data['horizontal_metrics'].get(cp)]
                check(not differences,weight+': expanded source maps a character to a different original outline/hmtx')
                external.update({'sha256':actual_hash,'oracle_performed':True,'actual_han_count':len(actual_han),
                    'actual_non_bmp_han_count':sum(cp>0xFFFF for cp in actual_han),
                    'actual_compatibility_han_count':sum(compatibility(cp) for cp in actual_han),
                    'actual_han_set_sha256':digest(sorted(actual_han)),
                    'distinct_mapped_han_glyphs':len({original.getBestCmap()[cp] for cp in actual_han}),
                    'alias_groups':len(original_groups),'alias_codepoints':sum(map(len,original_groups)),
                    'source_outline_hmtx_codepoints_compared':len(expected_source),
                    'source_outline_hmtx_mismatch_codepoints':differences,'cmap_audit':original_summary['cmap_audit']})
                del original_data
            del original_bytes
        else:
            unavailable.append('original_'+weight+'_TTC_face2')
            oracle_groups[variant]=groups
            external['oracle_performed']=False
        gc.collect()
    # These exact source relationships, rather than compatibility normalization,
    # determine which output codepoints must share the same rendered outline.
    protected=set(map(ord,plans[0]['glyphs']))|set(map(ord,'羁螣攥黛'))|set(range(0x4DC0,0x4E00))
    check(len(protected)==229,'Protected original161/dense4/64hexagram union differs')
    for variant in VARIANTS:
        check(provenance['fonts'][variant]['inherited_source_glyph_refinements']==EXPECTED_INHERITED,
              variant+': inherited source-glyph refinement record differs from the reviewed 更/更 alias')
    comparisons={}
    raster_diagnostics={'non_gating':True,'policy':'Coverage, exact old outlines/hmtx/points/line, aliases and source preservation are mandatory. Pixel identity across expanded character coverage is an explicit diagnostic, not a mandatory requirement.',
        'method':'Pillow/FreeType BASIC native L masks, common baseline, fixed integer physical pixels; no resampling. Alpha64/128 crossings are diagnostics, not readability pass thresholds.',
        'environment':result['environment'],'ttf_control_samples':[],
        'official_sources':[
            {'title':'FreeType2.14.3 CJK bottom blue reference characters','url':'https://github.com/freetype/freetype/blob/VER-2-14-3/src/autofit/afblue.dat#L515-L523','supports':'進過還 are in the CJK_BOTTOM reference-character list.'},
            {'title':'FreeType2.14.3 CJK global blue-zone initialization','url':'https://github.com/freetype/freetype/blob/VER-2-14-3/src/autofit/afcjk.c#L248-L505','supports':'Available mapped reference glyphs supply extrema; implementation sorts samples and chooses central values. Internal values were not instrumented here.'},
            {'title':'FreeType2.14.3 default automatic hint selection','url':'https://github.com/freetype/freetype/blob/VER-2-14-3/src/base/ftobjs.c#L908-L946','supports':'A TrueType font without fpgm and with a sufficiently short prep table can use runtime autohint under default loading.'}],
        'limits':'The sampled control text does not exhaust every old glyph at every size/platform. These native FreeType results do not establish Chromium or device readability.'}
    for variant,(stem,family) in VARIANTS.items():
        comparisons[variant],result['formats'][variant]={},{}
        for extension in FORMATS:
            name=f'fonts/{stem}.{extension}'
            progress('Checking derived font '+name)
            content=payload(name)
            with TTFont(BytesIO(content)) as new:
                summary,comp=scan(new,expected,check,name,family=family)
                comparisons[variant][extension]=comp
                result['formats'][variant][extension]=summary
                check(comp['cmap']==expected,name+': final cmap is not exactly30413 characters')
                check(provenance['fonts'][Path(name).name]['sha256']==sha(content) and
                      provenance['fonts'][Path(name).name]['bytes']==len(content),name+': font provenance hash/size differs')
                summary.update({'sha256':sha(content),'bytes':len(content)})
                digits={str(i):comp['advances'].get(ord(str(i))) for i in range(10)}
                digit_width=450 if variant=='Regular' else 434
                check(set(digits.values())=={digit_width},name+': preserved tabular digit width differs')
                summary['digits']={'advances':digits,'expected_preserved_width':digit_width}
                alias_differences=[]
                for group in oracle_groups[variant]:
                    if len({comp['outlines'].get(cp) for cp in group})!=1 or len({comp['horizontal_metrics'].get(cp) for cp in group})!=1:
                        alias_differences.append(list(group))
                check(not alias_differences,name+': source-shared glyph aliases differ in output outline or hmtx')
                summary['shared_source_glyph_aliases']={'groups_checked':len(oracle_groups[variant]),
                    'codepoints_checked':sum(map(len,oracle_groups[variant])),'mismatch_groups':alias_differences,
                    'inherited_refinements':EXPECTED_INHERITED,'normalization':'None; only actual original source glyph identity is used.'}
                old_bytes=old_payload(name) if archive is not None else None
                if old_bytes is not None:
                    with TTFont(BytesIO(old_bytes)) as old:
                        om,nm=old.getBestCmap(),new.getBestCmap()
                        outline_changes=[cp for cp in om if outlines_only(old,cp)!=comp['outlines'].get(cp)]
                        mapping_changes=[cp for cp,name2 in om.items() if nm.get(cp)!=name2]
                        hmtx_changes=[glyph for glyph,value in old['hmtx'].metrics.items() if new['hmtx'].metrics.get(glyph)!=value]
                        lines_equal=line_metrics(old)==line_metrics(new)
                        check(not outline_changes and not mapping_changes and not hmtx_changes and lines_equal,name+': previous6994 outline/mapping/complete-hmtx/line regression failed')
                        check(set(nm)-set(om)==added and not set(om)-set(nm),name+': added or removed characters differ from independent source difference')
                        oldgs,newgs=old.getGlyphSet(),new.getGlyphSet()
                        pa,pb=DecomposingRecordingPen(oldgs),DecomposingRecordingPen(newgs)
                        oldgs['.notdef'].draw(pa);newgs['.notdef'].draw(pb)
                        check(pa.value==pb.value,name+': .notdef outline changed')
                        coordinates_changed,instructions_changed=[],[]
                        if extension=='ttf':
                            for glyph in old.getGlyphOrder():
                                if glyph not in new['glyf'] or coordinates(old,glyph)!=coordinates(new,glyph):coordinates_changed.append(glyph)
                                a,b=old['glyf'][glyph],new['glyf'][glyph]
                                ai=bytes(a.program.getBytecode()) if hasattr(a,'program') else b''
                                bi=bytes(b.program.getBytecode()) if hasattr(b,'program') else b''
                                if ai!=bi:instructions_changed.append(glyph)
                            check(not coordinates_changed and not instructions_changed,name+': old quadratic points/flags/endpoints or instructions changed')
                        hint_changes=[tag for tag in HINT_TABLES if (tag in old)!=(tag in new) or (tag in old and bytes(old.reader[tag])!=bytes(new.reader[tag]))]
                        check(not hint_changes,name+': global hint/render tables changed')
                        if 'CFF ' in new:
                            ca,cb=old['CFF '].cff,new['CFF '].cff
                            check(ca.topDictIndex[0].Private.rawDict==cb.topDictIndex[0].Private.rawDict and
                                  len(ca.GlobalSubrs)==len(cb.GlobalSubrs)==0,name+': CFF global hints/subroutines changed')
                        special_equal=check(not set(outline_changes)&protected and not set(mapping_changes)&protected,name+': protected229-character subset changed')
                        summary['previous_release_regression']={'encoded_characters_compared':len(om),
                            'complete_hmtx_entries_compared':len(old['hmtx'].metrics),'old_outline_changes':outline_changes,
                            'old_mapping_changes':mapping_changes,'old_hmtx_glyph_changes':hmtx_changes,'line_metrics_equal':lines_equal,
                            'old_quadratic_point_flag_endpoint_changes':coordinates_changed,'old_instruction_glyph_changes':instructions_changed,
                            'global_hint_table_changes':hint_changes,'protected_special_character_count':len(protected),
                            'protected_special_subset_equal':special_equal,'preserved_hmtx_sha256':digest(sorted((n,new['hmtx'][n]) for n in old['hmtx'].metrics))}
                engine=ImageFont.truetype(BytesIO(font_bytes_for_pillow(content)),RASTER_PX,layout_engine=ImageFont.Layout.BASIC)
                rasters=raster_added(engine,added,comp)
                check(not rasters['empty_codepoints'] and not rasters['outside_line_cell_codepoints'],name+': added native32px raster is empty or outside the line cell')
                summary['added_glyph_raster']=rasters
                if old_bytes is not None:
                    old_engine=ImageFont.truetype(BytesIO(font_bytes_for_pillow(old_bytes)),RASTER_PX,layout_engine=ImageFont.Layout.BASIC)
                    a,b=old_engine.getmask2(OLD_CONTROL,mode='L',anchor='ls'),engine.getmask2(OLD_CONTROL,mode='L',anchor='ls')
                    same=a[1]==b[1] and a[0].size==b[0].size and bytes(a[0])==bytes(b[0])
                    summary['old_control_raster']={'text':OLD_CONTROL,'size_physical_px':RASTER_PX,'mask_and_offset_equal':same,
                        'non_gating':True,'policy':'Actual false values are retained as raster diagnostics; old geometry/metrics checks remain mandatory.'}
                    if extension=='ttf':
                        raster_diagnostics['ttf_control_samples'].extend(ttf_control_diagnostics(old_bytes,content,variant))
                        if variant=='Display':
                            raster_diagnostics['in_memory_causal_probe']=cmap_autohint_probe(old_bytes,content)
            gc.collect()
        reference=comparisons[variant]['otf']
        result['cross_format'][variant]={}
        for extension in ('ttf','woff2'):
            other=comparisons[variant][extension]
            fields={key:reference[key]==other[key] for key in ('upm','cmap','advances','line_metrics')}
            check(all(fields.values()),variant+'/'+extension+': cross-format coverage/widths/line metrics differ')
            differences=[]
            for cp,box in reference['bounds'].items():
                candidate=other['bounds'].get(cp)
                if (box is None)!=(candidate is None) or (box is not None and candidate is not None and any(abs(a-b)>3 for a,b in zip(box,candidate))):differences.append(cp)
            check(not differences,variant+'/'+extension+': cross-format ink bounds differ by more than3UPM')
            result['cross_format'][variant][extension]={**fields,'bounds_tolerance_upm':3,'out_of_tolerance_codepoints':differences}
    baseline_expected,baseline_scope=baseline_source_scope(project,[chr(cp) for cp in sorted(expected)],charset,comparisons,failures)
    check(set(map(ord,baseline_expected))==expected_source and baseline_scope['excluded_count']==78,'Source comparison exclusion differs from the explicit78 original symbols')
    baseline_name='fonts/SourceHanSansSC-Baseline.woff2'
    with TTFont(BytesIO(payload(baseline_name))) as baseline:
        summary,comp=scan(baseline,expected_source,check,baseline_name)
        differences=[cp for cp in expected_source if comp['outlines'].get(cp)!=source_data['Regular']['outlines'].get(cp) or
                     comp['horizontal_metrics'].get(cp)!=source_data['Regular']['horizontal_metrics'].get(cp)]
        check(comp['cmap']==expected_source and not differences,'Source comparison baseline differs from30335 genuine Regular-source characters')
        result['source_comparison_baseline']={'inspection':summary,'scope':baseline_scope,'source_outline_hmtx_mismatch_codepoints':differences}
    result['variant_distinction']={'han_outline_differences':sum(comparisons['Regular']['otf']['outlines'].get(cp)!=comparisons['Display']['otf']['outlines'].get(cp) for cp in declared)}
    check(result['variant_distinction']['han_outline_differences']>0,'Regular and Display Han outlines are identical')
    if os.name=='nt':
        import ctypes
        gdi=ctypes.WinDLL('gdi32',use_last_error=True)
        gdi.AddFontResourceExW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint,ctypes.c_void_p];gdi.AddFontResourceExW.restype=ctypes.c_int
        gdi.RemoveFontResourceExW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint,ctypes.c_void_p];gdi.RemoveFontResourceExW.restype=ctypes.c_int
        result['windows_private_loading']=[]
        for stem,_family in VARIANTS.values():
            for extension in ('otf','ttf'):
                name=f'fonts/{stem}.{extension}';loaded,removed=0,0
                try:loaded=gdi.AddFontResourceExW(str((project/name).resolve()),0x30,None)
                finally:
                    if loaded:removed=gdi.RemoveFontResourceExW(str((project/name).resolve()),0x30,None)
                check(loaded>0 and removed!=0,name+': Windows private font registration/release failed')
                result['windows_private_loading'].append({'file':name,'faces_loaded':loaded,'released':bool(removed)})
    raster_diagnostics['different_ttf_control_samples']=sum(row['whole_control']['changed_pixels']>0 for row in raster_diagnostics['ttf_control_samples'])
    raster_diagnostics['total_ttf_control_samples']=len(raster_diagnostics['ttf_control_samples'])
    raster_diagnostics['raster_differences_present']=raster_diagnostics['different_ttf_control_samples']>0
    raster_diagnostics['formal_font_sha256']={f'{variant}.{extension}':result['formats'][variant][extension]['sha256'] for variant in VARIANTS for extension in FORMATS}
    result['raster_diagnostics']=raster_diagnostics
    for name,value in result['input_hashes'].items():check(sha((project/name).read_bytes())==value,name+': input changed during review')
    check(sha(Path(__file__).read_bytes())==result['checker']['sha256'],'Checker source changed during verification')
    for path,value in ttc_hash_snapshots.items():check(sha(Path(path).read_bytes())==value,path+': original TTC changed during review')
    regression=archive is not None
    if archive is not None:
        archive.close();check(sha(baseline_path.read_bytes())==BASELINE_SHA,'Previous release archive changed during review')
    external_done=all(value['available'] for value in result['external_sources'].values()) and len(result['external_sources'])==2
    full=regression and external_done
    result['regression_performed']=regression
    result['external_ttc_oracle_performed']=external_done
    result['mandatory_requirements_passed']=False if failures else True if full else None
    result['ok']=False if failures else True if full else None
    result['status']='failed' if failures else ('passed-with-raster-differences' if raster_diagnostics['raster_differences_present'] else 'passed') if full else 'current_checks_passed_external_inputs_unavailable'
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir',type=Path,default=DEFAULT_PROJECT)
    parser.add_argument('--baseline-zip',type=Path)
    parser.add_argument('--source-root',type=Path,default=ROOT)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    result=verify(args.project_dir,args.baseline_zip or args.project_dir/BASELINE_NAME,args.source_root)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        if 'raster_diagnostics' in result:
            diagnostic=result['raster_diagnostics']
            diagnostic['checker']=result['checker']
            diagnostic_bytes=(json.dumps(diagnostic,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
            diagnostic_path=args.report.with_name('sourcehan-raster-diagnostics.json')
            diagnostic_path.write_bytes(diagnostic_bytes)
            result['raster_diagnostics']={key:diagnostic[key] for key in ('non_gating','policy','raster_differences_present','different_ttf_control_samples','total_ttf_control_samples')}
            result['raster_diagnostics']['artifact']={'file':str(diagnostic_path),'sha256':sha(diagnostic_bytes),'bytes':len(diagnostic_bytes)}
        args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'ok':result['ok'],'status':result['status'],'failures':result['failures'],
                          'report':str(args.report),'character_scope':result.get('character_scope'),
                          'regression_performed':result['regression_performed'],'external_ttc_oracle_performed':result['external_ttc_oracle_performed']},ensure_ascii=False))
    else:print(json.dumps(result,ensure_ascii=False,indent=2))
    return 1 if result['failures'] else 0 if result['ok'] else 2


if __name__=='__main__':sys.exit(main())
