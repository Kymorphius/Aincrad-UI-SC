"""Compare four dense Regular glyphs at real 14 CSS px against an immutable ZIP.

Prepare the baseline and HTML with --prepare-only. Full rendering requires the
candidate font to be ready: each target must produce a real changed raster.
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
import os
from pathlib import Path
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from zipfile import ZipFile

from fontTools.ttLib import TTFont
from PIL import Image, ImageChops, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT if (ROOT / "fonts").is_dir() else ROOT / "design" / "aincrad-ui-sc"
DEFAULT_ARCHIVE = ARTIFACT / "Aincrad-UI-SC-v0.3-xingpan-symbols.zip"
BEFORE_FILE = "AincradUISc-v030-before-dense-Regular.woff2"
AFTER_FILE = "AincradUISc-Regular.woff2"
ALIASES = {"before": "Dense Before Regular", "after": "Dense After Regular"}
GLYPHS = ("羁", "螣", "攥", "黛")
PHRASES = ("羁绊", "螣蛇", "手攥", "黛色")
CONTROL = "命宫 2026"
PALETTES = {"light": (241, 244, 238), "dark": (36, 52, 62)}


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_baseline(archive: Path) -> dict:
    """Read one font from the archive; never rewrite or extract the whole ZIP."""
    zip_hash = digest(archive)
    with ZipFile(archive) as package:
        members = [name for name in package.namelist()
                   if name.endswith("fonts/AincradUISc-Regular.woff2")]
        if len(members) != 1:
            raise ValueError("Expected exactly one Regular WOFF2 in the baseline archive")
        payload = package.read(members[0])
    baseline = ARTIFACT / "fonts" / BEFORE_FILE
    if baseline.exists():
        if baseline.read_bytes() != payload:
            raise ValueError("Existing immutable baseline differs from the requested archive")
    else:
        baseline.write_bytes(payload)
    assert digest(archive) == zip_hash, "Baseline ZIP changed during extraction"
    return {
        "archive": archive.name, "archive_sha256": zip_hash, "member": members[0],
        "font": "fonts/" + BEFORE_FILE, "font_sha256": digest(baseline),
        "archive_preserved": True,
    }


def pair_markup(text: str, theme: str, kind: str) -> str:
    code = f"u{ord(text):04x}" if kind == "glyph" else str(PHRASES.index(text)) if kind == "phrase" else "control"
    title = text + (f" / U+{ord(text):04X}" if kind == "glyph" else "")
    panes = "".join(
        '<div class="version"><p class="version-label">'
        + ("修改前 / BEFORE" if version == "before" else "修改后 / AFTER")
        + '</p><div class="glyph-surface" data-version="' + version
        + '"><span class="sample ' + version + '">' + html.escape(text)
        + "</span></div></div>"
        for version in ("before", "after")
    )
    return (
        '<article class="comparison-pair ' + kind + '-pair" data-kind="' + kind
        + '" data-id="' + code + '" data-theme="' + theme + '">'
        + '<h3>' + html.escape(title) + '</h3><div class="version-grid">' + panes + "</div></article>"
    )


def write_html(baseline: dict) -> Path:
    sections = []
    for theme, label in (("light", "浅色"), ("dark", "深色")):
        sections.append(
            '<section class="theme-study ' + theme + '" data-theme="' + theme
            + '"><header class="theme-head"><h2>' + label
            + '</h2><p>Regular · 14 CSS px · 字距 0 · 相同字宽与底色</p></header>'
            + '<div class="glyph-grid">' + "".join(pair_markup(text, theme, "glyph") for text in GLYPHS)
            + '</div><h2 class="subhead">词语中的字形</h2><div class="glyph-grid">'
            + "".join(pair_markup(text, theme, "phrase") for text in PHRASES)
            + '</div><h2 class="subhead">未修改内容控制</h2><div class="control-row">'
            + pair_markup(CONTROL, theme, "control")
            + '<p>控制文字应保持像素相同，用于排除不同采样位置、颜色或整体排版变化造成的假差异。'
            + '自动检查只证明字形确实渲染、宽度与像素变化；是否更好辨认仍须查看原图和逐字放大图。</p>'
            + "</div></section>"
        )
    document = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,">
<title>Aincrad UI SC · 羁螣攥黛 14 px 前后对照</title>
<style>
@font-face{font-family:"Dense Before Regular";src:url("fonts/AincradUISc-v030-before-dense-Regular.woff2") format("woff2");font-weight:400;font-style:normal;font-display:block}
@font-face{font-family:"Dense After Regular";src:url("fonts/AincradUISc-Regular.woff2") format("woff2");font-weight:400;font-style:normal;font-display:block}
*{box-sizing:border-box}body{margin:0;background:#dbe3df;color:#24343e;font:12px "Segoe UI","Microsoft YaHei",sans-serif}main{width:1066px;max-width:100%;margin:auto;padding:24px}.study-header{padding-bottom:20px;margin-bottom:24px;border-bottom:1px solid #a9bbb4}.eyebrow{font-size:10px;letter-spacing:.16em;color:#657b72;margin:0 0 10px}.study-header h1{font-size:27px;font-weight:400;margin:0 0 12px}.study-header p{font-size:11px;line-height:1.8;margin:0;color:#61766f}.study-header .runtime{margin-top:9px;color:#94712f}.theme-study{padding:20px;border:1px solid var(--rule);background:var(--surface);color:var(--ink);margin:0 0 24px}.light{--surface:#f1f4ee;--ink:#24343e;--muted:#61767c;--rule:#c3d0c7}.dark{--surface:#24343e;--ink:#f1f4ee;--muted:#b8c6c5;--rule:#50646c}.theme-head{display:flex;align-items:baseline;justify-content:space-between;gap:14px;margin:0 0 17px}.theme-head h2{font-weight:500;font-size:15px;margin:0}.theme-head p{font-size:10px;color:var(--muted);margin:0}.glyph-grid{display:grid;grid-template-columns:repeat(4,220px);gap:16px}.comparison-pair{width:220px;padding:12px;border:1px solid var(--rule);background:var(--surface);color:var(--ink)}.comparison-pair h3{font:400 11px "Segoe UI","Microsoft YaHei",sans-serif;color:var(--muted);margin:0 0 12px}.version-grid{display:grid;grid-template-columns:88px 88px;gap:16px}.version-label{font:9px "Segoe UI","Microsoft YaHei",sans-serif;color:var(--muted);margin:0 0 5px;white-space:nowrap}.glyph-surface{width:88px;height:52px;padding:12px 8px;background:var(--surface);color:var(--ink);overflow:visible;border:0;transform:none;filter:none;opacity:1}.sample{display:inline-block;font-weight:400;font-style:normal;font-size:14px;line-height:28px;letter-spacing:0;white-space:pre;font-synthesis:none;font-variant-numeric:normal;transform:none;filter:none;opacity:1}.before{font-family:"Dense Before Regular",sans-serif}.after{font-family:"Dense After Regular",sans-serif}.subhead{font-size:12px;font-weight:500;margin:24px 0 13px}.control-row{display:flex;align-items:center;gap:25px}.control-row>p{font-size:11px;line-height:1.8;color:var(--muted);margin:0;max-width:550px}.study-foot{font-size:11px;line-height:1.8;color:#61766f;margin:0}.archive-id{font-size:9px;overflow-wrap:anywhere;color:#7a8e84;margin-top:10px!important}
@media(max-width:1050px){main{width:594px}.glyph-grid{grid-template-columns:repeat(2,220px)}.theme-head{align-items:flex-start;flex-direction:column;gap:6px}.control-row{flex-direction:column;align-items:flex-start}}@media(max-width:570px){main{width:310px;padding:14px}.theme-study{padding:16px}.glyph-grid{grid-template-columns:220px;justify-content:center}.study-header h1{font-size:23px}}
</style></head><body><main id="comparison-study">
<header class="study-header"><p class="eyebrow">AINCRAD UI SC / DENSE GLYPH COMPARISON</p><h1>羁 · 螣 · 攥 · 黛 / 14 px 修改前后</h1><p>左列使用原 symbols 分发包中的 Regular，右列使用当前 Regular。样本使用真实 14 CSS px、0 字距和相同前景／背景，没有 CSS 缩放、滤镜或字宽补偿。原始 PNG 保留浏览器像素，放大图只用最近邻显示像素变化。</p><p class="runtime" id="runtime">正在加载前后两版字体</p><p class="archive-id">Baseline ZIP SHA-256: %%ARCHIVE_HASH%%</p></header>
%%SECTIONS%%
<p class="study-foot">本页是桌面 Chromium、DPR 1／2 的静态对照，不能代替 Flutter / Android 真实盘面验收。自动检查不代表所有小字号已经可读；单字识别与修改后的改善需要结合原始尺寸和像素放大图人工判断。</p>
</main><script>
window.comparisonReady=Promise.all([
 document.fonts.load('14px "Dense Before Regular"','羁螣攥黛羁绊螣蛇手攥黛色命宫2026'),
 document.fonts.load('14px "Dense After Regular"','羁螣攥黛羁绊螣蛇手攥黛色命宫2026')
]).then(fonts=>{const ready=fonts.every(items=>items.length>0);document.getElementById('runtime').textContent=(ready?'前后两版字体已加载':'字体未完整加载')+' / DPR '+devicePixelRatio+' / browser zoom '+visualViewport.scale;return ready;});
</script></body></html>
"""
    document = document.replace("%%SECTIONS%%", "".join(sections)).replace("%%ARCHIVE_HASH%%", baseline["archive_sha256"])
    path = ARTIFACT / "dense-14px-comparison.html"
    path.write_text(document.rstrip() + "\n", encoding="utf-8")
    return path


def verify_fonts() -> dict:
    texts = GLYPHS + PHRASES + (CONTROL,)
    required = {character for text in texts for character in text}
    records = {}
    for version, filename in (("before", BEFORE_FILE), ("after", AFTER_FILE)):
        path = ARTIFACT / "fonts" / filename
        with TTFont(path) as font:
            cmap = font.getBestCmap()
            missing = sorted(required - {chr(codepoint) for codepoint in cmap})
            assert not missing, (version, missing)
            records[version] = {
                "file": "fonts/" + filename, "sha256": digest(path), "bytes": path.stat().st_size,
                "css_family_alias": ALIASES[version], "internal_family": font["name"].getDebugName(1),
                "font_version": font["name"].getDebugName(5), "upm": font["head"].unitsPerEm,
                "hhea": {name: getattr(font["hhea"], name) for name in ("ascent", "descent", "lineGap")},
                "glyphs": {character: {"name": cmap[ord(character)],
                                       "advance": font["hmtx"][cmap[ord(character)]][0],
                                       "lsb": font["hmtx"][cmap[ord(character)]][1]}
                           for character in GLYPHS}, "missing": missing,
            }
    assert records["before"]["upm"] == records["after"]["upm"]
    assert records["before"]["hhea"] == records["after"]["hhea"]
    for character in GLYPHS:
        assert records["before"]["glyphs"][character]["advance"] == records["after"]["glyphs"][character]["advance"]
    return records


def actual_fonts(cdp, selector: str) -> list[dict]:
    document = cdp.send("DOM.getDocument")
    node = cdp.send("DOM.querySelector", {"nodeId": document["root"]["nodeId"], "selector": selector})
    assert node["nodeId"], selector
    return cdp.send("CSS.getPlatformFontsForNode", {"nodeId": node["nodeId"]})["fonts"]


def glyph_bounds(image: Image.Image, background: tuple[int, int, int]) -> tuple[int, int, int, int]:
    difference = ImageChops.difference(image.convert("RGB"), Image.new("RGB", image.size, background))
    mask = difference.convert("L").point(lambda value: 255 if value > 2 else 0)
    bounds = mask.getbbox()
    assert bounds, "Rendered glyph has no visible ink"
    assert bounds[0] > 1 and bounds[1] > 1 and bounds[2] < image.width - 1 and bounds[3] < image.height - 1, bounds
    return bounds


def compare_pair(page, cdp, selector: str, sources: dict, dpr: int, theme: str) -> tuple[dict, Image.Image, dict]:
    page.locator(selector).scroll_into_view_if_needed()
    record = {"selector": selector, "versions": {}}
    surfaces = {}
    for version in ("before", "after"):
        leaf = selector + f' [data-version="{version}"] .sample'
        fonts = actual_fonts(cdp, leaf)
        assert fonts and all(font["isCustomFont"] and font["glyphCount"] > 0 for font in fonts), fonts
        assert all(font["familyName"] == sources[version]["internal_family"] for font in fonts), fonts
        metrics = page.locator(leaf).evaluate(
            """element=>{const css=getComputedStyle(element),rect=element.getBoundingClientRect();
              return {text:element.textContent,fontFamily:css.fontFamily,fontSize:css.fontSize,
                fontWeight:css.fontWeight,lineHeight:css.lineHeight,letterSpacing:css.letterSpacing,
                color:css.color,filter:css.filter,transform:css.transform,opacity:css.opacity,
                width:rect.width,height:rect.height,x:rect.x+scrollX,y:rect.y+scrollY};}""")
        assert ALIASES[version] in metrics["fontFamily"]
        assert metrics["fontSize"] == "14px" and metrics["fontWeight"] == "400"
        assert metrics["letterSpacing"] in ("0px", "normal") and metrics["lineHeight"] == "28px"
        assert metrics["filter"] == metrics["transform"] == "none" and metrics["opacity"] == "1"
        surface = selector + f' [data-version="{version}"]'
        palette = page.locator(surface).evaluate(
            "element=>{const css=getComputedStyle(element);return {background:css.backgroundColor,color:css.color};}")
        raw = page.locator(surface).screenshot(scale="device")
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        bounds = glyph_bounds(image, PALETTES[theme])
        surfaces[version] = image
        record["versions"][version] = {"actual_fonts": fonts, **metrics, **palette,
                                        "ink_bounds_physical_px": list(bounds),
                                        "raster_sha256": hashlib.sha256(image.tobytes()).hexdigest()}
    before, after = record["versions"]["before"], record["versions"]["after"]
    for key in ("fontSize", "fontWeight", "lineHeight", "letterSpacing", "color", "background", "width", "height"):
        assert before[key] == after[key], (key, before[key], after[key])
    assert abs((before["x"] - after["x"]) * dpr - round((before["x"] - after["x"]) * dpr)) < 0.001
    assert abs(before["y"] - after["y"]) < 0.001
    assert surfaces["before"].size == surfaces["after"].size
    difference = ImageChops.difference(surfaces["before"], surfaces["after"])
    colors = difference.getcolors(maxcolors=difference.width * difference.height)
    assert colors is not None
    changed = sum(count for count, color in colors if color != (0, 0, 0))
    record["changed_physical_pixels"] = changed
    record["difference_bounds_physical_px"] = list(difference.getbbox()) if difference.getbbox() else None
    record["same_css_width"] = True
    record["unclipped"] = True
    pair_image = Image.open(io.BytesIO(page.locator(selector).screenshot(scale="device"))).convert("RGB")
    return record, pair_image, surfaces


def focus_sheet(pairs: list[dict], destination: Path, dpr: int) -> dict:
    factor = 4 if dpr == 1 else 2
    cell_width = max(item["image"].width for item in pairs)
    cell_height = max(item["image"].height for item in pairs)
    heading_height = 35 * dpr
    sheet = Image.new("RGB", (cell_width * 2, cell_height * 4 + heading_height), "#dbe3df")
    draw = ImageDraw.Draw(sheet)
    draw.text((8 * dpr, 10 * dpr), f"14 CSS px / DPR {dpr} / PHYSICAL PIXELS x{factor} / BEFORE LEFT - AFTER RIGHT",
              fill="#24343e", font=ImageFont.load_default(size=10 * dpr))
    for item in pairs:
        x = (0 if item["theme"] == "light" else 1) * cell_width
        y = GLYPHS.index(item["character"]) * cell_height + heading_height
        sheet.paste(item["image"], (x, y))
    sheet = sheet.resize((sheet.width * factor, sheet.height * factor), Image.Resampling.NEAREST)
    sheet.save(destination)
    return {"file": destination.name, "dpr": dpr, "method": "nearest-neighbor",
            "physical_pixel_magnification": factor, "width": sheet.width, "height": sheet.height}


def compact_sheet(pairs: list[dict], destination: Path) -> dict:
    """Crop both versions to their shared ink bounds, preserving pixel alignment."""
    columns = [(1, "light"), (1, "dark"), (2, "light"), (2, "dark")]
    cell_width, cell_height, margin, top = 330, 190, 20, 100
    sheet = Image.new("RGB", (cell_width * 4 + margin * 2, top + cell_height * 4 + 50), "#dbe3df")
    draw = ImageDraw.Draw(sheet)
    heading_font = ImageFont.load_default(size=18)
    label_font = ImageFont.load_default(size=13)
    draw.text((margin, 16), "REGULAR / 14 CSS px / BEFORE LEFT - AFTER RIGHT", fill="#24343e", font=heading_font)
    draw.text((margin, 44), "Actual browser pixels; nearest-neighbor enlargement for pixel observation only.",
              fill="#50646c", font=label_font)
    crops = []
    for column, (dpr, theme) in enumerate(columns):
        factor = 8 if dpr == 1 else 4
        x = margin + column * cell_width
        draw.text((x + 12, 76), f"DPR {dpr} / {theme.upper()} / physical pixels x{factor}",
                  fill="#24343e", font=label_font)
        background = PALETTES[theme]
        foreground = PALETTES["dark" if theme == "light" else "light"]
        for row, character in enumerate(GLYPHS):
            item = next(item for item in pairs if item["dpr"] == dpr
                        and item["theme"] == theme and item["character"] == character)
            bounds = [glyph_bounds(item["surfaces"][version], background) for version in ("before", "after")]
            padding = dpr
            crop = (min(box[0] for box in bounds) - padding,
                    min(box[1] for box in bounds) - padding,
                    max(box[2] for box in bounds) + padding,
                    max(box[3] for box in bounds) + padding)
            y = top + row * cell_height
            draw.rectangle((x, y, x + cell_width - 2, y + cell_height - 2), fill=background)
            draw.text((x + 12, y + 9), f"U+{ord(character):04X}", fill=foreground, font=label_font)
            for index, version in enumerate(("before", "after")):
                image = item["surfaces"][version].crop(crop)
                image = image.resize((image.width * factor, image.height * factor), Image.Resampling.NEAREST)
                left = x + cell_width // 4 + index * cell_width // 2 - image.width // 2
                draw.text((x + 40 + index * cell_width // 2, y + 29), version.upper(), fill=foreground, font=label_font)
                sheet.paste(image, (left, y + 49))
            crops.append({"character": character, "dpr": dpr, "theme": theme,
                          "shared_source_crop_physical_px": list(crop), "physical_pixel_magnification": factor})
    draw.text((margin, sheet.height - 32), "Shared before/after crop preserves position. No filters, interpolation, or synthetic glyph pixels.",
              fill="#50646c", font=label_font)
    sheet.save(destination)
    return {"file": destination.name, "method": "shared ink-bounds crop, nearest-neighbor",
            "source": "Real 14 CSS px glyph-surface screenshots", "crops": crops,
            "width": sheet.width, "height": sheet.height}


def current_font_files() -> dict:
    return {f"AincradUISc-{variant}.{extension}": {
        "sha256": digest(ARTIFACT / "fonts" / f"AincradUISc-{variant}.{extension}"),
        "bytes": (ARTIFACT / "fonts" / f"AincradUISc-{variant}.{extension}").stat().st_size,
        "browser_rendered_in_this_report": variant == "Regular" and extension == "woff2",
    } for variant in ("Regular", "Display") for extension in ("otf", "ttf", "woff2")}


def render(archive: Path, baseline: dict, browser_path: str | None = None) -> dict:
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Desktop headless Chromium; real 14 CSS px; not Flutter/Android acceptance",
        "baseline": baseline, "sources": {}, "css_font_size": 14, "letter_spacing": 0,
        "dprs": [1, 2], "glyphs": list(GLYPHS), "phrases": list(PHRASES),
        "runs": [], "native_screenshots": [], "focus_sheets": [], "individual_crops": [],
        "console_errors": [], "page_errors": [], "failed_requests": [], "http_errors": [],
        "recognizability": {
            "automated": "Correct Unicode/cmap identities, visible unclipped ink and four distinct glyph rasters.",
            "human_review": "pending; pixel differences do not establish improved readability",
        },
    }
    server = None
    try:
        result["sources"] = verify_fonts()
        result["current_font_files"] = current_font_files()
        compact_pairs = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(ARTIFACT)))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f"http://127.0.0.1:{server.server_port}/dense-14px-comparison.html"
        with sync_playwright() as playwright, ExitStack() as owned:
            options = {"headless": True}
            if browser_path:
                options["executable_path"] = browser_path
            browser = playwright.chromium.launch(**options)
            owned.callback(browser.close)
            result["browser_version"] = browser.version
            for dpr in (1, 2):
                context = browser.new_context(viewport={"width": 1080, "height": 1000}, device_scale_factor=dpr)
                page = context.new_page()
                page.on("console", lambda message: result["console_errors"].append(message.text)
                        if message.type == "error" else None)
                page.on("pageerror", lambda error: result["page_errors"].append(str(error)))
                page.on("requestfailed", lambda request: result["failed_requests"].append(request.failure))
                page.on("response", lambda response: result["http_errors"].append(
                    {"path": response.url.split("/")[-1], "status": response.status})
                    if response.status >= 400 else None)
                page.goto(url, wait_until="networkidle")
                assert page.evaluate("window.comparisonReady")
                assert page.evaluate("devicePixelRatio") == dpr and page.evaluate("visualViewport.scale") == 1
                cdp = context.new_cdp_session(page)
                cdp.send("DOM.enable")
                cdp.send("CSS.enable")
                run = {"dpr": dpr, "themes": []}
                focus_pairs = []
                for theme in ("light", "dark"):
                    theme_record = {"theme": theme, "single_glyphs": [], "phrases": [], "control": {}}
                    before_hashes, after_hashes = [], []
                    for character in GLYPHS:
                        code = f"u{ord(character):04x}"
                        selector = f'.glyph-pair[data-theme="{theme}"][data-id="{code}"]'
                        evidence, image, surfaces = compare_pair(page, cdp, selector, result["sources"], dpr, theme)
                        evidence["character"], evidence["codepoint"] = character, f"U+{ord(character):04X}"
                        assert evidence["changed_physical_pixels"] > 0, (character, theme, dpr, "No real pixel change")
                        before_hashes.append(evidence["versions"]["before"]["raster_sha256"])
                        after_hashes.append(evidence["versions"]["after"]["raster_sha256"])
                        theme_record["single_glyphs"].append(evidence)
                        filename = f"dense-14px-{code}-{theme}-dpr{dpr}.png"
                        image.save(ARTIFACT / filename)
                        factor = 4 if dpr == 1 else 2
                        zoom_name = f"dense-14px-{code}-{theme}-dpr{dpr}-zoom.png"
                        image.resize((image.width * factor, image.height * factor), Image.Resampling.NEAREST).save(ARTIFACT / zoom_name)
                        result["individual_crops"].append({"character": character, "theme": theme, "dpr": dpr,
                                                           "native": filename, "zoom": zoom_name,
                                                           "physical_pixel_magnification": factor})
                        focus_pairs.append({"character": character, "theme": theme, "image": image})
                        compact_pairs.append({"character": character, "theme": theme, "dpr": dpr, "surfaces": surfaces})
                    assert len(set(before_hashes)) == len(set(after_hashes)) == 4
                    theme_record["four_glyph_rasters_distinct"] = True
                    for index, phrase in enumerate(PHRASES):
                        selector = f'.phrase-pair[data-theme="{theme}"][data-id="{index}"]'
                        evidence, _, _ = compare_pair(page, cdp, selector, result["sources"], dpr, theme)
                        evidence["text"] = phrase
                        assert evidence["changed_physical_pixels"] > 0, (phrase, theme, dpr)
                        theme_record["phrases"].append(evidence)
                    selector = f'.control-pair[data-theme="{theme}"]'
                    control, _, _ = compare_pair(page, cdp, selector, result["sources"], dpr, theme)
                    assert control["changed_physical_pixels"] == 0, ("Unchanged control raster differs", theme, dpr)
                    theme_record["control"] = control
                    run["themes"].append(theme_record)
                assert page.evaluate("document.documentElement.scrollWidth") == 1080
                result["runs"].append(run)
                filename = "dense-14px-comparison.png" if dpr == 1 else "dense-14px-comparison-dpr2.png"
                page.locator("#comparison-study").screenshot(path=str(ARTIFACT / filename), scale="device")
                result["native_screenshots"].append({"file": filename, "dpr": dpr})
                result["focus_sheets"].append(focus_sheet(
                    focus_pairs, ARTIFACT / f"dense-14px-comparison-focus-dpr{dpr}.png", dpr))
                context.close()
        for key in ("console_errors", "page_errors", "failed_requests", "http_errors"):
            assert not result[key], (key, result[key])
        result["compact_sheet"] = compact_sheet(compact_pairs, ARTIFACT / "dense-14px-comparison-compact.png")
        assert digest(archive) == baseline["archive_sha256"], "Immutable source ZIP changed"
        for source in result["sources"].values():
            assert digest(ARTIFACT / source["file"]) == source["sha256"], "Font changed during comparison"
        assert current_font_files() == result["current_font_files"], "Current font files changed during comparison"
        names = ["dense-14px-comparison.html", result["compact_sheet"]["file"]] + [
            item["file"] for key in ("native_screenshots", "focus_sheets") for item in result[key]
        ] + [item[key] for item in result["individual_crops"] for key in ("native", "zoom")]
        result["artifact_hashes"] = {name: digest(ARTIFACT / name) for name in names}
        result["passed"] = True
    except Exception as error:
        result["passed"] = False
        result["error"] = str(error)
        raise
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
        path = ARTIFACT / "data/dense-14px-comparison.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def browser_default() -> str | None:
    cache = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    candidates = sorted(cache.glob("chromium-*/**/chrome.exe"),
                        key=lambda path: int(path.relative_to(cache).parts[0].split("-")[-1]), reverse=True)
    return str(candidates[0]) if candidates else None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-zip", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--browser", default=browser_default())
    parser.add_argument("--prepare-only", action="store_true",
                        help="Extract/verify the immutable baseline and write HTML without rendering a candidate.")
    args = parser.parse_args()
    baseline = prepare_baseline(args.baseline_zip.resolve())
    fixture = write_html(baseline)
    if args.prepare_only:
        print(json.dumps({"html": str(fixture), "baseline": baseline, "rendered": False}, ensure_ascii=False))
    else:
        report = render(args.baseline_zip.resolve(), baseline, args.browser)
        print(json.dumps({"passed": report["passed"], "runs": len(report["runs"]),
                          "individual_crops": len(report["individual_crops"]),
                          "report": str(ARTIFACT / "data/dense-14px-comparison.json")}, ensure_ascii=False))
