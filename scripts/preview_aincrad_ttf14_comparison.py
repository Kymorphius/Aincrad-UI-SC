"""Render a real Regular TTF A/B for 攥 and 螣 at 14 CSS px.

--prepare-only extracts/verifies the immutable baseline and writes the page.
--load-only additionally verifies TTF resources and custom-font loading, without
requiring a changed candidate or producing a readability/comparison verdict.
The normal run requires target pixel changes and pixel-identical controls.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import functools
import hashlib
import html
import io
import json
import math
import os
from pathlib import Path
import threading
from http.server import ThreadingHTTPServer
from zipfile import ZipFile

from fontTools.ttLib import TTFont
from PIL import Image, ImageChops, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

from preview_aincrad_dense_comparison import (
    QuietHandler, actual_fonts, browser_default, digest, glyph_bounds,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT if (ROOT / "fonts").is_dir() else ROOT / "design" / "aincrad-ui-sc"
ARCHIVE = ARTIFACT / "Aincrad-UI-SC-v0.3-dense14-hexagrams.zip"
BEFORE = "AincradUISc-v030-before-ttf14-Regular.ttf"
AFTER = "AincradUISc-Regular.ttf"
ALIASES = {"before": "TTF14 Before Regular", "after": "TTF14 After Regular"}
TARGETS = ("攥", "螣")
PHRASES = ("攥紧", "螣蛇")
CONTROLS = ("羁黛", "命宫2026")
PALETTES = {"light": (241, 244, 238), "dark": (36, 52, 62)}


def baseline_copy(archive: Path) -> dict:
    archive_hash = digest(archive)
    with ZipFile(archive) as package:
        members = [name for name in package.namelist() if name.endswith("fonts/AincradUISc-Regular.ttf")]
        assert len(members) == 1, "Expected exactly one Regular TTF archive member"
        payload = package.read(members[0])
    path = ARTIFACT / "fonts" / BEFORE
    if path.exists():
        assert path.read_bytes() == payload, "Existing immutable TTF baseline differs from archive"
    else:
        path.write_bytes(payload)
    assert digest(archive) == archive_hash
    return {"archive": archive.name, "archive_sha256": archive_hash, "member": members[0],
            "file": "fonts/" + BEFORE, "sha256": digest(path), "bytes": len(payload),
            "archive_preserved": True}


def pair(text: str, theme: str, kind: str, index: int) -> str:
    title = text + (f" / U+{ord(text):04X}" if kind == "target" else "")
    return (f'<article class="pair" data-theme="{theme}" data-kind="{kind}" data-index="{index}">'
            f'<h3>{html.escape(title)}</h3><div class="versions">' + "".join(
                f'<div><p class="caption">{label}</p><div class="surface" data-version="{version}">'
                f'<span class="sample {version}">{html.escape(text)}</span></div></div>'
                for version, label in (("before", "修改前 / BEFORE"), ("after", "修改后 / AFTER")))
            + "</div></article>")


def write_html(baseline: dict) -> Path:
    sections = []
    for theme, label in (("light", "浅色"), ("dark", "深色")):
        content = "".join(
            f'<h2 class="subhead">{heading}</h2><div class="grid">'
            + "".join(pair(text, theme, kind, index) for index, text in enumerate(texts)) + "</div>"
            for kind, heading, texts in (("target", "单字 · 本次修改", TARGETS),
                                         ("phrase", "词语 · 保留相邻文字", PHRASES),
                                         ("control", "未修改控制 · 像素应相同", CONTROLS)))
        sections.append(f'<section class="theme {theme}"><header><h2>{label}</h2>'
                        '<p>Regular TTF · 14 CSS px · 0 字距 · 相同字宽、行高与底色</p></header>'
                        + content + "</section>")
    document = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,">
<title>Aincrad UI SC · Regular TTF 攥螣 14px 对照</title><style>
@font-face{font-family:"TTF14 Before Regular";src:url("fonts/AincradUISc-v030-before-ttf14-Regular.ttf") format("truetype");font-weight:400;font-style:normal;font-display:block}
@font-face{font-family:"TTF14 After Regular";src:url("fonts/AincradUISc-Regular.ttf") format("truetype");font-weight:400;font-style:normal;font-display:block}
*{box-sizing:border-box}body{margin:0;background:#dbe3df;color:#24343e;font:12px "Segoe UI","Microsoft YaHei",sans-serif}main{width:850px;max-width:100%;margin:auto;padding:24px}.intro{padding-bottom:18px;margin-bottom:20px;border-bottom:1px solid #a9bbb4}.intro h1{font-size:25px;font-weight:400;margin:9px 0}.intro p,.foot{font-size:11px;line-height:1.8;color:#61766f;margin:5px 0}.eyebrow{letter-spacing:.13em}.hash{font-size:9px!important;overflow-wrap:anywhere}#runtime{color:#94712f}.theme{padding:20px;border:1px solid var(--rule);background:var(--surface);color:var(--ink);margin-bottom:22px}.light{--surface:#f1f4ee;--ink:#24343e;--rule:#c3d0c7;--muted:#61767c}.dark{--surface:#24343e;--ink:#f1f4ee;--rule:#50646c;--muted:#b8c6c5}.theme header{display:flex;align-items:baseline;justify-content:space-between;gap:15px}.theme header h2{font-size:15px;font-weight:500;margin:0}.theme header p{font-size:10px;color:var(--muted);margin:0}.subhead{font-size:11px;font-weight:500;color:var(--muted);margin:20px 0 9px}.grid{display:grid;grid-template-columns:repeat(2,300px);gap:18px}.pair{width:300px;padding:12px;border:1px solid var(--rule);background:var(--surface);color:var(--ink)}.pair h3{font:400 11px "Segoe UI","Microsoft YaHei",sans-serif;margin:0 0 11px;color:var(--muted)}.versions{display:grid;grid-template-columns:122px 122px;gap:18px}.caption{font:9px "Segoe UI","Microsoft YaHei",sans-serif;color:var(--muted);margin:0 0 5px;white-space:nowrap}.surface{width:122px;height:52px;padding:12px 8px;background:var(--surface);color:var(--ink);overflow:visible}.sample{display:inline-block;font-size:14px;font-weight:400;font-style:normal;line-height:28px;letter-spacing:0;font-synthesis:none;font-variant-numeric:normal;white-space:pre;transform:none;filter:none;opacity:1}.before{font-family:"TTF14 Before Regular",sans-serif}.after{font-family:"TTF14 After Regular",sans-serif}@media(max-width:760px){main{width:390px;padding:16px}.theme{padding:16px}.grid{grid-template-columns:300px}.theme header{display:block}.theme header p{margin-top:5px}}
</style></head><body><main id="ttf14-study"><div class="intro"><p class="eyebrow">AINCRAD UI SC / TTF / NATIVE 14 PX</p><h1>攥 · 螣 / Regular TTF 前后对照</h1><p>左列为已归档的 dense14-hexagrams 包内 TTF，右列为当前 Regular TTF。两列直接加载 .ttf，使用真实 14 CSS px；不缩放字体、不补偿字宽、不使用滤镜。原图保留浏览器像素，紧凑放大图仅用于观察像素。</p><p id="runtime">正在加载两版 TTF</p><p class="hash">Baseline archive SHA-256: %%HASH%%</p></div>%%SECTIONS%%<p class="foot">优先观察 DPR 1 的浅深两种主题；DPR 2 用于回归检查。像素改变和字宽不变不等于所有小字号都可读。本页只验证桌面 Chromium 的 TTF 渲染，不能代替 Flutter / Android 真实盘面验收。</p></main><script>
window.ttf14Ready=Promise.all([
 document.fonts.load('14px "TTF14 Before Regular"','攥螣攥紧螣蛇羁黛命宫2026'),
 document.fonts.load('14px "TTF14 After Regular"','攥螣攥紧螣蛇羁黛命宫2026')
]).then(fonts=>{const ready=fonts.every(items=>items.length>0);document.getElementById('runtime').textContent=(ready?'两版 TTF 已加载':'TTF 未完整加载')+' / DPR '+devicePixelRatio+' / browser zoom '+visualViewport.scale;return ready;});
</script></body></html>
'''
    document = document.replace("%%HASH%%", baseline["archive_sha256"]).replace("%%SECTIONS%%", "".join(sections))
    path = ARTIFACT / "ttf14-comparison.html"
    path.write_text(document.rstrip() + "\n", encoding="utf-8")
    return path


def source_records() -> dict:
    required = set("".join(TARGETS + PHRASES + CONTROLS))
    charset = json.loads((ARTIFACT / "data/charset.json").read_text(encoding="utf-8"))
    assert not required - set(charset["characters"]), "Study contains unrelated missing characters"
    records = {}
    for version, filename in (("before", BEFORE), ("after", AFTER)):
        path = ARTIFACT / "fonts" / filename
        with TTFont(path) as font:
            assert "glyf" in font and "CFF " not in font and font.flavor is None, "Expected actual sfnt TrueType outlines"
            cmap = font.getBestCmap()
            assert all(ord(character) in cmap for character in required)
            records[version] = {
                "file": "fonts/" + filename, "sha256": digest(path), "bytes": path.stat().st_size,
                "css_alias": ALIASES[version], "internal_family": font["name"].getDebugName(1),
                "postscript_name": font["name"].getDebugName(6), "version": font["name"].getDebugName(5),
                "format": "TrueType sfnt/glyf", "upm": font["head"].unitsPerEm,
                "hhea": {key: getattr(font["hhea"], key) for key in ("ascent", "descent", "lineGap")},
                "os2_line_metrics": {key: getattr(font["OS/2"], key) for key in
                                     ("sTypoAscender", "sTypoDescender", "sTypoLineGap", "usWinAscent", "usWinDescent")},
                "advances": {character: font["hmtx"][cmap[ord(character)]][0] for character in sorted(required)},
            }
    for key in ("upm", "hhea", "os2_line_metrics", "advances"):
        assert records["before"][key] == records["after"][key], ("Metrics changed", key)
    return records


def compare_pair(page, cdp, selector: str, sources: dict, dpr: int, theme: str, aliases: dict | None = None) -> tuple[dict, dict]:
    aliases = aliases or ALIASES
    page.locator(selector).evaluate("element=>element.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'})")
    record, images = {"selector": selector, "versions": {}}, {}
    for version in ("before", "after"):
        leaf = selector + f' [data-version="{version}"] .sample'
        fonts = actual_fonts(cdp, leaf)
        assert fonts and all(font["isCustomFont"] and font["glyphCount"] > 0
                             and font["familyName"] == sources[version]["internal_family"] for font in fonts), fonts
        metrics = page.locator(leaf).evaluate('''element=>{
          const css=getComputedStyle(element),rect=element.getBoundingClientRect(),
            bg=getComputedStyle(element.parentElement);
          const ancestors=[];for(let node=element;node;node=node.parentElement){const s=getComputedStyle(node);
            ancestors.push({transform:s.transform,filter:s.filter,zoom:s.zoom,opacity:s.opacity});}
          return {text:element.textContent,fontFamily:css.fontFamily,fontSize:css.fontSize,
            fontWeight:css.fontWeight,lineHeight:css.lineHeight,letterSpacing:css.letterSpacing,
            color:css.color,background:bg.backgroundColor,width:rect.width,height:rect.height,
            x:rect.x+scrollX,y:rect.y+scrollY,ancestors};}''')
        assert aliases[version] in metrics["fontFamily"]
        assert metrics["fontSize"] == "14px" and metrics["lineHeight"] == "28px" and metrics["fontWeight"] == "400"
        assert metrics["letterSpacing"] == "normal" or metrics["letterSpacing"] == "0px"
        assert all(item["transform"] == item["filter"] == "none" and item["zoom"] == item["opacity"] == "1"
                   for item in metrics["ancestors"])
        image = Image.open(io.BytesIO(page.locator(selector + f' [data-version="{version}"]').screenshot(scale="device"))).convert("RGB")
        bounds = glyph_bounds(image, PALETTES[theme])
        images[version] = image
        record["versions"][version] = {**metrics, "actual_fonts": fonts, "ink_bounds_physical_px": list(bounds),
                                      "surface_size_physical_px": list(image.size),
                                      "raster_sha256": hashlib.sha256(image.tobytes()).hexdigest()}
    before, after = (record["versions"][key] for key in ("before", "after"))
    for key in ("fontSize", "fontWeight", "lineHeight", "letterSpacing", "color", "background", "width", "height", "y"):
        assert before[key] == after[key], (key, before[key], after[key])
    phase_delta = (after["x"] - before["x"]) * dpr
    assert abs(phase_delta - round(phase_delta)) < 0.000001
    assert images["before"].size == images["after"].size
    difference = ImageChops.difference(images["before"], images["after"])
    colors = difference.getcolors(difference.width * difference.height)
    assert colors is not None
    record.update({"changed_physical_pixels": sum(count for count, color in colors if color != (0, 0, 0)),
                   "difference_bounds_physical_px": list(difference.getbbox()) if difference.getbbox() else None,
                   "same_width_line_y_phase": True, "unclipped": True})
    return record, images


def compact_sheet(cases: list[dict], destination: Path | None = None) -> dict:
    width, height, top, margin = 330, 190, 100, 20
    sheet = Image.new("RGB", (width * 4 + margin * 2, top + height * len(TARGETS) + 50), "#dbe3df")
    draw, font = ImageDraw.Draw(sheet), ImageFont.load_default(size=13)
    draw.text((margin, 16), "REGULAR TTF / REAL 14 CSS px / BEFORE LEFT - AFTER RIGHT", fill="#24343e", font=ImageFont.load_default(size=18))
    draw.text((margin, 45), "Original browser pixels, shared crop; nearest-neighbor enlargement for pixel observation only.", fill="#50646c", font=font)
    crops = []
    for column, (dpr, theme) in enumerate(((1, "light"), (1, "dark"), (2, "light"), (2, "dark"))):
        factor, x = 8 if dpr == 1 else 4, margin + column * width
        draw.text((x + 12, 76), f"DPR {dpr} / {theme.upper()} / physical pixels x{factor}", fill="#24343e", font=font)
        background, foreground = PALETTES[theme], PALETTES["dark" if theme == "light" else "light"]
        for row, character in enumerate(TARGETS):
            item = next(case for case in cases if case["character"] == character and case["dpr"] == dpr and case["theme"] == theme)
            bounds = [glyph_bounds(item["images"][version], background) for version in ("before", "after")]
            crop = (min(box[0] for box in bounds) - dpr, min(box[1] for box in bounds) - dpr,
                    max(box[2] for box in bounds) + dpr, max(box[3] for box in bounds) + dpr)
            y = top + row * height
            draw.rectangle((x, y, x + width - 2, y + height - 2), fill=background)
            draw.text((x + 12, y + 9), f"U+{ord(character):04X}", fill=foreground, font=font)
            for index, version in enumerate(("before", "after")):
                image = item["images"][version].crop(crop)
                image = image.resize((image.width * factor, image.height * factor), Image.Resampling.NEAREST)
                draw.text((x + 40 + index * width // 2, y + 29), version.upper(), fill=foreground, font=font)
                sheet.paste(image, (x + width // 4 + index * width // 2 - image.width // 2, y + 49))
            crops.append({"character": character, "dpr": dpr, "theme": theme, "shared_crop_physical_px": list(crop), "magnification": factor})
    draw.text((margin, sheet.height - 32), "DPR1 is the primary case; DPR2 is a regression sample. No filters or interpolated glyph pixels.", fill="#50646c", font=font)
    path = destination or ARTIFACT / "ttf14-comparison-compact.png"
    sheet.save(path)
    return {"file": path.name, "method": "shared crop / nearest-neighbor", "crops": crops, "width": sheet.width, "height": sheet.height}


def run(archive: Path, baseline: dict, browser_path: str | None, load_only: bool = False) -> dict:
    result = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "mode": "load-only" if load_only else "comparison",
              "scope": "Desktop Chromium, actual Regular TTF; primary DPR1, DPR2 regression; not Flutter/Android acceptance",
              "baseline": baseline, "sources": {}, "runs": [], "font_resources": [], "native_screenshots": [],
              "console_errors": [], "page_errors": [], "failed_requests": [], "http_errors": [],
              "css_font_size": 14, "letter_spacing": 0, "dprs": [1] if load_only else [1, 2],
              "visual_review": {"status": "not-performed-load-only" if load_only else "requires-human-review",
                                "note": "Pixel changes alone do not establish improved readability."}}
    server = None
    try:
        result["sources"] = source_records()
        charset = json.loads((ARTIFACT / "data/charset.json").read_text(encoding="utf-8"))
        result["charset_summary"] = {key: charset[key] for key in ("version", "han_count", "character_count")}
        server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(ARTIFACT)))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        compact_cases = []
        with sync_playwright() as playwright, ExitStack() as owned:
            options = {"headless": True}
            if browser_path:
                options["executable_path"] = browser_path
            browser = playwright.chromium.launch(**options)
            owned.callback(browser.close)
            result["browser_version"] = browser.version
            for dpr in (1,) if load_only else (1, 2):
                context = browser.new_context(viewport={"width": 900, "height": 1000}, device_scale_factor=dpr)
                page = context.new_page()
                responses = []
                page.on("console", lambda message: result["console_errors"].append(message.text) if message.type == "error" else None)
                page.on("pageerror", lambda error: result["page_errors"].append(str(error)))
                page.on("requestfailed", lambda request: result["failed_requests"].append(request.failure))
                page.on("response", lambda response: result["http_errors"].append({"url": response.url, "status": response.status}) if response.status >= 400 else None)
                page.on("response", lambda response: responses.append(response) if response.request.resource_type == "font" else None)
                page.goto(f"http://127.0.0.1:{server.server_port}/ttf14-comparison.html", wait_until="networkidle")
                assert page.evaluate("window.ttf14Ready")
                assert page.evaluate("devicePixelRatio") == dpr and page.evaluate("visualViewport.scale") == 1
                faces = page.evaluate("Array.from(document.fonts,face=>({family:face.family,status:face.status}))")
                assert len(faces) == 2 and all(face["status"] == "loaded" for face in faces)
                rules = page.evaluate("Array.from(document.styleSheets[0].cssRules).filter(rule=>rule.type===CSSRule.FONT_FACE_RULE).map(rule=>({family:rule.style.fontFamily,src:rule.style.src}))")
                assert len(rules) == 2 and all('format("truetype")' in rule["src"] and ".ttf" in rule["src"] for rule in rules)
                assert {response.url.rsplit("/", 1)[-1] for response in responses} == {BEFORE, AFTER}
                for response in responses:
                    filename = response.url.rsplit("/", 1)[-1]
                    version = "before" if filename == BEFORE else "after"
                    resource = {"dpr": dpr, "file": filename, "resource_type": response.request.resource_type,
                                "status": response.status, "mime": response.headers.get("content-type"),
                                "response_sha256": hashlib.sha256(response.body()).hexdigest()}
                    assert resource["status"] == 200 and resource["response_sha256"] == result["sources"][version]["sha256"]
                    result["font_resources"].append(resource)
                cdp = context.new_cdp_session(page)
                cdp.send("DOM.enable")
                cdp.send("CSS.enable")
                current = {"dpr": dpr, "font_faces": faces, "font_face_rules": rules, "themes": []}
                if load_only:
                    current["loaded_samples"] = []
                    for theme in ("light", "dark"):
                        for kind, texts in (("target", TARGETS), ("phrase", PHRASES), ("control", CONTROLS)):
                            for index, text in enumerate(texts):
                                for version in ("before", "after"):
                                    selector = f'.pair[data-theme="{theme}"][data-kind="{kind}"][data-index="{index}"] .sample.{version}'
                                    fonts = actual_fonts(cdp, selector)
                                    assert fonts and all(font["isCustomFont"] and font["glyphCount"] > 0
                                                         and font["familyName"] == result["sources"][version]["internal_family"] for font in fonts)
                                    current["loaded_samples"].append({"theme": theme, "kind": kind, "text": text,
                                                                       "version": version, "actual_fonts": fonts})
                    result["runs"].append(current)
                    context.close()
                    continue
                for theme in ("light", "dark"):
                    theme_result = {"theme": theme, "targets": [], "phrases": [], "controls": []}
                    for kind, texts, destination in (("target", TARGETS, "targets"), ("phrase", PHRASES, "phrases"), ("control", CONTROLS, "controls")):
                        for index, text in enumerate(texts):
                            selector = f'.pair[data-theme="{theme}"][data-kind="{kind}"][data-index="{index}"]'
                            evidence, images = compare_pair(page, cdp, selector, result["sources"], dpr, theme)
                            evidence["text"] = text
                            if not load_only:
                                assert evidence["changed_physical_pixels"] == 0 if kind == "control" else evidence["changed_physical_pixels"] > 0, (kind, text, theme, dpr, evidence["changed_physical_pixels"])
                                if kind == "target":
                                    compact_cases.append({"character": text, "dpr": dpr, "theme": theme, "images": images})
                            theme_result[destination].append(evidence)
                    current["themes"].append(theme_result)
                assert page.evaluate("document.documentElement.scrollWidth") == 900
                result["runs"].append(current)
                if not load_only:
                    filename = "ttf14-comparison.png" if dpr == 1 else "ttf14-comparison-dpr2.png"
                    page.locator("#ttf14-study").screenshot(path=str(ARTIFACT / filename), scale="device")
                    result["native_screenshots"].append({"file": filename, "dpr": dpr})
                context.close()
        for key in ("console_errors", "page_errors", "failed_requests", "http_errors"):
            assert not result[key], (key, result[key])
        assert digest(archive) == baseline["archive_sha256"]
        assert source_records() == result["sources"], "TTF fonts changed during verification"
        names = ["ttf14-comparison.html"]
        if not load_only:
            result["compact_sheet"] = compact_sheet(compact_cases)
            names += [item["file"] for item in result["native_screenshots"]] + [result["compact_sheet"]["file"]]
        result["artifact_hashes"] = {name: digest(ARTIFACT / name) for name in names}
        result["comparison_performed"] = not load_only
        result["passed"] = True
    except Exception as error:
        result.update({"passed": False, "error": str(error)})
        raise
    finally:
        if server:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
        report_name = "ttf14-comparison-load.json" if load_only else "ttf14-comparison.json"
        (ARTIFACT / "data" / report_name).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def candidate_study(directory: Path, browser_path: str | None) -> dict:
    """One Chromium page, DPR1, all candidate TTFs; never replace production files."""
    paths = {"baseline": ARTIFACT / "fonts" / BEFORE,
             **{label: directory / f"candidate-{label}.ttf" for label in "abcdef"}}
    aliases = {key: "TTF14 Study " + key.upper() for key in paths}
    required = set("".join(TARGETS + PHRASES + CONTROLS))
    sources = {}
    for key, path in paths.items():
        with TTFont(path) as font:
            assert "glyf" in font and "CFF " not in font and font.flavor is None
            cmap = font.getBestCmap()
            assert all(ord(character) in cmap for character in required)
            sources[key] = {"file": str(path.relative_to(ARTIFACT)).replace("\\", "/"), "sha256": digest(path),
                            "internal_family": font["name"].getDebugName(1),
                            "advances": {character: font["hmtx"][cmap[ord(character)]][0] for character in sorted(required)},
                            "hhea": {name: getattr(font["hhea"], name) for name in ("ascent", "descent", "lineGap")}}
        assert sources[key]["advances"] == sources["baseline"]["advances"]
        assert sources[key]["hhea"] == sources["baseline"]["hhea"]
    faces = "".join(f'@font-face{{font-family:"{aliases[key]}";src:url("{Path(os.path.relpath(path,directory)).as_posix()}") format("truetype");font-display:block}}' for key, path in paths.items())
    sections = []
    for theme in ("light", "dark"):
        rows = []
        for label in "abcdef":
            cells = []
            for kind, texts in (("target", TARGETS), ("phrase", PHRASES), ("control", CONTROLS)):
                for index, text in enumerate(texts):
                    markup = pair(text, theme, kind, index)
                    markup = markup.replace('class="sample before"', f'class="sample before" style="font-family:\'{aliases["baseline"]}\'"')
                    markup = markup.replace('class="sample after"', f'class="sample after" style="font-family:\'{aliases[label]}\'"')
                    cells.append(markup)
            rows.append(f'<section class="candidate" data-candidate="{label}"><h2>CANDIDATE {label.upper()} / baseline left, candidate right</h2><div class="grid">' + "".join(cells) + "</div></section>")
        sections.append(f'<section class="theme {theme}" data-theme="{theme}"><h1>{theme.upper()} / DPR1 / 14 CSS px</h1>' + "".join(rows) + "</section>")
    document = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><link rel="icon" href="data:,"><title>TTF14 candidates A–F</title><style>' + faces + '''
*{box-sizing:border-box}body{margin:0;background:#dbe3df;color:#24343e;font:12px "Segoe UI","Microsoft YaHei",sans-serif}main{width:1480px;margin:auto;padding:20px}main>h1{font-size:24px;font-weight:400;margin:0 0 8px}.intro{font-size:11px;line-height:1.8;margin:0 0 20px}.theme{padding:16px;border:1px solid var(--rule);background:var(--surface);color:var(--ink);margin-bottom:20px}.light{--surface:#f1f4ee;--ink:#24343e;--rule:#c3d0c7;--muted:#61767c}.dark{--surface:#24343e;--ink:#f1f4ee;--rule:#50646c;--muted:#b8c6c5}.theme>h1{font-size:15px;font-weight:500;margin:0 0 15px}.candidate{margin:0 0 18px}.candidate:last-child{margin-bottom:0}.candidate>h2{font-size:11px;font-weight:500;color:var(--muted);margin:0 0 7px}.grid{display:grid;grid-template-columns:repeat(6,220px);gap:12px}.pair{width:220px;padding:12px;border:1px solid var(--rule);background:var(--surface);color:var(--ink)}.pair h3{font:400 11px "Segoe UI","Microsoft YaHei",sans-serif;margin:0 0 10px;color:var(--muted)}.versions{display:grid;grid-template-columns:88px 88px;gap:16px}.caption{font:9px "Segoe UI","Microsoft YaHei",sans-serif;color:var(--muted);margin:0 0 4px;white-space:nowrap}.surface{width:88px;height:52px;padding:12px 8px;background:var(--surface);color:var(--ink);overflow:visible}.sample{display:inline-block;font-size:14px;font-weight:400;font-style:normal;line-height:28px;letter-spacing:0;font-synthesis:none;font-variant-numeric:normal;white-space:pre;transform:none;filter:none;opacity:1}
</style></head><body><main id="candidate-study"><h1>攥 · 螣 / TTF 14px 候选 A–F</h1><p class="intro">每格左为当前 Regular TTF 基线，右为候选。真实 14 CSS px，DPR 1，0 字距，行高与颜色相同。字形样张不使用缩放或滤镜；控制文字应保持像素相同。候选尚未集成进正式字体。</p>''' + "".join(sections) + "</main></body></html>"
    (directory / "study.html").write_text(document.rstrip() + "\n", encoding="utf-8")
    result = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "mode": "candidate-study", "dpr": 1,
              "sources": sources, "font_resources": [], "comparisons": [], "console_errors": [], "page_errors": [],
              "visual_review": {"status": "requires-human-review"}, "scope": "Actual TTF, desktop Chromium DPR1 only; no production changes"}
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(ARTIFACT)))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    compact_cases = []
    try:
        with sync_playwright() as playwright, ExitStack() as owned:
            options = {"headless": True}
            if browser_path:
                options["executable_path"] = browser_path
            browser = playwright.chromium.launch(**options)
            owned.callback(browser.close)
            result["browser_version"] = browser.version
            context = browser.new_context(viewport={"width": 1500, "height": 1000}, device_scale_factor=1)
            page = context.new_page()
            responses = []
            page.on("console", lambda message: result["console_errors"].append(message.text) if message.type == "error" else None)
            page.on("pageerror", lambda error: result["page_errors"].append(str(error)))
            page.on("response", lambda response: responses.append(response) if response.request.resource_type == "font" else None)
            page.goto(f"http://127.0.0.1:{server.server_port}/research/ttf14-candidates/study.html", wait_until="networkidle")
            assert page.evaluate("async families=>(await Promise.all(families.map(family=>document.fonts.load('14px \"'+family+'\"','攥螣攥紧螣蛇羁黛命宫2026')))).every(items=>items.length>0)", list(aliases.values()))
            assert page.evaluate("devicePixelRatio") == 1 and page.evaluate("visualViewport.scale") == 1
            expected = {path.name: key for key, path in paths.items()}
            assert {response.url.rsplit("/", 1)[-1] for response in responses} == set(expected)
            for response in responses:
                filename = response.url.rsplit("/", 1)[-1]
                entry = {"file": filename, "status": response.status, "response_sha256": hashlib.sha256(response.body()).hexdigest()}
                assert entry["status"] == 200 and entry["response_sha256"] == sources[expected[filename]]["sha256"]
                result["font_resources"].append(entry)
            cdp = context.new_cdp_session(page)
            cdp.send("DOM.enable")
            cdp.send("CSS.enable")
            for theme in ("light", "dark"):
                for label in "abcdef":
                    for kind, texts in (("target", TARGETS), ("phrase", PHRASES), ("control", CONTROLS)):
                        for index, text in enumerate(texts):
                            selector = f'.theme[data-theme="{theme}"] .candidate[data-candidate="{label}"] .pair[data-kind="{kind}"][data-index="{index}"]'
                            evidence, images = compare_pair(page, cdp, selector,
                                {"before": sources["baseline"], "after": sources[label]}, 1, theme,
                                {"before": aliases["baseline"], "after": aliases[label]})
                            evidence.update({"candidate": label, "theme": theme, "kind": kind, "text": text})
                            if kind == "control":
                                assert evidence["changed_physical_pixels"] == 0, (label, theme, text)
                            if kind == "target":
                                compact_cases.append({"candidate": label, "theme": theme, "character": text, "images": images})
                            result["comparisons"].append(evidence)
            assert not result["console_errors"] and not result["page_errors"]
            page.locator("#candidate-study").screenshot(path=str(directory / "study.png"), scale="device")
            context.close()
        cell_width, cell_height, margin, top = 274, 190, 20, 100
        sheet = Image.new("RGB", (cell_width * 6 + margin * 2, top + cell_height * 4 + 50), "#dbe3df")
        draw, font = ImageDraw.Draw(sheet), ImageFont.load_default(size=13)
        draw.text((margin, 16), "REGULAR TTF CANDIDATES / REAL 14 CSS px / DPR1 / BASELINE LEFT - CANDIDATE RIGHT", fill="#24343e", font=ImageFont.load_default(size=18))
        draw.text((margin, 45), "Native browser glyph pixels, shared crop, nearest-neighbor x8. Labels identify candidates; pixel zoom is for observation only.", fill="#50646c", font=font)
        for column, label in enumerate("abcdef"):
            x = margin + column * cell_width
            draw.text((x + 12, 76), "CANDIDATE " + label.upper(), fill="#24343e", font=font)
            for row, (theme, character) in enumerate((theme, character) for theme in ("light", "dark") for character in TARGETS):
                item = next(case for case in compact_cases if case["candidate"] == label and case["theme"] == theme and case["character"] == character)
                background, foreground = PALETTES[theme], PALETTES["dark" if theme == "light" else "light"]
                bounds = [glyph_bounds(item["images"][version], background) for version in ("before", "after")]
                crop = (min(box[0] for box in bounds)-1, min(box[1] for box in bounds)-1, max(box[2] for box in bounds)+1, max(box[3] for box in bounds)+1)
                y = top + row * cell_height
                draw.rectangle((x, y, x + cell_width - 2, y + cell_height - 2), fill=background)
                draw.text((x + 10, y + 7), f'{theme.upper()} / U+{ord(character):04X}', fill=foreground, font=font)
                for index, version in enumerate(("before", "after")):
                    image = item["images"][version].crop(crop)
                    image = image.resize((image.width*8, image.height*8), Image.Resampling.NEAREST)
                    draw.text((x + 25 + index * cell_width//2, y + 29), "BASELINE" if index == 0 else label.upper(), fill=foreground, font=font)
                    sheet.paste(image, (x + cell_width//4 + index*cell_width//2 - image.width//2, y + 49))
        sheet.save(directory / "study-compact.png")
        assert all(digest(paths[key]) == source["sha256"] for key, source in sources.items()), "Study font changed during rendering"
        result["artifact_hashes"] = {name: digest(directory / name) for name in ("study.html", "study.png", "study-compact.png")}
        result["passed"] = True
    except Exception as error:
        result.update({"passed": False, "error": str(error)})
        raise
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
        (directory / "study.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def candidate_regression(directory: Path, browser_path: str | None) -> dict:
    """Check only candidate D at DPR2, reusing exact DPR1 screenshot pixels."""
    study = json.loads((directory / "study.json").read_text(encoding="utf-8"))
    sources = {"before": dict(study["sources"]["baseline"]), "after": study["sources"]["d"]}
    sources["before"]["file"] = "fonts/" + BEFORE
    assert all(digest(ARTIFACT / source["file"]) == source["sha256"] for source in sources.values())
    document = (directory / "study.html").read_text(encoding="utf-8").replace(
        "../../fonts/" + AFTER, "../../fonts/" + BEFORE)
    (directory / "study-d-regression.html").write_text(document.rstrip() + "\n", encoding="utf-8")
    result = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "candidate": "d", "dpr": 2,
              "sources": sources, "comparisons": [], "console_errors": [], "page_errors": [],
              "visual_review": {"status": "requires-human-review"}}
    native = Image.open(directory / "study.png").convert("RGB")
    cases = []
    for evidence in study["comparisons"]:
        if evidence["candidate"] != "d" or evidence["kind"] != "target":
            continue
        images = {}
        for version in ("before", "after"):
            metrics = evidence["versions"][version]
            x, y = math.floor(metrics["x"] - 8 - 10), math.floor(metrics["y"] - 12)
            height = math.ceil(metrics["y"] - 12 + 52) - y
            images[version] = native.crop((x, y, x + 88, y + height))
            assert hashlib.sha256(images[version].tobytes()).hexdigest() == metrics["raster_sha256"], "DPR1 crop differs from original surface"
        cases.append({"dpr": 1, "theme": evidence["theme"], "character": evidence["text"], "images": images})
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(ARTIFACT)))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with sync_playwright() as playwright, ExitStack() as owned:
            options = {"headless": True}
            if browser_path:
                options["executable_path"] = browser_path
            browser = playwright.chromium.launch(**options)
            owned.callback(browser.close)
            result["browser_version"] = browser.version
            context = browser.new_context(viewport={"width": 1500, "height": 1000}, device_scale_factor=2)
            page = context.new_page()
            page.on("console", lambda message: result["console_errors"].append(message.text) if message.type == "error" else None)
            page.on("pageerror", lambda error: result["page_errors"].append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}/research/ttf14-candidates/study-d-regression.html", wait_until="networkidle")
            assert page.evaluate("devicePixelRatio") == 2 and page.evaluate("visualViewport.scale") == 1
            assert page.evaluate("async()=>{await document.fonts.ready;return document.fonts.check('14px \"TTF14 Study D\"','攥螣')} ")
            cdp = context.new_cdp_session(page)
            cdp.send("DOM.enable")
            cdp.send("CSS.enable")
            for theme in ("light", "dark"):
                for kind, texts in (("target", TARGETS), ("phrase", PHRASES), ("control", CONTROLS)):
                    for index, text in enumerate(texts):
                        selector = f'.theme[data-theme="{theme}"] .candidate[data-candidate="d"] .pair[data-kind="{kind}"][data-index="{index}"]'
                        evidence, images = compare_pair(page, cdp, selector, sources, 2, theme,
                                                       {"before": "TTF14 Study BASELINE", "after": "TTF14 Study D"})
                        evidence.update({"theme": theme, "kind": kind, "text": text})
                        if kind == "control":
                            assert evidence["changed_physical_pixels"] == 0
                        if kind == "target":
                            cases.append({"dpr": 2, "theme": theme, "character": text, "images": images})
                        result["comparisons"].append(evidence)
                page.locator(f'.theme[data-theme="{theme}"] .candidate[data-candidate="d"]').screenshot(path=str(directory / f"study-d-dpr2-{theme}.png"), scale="device")
            context.close()
        assert not result["console_errors"] and not result["page_errors"]
        result["compact_sheet"] = compact_sheet(cases, directory / "study-d-regression-compact.png")
        assert all(digest(ARTIFACT / source["file"]) == source["sha256"] for source in sources.values())
        result["artifact_hashes"] = {name: digest(directory / name) for name in
                                     ("study-d-regression.html", "study-d-dpr2-light.png", "study-d-dpr2-dark.png", "study-d-regression-compact.png")}
        result["passed"] = True
    except Exception as error:
        result.update({"passed": False, "error": str(error)})
        raise
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
        (directory / "study-d-regression.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-zip", type=Path, default=ARCHIVE)
    parser.add_argument("--browser", default=browser_default())
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--load-only", action="store_true")
    mode.add_argument("--candidate-study", type=Path, help="Render independent research A-F study without replacing current fonts or final reports")
    mode.add_argument("--candidate-regression", type=Path, help="Check only candidate D at DPR2, using existing study pixels for the DPR1 comparison")
    args = parser.parse_args()
    if args.candidate_regression:
        report = candidate_regression(args.candidate_regression.resolve(), args.browser)
        print(json.dumps({"passed": report["passed"], "candidate": report["candidate"], "dpr": report["dpr"]}))
        raise SystemExit(0)
    if args.candidate_study:
        report = candidate_study(args.candidate_study.resolve(), args.browser)
        print(json.dumps({"passed": report["passed"], "mode": report["mode"], "comparisons": len(report["comparisons"])}))
        raise SystemExit(0)
    baseline = baseline_copy(args.baseline_zip.resolve())
    fixture = write_html(baseline)
    if args.prepare_only:
        print(json.dumps({"html": str(fixture), "baseline": baseline, "comparison_performed": False}, ensure_ascii=False))
    else:
        report = run(args.baseline_zip.resolve(), baseline, args.browser, args.load_only)
        print(json.dumps({"passed": report["passed"], "mode": report["mode"], "runs": len(report["runs"]),
                          "comparison_performed": report["comparison_performed"]}, ensure_ascii=False))
