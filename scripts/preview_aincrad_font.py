"""Verify and capture the local Aincrad UI SC specimen in a real browser."""
from __future__ import annotations

import argparse
import functools
import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT if (ROOT / "specimen.html").is_file() else ROOT / "design" / "aincrad-ui-sc"
DEFAULT_INPUT = "个人信息 / Lv. 42\n确认装备，返回任务。"
EXPANSION_PHRASES = (
    "系统设置", "文件管理", "网络连接", "账户安全",
    "更新下载", "任务进度", "背包装备", "消息通知",
    "开始游戏", "偏好设置", "崩溃报告",
)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def font_bindings() -> dict:
    return {f"AincradUISc-{variant}.{extension}": {
        "sha256": hashlib.sha256((ARTIFACT / "fonts" / f"AincradUISc-{variant}.{extension}").read_bytes()).hexdigest(),
        "bytes": (ARTIFACT / "fonts" / f"AincradUISc-{variant}.{extension}").stat().st_size,
        "browser_rendered": extension == "woff2",
    } for variant in ("Regular", "Display") for extension in ("otf", "ttf", "woff2")}


def platform_fonts(cdp, selector: str) -> list[dict]:
    document = cdp.send("DOM.getDocument")
    node = cdp.send(
        "DOM.querySelector",
        {"nodeId": document["root"]["nodeId"], "selector": selector},
    )
    return cdp.send(
        "CSS.getPlatformFontsForNode", {"nodeId": node["nodeId"]}
    )["fonts"]


def no_overflow(page) -> dict:
    return page.evaluate(
        """() => ({
          viewport: innerWidth,
          documentWidth: document.documentElement.scrollWidth,
          bodyWidth: document.body.scrollWidth,
          overflowing: [...document.querySelectorAll('main *')]
            .filter(el => el.getBoundingClientRect().right > innerWidth + 1 ||
                          el.getBoundingClientRect().left < -1)
            .map(el => ({tag:el.tagName,class:el.className,
                        right:el.getBoundingClientRect().right}))
        })"""
    )


def refinement_contract(page, cdp, variant: str, desktop: bool = False) -> dict:
    """Check that color/scale remain equal while the chosen font sources differ."""
    expected = {
        "regular": ("Aincrad Previous UI", "Aincrad UI SC"),
        "display": ("Aincrad Previous Display", "Aincrad UI SC Display"),
    }[variant]
    cards = page.locator(".refinement-card")
    assert cards.count() == 2
    result = {"variant": variant, "cards": []}
    for index, family in enumerate(expected):
        selector = f".refinement-card:nth-child({index+1})"
        card = cards.nth(index)
        evidence = card.evaluate("""element => {
          const style=getComputedStyle(element);
          const rows=[...element.querySelectorAll('.refinement-words')].map(row=>{
            const css=getComputedStyle(row);
            return {text:row.textContent.replace(/\\s+/g,' ').trim(),
              fontFamily:css.fontFamily, fontSize:css.fontSize,
              fontWeight:css.fontWeight, lineHeight:css.lineHeight,
              letterSpacing:css.letterSpacing, color:css.color,
              words:[...row.children].map(word=>({text:word.textContent,
                x:word.getBoundingClientRect().x, y:word.getBoundingClientRect().y,
                width:word.getBoundingClientRect().width,
                height:word.getBoundingClientRect().height}))};
          });
          return {background:style.backgroundColor,rows};
        }""")
        for row in evidence["rows"]:
            assert row["text"] == "设置 保存 取消 返回"
            assert family in row["fontFamily"]
            if desktop:
                assert len({round(word["y"], 2) for word in row["words"]}) == 1
        assert [row["fontSize"] for row in evidence["rows"]] == ["48px", "16px"]
        evidence["actual_fonts"] = {}
        for size in ("large", "small"):
            evidence["actual_fonts"][size] = [
                platform_fonts(cdp, selector + f" .refinement-{size} span:nth-child({word})")
                for word in range(1, 5)
            ]
            for word_fonts in evidence["actual_fonts"][size]:
                assert word_fonts, (selector, size)
                assert all(font["isCustomFont"] and font["glyphCount"] == 2
                           for font in word_fonts), (selector, size, word_fonts)
                if variant == "display":
                    assert all("Display" in font["familyName"] for font in word_fonts)
                else:
                    assert all("Display" not in font["familyName"] for font in word_fonts)
        result["cards"].append(evidence)
    old, new = result["cards"]
    assert old["background"] == new["background"]
    assert old["background"] == "rgb(232, 238, 234)", "Comparison must use an opaque shared background"
    for before, after in zip(old["rows"], new["rows"]):
        for property_name in ("fontSize", "fontWeight", "lineHeight", "letterSpacing", "color"):
            assert before[property_name] == after[property_name], property_name
    return result


def vocabulary_contract(page, cdp, variant: str, charset: dict, vocabulary: dict) -> dict:
    evidence = {"variant": variant, "phrases": []}
    catalog = page.evaluate("window.AINCRAD_CATALOG")
    assert catalog["charset"] == charset, "Generated JS charset differs from JSON"
    assert catalog["vocabulary"] == vocabulary, "Generated JS vocabulary differs from JSON"
    expected = {character for character in charset["characters"]}
    result_count = sum(len(category["phrases"]) for category in vocabulary["categories"])
    uncovered = sorted({character for category in vocabulary["categories"]
                        for phrase in category["phrases"] for character in phrase
                        if not character.isspace() and character not in expected})
    assert not uncovered, ("Vocabulary contains uncovered characters", uncovered)
    evidence["uncovered_vocabulary_characters"] = uncovered
    assert page.locator("#vocabulary-category option").count() == len(vocabulary["categories"]) + 1
    evidence["category_count"] = len(vocabulary["categories"])
    evidence["phrase_count"] = result_count
    evidence["stats"] = page.locator("#catalog-stats").inner_text()
    for number in (len(expected), len(vocabulary["categories"]), result_count):
        assert str(number) in evidence["stats"]
    page.locator("#vocabulary-category").select_option("all")
    page.locator("#vocabulary-search").fill("")
    initial_count = page.locator(".vocabulary-phrase").count()
    if result_count > 24:
        assert initial_count == 24
        page.locator("#vocabulary-more").click()
        assert page.locator(".vocabulary-phrase").count() == min(48, result_count)
        evidence["load_more"] = True
    for phrase in EXPANSION_PHRASES:
        assert all(character in expected for character in phrase), phrase
        page.locator("#vocabulary-search").fill(phrase)
        option = page.get_by_role("button", name=phrase, exact=True).first
        assert option.count(), phrase
        option.click()
        assert page.locator("#vocabulary-selected").inner_text() == phrase
        assert "搜索文字均在当前字表中" in page.locator("#vocabulary-search-coverage").inner_text()
        fonts = platform_fonts(cdp, "#vocabulary-selected")
        assert fonts and all(font["isCustomFont"] for font in fonts), (phrase, fonts)
        assert sum(font["glyphCount"] for font in fonts) == len(set(phrase)), (phrase, fonts)
        assert all(("Display" in font["familyName"]) == (variant == "display")
                   for font in fonts), (phrase, fonts)
        evidence["phrases"].append({"text": phrase, "actual_fonts": fonts})
    first_category = vocabulary["categories"][0]
    page.locator("#vocabulary-search").fill("")
    page.locator("#vocabulary-category").select_option(first_category["id"])
    rendered = page.locator(".vocabulary-phrase").all_text_contents()
    assert rendered and all(phrase in first_category["phrases"] for phrase in rendered)
    evidence["category_selection"] = first_category["id"]
    page.locator("#vocabulary-category").select_option("all")
    missing_query = next(chr(codepoint) for codepoint in
                         (0x9F98, 0x2B740, 0x30EDD, 0x1F984)
                         if chr(codepoint) not in expected)
    page.locator("#vocabulary-search").fill(missing_query)
    assert page.locator(".vocabulary-phrase").count() == 0
    assert "没有匹配词句" in page.locator(".vocabulary-empty").inner_text()
    assert "搜索含未覆盖字" in page.locator("#vocabulary-search-coverage").inner_text()
    page.locator("#vocabulary-search").fill("系统设置")
    page.get_by_role("button", name="系统设置", exact=True).first.click()
    page.locator("#vocabulary-search").fill("")
    page.locator("#vocabulary-search").blur()
    return evidence


def run(browser_path: str | None) -> dict:
    handler = functools.partial(QuietHandler, directory=str(ARTIFACT))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "transport": "loopback HTTP; server stopped after verification",
        "console_errors": [],
        "page_errors": [],
        "failed_requests": [],
        "http_errors": [],
        "font_resources": [],
        "checks": {},
    }
    try:
        result["font_files"] = font_bindings()
        charset = json.loads((ARTIFACT / "data" / "charset.json").read_text(encoding="utf-8"))
        result["charset_summary"] = {key: charset[key] for key in ("version", "han_count", "character_count")}
        vocabulary = json.loads((ARTIFACT / "data" / "ui-vocabulary.json").read_text(encoding="utf-8"))
        missing_sample = "".join(chr(codepoint) for codepoint in
                                 (0x9F98, 0x2B740, 0x30EDD, 0x1F984)
                                 if chr(codepoint) not in charset["characters"])[:3]
        assert missing_sample
        with sync_playwright() as playwright:
            options = {"headless": True}
            if browser_path:
                options["executable_path"] = browser_path
            browser = playwright.chromium.launch(**options)
            result["browser_version"] = browser.version
            page = browser.new_page(viewport={"width": 1440, "height": 1100},
                                    device_scale_factor=1)
            page.on("console", lambda message: result["console_errors"].append(
                message.text) if message.type == "error" else None)
            page.on("pageerror", lambda error: result["page_errors"].append(str(error)))
            page.on("requestfailed", lambda request: result["failed_requests"].append(
                {"url": request.url.split("/")[-1], "failure": request.failure}))
            page.on("response", lambda response: result["http_errors"].append(
                {"path": response.url.split("/")[-1], "status": response.status})
                if response.status >= 400 else None)
            page.on("response", lambda response: result["font_resources"].append(
                {"filename": response.url.split("/")[-1], "status": response.status})
                if response.url.endswith(".woff2") else None)
            url = f"http://127.0.0.1:{server.server_port}/specimen.html"
            page.goto(url, wait_until="networkidle")
            page.wait_for_selector("#font-status.ready")
            han_count = charset["han_count"]
            page.wait_for_function(
                "count => document.getElementById('charset-count').textContent.includes(String(count))",
                arg=han_count)
            cdp = page.context.new_cdp_session(page)
            cdp.send("DOM.enable")
            cdp.send("CSS.enable")
            result["checks"]["font_status"] = page.locator("#font-status-text").inner_text()
            assert result["checks"]["font_status"] == "5 组字体已加载"
            result["checks"]["font_faces"] = page.evaluate(
                "()=>[...document.fonts].map(font=>({family:font.family,status:font.status}))")
            assert len(result["checks"]["font_faces"]) == 5
            assert all(face["status"] == "loaded" for face in result["checks"]["font_faces"])
            result["checks"]["regular_actual_fonts"] = platform_fonts(cdp, "#panel-title")
            result["checks"]["baseline_actual_fonts"] = platform_fonts(cdp, ".baseline")
            assert all(font["isCustomFont"] for font in
                       result["checks"]["regular_actual_fonts"]), "Regular fell back"
            assert all(font["isCustomFont"] for font in
                       result["checks"]["baseline_actual_fonts"]), "Baseline fell back"
            page.locator("#type-input").fill("系统设置 / 文件管理 / 网络连接")
            result["checks"]["covered_input"] = page.locator("#coverage").inner_text()
            assert not page.locator("#coverage").evaluate(
                "element => element.classList.contains('missing')")
            page.locator("#type-input").fill(missing_sample)
            result["checks"]["missing_input"] = page.locator("#coverage").inner_text()
            assert f"未覆盖 {len(missing_sample)} 字" in result["checks"]["missing_input"]
            page.locator("#type-input").fill(DEFAULT_INPUT)
            page.locator("#font-size").evaluate(
                "element=>{element.value='40';element.dispatchEvent(new Event('input',{bubbles:true}))}")
            result["checks"]["slider_size"] = page.locator("#type-input").evaluate(
                "element=>getComputedStyle(element).fontSize")
            assert result["checks"]["slider_size"] == "40px"
            page.locator("#font-size").evaluate(
                "element=>{element.value='28';element.dispatchEvent(new Event('input',{bubbles:true}))}")
            page.locator('[data-title="系统设置"]').click()
            assert page.locator("#panel-title").inner_text() == "系统设置"
            result["checks"]["menu_switch"] = True
            page.locator('[data-title="个人信息"]').click()
            page.locator('[data-variant="regular"]').click()
            result["checks"]["regular_refinement"] = refinement_contract(
                page, cdp, "regular", desktop=True)
            result["checks"]["regular_vocabulary"] = vocabulary_contract(
                page, cdp, "regular", charset, vocabulary)
            result["checks"]["desktop_overflow"] = no_overflow(page)
            assert not result["checks"]["desktop_overflow"]["overflowing"]
            page.screenshot(path=str(ARTIFACT / "preview.png"), full_page=True)
            page.locator(".refinement").screenshot(path=str(ARTIFACT / "refinement-comparison.png"))
            page.locator(".vocabulary").screenshot(path=str(ARTIFACT / "coverage-preview.png"))
            page.locator('[data-variant="display"]').click()
            result["checks"]["display_computed_family"] = page.locator("#panel-title").evaluate(
                "element=>getComputedStyle(element).fontFamily")
            result["checks"]["display_actual_fonts"] = platform_fonts(cdp, "#panel-title")
            assert "Aincrad UI SC Display" in result["checks"]["display_computed_family"]
            assert any("Display" in font["familyName"] for font in
                       result["checks"]["display_actual_fonts"])
            result["checks"]["display_refinement"] = refinement_contract(
                page, cdp, "display", desktop=True)
            result["checks"]["display_vocabulary"] = vocabulary_contract(
                page, cdp, "display", charset, vocabulary)
            page.screenshot(path=str(ARTIFACT / "preview-display.png"), full_page=True)
            result["checks"]["responsive_layouts"] = []
            for width in (1440, 1000, 768, 390):
                page.set_viewport_size({"width": width, "height": 844})
                for variant in ("regular", "display"):
                    page.locator(f'[data-variant="{variant}"]').click()
                    overflow = no_overflow(page)
                    result["checks"]["responsive_layouts"].append(
                        {"width": width, "variant": variant, **overflow})
                    assert overflow["documentWidth"] == width, overflow
                    assert not overflow["overflowing"], overflow
                    refinement_contract(page, cdp, variant, desktop=width == 1440)
            page.screenshot(path=str(ARTIFACT / "preview-mobile.png"), full_page=True)
            page.goto((ARTIFACT / "specimen.html").as_uri(), wait_until="networkidle")
            page.wait_for_selector("#font-status.ready")
            page.locator("#type-input").fill("系统设置 / 文件管理 / 网络连接")
            assert not page.locator("#coverage").evaluate(
                "element=>element.classList.contains('missing')")
            page.locator("#type-input").fill(missing_sample)
            assert f"未覆盖 {len(missing_sample)} 字" in page.locator("#coverage").inner_text()
            result["checks"]["file_uri_fonts_and_coverage"] = True
            result["checks"]["file_uri_font_status"] = page.locator("#font-status-text").inner_text()
            assert result["checks"]["file_uri_font_status"] == "5 组字体已加载"
            result["checks"]["file_uri_vocabulary"] = vocabulary_contract(
                page, cdp, "regular", charset, vocabulary)
            browser.close()
        assert not result["console_errors"], result["console_errors"]
        assert not result["page_errors"], result["page_errors"]
        assert not result["failed_requests"], result["failed_requests"]
        assert not result["http_errors"], result["http_errors"]
        assert font_bindings() == result["font_files"], "Current font files changed during browser verification"
        result["artifact_hashes"] = {
            name: hashlib.sha256((ARTIFACT / name).read_bytes()).hexdigest()
            for name in ("specimen.html", "preview.png", "preview-display.png", "preview-mobile.png",
                         "coverage-preview.png", "refinement-comparison.png")
        }
        result["passed"] = True
    except Exception as error:
        result["passed"] = False
        result["error"] = str(error)
        raise
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
        destination = ARTIFACT / "data" / "browser-verification.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    return result


if __name__ == "__main__":
    browser_cache = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    candidates = sorted(browser_cache.glob("chromium-*/**/chrome.exe"),
                        key=lambda path: int(path.relative_to(browser_cache).parts[0].split("-")[-1]),
                        reverse=True)
    default_browser = candidates[0] if candidates else None
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", default=str(default_browser) if default_browser else None)
    args = parser.parse_args()
    report = run(args.browser)
    print(json.dumps({"passed": report["passed"], "checks": len(report["checks"]),
                      "report": str(ARTIFACT / "data" / "browser-verification.json")},
                     ensure_ascii=False))
