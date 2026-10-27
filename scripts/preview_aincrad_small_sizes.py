"""Render repeatable 11–14 CSS px Aincrad studies in desktop Chromium.

The native screenshots preserve browser rasterization at DPR 1 and 2.
Pixel enlargements use nearest-neighbor resampling of those screenshots.
These fixtures do not validate Flutter, Android, or the real Xingpan chart.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import functools
import hashlib
import html
import io
import json
import math
import os
import threading
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT if (ROOT / "fonts").is_dir() else ROOT / "design" / "aincrad-ui-sc"
SIZES = (11, 12, 13, 14)
FONTS = {
    "regular": {"family": "Aincrad UI SC", "file": "AincradUISc-Regular.woff2", "label": "界面体"},
    "display": {"family": "Aincrad UI SC Display", "file": "AincradUISc-Display.woff2", "label": "标题体"},
}
SYMBOL_CODEPOINTS = (
    0x00B0, 0x00B1, 0x00BD, 0x0394, 0x2013, 0x2022, 0x2032, 0x203A,
    0x2212, 0x2585, 0x25AC, 0x25CB, 0x2605, 0x2630, 0x2631, 0x2632,
    0x2633, 0x2634, 0x2635, 0x2636, 0x2637, 0x2722, 0x2731, 0x2736,
    0x273B, 0x273D, 0x274B, 0xFF0F, 0xFF3B, 0xFF3D, 0xFF5C, 0xFF5E,
)
PALACES = ("命宫", "兄弟宫", "夫妻宫", "子女宫", "财帛宫", "疾厄宫",
           "迁移宫", "交友宫", "官禄宫", "田宅宫", "福德宫", "父母宫")
STARS = ("紫微 天府", "天机 太阴", "太阳 巨门", "武曲 天相", "廉贞 贪狼", "天同 天梁",
         "七杀 破军", "左辅 右弼", "文昌 文曲", "天魁 天钺", "禄存 天马", "地空 地劫")
POSITIONS = ((1, 1), (1, 2), (1, 3), (1, 4), (2, 4), (3, 4),
             (4, 4), (4, 3), (4, 2), (4, 1), (3, 1), (2, 1))
CASE_LABELS = {
    "palaces": "十二宫标签", "stars": "密集星曜短词", "extensions": "首批 48 字",
    "symbols": "本批 32 符号", "degrees": "度数与全角标签", "columns": "年份与数值列",
}


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def samples() -> dict[str, str]:
    additions = json.loads((ARTIFACT / "data/charset-extensions.json").read_text(encoding="utf-8"))
    first_batch_han = "".join(character for character in additions["characters"]
                              if 0x3400 <= ord(character) <= 0x9FFF or
                              0x20000 <= ord(character) <= 0x323AF)
    assert len(first_batch_han) == len(set(first_batch_han)) == 48
    return {
        "palaces": "  ".join(PALACES),
        "stars": "紫微 天机 太阳 武曲 天同 廉贞 天府 太阴 贪狼 巨门 天相 天梁 七杀 破军",
        "extensions": first_batch_han,
        "symbols": " ".join(chr(codepoint) for codepoint in SYMBOL_CODEPOINTS),
        "degrees": "23°59′  ±0.5°  −12.5  Δ ½\n［命宫］／财帛宫｜～  ★ ○ ▅ ▬",
        "columns": "2026  03  07  23°59′\n1111  11  11  11°11′\n8888  08  08  88°08′",
    }


def write_html(cases: dict[str, str]) -> Path:
    sections, phones = [], []
    for font_key, font in FONTS.items():
        for theme, theme_label in (("light", "浅色"), ("dark", "深色")):
            cards = []
            for size in SIZES:
                items = "".join(
                    '<div class="test-case"><p class="case-label">' + CASE_LABELS[key]
                    + '</p><p class="sample sample-text" data-case="' + key + '">'
                    + html.escape(text) + "</p></div>"
                    for key, text in cases.items()
                )
                probes = "".join(
                    '<span class="number-probe sample" data-digit="' + digit + '">'
                    + digit * 8 + "</span>" for digit in "0123456789"
                )
                cards.append(
                    '<article class="size-card" data-font="' + font_key + '" data-theme="' + theme
                    + '" data-size="' + str(size) + '" style="--sample-size:' + str(size) + 'px">'
                    + '<header class="card-head"><h3>' + str(size) + ' CSS px</h3><span>'
                    + font["label"] + " / " + theme_label + '</span></header>'
                    + '<div class="zoom-target">' + items + "</div>"
                    + '<div class="test-case"><p class="case-label">默认数字等宽探针 / 每列 8 位</p>'
                    + '<div class="numeric-probes">' + probes + "</div></div></article>"
                )
            sections.append(
                '<section class="font-section ' + theme + '" data-font="' + font_key
                + '" data-theme="' + theme + '" style="--sample-family:&quot;'
                + font["family"] + '&quot;"><h2>' + font["label"] + " / " + theme_label
                + '<span>' + font["family"] + ' · 0 letter spacing</span></h2>'
                + '<div class="size-grid">' + "".join(cards) + "</div></section>"
            )
            cells = "".join(
                '<article class="palace" style="grid-row:' + str(row)
                + ";grid-column:" + str(column) + '"><h3 class="phone-sample">'
                + palace + '</h3><p class="phone-sample">' + STARS[index]
                + '</p><p class="phone-label phone-sample">甲子 23°59′</p></article>'
                for index, ((row, column), palace) in enumerate(zip(POSITIONS, PALACES))
            )
            phones.append(
                '<section class="phone-frame ' + theme + '" data-phone="' + font_key + "-"
                + theme + '" data-font="' + font_key + '" style="--sample-family:&quot;'
                + font["family"] + '&quot;"><header class="phone-header"><h2>十二宫静态字号示意</h2>'
                + '<p>' + font["label"] + " / " + theme_label
                + ' · 主文字 14 CSS px · 标签 11 CSS px</p></header><div class="palace-grid">'
                + cells + '<div class="palace-center"><strong>390 × 844 CSS px</strong>'
                + '<p>十二宫名与星曜为字体样本，未计算实际排盘。</p>'
                + '<p>桌面 Chromium 渲染，不能代替 Flutter / Android 的真实页面验收。</p>'
                + '</div></div><p class="phone-foot">主内容保持 14 CSS px，未用缩放把整盘挤入屏幕。'
                + '此图只检查静态文字与布局；系统字体设置、Flutter 排版和真实内容密度仍须在应用里验证。</p></section>'
            )
    document = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="data:,"><title>Aincrad UI SC · 11–14 px 浏览器样张</title>
<style>
@font-face{font-family:"Aincrad UI SC";src:url("fonts/AincradUISc-Regular.woff2") format("woff2");font-style:normal;font-weight:400;font-display:block}
@font-face{font-family:"Aincrad UI SC Display";src:url("fonts/AincradUISc-Display.woff2") format("woff2");font-style:normal;font-weight:400;font-display:block}
*{box-sizing:border-box}body{margin:0;background:#dbe3df;color:#24343e;font-family:"Segoe UI","Microsoft YaHei",sans-serif;font-size:12px}main{max-width:1480px;margin:auto;padding:28px 32px}.study-header{margin:0 0 25px;border-bottom:1px solid #a9bbb4;padding-bottom:20px}.study-header .eyebrow{font-size:10px;letter-spacing:.19em;color:#687d77;margin:0 0 10px}.study-header h1{font-weight:400;font-size:27px;letter-spacing:-.02em;margin:0 0 12px}.study-header p{font-size:11px;line-height:1.8;color:#61766f;margin:0}.study-header .runtime{margin-top:9px;color:#97702e}.font-section{margin-bottom:24px;padding:20px;background:var(--surface);color:var(--ink)}.light{--surface:#f1f4ee;--ink:#24343e;--muted:#61767c;--rule:#c3d0c7}.dark{--surface:#24343e;--ink:#f1f4ee;--muted:#b8c6c5;--rule:#50646c}.font-section h2{margin:0 0 16px;display:flex;justify-content:space-between;gap:15px;font-size:13px;font-weight:500;letter-spacing:.06em}.font-section h2 span{font-size:10px;font-weight:400;color:var(--muted);letter-spacing:.03em}.size-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;align-items:stretch}.size-card{min-width:0;border:1px solid var(--rule);padding:14px;background:var(--surface);color:var(--ink)}.card-head{display:flex;align-items:baseline;justify-content:space-between;gap:8px;padding-bottom:12px;border-bottom:1px solid var(--rule);margin-bottom:13px}.card-head h3{font-size:13px;font-weight:500;margin:0}.card-head span{font-size:9px;color:var(--muted)}.test-case{margin:0 0 12px;min-width:0}.test-case:last-child{margin-bottom:0}.case-label{font-size:9px;color:var(--muted);letter-spacing:.03em;margin:0 0 5px;font-family:"Segoe UI","Microsoft YaHei",sans-serif}.sample{font-family:var(--sample-family),sans-serif;font-weight:400;font-style:normal;font-synthesis:none;font-size:var(--sample-size);line-height:1.6;letter-spacing:0;font-variant-numeric:normal;font-variant-emoji:text;transform:none}.sample-text{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;word-break:normal}.numeric-probes{display:flex;flex-wrap:wrap;gap:3px 7px}.number-probe{display:inline-block;white-space:pre;padding:0;margin:0;border:0;line-height:1.6}.study-scope{font-size:11px;color:#61766f;line-height:1.8;margin:0 0 20px}.phone-study{padding-top:16px}.phone-study>h2{font-size:19px;font-weight:400;margin:0 0 9px}.phone-study>.study-scope{margin-bottom:20px}.phone-gallery{display:grid;grid-template-columns:390px 390px;gap:20px;justify-content:center}.phone-frame{width:390px;height:844px;padding:12px;background:var(--surface);color:var(--ink);overflow:hidden}.phone-header{height:63px;padding:6px 4px 0}.phone-header h2{font:400 17px "Segoe UI","Microsoft YaHei",sans-serif;margin:0 0 8px}.phone-header p{font-size:10px;color:var(--muted);margin:0}.palace-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));grid-template-rows:repeat(4,minmax(0,1fr));height:644px;gap:2px}.palace{padding:7px 5px;border:1px solid var(--rule);min-width:0;background:var(--surface);color:var(--ink)}.phone-sample{font-family:var(--sample-family),sans-serif;font-size:14px;line-height:1.55;font-weight:400;letter-spacing:0;font-synthesis:none;font-variant-numeric:normal;font-variant-emoji:text;overflow-wrap:anywhere;transform:none}.palace h3{margin:0 0 12px}.palace p{margin:0 0 11px}.palace .phone-label{font-size:11px;color:var(--muted)}.palace-center{grid-row:2/4;grid-column:2/4;padding:16px 12px;display:flex;flex-direction:column;justify-content:center;gap:12px;color:var(--muted);font-size:11px;line-height:1.8}.palace-center strong{font-weight:500;font-size:12px;color:var(--ink)}.palace-center p{margin:0}.phone-foot{font-size:10px;line-height:1.75;margin:15px 4px 0;color:var(--muted)}body.phone-only{background:#f1f4ee}body.phone-only main{max-width:none;width:390px;margin:0;padding:0}body.phone-only #desktop-study,body.phone-only .phone-study>h2,body.phone-only .phone-study>.study-scope{display:none}body.phone-only .phone-study{padding:0}body.phone-only .phone-gallery{display:block}body.phone-only .phone-frame[hidden]{display:none}
@media(max-width:1000px){.size-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.phone-gallery{grid-template-columns:390px}}@media(max-width:650px){main{padding:20px 14px}.study-header h1{font-size:23px}.size-grid{grid-template-columns:1fr}.font-section{padding:14px}.font-section h2{flex-direction:column;gap:5px}.phone-gallery{justify-content:start}.phone-frame{max-width:100%}}
</style>
</head>
<body><main>
<div id="desktop-study">
<header class="study-header"><p class="eyebrow">AINCRAD UI SC / BROWSER RASTER STUDY</p><h1>11–14 px · 同字号、同字距的屏幕样张</h1><p>两种字体以真实 CSS 字号绘制，字距为 0，没有用 transform 或页面缩放模拟小字号。浅色与深色使用相同的前景／背景色对调。数字探针未强制列宽，也未启用 tnum。</p><p class="runtime" id="runtime">正在加载当前字体</p></header>
%%SECTIONS%%
<p class="study-scope">本页是桌面 Chromium 的字形与排版样张。字号、DPR 和实际字体使用可以核验；截图观察不能证明所有小字都可读，也不能代替 Flutter / Android 上真实十二宫页面的验收。原始 PNG 保留浏览器像素；图片查看器若自动适应窗口，会再次缩放，请以原始尺寸检查。另附像素放大图，仅用最近邻放大帮助观察笔画，不改变字形。</p>
</div>
<section class="phone-study"><h2>14 px · 十二宫静态布局示意</h2><p class="study-scope">每幅示意固定为 390 × 844 CSS px。主文字 14 px、次要标签 11 px；宫名与星曜只用于测试字体，不代表实际排盘结果。</p><div class="phone-gallery">%%PHONES%%</div></section>
</main>
<script>
const requested=new URLSearchParams(location.search).get('phone');
if(requested){document.body.classList.add('phone-only');document.querySelectorAll('.phone-frame').forEach(frame=>frame.hidden=frame.dataset.phone!==requested);}
window.studyReady=Promise.all([
 document.fonts.load('14px "Aincrad UI SC"',%%SAMPLE_JSON%%),
 document.fonts.load('14px "Aincrad UI SC Display"',%%SAMPLE_JSON%%)
]).then(fonts=>{
 const ok=fonts.every(items=>items.length>0);
 document.getElementById('runtime').textContent=(ok?'两种当前字体已加载':'部分字体未加载')+' / DPR '+devicePixelRatio+' / browser zoom '+visualViewport.scale+' / CSS px 11, 12, 13, 14';
 return ok;
});
</script></body></html>
"""
    document = document.replace("%%SECTIONS%%", "".join(sections)).replace("%%PHONES%%", "".join(phones))
    document = document.replace("%%SAMPLE_JSON%%", json.dumps("".join(cases.values()), ensure_ascii=False))
    path = ARTIFACT / "small-size-study.html"
    path.write_text(document.rstrip() + "\n", encoding="utf-8")
    return path


def actual_fonts(cdp, selector: str) -> list[dict]:
    document = cdp.send("DOM.getDocument")
    node = cdp.send("DOM.querySelector", {"nodeId": document["root"]["nodeId"], "selector": selector})
    assert node["nodeId"], selector
    return cdp.send("CSS.getPlatformFontsForNode", {"nodeId": node["nodeId"]})["fonts"]


def require_custom(fonts: list[dict], font_key: str, selector: str) -> None:
    assert fonts and all(font["isCustomFont"] and font["glyphCount"] > 0 for font in fonts), (selector, fonts)
    assert all(font["familyName"] == FONTS[font_key]["family"] for font in fonts), (selector, fonts)


def pixel_zoom(images: list[Image.Image], destination: Path, dpr: int) -> dict:
    factor = 4 if dpr == 1 else 2
    cell_width = max(image.width for image in images)
    cell_height = max(image.height for image in images)
    header_height = 38 * dpr
    sheet = Image.new("RGB", (cell_width * 4, cell_height * 4 + header_height), "#dbe3df")
    draw = ImageDraw.Draw(sheet)
    caption = "NEAREST-NEIGHBOR / DPR " + str(dpr) + " / PHYSICAL PIXEL MAGNIFICATION x" + str(factor)
    draw.text((12 * dpr, 10 * dpr), caption, fill="#24343e",
              font=ImageFont.load_default(size=12 * dpr))
    for index, image in enumerate(images):
        sheet.paste(image, ((index % 4) * cell_width, (index // 4) * cell_height + header_height))
    sheet = sheet.resize((sheet.width * factor, sheet.height * factor), Image.Resampling.NEAREST)
    sheet.save(destination)
    return {"file": destination.name, "width": sheet.width, "height": sheet.height,
            "physical_pixel_magnification": factor, "method": "nearest-neighbor"}


def focused_zoom(cells: list[dict], destination: Path, size: int, dpr: int) -> dict:
    """Magnify browser crops, retaining the original dense Han and symbol pixels."""
    factor = 4 if dpr == 1 else 2
    label_height, title_height = 25 * dpr, 31 * dpr
    cell_width = max(cell["image"].width for cell in cells)
    cell_height = max(cell["image"].height for cell in cells) + label_height
    sheet = Image.new("RGB", (cell_width * 2, cell_height * 2 + title_height), "#dbe3df")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=11 * dpr)
    draw.text((8 * dpr, 8 * dpr),
              f"{size} CSS px / DPR {dpr} / PHYSICAL PIXELS x{factor} / NEAREST-NEIGHBOR",
              fill="#24343e", font=font)
    for index, cell in enumerate(cells):
        x, y = (index % 2) * cell_width, (index // 2) * cell_height + title_height
        draw.text((x + 8 * dpr, y + 6 * dpr),
                  cell["font"].upper() + " / " + cell["theme"].upper(),
                  fill="#24343e", font=font)
        sheet.paste(cell["image"], (x, y + label_height))
    sheet = sheet.resize((sheet.width * factor, sheet.height * factor), Image.Resampling.NEAREST)
    sheet.save(destination)
    return {"file": destination.name, "width": sheet.width, "height": sheet.height,
            "css_size": size, "dpr": dpr, "physical_pixel_magnification": factor,
            "method": "nearest-neighbor; crops from native browser screenshots",
            "scope": "48 application Han and 32 requested symbols"}


def verify_inputs(cases: dict[str, str]) -> dict:
    required = {character for text in cases.values() for character in text if not character.isspace()}
    required.update(character for text in PALACES + STARS for character in text)
    required.update("0123456789")
    records = {}
    for font_key, font in FONTS.items():
        path = ARTIFACT / "fonts" / font["file"]
        with TTFont(path) as loaded:
            cmap = loaded.getBestCmap()
            missing = sorted(required - {chr(codepoint) for codepoint in cmap})
            assert not missing, (font_key, "Required sample characters missing", missing)
            records[font_key] = {"file": "fonts/" + font["file"],
                                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                 "font_version": loaded["name"].getDebugName(5),
                                 "required_characters": len(required), "missing": missing}
    return records


def render(browser_path: str | None, cases: dict[str, str]) -> dict:
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Desktop Chromium only; not Flutter or Android real-chart acceptance",
        "rendering_environment": "Headless desktop Chromium with Playwright DPR 1/2 contexts; no Android device used.",
        "browser_zoom": 1, "css_sizes": list(SIZES), "dprs": [1, 2], "letter_spacing": 0,
        "sample_symbols": [f"U+{codepoint:04X}" for codepoint in SYMBOL_CODEPOINTS],
        "sources": {}, "font_files": {}, "native_screenshots": [], "pixel_enlargements": [],
        "panels": [], "phone_mockups": [], "console_errors": [], "page_errors": [],
        "failed_requests": [], "http_errors": [],
        "interpretation": {
            "automated": "Coverage, actual custom fonts, CSS sizes, DPR, numeric advances and viewport bounds.",
            "visual": "Readability requires separate human inspection; no universal small-size readability claim.",
            "not_tested": ["Flutter text layout", "Android rasterization", "actual Xingpan twelve-palace contents",
                           "OS font-scale preferences", "device-specific screens"],
        },
        "visual_review": {
            "status": "requires-human-review",
            "note": "A successful automated run is not a readability verdict; inspect native and pixel-zoom images.",
        },
    }
    server = None
    try:
        result["sources"] = verify_inputs(cases)
        charset = json.loads((ARTIFACT / "data/charset.json").read_text(encoding="utf-8"))
        result["charset_summary"] = {key: charset[key] for key in ("version", "han_count", "character_count")}
        for font in FONTS.values():
            for extension in ("otf", "ttf", "woff2"):
                filename = Path(font["file"]).stem + "." + extension
                path = ARTIFACT / "fonts" / filename
                result["font_files"][filename] = {
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "bytes": path.stat().st_size,
                    "browser_rendered": extension == "woff2",
                }
        handler = functools.partial(QuietHandler, directory=str(ARTIFACT))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f"http://127.0.0.1:{server.server_port}/small-size-study.html"
        with sync_playwright() as playwright, ExitStack() as owned_resources:
            options = {"headless": True}
            if browser_path:
                options["executable_path"] = browser_path
            browser = playwright.chromium.launch(**options)
            owned_resources.callback(browser.close)
            result["browser_version"] = browser.version
            for dpr in (1, 2):
                context = browser.new_context(viewport={"width": 1440, "height": 1100}, device_scale_factor=dpr)
                page = context.new_page()
                page.on("console", lambda message: result["console_errors"].append(message.text)
                        if message.type == "error" else None)
                page.on("pageerror", lambda error: result["page_errors"].append(str(error)))
                page.on("requestfailed", lambda request: result["failed_requests"].append(request.failure))
                page.on("response", lambda response: result["http_errors"].append(
                    {"path": response.url.split("/")[-1], "status": response.status})
                    if response.status >= 400 else None)
                page.goto(url, wait_until="networkidle")
                assert page.evaluate("window.studyReady")
                assert page.evaluate("devicePixelRatio") == dpr
                assert page.evaluate("visualViewport.scale") == 1
                cdp = context.new_cdp_session(page)
                cdp.send("DOM.enable")
                cdp.send("CSS.enable")
                zoom_images = []
                focus_cells = {size: [] for size in SIZES}
                for font_key in FONTS:
                    for theme in ("light", "dark"):
                        for size in SIZES:
                            selector = f'.size-card[data-font="{font_key}"][data-theme="{theme}"][data-size="{size}"]'
                            panel = {"font": font_key, "theme": theme, "css_size": size, "dpr": dpr, "cases": {}}
                            for case_key in cases:
                                leaf = selector + f' [data-case="{case_key}"]'
                                fonts = actual_fonts(cdp, leaf)
                                require_custom(fonts, font_key, leaf)
                                metrics = page.locator(leaf).evaluate(
                                    """element=>{const css=getComputedStyle(element);return {
                                      fontSize:css.fontSize,letterSpacing:css.letterSpacing,
                                      transform:css.transform,lineHeight:css.lineHeight,
                                      fontVariantNumeric:css.fontVariantNumeric,
                                      clipped:element.scrollWidth>element.clientWidth+1};}""")
                                assert metrics["fontSize"] == str(size) + "px"
                                assert metrics["letterSpacing"] == "normal" or metrics["letterSpacing"] == "0px"
                                assert metrics["transform"] == "none" and not metrics["clipped"]
                                panel["cases"][case_key] = {"actual_fonts": fonts, **metrics}
                            digits = page.locator(selector + " .number-probe").evaluate_all(
                                "elements=>elements.map(el=>({digit:el.dataset.digit,width:el.getBoundingClientRect().width}))")
                            for digit in digits:
                                leaf = selector + ' [data-digit="' + digit["digit"] + '"]'
                                fonts = actual_fonts(cdp, leaf)
                                require_custom(fonts, font_key, leaf)
                                digit["actual_fonts"] = fonts
                            widths = [item["width"] for item in digits]
                            assert max(widths) - min(widths) <= 1 / 64, (font_key, size, digits)
                            panel["default_digits"] = {"probes": digits, "max_css_width_difference": max(widths) - min(widths)}
                            result["panels"].append(panel)
                            image_bytes = page.locator(selector).screenshot(scale="device")
                            native_card = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                            zoom_images.append(native_card)
                            boxes = page.locator(selector).evaluate(
                                """element=>{const card=element.getBoundingClientRect();
                                  return ['extensions','symbols'].map(key=>{
                                    const rect=element.querySelector('[data-case="'+key+'"]').parentElement.getBoundingClientRect();
                                    return {left:rect.left-card.left,top:rect.top-card.top,
                                      right:rect.right-card.left,bottom:rect.bottom-card.top};});}""")
                            crops = [native_card.crop((math.floor(box["left"] * dpr), math.floor(box["top"] * dpr),
                                                       math.ceil(box["right"] * dpr), math.ceil(box["bottom"] * dpr)))
                                     for box in boxes]
                            focus = Image.new("RGB", (max(crop.width for crop in crops), sum(crop.height for crop in crops)),
                                              "#f1f4ee" if theme == "light" else "#24343e")
                            offset = 0
                            for crop in crops:
                                focus.paste(crop, (0, offset))
                                offset += crop.height
                            focus_cells[size].append({"font": font_key, "theme": theme, "image": focus})
                screenshot_name = "small-size-study.png" if dpr == 1 else "small-size-study-dpr2.png"
                page.locator("#desktop-study").screenshot(path=str(ARTIFACT / screenshot_name), scale="device")
                with Image.open(ARTIFACT / screenshot_name) as native:
                    result["native_screenshots"].append({"file": screenshot_name, "dpr": dpr,
                                                         "width": native.width, "height": native.height})
                result["pixel_enlargements"].append(pixel_zoom(
                    zoom_images, ARTIFACT / f"small-size-zoom-dpr{dpr}.png", dpr))
                for size in SIZES:
                    result["pixel_enlargements"].append(focused_zoom(
                        focus_cells[size], ARTIFACT / f"small-size-focus-{size}px-dpr{dpr}.png", size, dpr))
                page.set_viewport_size({"width": 390, "height": 844})
                for font_key in FONTS:
                    for theme in ("light", "dark"):
                        phone_id = font_key + "-" + theme
                        page.goto(url + "?phone=" + phone_id, wait_until="networkidle")
                        assert page.evaluate("window.studyReady")
                        selector = f'.phone-frame[data-phone="{phone_id}"]'
                        geometry = page.locator(selector + " .palace").evaluate_all(
                            """elements=>elements.map(el=>{const rect=el.getBoundingClientRect();
                              return {top:rect.top,bottom:rect.bottom,left:rect.left,right:rect.right};})""")
                        assert len(geometry) == 12
                        assert all(rect["top"] >= 0 and rect["bottom"] <= 844 and
                                   rect["left"] >= 0 and rect["right"] <= 390 for rect in geometry), geometry
                        assert page.evaluate("document.documentElement.scrollWidth") == 390
                        main_sizes = page.locator(selector + " .palace h3, " + selector + " .palace p:not(.phone-label)").evaluate_all(
                            "elements=>[...new Set(elements.map(el=>getComputedStyle(el).fontSize))]")
                        assert main_sizes == ["14px"]
                        clipping = page.locator(selector + " .phone-sample").evaluate_all(
                            """elements=>elements.filter(el=>el.scrollWidth>el.clientWidth+1 ||
                              el.scrollHeight>el.clientHeight+1).map(el=>el.textContent)""")
                        assert not clipping, clipping
                        phone_fonts = []
                        for index in range(1, 13):
                            for suffix in ("h3", "p:not(.phone-label)", ".phone-label"):
                                leaf = selector + f" .palace:nth-child({index}) " + suffix
                                fonts = actual_fonts(cdp, leaf)
                                require_custom(fonts, font_key, leaf)
                                phone_fonts.append({"node": f"{index}/{suffix}", "fonts": fonts})
                        filename = f"small-size-phone-{phone_id}-dpr{dpr}.png"
                        page.screenshot(path=str(ARTIFACT / filename), full_page=False, scale="device")
                        result["phone_mockups"].append({"font": font_key, "theme": theme, "dpr": dpr,
                                                        "file": filename, "main_css_sizes": main_sizes,
                                                        "palace_bounds": geometry, "clipped_labels": clipping,
                                                        "actual_fonts": phone_fonts})
                context.close()
        for key in ("console_errors", "page_errors", "failed_requests", "http_errors"):
            assert not result[key], (key, result[key])
        result["default_digit_summary"] = {
            "panels": len(result["panels"]), "digits": "0123456789", "repeated_probe_length": 8,
            "maximum_css_width_difference": max(panel["default_digits"]["max_css_width_difference"]
                                                for panel in result["panels"]),
            "features": "font-variant-numeric: normal; no forced cell widths; no tnum activation",
        }
        artifact_names = ["small-size-study.html"] + [
            item["file"] for key in ("native_screenshots", "pixel_enlargements", "phone_mockups")
            for item in result[key]
        ]
        result["artifact_hashes"] = {
            filename: hashlib.sha256((ARTIFACT / filename).read_bytes()).hexdigest()
            for filename in artifact_names
        }
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
        report = ARTIFACT / "data/small-size-verification.json"
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def browser_default() -> str | None:
    browser_cache = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    candidates = sorted(browser_cache.glob("chromium-*/**/chrome.exe"),
                        key=lambda path: int(path.relative_to(browser_cache).parts[0].split("-")[-1]),
                        reverse=True)
    return str(candidates[0]) if candidates else None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", default=browser_default())
    parser.add_argument("--write-html-only", action="store_true",
                        help="Prepare the HTML fixture without validating or rendering fonts.")
    args = parser.parse_args()
    cases = samples()
    destination = write_html(cases)
    if args.write_html_only:
        print(json.dumps({"html": str(destination), "rendered": False}, ensure_ascii=False))
    else:
        report = render(args.browser, cases)
        print(json.dumps({"passed": report["passed"], "panels": len(report["panels"]),
                          "phone_mockups": len(report["phone_mockups"]),
                          "report": str(ARTIFACT / "data/small-size-verification.json")}, ensure_ascii=False))
