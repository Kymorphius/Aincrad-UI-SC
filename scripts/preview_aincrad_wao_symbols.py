"""Render the 24 WAO symbols with the current real Regular/Display TTFs.

Primary evidence is native 14 CSS px at DPR1, with DPR2 regression. Auxiliary
11-14px rows and a connected box-frame sample retain native browser pixels.
This is desktop Chromium evidence, not WAO Flutter/Android acceptance.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import functools
import hashlib
import html
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import threading

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

from preview_aincrad_font import QuietHandler, platform_fonts
from preview_aincrad_small_sizes import browser_default
from preview_aincrad_dense_comparison import glyph_bounds


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT if (ROOT / "fonts").is_dir() else ROOT / "design" / "aincrad-ui-sc"
SYMBOLS = "◆◇●■□▲▼▶◀‹«»─│┌┐└┘‥⟨⟩※†‖"
CONTROLS = "○›…±×÷·—"
SIZE_SAMPLE = "◆◇●□‹⟨⟩※"
HUD = (
    "◆ 角色状态  ◇ 装备详情",
    "● 在线  ○ 离线  ■ 已完成  □ 待处理",
    "▲ 展开  ▼ 收起  ▶ 进入  ◀ 返回",
    "‹ 返回 ›  « 上一组 »",
    "⟨ 技能 ⟩  ※ 注记 †  ‖ 连接 ‥",
)
FONTS = {
    "display": {"family": "Aincrad UI SC Display", "alias": "WAO Display TTF", "variant": "Display"},
    "regular": {"family": "Aincrad UI SC", "alias": "WAO Regular TTF", "variant": "Regular"},
}
PALETTES = {"light": (241, 244, 238), "dark": (36, 52, 62)}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs() -> tuple[dict, dict, dict]:
    charset = json.loads((PROJECT / "data/charset.json").read_text(encoding="utf-8"))
    required = set(SYMBOLS + CONTROLS + SIZE_SAMPLE + "".join(HUD)) - {" "}
    assert len(SYMBOLS) == len(set(SYMBOLS)) == 24
    assert required <= set(charset["characters"]), "Current charset does not cover the WAO study"
    sources, files = {}, {}
    for key, info in FONTS.items():
        filename = f"AincradUISc-{info['variant']}.ttf"
        path = PROJECT / "fonts" / filename
        with TTFont(path, recalcTimestamp=False) as font:
            cmap = font.getBestCmap()
            assert required <= set(map(chr, cmap)), (key, "Study glyphs missing in actual TTF")
            assert font["name"].getDebugName(1) == info["family"]
            advances = {character: font["hmtx"][cmap[ord(character)]][0] for character in "─│┌┐└┘"}
            assert len(set(advances.values())) == 1, (key, "Box characters have different advances")
            sources[key] = {
                "file": "fonts/" + filename, "sha256": digest(path), "bytes": path.stat().st_size,
                "family": info["family"], "css_alias": info["alias"],
                "postscript_name": font["name"].getDebugName(6), "format": "TrueType glyf",
                "units_per_em": font["head"].unitsPerEm,
                "box_advance": next(iter(advances.values())),
                "line_units": font["hhea"].ascent - font["hhea"].descent + font["hhea"].lineGap,
                "line_metrics": {k: getattr(font["hhea"], k) for k in ("ascent", "descent", "lineGap")},
            }
        for extension in ("otf", "ttf", "woff2"):
            name = f"AincradUISc-{info['variant']}.{extension}"
            actual = PROJECT / "fonts" / name
            files[name] = {"sha256": digest(actual), "bytes": actual.stat().st_size,
                           "browser_rendered": extension == "ttf"}
    return charset, sources, files


def glyph_cells(text: str, kind: str) -> str:
    return "".join(
        '<div class="cell"><span class="label">U+' + f"{ord(c):04X}" + '</span>'
        '<div class="surface"><span class="glyph" data-kind="' + kind + '" data-cp="'
        + str(ord(c)) + '">' + html.escape(c) + '</span></div></div>' for c in text
    )


def box_frame() -> str:
    rows = ("┌───┐", "│   │", "└───┘")
    return '<div class="box-lines">' + "".join(
        '<div class="box-row">' + "".join(
            '<span class="box-cell">' + (html.escape(c) if c != " " else "") + '</span>'
            for c in row
        ) + '</div>' for row in rows
    ) + '</div>'


def write_html(charset: dict, sources: dict) -> Path:
    panels = []
    for key, info in FONTS.items():
        source = sources[key]
        for theme in PALETTES:
            panels.append(
                f'<section class="panel {theme}" data-font="{key}" data-theme="{theme}" '
                f'style="--sample-family:&quot;{info["alias"]}&quot;;--box-advance:{source["box_advance"] / source["units_per_em"]};'
                f'--line-factor:{source["line_units"] / source["units_per_em"]}">'
                f'<h2>{key.upper()} TTF / {theme.upper()} / 14 CSS px</h2>'
                '<h3>本批 24 个符号</h3><div class="glyph-grid">' + glyph_cells(SYMBOLS, "new") + '</div>'
                '<h3>旧符号参照</h3><div class="control-grid">' + glyph_cells(CONTROLS, "control") + '</div>'
                '<h3>界面文案 · 原生 14px</h3><div class="hud">' + "".join(
                    f'<p class="hud-line" data-line="{i}">{html.escape(text)}</p>' for i, text in enumerate(HUD)
                ) + '</div><div class="aux"><div><h3>制表线连接 · 字体原行高</h3>' + box_frame() + '</div>'
                '<div class="sizes"><h3>11–14px 辅助观察</h3>' + "".join(
                    f'<p><span class="size-label">{size}px</span><span class="size-sample" data-size="{size}" style="font-size:{size}px">'
                    + html.escape(SIZE_SAMPLE) + '</span></p>' for size in (11, 12, 13, 14)
                ) + '</div></div></section>'
            )
    faces = "".join(
        f'@font-face{{font-family:"{info["alias"]}";src:url("fonts/AincradUISc-{info["variant"]}.ttf") format("truetype");font-display:block;font-weight:400;font-style:normal}}'
        for info in FONTS.values()
    )
    doc = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>Aincrad UI SC · WAO 符号 14px TTF 样张</title><style>' + faces + '''
*{box-sizing:border-box}body{margin:0;background:#dbe3df;color:#24343e;font:12px "Segoe UI","Microsoft YaHei",sans-serif}main{width:1400px;margin:auto;padding:24px}.intro{padding-bottom:16px;margin-bottom:20px;border-bottom:1px solid #a9bbb4}.intro h1{font-size:25px;font-weight:400;margin:0 0 12px}.intro p,.foot{font-size:11px;line-height:1.8;color:#61766f;margin:5px 0}.panels{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.panel{padding:20px;background:var(--surface);color:var(--ink);border:1px solid var(--rule)}.light{--surface:#f1f4ee;--ink:#24343e;--muted:#61767c;--rule:#c3d0c7}.dark{--surface:#24343e;--ink:#f1f4ee;--muted:#b8c6c5;--rule:#50646c}.panel h2{font-size:12px;font-weight:500;letter-spacing:.025em;margin:0 0 16px}.panel h3{font-size:10px;font-weight:400;color:var(--muted);margin:14px 0 7px}.glyph-grid,.control-grid{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:5px}.cell{border:1px solid var(--rule);padding:4px;min-width:0}.label{font:8px/11px "Consolas",monospace;color:var(--muted)}.surface{height:33px;text-align:center;background:var(--surface);color:var(--ink);padding-top:2px}.glyph,.hud-line,.size-sample,.box-lines{font-family:var(--sample-family),sans-serif;font-weight:400;font-style:normal;font-synthesis:none;letter-spacing:0;font-variant-emoji:text;font-variant-numeric:normal;transform:none;filter:none}.glyph{display:inline-block;font-size:14px;line-height:28px;white-space:pre}.hud{border:1px solid var(--rule);padding:9px 12px}.hud-line{font-size:14px;line-height:24px;white-space:pre;margin:0}.aux{display:grid;grid-template-columns:180px 1fr;gap:20px;align-items:start}.sizes p{display:flex;align-items:center;gap:12px;margin:4px 0}.size-label{font:9px/16px "Consolas",monospace;color:var(--muted);width:28px}.size-sample{line-height:24px;white-space:pre}.box-lines{font-size:14px;line-height:calc(var(--line-factor)*1em);margin:12px 0 0 24px;display:inline-block;vertical-align:top}.box-row{display:flex;height:calc(var(--line-factor)*1em);line-height:calc(var(--line-factor)*1em)}.box-cell{display:block;width:calc(var(--box-advance)*1em);height:calc(var(--line-factor)*1em);line-height:calc(var(--line-factor)*1em);white-space:pre;flex:none}.foot{margin-top:20px}
</style></head><body><main id="wao-study"><header class="intro"><h1>WAO 界面符号 / 原生 14px TTF 样张</h1><p>Display 为主，Regular 同字号参照。两档均直接加载本批 TTF；不缩放字体、不补偿字宽、不使用滤镜。浅深主题保持同一字形和字号。</p><p>当前 ''' + str(charset["han_count"]) + ' 汉字 / ' + str(charset["character_count"]) + ' 字符；本批 24 个符号含全部制表线。</p><p id="runtime">正在加载字体</p></header><div class="panels">' + "".join(panels) + '</div><p class="foot">DPR 1 为主要验收条件，DPR 2 为回归样本。图中制表框使用相同字体的原始字宽及行高。原始 PNG 保留浏览器像素，整数放大图仅帮助观察边缘。本页为桌面 Chromium 证据，未替代 WAO Flutter / Android 实机验收。</p></main>'
    sample = SYMBOLS + CONTROLS + "".join(HUD)
    doc += '<script>window.waoReady=Promise.all(' + json.dumps([x["alias"] for x in FONTS.values()]) + '.map(f=>document.fonts.load(\'14px "\'+f+\'"\',' + json.dumps(sample) + '))).then(fonts=>{const ready=fonts.every(items=>items.length>0);document.getElementById("runtime").textContent=(ready?"两档 TTF 已加载":"字体未完整加载")+" / DPR "+devicePixelRatio+" / browser zoom "+visualViewport.scale;return ready;});</script></body></html>'
    path = PROJECT / "wao-symbols-study.html"
    path.write_text(doc + "\n", encoding="utf-8")
    return path


def require_font(cdp, selector: str, family: str) -> list[dict]:
    fonts = platform_fonts(cdp, selector)
    assert fonts and all(f["isCustomFont"] and f["familyName"] == family and f["glyphCount"] > 0 for f in fonts), (selector, fonts)
    return fonts


def zoom_sheet(cases: list[dict], destination: Path) -> dict:
    factor, tile_width, tile_height = 6, 450, 260
    sheet = Image.new("RGB", (tile_width * 8, 42 + tile_height * 3 * 4), "#dbe3df")
    draw = ImageDraw.Draw(sheet)
    label = ImageFont.load_default(size=14)
    draw.text((14, 12), "CURRENT TTF / native14px DPR1 pixels x6 / nearest-neighbor", fill="#24343e", font=label)
    for group, (font, theme) in enumerate((key, palette) for key in FONTS for palette in PALETTES):
        for index, char in enumerate(SYMBOLS):
            item = next(x for x in cases if x["font"] == font and x["theme"] == theme and x["character"] == char)
            x, y = (index % 8) * tile_width, 42 + (group * 3 + index // 8) * tile_height
            draw.rectangle((x, y, x + tile_width - 2, y + tile_height - 2), fill=PALETTES[theme])
            ink = PALETTES["dark" if theme == "light" else "light"]
            draw.text((x + 12, y + 12), f"{font.upper()} / {theme.upper()} / U+{ord(char):04X}", fill=ink, font=label)
            image = item["image"]
            enlarged = image.resize((image.width * factor, image.height * factor), Image.Resampling.NEAREST)
            sheet.paste(enlarged, (x + (tile_width - enlarged.width) // 2, y + 42))
    sheet.save(destination)
    return {"file": destination.name, "factor": factor, "method": "nearest-neighbor from native DPR1 surface crops", "glyphs": len(cases), "width": sheet.width, "height": sheet.height}


def run(browser_path: str | None) -> dict:
    charset, sources, files = inputs()
    fixture = write_html(charset, sources)
    result = {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Desktop Chromium, current actual TTF; 14 CSSpx/DPR1 primary, DPR2 regression, auxiliary11-14px; not WAO Flutter/Android real-app acceptance",
              "charset_summary": {k: charset[k] for k in ("version", "han_count", "character_count")},
              "requested_symbols": SYMBOLS, "requested_symbol_count": 24,
              "controls": CONTROLS, "sources": sources, "font_files": files,
              "runs": [], "font_resources": [], "native_screenshots": [],
              "console_errors": [], "page_errors": [], "failed_requests": [], "http_errors": [],
              "visual_review": {"status": "requires-human-review"}}
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(PROJECT)))
    worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
    zoom_cases = []
    try:
        with sync_playwright() as playwright, ExitStack() as owned:
            options = {"headless": True}
            if browser_path: options["executable_path"] = browser_path
            browser = playwright.chromium.launch(**options); owned.callback(browser.close)
            result["browser_version"] = browser.version
            for dpr in (1, 2):
                context = browser.new_context(viewport={"width": 1440, "height": 1100}, device_scale_factor=dpr)
                page, responses = context.new_page(), []
                page.set_default_timeout(60000)
                page.on("console", lambda m: result["console_errors"].append(m.text) if m.type == "error" else None)
                page.on("pageerror", lambda e: result["page_errors"].append(str(e)))
                page.on("requestfailed", lambda req: result["failed_requests"].append(req.failure))
                page.on("response", lambda res: result["http_errors"].append({"url": res.url, "status": res.status}) if res.status >= 400 else None)
                page.on("response", lambda res: responses.append(res) if res.request.resource_type == "font" else None)
                page.goto(f"http://127.0.0.1:{server.server_port}/{fixture.name}", wait_until="networkidle")
                assert page.evaluate("window.waoReady")
                assert page.evaluate("devicePixelRatio") == dpr and page.evaluate("visualViewport.scale") == 1
                assert {r.url.rsplit("/", 1)[-1] for r in responses} == {Path(s["file"]).name for s in sources.values()}
                for response in responses:
                    name = response.url.rsplit("/", 1)[-1]
                    record = {"dpr": dpr, "file": name, "status": response.status, "response_sha256": hashlib.sha256(response.body()).hexdigest()}
                    assert record["status"] == 200 and record["response_sha256"] == files[name]["sha256"]
                    result["font_resources"].append(record)
                cdp = context.new_cdp_session(page); cdp.send("DOM.enable"); cdp.send("CSS.enable")
                current = {"dpr": dpr, "glyphs": [], "hud_lines": [], "size_rows": [], "box_frames": []}
                for key, info in FONTS.items():
                    for theme in PALETTES:
                        parent = f'.panel[data-font="{key}"][data-theme="{theme}"]'
                        for kind, text in (("new", SYMBOLS), ("control", CONTROLS)):
                            for char in text:
                                sel = parent + f' .glyph[data-kind="{kind}"][data-cp="{ord(char)}"]'
                                actual = require_font(cdp, sel, info["family"])
                                css = page.locator(sel).evaluate("e=>{const c=getComputedStyle(e);return {text:e.textContent,fontSize:c.fontSize,lineHeight:c.lineHeight,letterSpacing:c.letterSpacing,transform:c.transform,filter:c.filter}}")
                                assert css["text"] == char and css["fontSize"] == "14px" and css["lineHeight"] == "28px"
                                assert css["letterSpacing"] in ("normal", "0px") and css["transform"] == css["filter"] == "none"
                                image = Image.open(io.BytesIO(page.locator(sel).locator("..").screenshot(scale="device"))).convert("RGB")
                                bounds = glyph_bounds(image, PALETTES[theme])
                                record = {"font": key, "theme": theme, "kind": kind, "character": char, "codepoint": f"U+{ord(char):04X}", "actual_fonts": actual, **css,
                                          "ink_bounds_physical_px": list(bounds), "raster_sha256": hashlib.sha256(image.tobytes()).hexdigest()}
                                current["glyphs"].append(record)
                                if dpr == 1 and kind == "new": zoom_cases.append({**record, "image": image})
                        for index, text in enumerate(HUD):
                            sel = parent + f' .hud-line[data-line="{index}"]'
                            actual = require_font(cdp, sel, info["family"])
                            assert page.locator(sel).inner_text() == text
                            current["hud_lines"].append({"font": key, "theme": theme, "text": text, "actual_fonts": actual})
                        for size in (11, 12, 13, 14):
                            sel = parent + f' .size-sample[data-size="{size}"]'
                            actual = require_font(cdp, sel, info["family"])
                            assert page.locator(sel).evaluate("e=>getComputedStyle(e).fontSize") == f"{size}px"
                            current["size_rows"].append({"font": key, "theme": theme, "size": size, "actual_fonts": actual})
                        sel = parent + " .box-lines"
                        for index in (0, 1, 2, 3, 4, 5, 9, 10, 11, 12, 13, 14):
                            require_font(cdp, parent + f" .box-row:nth-child({index // 5 + 1}) .box-cell:nth-child({index % 5 + 1})", info["family"])
                        metrics = page.locator(sel).evaluate("e=>({fontSize:getComputedStyle(e).fontSize,lineHeight:getComputedStyle(e).lineHeight,cells:Array.from(e.querySelectorAll('.box-cell'),x=>({text:x.textContent,width:x.getBoundingClientRect().width,height:x.getBoundingClientRect().height}))})")
                        cell_width = sources[key]["box_advance"] / sources[key]["units_per_em"] * 14
                        row_height = sources[key]["line_units"] / sources[key]["units_per_em"] * 14
                        assert all(abs(c["width"] - cell_width) < .02 and abs(c["height"] - row_height) < .02 for c in metrics["cells"])
                        current["box_frames"].append({"font": key, "theme": theme, "expected_advance_css_px": cell_width, "expected_line_css_px": row_height, **metrics})
                assert page.evaluate("document.documentElement.scrollWidth") == 1440
                filename = "wao-symbols-study.png" if dpr == 1 else "wao-symbols-study-dpr2.png"
                page.locator("#wao-study").screenshot(path=str(PROJECT / filename), scale="device")
                result["native_screenshots"].append({"file": filename, "dpr": dpr, "css_font_size": 14})
                result["runs"].append(current); context.close()
        for key in ("console_errors", "page_errors", "failed_requests", "http_errors"): assert not result[key], (key, result[key])
        for name, info in files.items(): assert digest(PROJECT / "fonts" / name) == info["sha256"], "Font changed during rendering"
        result["integer_enlargement"] = zoom_sheet(zoom_cases, PROJECT / "wao-symbols-zoom-dpr1.png")
        names = [fixture.name, "wao-symbols-study.png", "wao-symbols-study-dpr2.png", "wao-symbols-zoom-dpr1.png"]
        result["artifact_hashes"] = {name: digest(PROJECT / name) for name in names}
        result["passed"] = True
    except Exception as error:
        result.update(passed=False, error=str(error)); raise
    finally:
        server.shutdown(); server.server_close(); worker.join(timeout=5)
        (PROJECT / "data/wao-symbol-browser-verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", default=browser_default())
    args = parser.parse_args()
    report = run(args.browser)
    print(json.dumps({"passed": report["passed"], "runs": len(report["runs"]), "requested": 24, "report": "data/wao-symbol-browser-verification.json"}))
