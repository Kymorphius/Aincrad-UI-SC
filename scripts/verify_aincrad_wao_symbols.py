"""Verify the24 WAO symbols and exact preservation of the SourceHan release.

The immutable sourcehan-han ZIP is required for a full old-font verdict. Missing
history returns ok=null/exit2. This reads font/plan inputs and writes only the
requested report. Raster pixel identity is diagnostic, not a hard requirement.
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
import struct
import sys
from zipfile import ZipFile

from PIL import Image, ImageFont, features
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen, RecordingPen
from fontTools.pens.teePen import TeePen
from fontTools.ttLib import TTFont

from verify_aincrad_font import baseline_source_scope, FORMATS, VARIANTS
from verify_aincrad_sourcehan import alias_groups, cmap_audit, coordinates, han
from verify_aincrad_dense_hexagrams import DEFAULT_PROJECT, font_bytes_for_pillow, line_metrics


ROOT = Path(__file__).resolve().parents[1]
BASELINE_NAME = 'Aincrad-UI-SC-v0.3-sourcehan-han.zip'
BASELINE_SHA = '1a4111fbb49a3300a539cdae6bbb291452d1e2b8698f93b6f030605bd3855be1'
REQUESTED = '◆◇●■□▲▼▶◀‹«»─│┌┐└┘‥⟨⟩※†‖'
ORIGINAL = '─│┌┐└┘⟨⟩'
SOURCED = ''.join(c for c in REQUESTED if c not in ORIGINAL)
MANIFEST = 'data/wao-symbol-extension.json'
GEOMETRY = 'data/wao-symbols-v030.json'
OLD_PLANS = ('data/refinements-v030.json','data/dense-refinements-v030.json',
             'data/ttf14-refinements-v030.json')
OLD_MANIFESTS = ('data/symbols-v030.json','data/hexagram-outlines-v030.json',
                 'data/gb2312-han-extension.json','data/sourcehan-han-extension.json')
HINT_TABLES = ('fpgm','prep','cvt ','gasp','LTSH','hdmx','VDMX')
CONTROL = '角色装备技能确认羁螣攥黛更2026☰䷀䷿'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            value.update(block)
    return value.hexdigest()


def drawing(font, character):
    glyphs=font.getGlyphSet();name=font.getBestCmap()[ord(character)]
    pen, bounds=DecomposingRecordingPen(glyphs),BoundsPen(glyphs)
    glyphs[name].draw(TeePen(pen,bounds))
    return pen.value,bounds.bounds


def segments(recording, reflect_advance=None):
    """Canonical geometric edges, independent of contour winding and order."""
    result=[];start=current=None
    def point(p):
        return (round(reflect_advance-p[0] if reflect_advance is not None else p[0],3),round(p[1],3))
    def add(kind, points):
        values=tuple(point(p) for p in points)
        result.append((kind,min(values,tuple(reversed(values)))))
    for operator,args in recording:
        if operator=='moveTo':start=current=tuple(args[0])
        elif operator=='lineTo':
            end=tuple(args[0]);add('line',(current,end));current=end
        elif operator=='curveTo':
            end=tuple(args[-1]);add('cubic',(current,*args));current=end
        elif operator=='qCurveTo':
            end=tuple(args[-1]);add('quadratic',(current,*args));current=end
        elif operator in ('closePath','endPath'):
            if operator=='closePath' and current!=start:add('line',(current,start))
            current=None
        else:raise ValueError('Unsupported glyph operator '+operator)
    return sorted(result)


def geometric_delta(left,right):
    if len(left)!=len(right):return None
    # CFF integer rounding can reorder edges sharing a nearly equal x value.
    # Match complete edges geometrically rather than relying on sorted order.
    remaining=list(right);maximum=0
    for kind_a,a in left:
        candidates=[]
        for index,(kind_b,b) in enumerate(remaining):
            if kind_a!=kind_b or len(a)!=len(b):continue
            delta=min(max((abs(x-y) for p,q in zip(a,points) for x,y in zip(p,q)),default=0)
                      for points in (b,tuple(reversed(b))))
            candidates.append((delta,index))
        if not candidates:return None
        delta,index=min(candidates);maximum=max(maximum,delta);remaining.pop(index)
    return maximum


def old_regression(old,new,check,label):
    """Exact simple-glyph programs prove points/flags/instructions unchanged.

    CFF outputs have no local/global subrs. Equal charstrings plus identical
    private dictionaries prove equal outline and width programs without drawing
    the whole30k set again. Nonidentical raw programs fall back to geometry.
    """
    old_map,new_map=old.getBestCmap(),new.getBestCmap()
    mappings=[cp for cp,name in old_map.items() if new_map.get(cp)!=name]
    metrics=[name for name,value in old['hmtx'].metrics.items() if new['hmtx'].metrics.get(name)!=value]
    check(not mappings and not metrics and line_metrics(old)==line_metrics(new),label+': previous cmap/hmtx/line changed')
    hint_changes=[tag for tag in HINT_TABLES if (tag in old)!=(tag in new) or
                  (tag in old and bytes(old.reader[tag])!=bytes(new.reader[tag]))]
    check(not hint_changes,label+': hint/render tables changed')
    changes,raw_equal,fallback=[],0,0
    names=old.getGlyphOrder()
    if 'CFF ' in old:
        a,b=old['CFF '].cff,new['CFF '].cff;at,bt=a.topDictIndex[0],b.topDictIndex[0]
        private_equal=at.Private.rawDict==bt.Private.rawDict
        no_subrs=len(a.GlobalSubrs)==len(b.GlobalSubrs)==len(getattr(at.Private,'Subrs',[]))==len(getattr(bt.Private,'Subrs',[]))==0
        check(private_equal and no_subrs,label+': CFF program environment changed')
        for name in names:
            if name not in bt.CharStrings:changes.append(name);continue
            x,y=at.CharStrings[name],bt.CharStrings[name]
            if private_equal and no_subrs and x.bytecode==y.bytecode:
                raw_equal+=1;continue
            fallback+=1
            xgs,ygs=old.getGlyphSet(),new.getGlyphSet()
            xp,yp=DecomposingRecordingPen(xgs),DecomposingRecordingPen(ygs)
            xgs[name].draw(xp);ygs[name].draw(yp)
            if xp.value!=yp.value:changes.append(name)
        method='Every old standalone CFF charstring including.notdef, exact private dict, and zero local/global subrs; fallback to decomposed commands if raw programs differ.'
    else:
        ag,bg=old['glyf'],new['glyf']
        for name in names:
            if name not in bg.glyphs:changes.append(name);continue
            x,y=ag.glyphs[name],bg.glyphs[name]
            xb,yb=getattr(x,'data',None),getattr(y,'data',None)
            simple=(not xb or struct.unpack('>h',xb[:2])[0]>=0)
            if xb is not None and yb is not None and xb==yb and simple:
                raw_equal+=1;continue
            fallback+=1
            if coordinates(old,name)!=coordinates(new,name):changes.append(name);continue
            a,b=ag[name],bg[name]
            ai=bytes(a.program.getBytecode()) if hasattr(a,'program') else b''
            bi=bytes(b.program.getBytecode()) if hasattr(b,'program') else b''
            if ai!=bi:changes.append(name)
        method='Every old simple glyf binary including.notdef; identical bytes prove coordinates/flags/endpoints/instructions. Nonidentical encodings fall back to decoded coordinates and instructions.'
    check(not changes,label+': an old glyph outline/point/instruction changed')
    return {'encoded_characters_compared':len(old_map),'glyph_programs_compared':len(names),
            'exact_raw_programs':raw_equal,'decoded_fallback_programs':fallback,
            'outline_point_instruction_changes':changes,'mapping_changes':mappings,
            'complete_hmtx_entries_compared':len(old['hmtx'].metrics),'hmtx_changes':metrics,
            'line_metrics_equal':line_metrics(old)==line_metrics(new),'hint_table_changes':hint_changes,
            'method':method}


def raster_checks(data, advances, metrics):
    output=[]
    raw=font_bytes_for_pillow(data)
    for size in (14,28):
        engine=ImageFont.truetype(BytesIO(raw),size,layout_engine=ImageFont.Layout.BASIC)
        empty,outside,samples=[],[],[]
        for character in REQUESTED:
            mask,offset=engine.getmask2(character,mode='L',anchor='ls')
            image=Image.frombytes('L',mask.size,bytes(mask));box=image.getbbox()
            if box is None:empty.append(character);continue
            actual=[offset[0]+box[0],offset[1]+box[1],offset[0]+box[2],offset[1]+box[3]]
            width=advances[ord(character)]*size/1000
            if (actual[0]<-1 or actual[2]>math.ceil(width)+1 or
                    actual[1]<-math.ceil(metrics[1]*size/1000)-1 or
                    actual[3]>math.ceil(-metrics[2]*size/1000)+1):outside.append(character)
            samples.append({'character':character,'gray_sum':sum(bytes(mask)),'ink_bounds':actual,
                            'mask_size':mask.size,'offset':offset})
        output.append({'size_physical_px':size,'css_equivalent':'14px/DPR1' if size==14 else '14px/DPR2',
                       'glyphs_checked':24,'empty':empty,'outside_line_cell':outside,'samples':samples})
    return output


def verify(project,baseline_path,source_root):
    project=project.resolve();failures=[];unavailable=[]
    def check(condition,message):
        if not condition:failures.append(message)
        return bool(condition)
    read=lambda rel:json.loads((project/rel).read_text(encoding='utf-8-sig'))
    charset,manifest,geometry,provenance=(read(f) for f in ('data/charset.json',MANIFEST,GEOMETRY,'data/provenance.json'))
    expected=set(map(ord,charset['characters']));added=set(map(ord,REQUESTED))
    check(len(expected)==len(charset['characters'])==30437 and charset['character_count']==30437,'Final charset must contain30437 distinct characters')
    check(sum(han(cp) for cp in expected)==charset['han_count']==30186,'Han set/count must stay30186')
    for field,characters in [('characters',REQUESTED),('original_characters',ORIGINAL),('source_characters',SOURCED)]:
        check(isinstance(manifest.get(field),str) and len(manifest[field])==len(characters) and set(manifest[field])==set(characters),'WAO manifest '+field+' differs')
    check(set(geometry['glyphs'])==set(REQUESTED),'WAO geometry must contain exactly24 characters')
    snapshot_paths=['data/charset.json',MANIFEST,GEOMETRY,'data/provenance.json',*OLD_PLANS,*OLD_MANIFESTS]
    snapshot_paths += [f'fonts/{stem}.{ext}' for stem,_ in VARIANTS.values() for ext in FORMATS]
    snapshot_paths += ['fonts/SourceHanSansSC-Baseline.woff2']
    snapshot_paths += [f'sources/AincradSeed-{edition}-{weight}.otf' for edition in ['v030','gb2312','sourcehan','wao'] for weight in ['Regular','Medium']]
    hashes={name:file_sha(project/name) for name in snapshot_paths}
    result={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'edition':'wao-symbols24',
        'scope':'24 requested symbols; all30413 prior encoded characters in six formats; exact raw glyph programs with geometric fallback, mappings, full hmtx and line metrics; new24 native14/28px rasters. Full Flutter application acceptance is outside this font-package check.',
        'scope_limits':['Native FreeType14/28px samples are not a substitute for the actual WAO Flutter app.',
                        'Exact grayscale equality of old rendered pixels is non-gating; full outline/metrics/points equality remains mandatory.',
                        'The previous SourceHan preparation report supplies its full original-TTC Han oracle; this check directly compares newly sourced16 characters to original TTC when available.'],
        'checker':{'file':Path(__file__).name,'sha256':file_sha(Path(__file__))},
        'input_hashes':hashes,'baseline':{'file':str(baseline_path),'expected_sha256':BASELINE_SHA,'available':baseline_path.is_file()},
        'character_scope':{'han':30186,'total':30437,'added':24,'source_added':16,'original_added':8},
        'sources':{},'formats':{},'cross_format':{},'failures':failures,'unavailable_inputs':unavailable}
    archive=None;prefix=''
    if baseline_path.is_file():
        check(file_sha(baseline_path)==BASELINE_SHA,'Previous sourcehan release ZIP hash differs')
        archive=ZipFile(baseline_path);check(archive.testzip() is None,'Previous release ZIP CRC failed')
        prefixes={n.split('/')[0] for n in archive.namelist() if '/' in n}
        check(len(prefixes)==1,'Previous release must have one root')
        prefix=next(iter(prefixes))+'/'
        old_charset=json.loads(archive.read(prefix+'data/charset.json').decode('utf-8-sig'))
        previous=set(map(ord,old_charset['characters']))
        check(len(previous)==30413 and expected-previous==added and not previous-expected,'Actual added set is not exactly the24 requested symbols')
        for path in (*OLD_PLANS,*OLD_MANIFESTS):
            check((project/path).read_bytes()==archive.read(prefix+path),path+': immutable previous plan/manifest bytes changed')
        for edition in ['v030','gb2312','sourcehan']:
            for weight in ['Regular','Medium']:
                name=f'sources/AincradSeed-{edition}-{weight}.otf'
                check((project/name).read_bytes()==archive.read(prefix+name),name+': previous source bytes changed')
    else:
        previous=expected-added;unavailable.append('previous_sourcehan_release_zip')
    source_points=expected-set(map(ord,ORIGINAL))-set(map(ord,provenance['custom_symbols']['characters']))
    check(len(source_points)==30351,'Source scope must contain30351 characters and exclude only86 originals')
    source_maps={};source_groups={}
    previous_source_manifest=read('data/sourcehan-han-extension.json')
    for variant,weight in [('Regular','Regular'),('Display','Medium')]:
        name=f'sources/AincradSeed-wao-{weight}.otf';record=manifest['sources'][weight]
        content=(project/name).read_bytes()
        check(record['file']==name and record['sha256']==sha(content),'Active WAO source identity differs: '+weight)
        check(provenance['sources'][variant]['file']==name and provenance['sources'][variant]['sha256']==sha(content),'Source provenance differs: '+variant)
        with TTFont(BytesIO(content),recalcTimestamp=False) as font,TTFont(project/f'sources/AincradSeed-sourcehan-{weight}.otf',recalcTimestamp=False) as old:
            mapping=font.getBestCmap();old_mapping=old.getBestCmap()
            check(set(mapping)==source_points and set(mapping)-set(old_mapping)==set(map(ord,SOURCED)) and not set(old_mapping)-set(mapping),weight+': source maps/count/additions differ')
            groups=alias_groups(mapping,{cp for cp in mapping if han(cp)})
            check(len(groups)==94 and sum(map(len,groups))==189,weight+': source alias relation differs')
            source_maps[weight]=mapping;source_groups[variant]=groups
            new_draws={c:drawing(font,c) for c in SOURCED}
            summary={'file':name,'sha256':sha(content),'characters':len(mapping),'previous_characters':len(old_mapping),
                     'source_added':SOURCED,'original_symbols_absent':''.join(c for c in ORIGINAL if ord(c) not in mapping),
                     'han_count':sum(han(cp) for cp in mapping),'alias_groups':len(groups),'cmap':cmap_audit(font,check,weight+' source')}
            source_ttc=f'collected-ui/SAO-Utils-2-Progressive/assets/Fonts/SourceHanSans-{weight}.ttc'
            check(record['source_ttc_file']==source_ttc and record['face_index']==2,
                  weight+': original source TTC identity/face differs')
            check(record['source_ttc_sha256']==previous_source_manifest['sources'][weight]['source_ttc_sha256'],
                  weight+': source TTC hash differs from immutable previous SourceHan manifest')
            path=source_root/source_ttc
            summary['original_ttc_available']=path.is_file()
            if path.is_file():
                summary['original_ttc_sha256']=file_sha(path)
                check(summary['original_ttc_sha256']==record['source_ttc_sha256'],weight+': original source TTC SHA differs')
                with TTFont(path,fontNumber=2,recalcTimestamp=False) as original:
                    different=[]
                    for c in SOURCED:
                        if ord(c) not in original.getBestCmap() or drawing(original,c)[0]!=new_draws[c][0] or original['hmtx'][original.getBestCmap()[ord(c)]]!=font['hmtx'][mapping[ord(c)]]:different.append(c)
                    check(not different,weight+': a new sourced symbol differs from original TTC outline/hmtx')
                    summary['new16_ttc_outline_hmtx_differences']=different
            else:unavailable.append('original_'+weight+'_TTC_new16_oracle')
            result['sources'][weight]=summary
    comparisons={}
    protected=set(map(ord,read(OLD_PLANS[0])['glyphs']))|set(map(ord,'羁螣攥黛'))|set(range(0x4DC0,0x4E00))
    check(len(protected)==229,'Protected existing-refinement/hexagram union must remain229')
    for variant,(stem,family) in VARIANTS.items():
        result['formats'][variant]={};comparisons[variant]={}
        for ext in FORMATS:
            name=f'fonts/{stem}.{ext}';data=(project/name).read_bytes()
            with TTFont(BytesIO(data),recalcTimestamp=False) as font:
                mapping=font.getBestCmap();lm=line_metrics(font)
                check(set(mapping)==expected,name+': final cmap differs from exact30437-character set')
                check(sha(data)==provenance['fonts'][Path(name).name]['sha256'],name+': font provenance SHA differs')
                summary={'file':name,'sha256':sha(data),'bytes':len(data),'characters':len(mapping),'han':sum(han(cp) for cp in mapping),
                         'line_metrics':lm,'cmap':cmap_audit(font,check,name),'new_characters':{}}
                if archive is not None:
                    old_bytes=archive.read(prefix+name)
                    with TTFont(BytesIO(old_bytes),recalcTimestamp=False) as old:
                        check(set(mapping)-set(old.getBestCmap())==added,name+': encoded additions differ')
                        summary['old_regression']=old_regression(old,font,check,name)
                        check(protected<=set(old.getBestCmap()),name+': protected old subset missing')
                        summary['old_regression']['protected_subset_count']=len(protected)
                    if ext=='ttf':
                        diagnostics=[]
                        for size in (14,28):
                            before=ImageFont.truetype(BytesIO(old_bytes),size,layout_engine=ImageFont.Layout.BASIC)
                            after=ImageFont.truetype(BytesIO(data),size,layout_engine=ImageFont.Layout.BASIC)
                            a,b=before.getmask2(CONTROL,mode='L',anchor='ls'),after.getmask2(CONTROL,mode='L',anchor='ls')
                            diagnostics.append({'text':CONTROL,'physical_px':size,
                                'mask_and_offset_equal':a[1]==b[1] and a[0].size==b[0].size and bytes(a[0])==bytes(b[0]),
                                'before_mask_size':a[0].size,'after_mask_size':b[0].size,
                                'before_offset':a[1],'after_offset':b[1],'non_gating':True})
                        summary['old_control_raster_diagnostics']=diagnostics
                digits={c:font['hmtx'][mapping[ord(c)]][0] for c in '0123456789'}
                check(set(digits.values())=={450 if variant=='Regular' else 434},name+': tabular digit width changed')
                summary['digits']=digits
                drawings={c:drawing(font,c) for c in REQUESTED+'›'}
                advances={cp:font['hmtx'][glyph][0] for cp,glyph in mapping.items()}
                for c in REQUESTED:
                    value,box=drawings[c];plan=geometry['glyphs'][c]['variants'][variant]
                    check(box is not None and box[0]<box[2] and box[1]<box[3] and bool(value),name+': empty '+c)
                    check(advances[ord(c)]==plan['advance'],name+': planned advance differs for '+c)
                    check(box is not None and box[1]>=lm[2]-2 and box[3]<=lm[1]+2,name+': glyph outside unchanged line metrics '+c)
                    summary['new_characters'][c]={'advance':advances[ord(c)],'ink_bbox':box,
                        'origin':geometry['glyphs'][c]['origin'],'visual_center_y':None if box is None else (box[1]+box[3])/2}
                    if ext in ('otf','woff2'):
                        delta=geometric_delta(segments(plan['outline']),segments(value))
                        check(delta is not None and delta<=1.1,name+': final-unit outline plan mismatch for '+c)
                mirrors=[]
                for left,right in [('‹','›'),('«','»'),('⟨','⟩')]:
                    same_width=advances[ord(left)]==advances[ord(right)]
                    if ext in ('otf','woff2'):
                        delta=geometric_delta(segments(drawings[left][0],advances[ord(left)]),segments(drawings[right][0]))
                        check(same_width and delta is not None and delta<=1.1,name+': mirrored pair mismatch '+left+right)
                    else:
                        a,b=drawings[left][1],drawings[right][1]
                        delta=max(abs((advances[ord(left)]-a[2])-b[0]),abs(a[1]-b[1]),abs((advances[ord(left)]-a[0])-b[2]),abs(a[3]-b[3]))
                        check(same_width and delta<=3,name+': mirrored TrueType pair bounds mismatch '+left+right)
                    mirrors.append({'pair':left+right,'equal_advance':same_width,'mirror_delta_upm':delta})
                summary['mirrors']=mirrors
                joins={}
                for c in '─│┌┐└┘':
                    box=drawings[c][1];w=advances[ord(c)]
                    wanted={
                        '─':{'left':0,'right':w},'│':{'bottom':-320,'top':1160},
                        '┌':{'right':w,'bottom':-320},'┐':{'left':0,'bottom':-320},
                        '└':{'right':w,'top':1160},'┘':{'left':0,'top':1160}}[c]
                    actual=dict(zip(['left','bottom','right','top'],box))
                    errors={key:abs(actual[key]-value) for key,value in wanted.items()}
                    check(all(v<=1 for v in errors.values()),name+': box edge does not reach connecting cell boundary '+c)
                    joins[c]={'ink_bbox':box,'connecting_boundary_error_upm':errors,'unchanged_normal_line_advance_upm':1480}
                summary['box_connections']=joins
                centers={c:summary['new_characters'][c]['visual_center_y'] for c in '◆◇●■□▲▼▶◀'}
                check(all(value is not None and abs(value-380)<=80 for value in centers.values()),name+': geometry symbol center is not aligned near Han visual center')
                summary['geometric_centers']={'target_y':380,'tolerance_upm':80,'centers':centers}
                rasters=raster_checks(data,advances,lm)
                check(all(not x['empty'] and not x['outside_line_cell'] for x in rasters),name+': native14/28px raster missing or out of line cell')
                summary['native_rasters']=rasters
                alias_differences=[]
                for group in source_groups[variant]:
                    records=[drawing(font,chr(cp))[0] for cp in group]
                    if any(x!=records[0] for x in records[1:]) or len({tuple(font['hmtx'][mapping[cp]]) for cp in group})!=1:alias_differences.append(group)
                check(not alias_differences,name+': preserved source-shared aliases differ')
                summary['shared_source_aliases']={'groups_checked':len(source_groups[variant]),'differences':alias_differences}
                result['formats'][variant][ext]=summary
                comparisons[variant][ext]={'upm':lm[0],'cmap':set(mapping),'advances':advances,'line_metrics':lm,
                                            'new_bounds':{ord(c):drawings[c][1] for c in REQUESTED}}
        ref=comparisons[variant]['otf'];result['cross_format'][variant]={}
        for ext in ('ttf','woff2'):
            candidate=comparisons[variant][ext]
            equal={key:ref[key]==candidate[key] for key in ['upm','cmap','advances','line_metrics']}
            check(all(equal.values()),variant+': cross-format coverage/advance/line differs '+ext)
            bad=[cp for cp,a in ref['new_bounds'].items() if any(abs(x-y)>3 for x,y in zip(a,candidate['new_bounds'][cp]))]
            check(not bad,variant+': new glyph cross-format ink bounds differ by more than3UPM')
            result['cross_format'][variant][ext]={**equal,'new_bounds_outside3upm':bad}
    baseline_expected,scope=baseline_source_scope(project,sorted(map(chr,expected),key=ord),charset,comparisons,failures)
    check(set(map(ord,baseline_expected))==source_points and scope['excluded_count']==86,'Generic source scope must exclude exact78+8 originals')
    with TTFont(project/'fonts/SourceHanSansSC-Baseline.woff2',recalcTimestamp=False) as baseline,TTFont(project/'sources/AincradSeed-wao-Regular.otf',recalcTimestamp=False) as source:
        check(baseline.getBestCmap()==source.getBestCmap() and set(baseline.getBestCmap())==source_points,'Source baseline cmap differs')
        same_cff=bytes(baseline.reader['CFF '])==bytes(source.reader['CFF '])
        same_hmtx=baseline['hmtx'].metrics==source['hmtx'].metrics
        check(same_cff and same_hmtx,'Source baseline CFF program table or hmtx differs from genuine Regular source')
        result['source_baseline']={'characters':len(baseline.getBestCmap()),'scope':scope,
            'entire_cff_table_byte_identical_to_source':same_cff,'complete_hmtx_equal_to_source':same_hmtx}
    if os.name=='nt':
        import ctypes
        gdi=ctypes.WinDLL('gdi32',use_last_error=True)
        gdi.AddFontResourceExW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint,ctypes.c_void_p];gdi.AddFontResourceExW.restype=ctypes.c_int
        gdi.RemoveFontResourceExW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint,ctypes.c_void_p];gdi.RemoveFontResourceExW.restype=ctypes.c_int
        result['windows_private_loading']=[]
        for stem,_ in VARIANTS.values():
            for ext in ('otf','ttf'):
                name=f'fonts/{stem}.{ext}';loaded=0;removed=0
                try:loaded=gdi.AddFontResourceExW(str((project/name).resolve()),0x30,None)
                finally:
                    if loaded:removed=gdi.RemoveFontResourceExW(str((project/name).resolve()),0x30,None)
                check(loaded>0 and bool(removed),name+': Windows private loading/release failed')
                result['windows_private_loading'].append({'file':name,'private_faces_loaded':loaded,'released':bool(removed)})
    for name,value in hashes.items():check(file_sha(project/name)==value,name+': input changed during verification')
    check(file_sha(Path(__file__))==result['checker']['sha256'],'Checker source changed during verification')
    if archive is not None:archive.close();check(file_sha(baseline_path)==BASELINE_SHA,'Previous release archive changed during verification')
    result['regression_performed']=archive is not None
    result['mandatory_requirements_passed']=False if failures else True if not unavailable else None
    result['ok']=result['mandatory_requirements_passed']
    result['status']='failed' if failures else 'passed' if not unavailable else 'current_checks_passed_external_inputs_unavailable'
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
        args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:result[k] for k in ['ok','status','failures','character_scope','unavailable_inputs']},ensure_ascii=False))
    else:print(json.dumps(result,ensure_ascii=False,indent=2))
    return 1 if result['failures'] else 0 if result['ok'] else 2


if __name__=='__main__':sys.exit(main())
