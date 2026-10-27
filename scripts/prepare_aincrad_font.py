#!/usr/bin/env python3
"""Prepare the v0.3 source subsets and explicit local UI refinement plans.

The vocabulary controls coverage. Local rules are limited to selected common UI
characters; the eight accepted v0.2 glyph plans are retained verbatim. This is
component-based outline work, not a claim of hand-designing an entire character set.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

from build_aincrad_font import DEFAULT_PROJECT, acquire_seed, get_contours, load_charset_extensions, sha256, vocabulary_characters, write_json


SPEECH = set('设计订让访许证识词话该语请读课谁调谢记录认')
HAND = set('打持指按提接换操搜排择拖拽抓拉推擦抹扫抄投折报护挂振损捡掉探插播摘撤拷捆抢')
TURNS = set('已己巴包记纪起导仓')


def area(nodes: list) -> float:
    return sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(nodes,nodes[1:]+nodes[:1]))/2


def local_plan(recording: RecordingPen, character: str, weight: str) -> dict:
    contours = get_contours(recording)
    plan = dict(expected_contour_nodes=[len(nodes) for nodes,_ in contours],
                node_deltas=[],edge_replacements=[],edge_path_replacements=[],rules=[])
    delta = 2 if weight=='Regular' else 3
    for ci,(nodes,edges) in enumerate(contours):
        xs,ys = [p[0] for p in nodes],[p[1] for p in nodes]
        left,right,bottom,top=min(xs),max(xs),min(ys),max(ys)
        # Open only simple enclosed rectangles. Do not scale whole characters or
        # touch curved counters and tight, tiny details.
        if (len(nodes)==4 and all(op=='lineTo' for op,_ in edges) and area(nodes)<0
            and right-left>=70 and top-bottom>=45
            and all(x in (left,right) and y in (bottom,top) for x,y in nodes)):
            for ni,(x,y) in enumerate(nodes):
                plan['node_deltas'].append(dict(contour=ci,nodes=[ni],
                    delta=[-delta if x==left else delta,-delta if y==bottom else delta]))
            plan['rules'].append('rectangular_counter')
        if character in SPEECH and len(nodes)==4 and right<440 and bottom>540 and top-bottom<300:
            for ei,(op,_controls) in enumerate(edges):
                if op=='curveTo':
                    plan['edge_replacements'].append(dict(contour=ci,edge=ei,operator='lineTo'))
            plan['rules'].append('speech_dot_straight_edges')
        if character in HAND and left<120 and right<430 and top-bottom>700:
            for ei,(p,q) in enumerate(zip(nodes,nodes[1:]+nodes[:1])):
                prev,nxt=nodes[ei-1],nodes[(ei+2)%len(nodes)]
                if (edges[ei][0]=='lineTo' and p[0]==q[0] and 250<p[0]<420
                    and 480<p[1]<700 and 40<q[1]-p[1]<130
                    and prev[0]<p[0]-40 and nxt[0]<q[0]-40
                    and prev[1]==p[1] and nxt[1]==q[1]):
                    plan['node_deltas'].append(dict(contour=ci,nodes=[ei,(ei+1)%len(nodes)],
                        delta=[-12 if weight=='Regular' else -14,0]))
                    plan['rules'].append('hand_radical_upper_terminal')
        if character in TURNS:
            for ei,(op,controls) in enumerate(edges):
                if op!='curveTo':continue
                p,q=nodes[ei],nodes[(ei+1)%len(nodes)]
                # Locate the concave bottom-left turn and its matching exterior.
                if not (p[0]-q[0]>60 and 40<q[1]-p[1]<180 and p[1]<100
                        and abs(controls[0][1]-p[1])<1 and abs(controls[1][0]-q[0])<1):continue
                for oi,(outer_op,outer_controls) in enumerate(edges):
                    if outer_op!='curveTo':continue
                    a,b=nodes[oi],nodes[(oi+1)%len(nodes)]
                    side,base=q[0]-a[0],p[1]-b[1]
                    if not (40<side<130 and 40<base<130 and abs(a[1]-q[1])<25
                            and abs(b[0]-p[0])<25
                            and abs(outer_controls[0][0]-a[0])<1
                            and abs(outer_controls[1][1]-b[1])<1):continue
                    inner=round(min(42 if weight=='Regular' else 48,(p[0]-q[0])*.45,(q[1]-p[1])*.6))
                    outer=round(inner+(side+base)*(1-1/math.sqrt(2)))
                    if outer>=min(b[0]-a[0],a[1]-b[1])*.85:continue
                    plan['edge_path_replacements'].extend([
                        dict(contour=ci,edge=ei,start=list(p),end=list(q),new_segments=[
                            ['lineTo',[q[0]+inner,p[1]]],['lineTo',[q[0],p[1]+inner]],['lineTo',list(q)]]),
                        dict(contour=ci,edge=oi,start=list(a),end=list(b),new_segments=[
                            ['lineTo',[a[0],b[1]+outer]],['lineTo',[a[0]+outer,b[1]]],['lineTo',list(b)]])])
                    plan['rules'].append('paired_lower_turn_chamfer')
                    break
        # Flatten only small, almost straight exposed cap curves. Main sweeps,
        # long curves, interior contours and edited turns are excluded.
        if area(nodes)>0:
            excluded={e['edge'] for e in plan['edge_path_replacements'] if e['contour']==ci}
            replaced={e['edge'] for e in plan['edge_replacements'] if e['contour']==ci}
            caps=0
            for ei,(op,controls) in enumerate(edges):
                if op!='curveTo' or ei in excluded or ei in replaced:continue
                p,q=nodes[ei],nodes[(ei+1)%len(nodes)]
                dx,dy=q[0]-p[0],q[1]-p[1]; length=math.hypot(dx,dy)
                if not 38<=length<=125:continue
                distances=[abs(dx*(c[1]-p[1])-dy*(c[0]-p[0]))/length for c in controls]
                projections=[((c[0]-p[0])*dx+(c[1]-p[1])*dy)/(length*length) for c in controls]
                if max(distances)<=6 and all(0<=t<=1 for t in projections) and max(distances)>.1:
                    plan['edge_replacements'].append(dict(contour=ci,edge=ei,operator='lineTo'))
                    plan['rules'].append('short_stroke_cap')
                    caps+=1
                    if caps==3:break
    plan['rules']=list(dict.fromkeys(plan['rules']))
    return plan


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir',type=Path,default=DEFAULT_PROJECT)
    parser.add_argument('--refresh-sources',action='store_true',help='Regenerate only v0.3 seed subsets from the original local TTC inputs')
    args=parser.parse_args()
    project=args.project_dir.resolve()
    vocabulary=json.loads((project/'data'/'ui-vocabulary.json').read_text(encoding='utf-8'))
    inherited=json.loads((project/'data'/'refinements-v020.json').read_text(encoding='utf-8'))
    with TTFont(project/'fonts'/'AincradUISc-v020-Regular.woff2') as previous:
        old=''.join(map(chr,previous.getBestCmap()))
    extensions,_=load_charset_extensions(project)
    characters=vocabulary_characters(vocabulary,old,extensions)
    candidates=set(vocabulary['refinement_candidates'])|SPEECH|HAND|TURNS
    candidates=(candidates&set(characters))-set(inherited['glyphs'])
    source_record=project/'data'/'source-v030.json'
    prior_sources=json.loads(source_record.read_text(encoding='utf-8')).get('sources',{}) if source_record.is_file() else {}
    fonts,source_info,drawings={},{},{}
    for weight in ('Regular','Medium'):
        seed,info=acquire_seed(project,weight,characters,refresh=args.refresh_sources)
        for key,value in prior_sources.get(weight,{}).items():
            if key not in ('file','sha256'):info.setdefault(key,value)
        fonts[weight]=seed; source_info[weight]=info
        gs=seed.getGlyphSet(); cmap=seed.getBestCmap(); drawings[weight]={}
        for c in sorted(candidates|set(inherited['glyphs'])):
            pen=RecordingPen(); gs[cmap[ord(c)]].draw(pen); drawings[weight][c]=pen
        # Verify that expanding the subset did not alter any accepted source path.
        with TTFont(project/'sources'/f'AincradSeed-{weight}.otf') as old_seed:
            old_set,old_map=old_seed.getGlyphSet(),old_seed.getBestCmap()
            for c in inherited['glyphs']:
                pen=RecordingPen();old_set[old_map[ord(c)]].draw(pen)
                if pen.value!=drawings[weight][c].value:
                    raise ValueError(f'Inherited source geometry changed for {c} / {weight}')
    glyphs=copy.deepcopy(inherited['glyphs']); new=[]
    for c in sorted(candidates):
        plans={weight:local_plan(drawings[weight][c],c,weight) for weight in fonts}
        if all(plan['rules'] for plan in plans.values()):
            glyphs[c]=dict(issue='Common UI local counter, terminal or component adjustment.',**plans)
            new.append(c)
    plan=dict(version='0.3.0',coordinate_space='Original 1000 UPM source contours before condensation.',
        method='Reviewed component rules applied only to selected UI characters; not full manual refinement of every glyph.',
        inherited_plan=dict(file='data/refinements-v020.json',sha256=sha256(project/'data'/'refinements-v020.json')),
        source_sha256_by_weight={w:i['sha256'] for w,i in source_info.items()},
        refined_characters=inherited['refined_characters']+''.join(new),new_refined_characters=''.join(new),glyphs=glyphs)
    write_json(project/'data'/'refinements-v030.json',plan)
    write_json(project/'data'/'source-v030.json',dict(version='0.3.0',sources=source_info))
    for seed in fonts.values():seed.close()
    print(json.dumps(dict(characters=len(characters),han=sum(0x4e00<=ord(c)<=0x9fff for c in characters),
        new_local_refinements=len(new),inherited_refinements=len(inherited['glyphs']),
        new_refined_characters=''.join(new)),ensure_ascii=True))


if __name__=='__main__':
    main()
