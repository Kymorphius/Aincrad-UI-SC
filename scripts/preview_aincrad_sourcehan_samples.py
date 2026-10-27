"""Smoke-test Source Han extension/compatibility samples in actual current WOFF2.

Samples are selected from the generated charset and both current font cmaps.
Each Unicode scalar is rendered in its own span so compatibility characters
that share a glyph are never mistaken for missing characters. No normalization
is applied. The script also checks the existing specimen's input/search logic.
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
from pathlib import Path
import threading
from http.server import ThreadingHTTPServer
import unicodedata

from fontTools.ttLib import TTFont
from PIL import Image
from playwright.sync_api import sync_playwright

from preview_aincrad_font import QuietHandler, platform_fonts
from preview_aincrad_small_sizes import browser_default
from preview_aincrad_dense_comparison import glyph_bounds


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT if (ROOT / "fonts").is_dir() else ROOT / "design" / "aincrad-ui-sc"
FONTS = {"regular": "Aincrad UI SC", "display": "Aincrad UI SC Display"}
PALETTES = {"light": (241, 244, 238), "dark": (36, 52, 62)}
BLOCKS = (
    ("unified", "统一汉字 · BMP", 0x4E00, 0x9FFF),
    ("extension-a", "扩展 A · BMP", 0x3400, 0x4DBF),
    ("extension-b", "扩展 B · 非 BMP", 0x20000, 0x2A6DF),
    ("extension-c", "扩展 C · 非 BMP", 0x2A700, 0x2B73F),
    ("extension-d", "扩展 D · 非 BMP", 0x2B740, 0x2B81F),
    ("extension-e", "扩展 E · 非 BMP", 0x2B820, 0x2CEAF),
    ("extension-f", "扩展 F · 非 BMP", 0x2CEB0, 0x2EBEF),
    ("compatibility", "兼容汉字 · BMP", 0xF900, 0xFAFF),
    ("compatibility-supplement", "补充兼容汉字 · 非 BMP", 0x2F800, 0x2FA1F),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare() -> tuple[dict, dict, dict, list]:
    charset = json.loads((PROJECT / "data/charset.json").read_text(encoding="utf-8"))
    declared = {ord(character) for character in charset["han_characters"]}
    sources, cmaps = {}, []
    for key in FONTS:
        filename = f"AincradUISc-{'Regular' if key == 'regular' else 'Display'}.woff2"
        path = PROJECT / "fonts" / filename
        with TTFont(path) as font:
            cmap = font.getBestCmap()
            cmaps.append(set(cmap))
            sources[key] = {"file": "fonts/" + filename, "sha256": digest(path), "bytes": path.stat().st_size,
                            "family": font["name"].getDebugName(1), "postscript_name": font["name"].getDebugName(6),
                            "version": font["name"].getDebugName(5),
                            "unicode_cmap_formats": sorted({table.format for table in font["cmap"].tables if table.isUnicode()}),
                            "compatibility_alias_reference": {
                                "codepoints": ["U+66F4", "U+F901"],
                                "glyph_names": [cmap.get(0x66F4), cmap.get(0xF901)],
                                "shared_glyph": cmap.get(0x66F4) is not None and cmap.get(0x66F4) == cmap.get(0xF901),
                                "note": "Codepoint identity is preserved even when the font intentionally shares one glyph."}}
    available = declared.intersection(*cmaps)
    blocks = []
    for block_id, title, first, last in BLOCKS:
        points = sorted(point for point in available if first <= point <= last)
        selected = sorted({points[index] for index in (0, len(points) // 2, len(points) - 1)}) if points else []
        preferred = 0x66F4 if block_id == "unified" else 0xF901 if block_id == "compatibility" else None
        if preferred in points:
            selected = sorted({points[0], preferred, points[-1]})
        blocks.append({"id": block_id, "title": title, "available_count": len(points), "samples": [
            {"character": chr(point), "codepoint": point, "label": f"U+{point:04X}",
             "utf16_code_units": 2 if point > 0xFFFF else 1,
             "nfkc_identity_reference_only": [f"U+{ord(character):04X}" for character in unicodedata.normalize("NFKC", chr(point))]}
            for point in selected]})
    assert next(block for block in blocks if block["id"] == "extension-a")["samples"], "No Extension A sample"
    assert next(block for block in blocks if block["id"] == "extension-b")["samples"], "No supplementary Han sample"
    assert any(block["samples"] for block in blocks if block["id"].startswith("compatibility")), "No compatibility Han sample"
    for source in sources.values():
        assert 12 in source["unicode_cmap_formats"] or 13 in source["unicode_cmap_formats"], "No full-Unicode cmap"
    files = {}
    for variant in ("Regular", "Display"):
        for extension in ("otf", "ttf", "woff2"):
            filename = f"AincradUISc-{variant}.{extension}"
            path = PROJECT / "fonts" / filename
            files[filename] = {"sha256": digest(path), "bytes": path.stat().st_size, "browser_rendered": extension == "woff2"}
    return charset, sources, files, blocks


def write_html(charset: dict, blocks: list) -> Path:
    panels = []
    for font, family in FONTS.items():
        for theme in PALETTES:
            rows = []
            for block in blocks:
                if not block["samples"]:
                    continue
                cells = "".join(f'<div class="cell"><span class="codepoint">{sample["label"]}</span>'
                                f'<div class="surface"><span class="glyph" data-codepoint="{sample["codepoint"]}">{html.escape(sample["character"])}</span></div></div>'
                                for sample in block["samples"])
                rows.append(f'<div class="block"><h3>{html.escape(block["title"])}</h3><div class="cells">{cells}</div></div>')
            panels.append(f'<section class="panel {theme}" data-font="{font}" data-theme="{theme}"><h2>{font.upper()} / {theme.upper()} / 14 CSS px</h2>' + "".join(rows) + "</section>")
    faces = "".join(f'@font-face{{font-family:"{family}";src:url("fonts/AincradUISc-{"Regular" if key == "regular" else "Display"}.woff2") format("woff2");font-display:block}}' for key, family in FONTS.items())
    document = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>Aincrad UI SC · 扩展与兼容汉字代表字</title><style>' + faces + '''
*{box-sizing:border-box}body{margin:0;background:#dbe3df;color:#24343e;font:12px "Segoe UI","Microsoft YaHei",sans-serif}main{width:1360px;margin:auto;padding:24px}.intro{border-bottom:1px solid #a9bbb4;padding-bottom:18px;margin-bottom:20px}.intro h1{font-size:25px;font-weight:400;margin:0 0 10px}.intro p,.foot{font-size:11px;line-height:20px;margin:5px 0;color:#61766f}.panels{display:grid;grid-template-columns:repeat(2,1fr);gap:20px}.panel{padding:20px;border:1px solid var(--rule);background:var(--surface);color:var(--ink)}.light{--surface:#f1f4ee;--ink:#24343e;--rule:#c3d0c7;--muted:#61767c}.dark{--surface:#24343e;--ink:#f1f4ee;--rule:#50646c;--muted:#b8c6c5}.panel h2{font-size:12px;line-height:18px;font-weight:500;margin:0 0 15px}.block{display:grid;grid-template-columns:165px 1fr;gap:10px;align-items:center;margin-top:8px}.block h3{font-size:11px;line-height:18px;font-weight:400;color:var(--muted);margin:0}.cells{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}.cell{border:1px solid var(--rule);background:var(--surface);padding:5px 6px}.codepoint{display:block;font:9px/12px "Consolas",monospace;color:var(--muted)}.surface{height:40px;padding:6px 4px;background:var(--surface);color:var(--ink);text-align:center}.glyph{display:inline-block;font-size:14px;font-weight:400;font-style:normal;line-height:28px;letter-spacing:0;font-synthesis:none;transform:none;filter:none}.panel[data-font="regular"] .glyph{font-family:"Aincrad UI SC",sans-serif}.panel[data-font="display"] .glyph{font-family:"Aincrad UI SC Display",sans-serif}.foot{margin-top:20px}
</style></head><body><main id="sourcehan-study"><header class="intro"><h1>扩展与兼容汉字 / 原生 14px 代表字</h1><p>从当前字表与两份字体的实际映射中选择代表字，逐字保留原码位。扩展区与兼容区可能包含外观相同的字符；这里不合并或归一化它们。</p><p>当前 ''' + str(charset["han_count"]) + ' 汉字 / ' + str(charset["character_count"]) + ' 字符 · 两种变体 · 亮暗背景 · 14 CSS px</p><p id="runtime">正在加载字体</p></header><div class="panels">' + "".join(panels) + '</div><p class="foot">这是代表字加载与显示检查，不能代替整库的小字号可读性验收。原图保留真实浏览器像素；DPR 1 与 DPR 2 分别渲染，没有字体缩放或插值。未完成 Flutter / Android 真实页面验收。</p></main></body></html>'
    text = "".join(sample["character"] for block in blocks for sample in block["samples"])
    ready = '<script>window.sourcehanReady=Promise.all(' + json.dumps(list(FONTS.values())) + '.map(family=>document.fonts.load(\'14px "\'+family+\'"\',' + json.dumps(text) + '))).then(items=>{const ok=items.every(fonts=>fonts.length>0);document.getElementById("runtime").textContent=(ok?"两种字体已加载":"字体未完整加载")+" / DPR "+devicePixelRatio+" / browser zoom "+visualViewport.scale;return ok;}).catch(()=>{document.getElementById("runtime").textContent="字体加载失败";return false;});</script>'
    document = document.replace("</body>", ready + "</body>")
    path = PROJECT / "sourcehan-samples.html"
    path.write_text(document.rstrip() + "\n", encoding="utf-8")
    return path


def specimen_unicode_contract(page, samples: list, charset: dict) -> dict:
    supplementary = next(sample["character"] for sample in samples if sample["codepoint"] > 0xFFFF)
    compatibility = next(sample["character"] for sample in samples if 0xF900 <= sample["codepoint"] <= 0xFAFF or 0x2F800 <= sample["codepoint"] <= 0x2FA1F)
    supported = set(charset["characters"])
    missing = next(chr(point) for point in (0x31350, 0x2EBF0, 0x30000, 0x10FFFD) if chr(point) not in supported)
    page.wait_for_selector("#font-status.ready")
    value = supplementary + compatibility
    page.locator("#type-input").fill(value)
    assert not page.locator("#coverage").evaluate("element=>element.classList.contains('missing')")
    roundtrip = page.locator("#type-input").evaluate("element=>({points:Array.from(element.value,character=>character.codePointAt(0)),units:element.value.length})")
    assert roundtrip["points"] == [ord(character) for character in value]
    covered_text = page.locator("#coverage").inner_text()
    page.locator("#vocabulary-search").fill(supplementary)
    search_text = page.locator("#vocabulary-search-coverage").inner_text()
    assert "搜索文字均在当前字表中" in search_text
    page.locator("#type-input").fill(supplementary + missing + missing)
    missing_text = page.locator("#coverage").inner_text()
    assert "未覆盖 1 字" in missing_text and missing in missing_text
    return {"covered_input_codepoints": roundtrip["points"], "covered_input_utf16_units": roundtrip["units"],
            "covered_input_message": covered_text, "supplementary_search_message": search_text,
            "unsupported_supplementary_codepoint": f"U+{ord(missing):04X}", "repeated_missing_message": missing_text,
            "raw_compatibility_codepoint_preserved": True, "normalization_applied": False}


def run(browser_path: str | None) -> dict:
    charset, sources, files, blocks = prepare()
    fixture = write_html(charset, blocks)
    samples = [sample for block in blocks for sample in block["samples"]]
    result = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "scope": "Current WOFF2 representative glyph smoke test, desktop Chromium, 14 CSS px, DPR1/2; not all-character readability acceptance",
              "charset_summary": {key: charset[key] for key in ("version", "han_count", "character_count")},
              "sources": sources, "font_files": files, "blocks": blocks, "runs": [], "font_resources": [],
              "console_errors": [], "page_errors": [], "failed_requests": [], "http_errors": [],
              "visual_review": {"status": "requires-human-review"}}
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(PROJECT)))
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
            for dpr in (1, 2):
                context = browser.new_context(viewport={"width": 1400, "height": 1100}, device_scale_factor=dpr)
                page, responses = context.new_page(), []
                page.set_default_timeout(60000)
                page.on("console", lambda message: result["console_errors"].append(message.text) if message.type == "error" else None)
                page.on("pageerror", lambda error: result["page_errors"].append(str(error)))
                page.on("requestfailed", lambda request: result["failed_requests"].append(request.failure))
                page.on("response", lambda response: result["http_errors"].append({"url": response.url, "status": response.status}) if response.status >= 400 else None)
                page.on("response", lambda response: responses.append(response) if response.request.resource_type == "font" else None)
                page.goto(f"http://127.0.0.1:{server.server_port}/sourcehan-samples.html", wait_until="networkidle")
                assert page.evaluate("window.sourcehanReady")
                assert page.evaluate("devicePixelRatio") == dpr and page.evaluate("visualViewport.scale") == 1
                page.locator("#runtime").evaluate("(element,dpr)=>element.textContent='两种字体已加载 / DPR '+dpr+' / browser zoom 1'", dpr)
                expected = {Path(source["file"]).name: source["sha256"] for source in sources.values()}
                assert {response.url.rsplit("/", 1)[-1] for response in responses} == set(expected)
                for response in responses:
                    filename = response.url.rsplit("/", 1)[-1]
                    resource = {"dpr": dpr, "file": filename, "status": response.status, "resource_type": response.request.resource_type,
                                "response_sha256": hashlib.sha256(response.body()).hexdigest()}
                    assert resource["status"] == 200 and resource["response_sha256"] == expected[filename]
                    result["font_resources"].append(resource)
                cdp = context.new_cdp_session(page)
                cdp.send("DOM.enable")
                cdp.send("CSS.enable")
                run_record = {"dpr": dpr, "glyphs": []}
                for font, family in FONTS.items():
                    for theme in PALETTES:
                        for sample in samples:
                            selector = f'.panel[data-font="{font}"][data-theme="{theme}"] .glyph[data-codepoint="{sample["codepoint"]}"]'
                            fonts = platform_fonts(cdp, selector)
                            assert fonts and all(item["isCustomFont"] and item["familyName"] == sources[font]["family"] and item["glyphCount"] == 1 for item in fonts), (sample, fonts)
                            metrics = page.locator(selector).evaluate("element=>{const css=getComputedStyle(element);return {text:element.textContent,points:Array.from(element.textContent,character=>character.codePointAt(0)),units:element.textContent.length,fontSize:css.fontSize,lineHeight:css.lineHeight,letterSpacing:css.letterSpacing,transform:css.transform,filter:css.filter}}")
                            assert metrics["points"] == [sample["codepoint"]] and metrics["units"] == sample["utf16_code_units"]
                            assert metrics["fontSize"] == "14px" and metrics["lineHeight"] == "28px" and metrics["letterSpacing"] in ("normal", "0px")
                            assert metrics["filter"] == metrics["transform"] == "none"
                            image = Image.open(io.BytesIO(page.locator(selector).locator("..").screenshot(scale="device"))).convert("RGB")
                            bounds = glyph_bounds(image, PALETTES[theme])
                            run_record["glyphs"].append({"font": font, "theme": theme, "codepoint": sample["label"], "actual_fonts": fonts,
                                                         **metrics, "ink_bounds_physical_px": list(bounds), "raster_sha256": hashlib.sha256(image.tobytes()).hexdigest()})
                assert page.evaluate("document.documentElement.scrollWidth") == 1400
                filename = "sourcehan-samples.png" if dpr == 1 else "sourcehan-samples-dpr2.png"
                page.locator("#sourcehan-study").screenshot(path=str(PROJECT / filename), scale="device")
                run_record["screenshot"] = filename
                page.goto(f"http://127.0.0.1:{server.server_port}/specimen.html", wait_until="networkidle")
                run_record["specimen_unicode_input"] = specimen_unicode_contract(page, samples, charset)
                result["runs"].append(run_record)
                context.close()
        for key in ("console_errors", "page_errors", "failed_requests", "http_errors"):
            assert not result[key], (key, result[key])
        for filename, record in files.items():
            assert digest(PROJECT / "fonts" / filename) == record["sha256"], "Current font changed during smoke test"
        result["artifact_hashes"] = {name: digest(PROJECT / name) for name in (fixture.name, "sourcehan-samples.png", "sourcehan-samples-dpr2.png")}
        result["passed"] = True
    except Exception as error:
        result.update({"passed": False, "error": str(error)})
        raise
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
        (PROJECT / "data/sourcehan-sample-verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", default=browser_default())
    args = parser.parse_args()
    report = run(args.browser)
    print(json.dumps({"passed": report["passed"], "runs": len(report["runs"]), "samples_per_font_theme": sum(len(block["samples"]) for block in report["blocks"])}))
