#!/usr/bin/env python3
"""Check the published Aincrad UI SC specimen files, without rebuilding them.

Requires fontTools and Brotli support (for WOFF2).  A failure exits with status 1;
the JSON result is printed to stdout and optionally copied to --report.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import unicodedata

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont


VARIANTS = {
    "Regular": ("AincradUISc-Regular", "Aincrad UI SC"),
    "Display": ("AincradUISc-Display", "Aincrad UI SC Display"),
}
FORMATS = ("otf", "ttf", "woff2")
CURRENT_FONT_VERSION = "0.300"
PREVIOUS_FONT_VERSION = "0.200"


def is_han(character: str) -> bool:
    point = ord(character)
    return (
        0x3400 <= point <= 0x4DBF
        or 0x4E00 <= point <= 0x9FFF
        or 0xF900 <= point <= 0xFAFF
        or 0x20000 <= point <= 0x323AF
    )


def visible(character: str) -> bool:
    return not character.isspace() and unicodedata.category(character) not in (
        "Cc", "Cf", "Zl", "Zp", "Zs"
    )


def label(character: str) -> str:
    return f"{character!r} U+{ord(character):04X}"


def name_text(font: TTFont, name_id: int) -> str:
    return "\n".join(
        sorted({record.toUnicode() for record in font["name"].names if record.nameID == name_id})
    )


def inspect_font(
    path: Path,
    expected: list[str] | None,
    family: str | None,
    failures: list[str],
    expected_version: str | None = None,
) -> tuple[dict, dict]:
    """Return a serializable summary and comparison data for one existing font."""
    local_failures: list[str] = []
    summary: dict = {"file": path.name}
    comparison: dict = {}
    if not path.is_file():
        failures.append(f"Missing font file: {path}")
        summary["ok"] = False
        summary["errors"] = ["File is missing"]
        return summary, comparison

    try:
        with TTFont(path, lazy=False) as font:
            for table in ("name", "head", "hhea", "hmtx", "maxp", "OS/2", "cmap"):
                if table not in font:
                    local_failures.append(f"Required table {table} is missing")
            if local_failures:
                raise ValueError("Missing required font tables")
            if "glyf" not in font and "CFF " not in font and "CFF2" not in font:
                local_failures.append("No supported outline table exists")

            cmap = font.getBestCmap() or {}
            if expected is None:
                expected = [chr(point) for point in sorted(cmap)]
            glyph_set = font.getGlyphSet()
            glyph_order = set(font.getGlyphOrder())
            upm = font["head"].unitsPerEm
            hhea = font["hhea"]
            os2 = font["OS/2"]
            metrics = font["hmtx"].metrics
            if not 16 <= upm <= 16384:
                local_failures.append(f"Invalid unitsPerEm: {upm}")
            if not (0 < hhea.ascent <= upm * 3 and -upm * 2 <= hhea.descent <= 0):
                local_failures.append("Unreasonable horizontal line ascent/descent")
            if hhea.lineGap < 0:
                local_failures.append("Negative horizontal line gap")
            if os2.sTypoAscender <= 0 or os2.sTypoDescender > 0 or os2.sTypoLineGap < 0:
                local_failures.append("Invalid typographic line metrics")
            if os2.usWinAscent <= 0 or os2.usWinDescent < 0:
                local_failures.append("Invalid Windows line metrics")
            if family is not None:
                families = {
                    record.toUnicode()
                    for record in font["name"].names
                    if record.nameID in (1, 16)
                }
                if family not in families:
                    local_failures.append(f"Expected family {family!r}, got {sorted(families)!r}")
                if any("source" in entry.lower() for entry in families):
                    local_failures.append("Derivative family uses the reserved font name 'Source'")
                copyright_text = name_text(font, 0)
                license_text = name_text(font, 13)
                if "adobe" not in copyright_text.lower():
                    local_failures.append("Source Adobe copyright attribution is missing")
                if "open font license" not in license_text.lower() or "1.1" not in license_text:
                    local_failures.append("OFL 1.1 license description is missing")
                if os2.fsType != 0:
                    local_failures.append(f"Embedding restrictions are set: fsType={os2.fsType}")
            version = name_text(font, 5)
            if expected_version is not None and expected_version not in version:
                local_failures.append(f"Expected version {expected_version!r}, got {version!r}")

            missing = [
                character
                for character in expected
                if ord(character) not in cmap
                or cmap[ord(character)] == ".notdef"
                or cmap[ord(character)] not in glyph_order
            ]
            if missing:
                local_failures.append("Missing mapped characters: " + ", ".join(map(label, missing)))

            advances: dict[int, int] = {}
            horizontal_metrics: dict[int, tuple[int, int]] = {}
            outlines: dict[int, str] = {}
            bounds_by_point: dict[int, tuple | None] = {}
            empty: list[str] = []
            clipped: list[str] = []
            bad_advances: list[str] = []
            for character in expected:
                point = ord(character)
                glyph_name = cmap.get(point)
                if glyph_name is None or glyph_name == ".notdef" or glyph_name not in glyph_order:
                    continue
                advance = metrics[glyph_name][0]
                advances[point] = advance
                horizontal_metrics[point] = tuple(metrics[glyph_name])
                if advance < 0 or advance > upm * 3 or (
                    visible(character) and not unicodedata.combining(character) and advance == 0
                ):
                    bad_advances.append(label(character))
                pen = BoundsPen(glyph_set)
                glyph_set[glyph_name].draw(pen)
                bounds_by_point[point] = pen.bounds
                if visible(character) and pen.bounds is None:
                    empty.append(label(character))
                if pen.bounds is not None:
                    _, bottom, _, top = pen.bounds
                    # Two design units tolerate CFF/TrueType rounding at the line edge.
                    if bottom < hhea.descent - 2 or top > hhea.ascent + 2:
                        clipped.append(label(character))
                    elif bottom < -os2.usWinDescent - 2 or top > os2.usWinAscent + 2:
                        clipped.append(label(character) + " (Windows metrics)")
                recording = DecomposingRecordingPen(glyph_set)
                glyph_set[glyph_name].draw(recording)
                outlines[point] = hashlib.sha256(repr(recording.value).encode()).hexdigest()
            if empty:
                local_failures.append("Mapped visible characters have empty outlines: " + ", ".join(empty))
            if clipped:
                local_failures.append("Glyphs exceed horizontal line metrics: " + ", ".join(clipped))
            if bad_advances:
                local_failures.append("Invalid glyph advances: " + ", ".join(bad_advances))

            summary.update(
                {
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "bytes": path.stat().st_size,
                    "family": name_text(font, 1),
                    "version": version,
                    "units_per_em": upm,
                    "glyphs": font["maxp"].numGlyphs,
                    "mapped_characters": len(cmap),
                    "expected_characters": len(expected),
                    "missing_characters": len(missing),
                    "han_characters": sum(is_han(chr(point)) for point in cmap),
                    "line_metrics": {
                        "ascent": hhea.ascent,
                        "descent": hhea.descent,
                        "line_gap": hhea.lineGap,
                        "typo_ascent": os2.sTypoAscender,
                        "typo_descent": os2.sTypoDescender,
                        "typo_line_gap": os2.sTypoLineGap,
                        "win_ascent": os2.usWinAscent,
                        "win_descent": os2.usWinDescent,
                    },
                    "embedding_flags": os2.fsType,
                }
            )
            comparison = {
                "upm": upm,
                "cmap": set(cmap),
                "cmap_mapping": cmap,
                "advances": advances,
                "horizontal_metrics": horizontal_metrics,
                "bounds": bounds_by_point,
                "outlines": outlines,
                "line_metrics": summary["line_metrics"],
                "usable_characters": {
                    point for point in advances
                    if not visible(chr(point)) or bounds_by_point.get(point) is not None
                },
            }
    except Exception as exc:
        local_failures.append(f"Font inspection failed: {type(exc).__name__}: {exc}")
    summary["ok"] = not local_failures
    if local_failures:
        summary["errors"] = local_failures
        failures.extend(f"{path.name}: {problem}" for problem in local_failures)
    return summary, comparison


def ink_diagnostics(previous_path: Path, current_path: Path, characters: str) -> dict:
    """Measure ink area at 128 px; this is a visual diagnostic, not a gate."""
    try:
        from PIL import ImageFont

        def load_font(path: Path):
            # FreeType builds differ in WOFF2 support; supply decoded sfnt bytes.
            stream = io.BytesIO()
            with TTFont(path) as font:
                font.flavor = None
                font.save(stream)
            stream.seek(0)
            return ImageFont.truetype(stream, size=128)

        previous = load_font(previous_path)
        current = load_font(current_path)
        measurements = []
        for character in characters:
            previous_area = sum(bytes(previous.getmask(character, mode="L"))) / 255
            current_area = sum(bytes(current.getmask(character, mode="L"))) / 255
            ratio = current_area / previous_area if previous_area else None
            measurements.append(
                {
                    "character": character,
                    "previous_ink_pixels": round(previous_area, 2),
                    "current_ink_pixels": round(current_area, 2),
                    "ratio": round(ratio, 4) if ratio is not None else None,
                    "within_reference_band": ratio is not None and 0.8 <= ratio <= 1.2,
                }
            )
        return {
            "available": True,
            "font_size_px": 128,
            "method": "Sum of grayscale glyph mask coverage / 255; diagnostics do not replace visual review",
            "reference_band": [0.8, 1.2],
            "hard_failure_gate": False,
            "measurements": measurements,
        }
    except Exception as exc:
        return {
            "available": False,
            "hard_failure_gate": False,
            "reason": f"{type(exc).__name__}: {exc}",
        }


def verify_targeted_refinement(
    project_dir: Path,
    expected: list[str],
    charset: dict,
    comparisons: dict[str, dict[str, dict]],
    failures: list[str],
) -> dict:
    """Check declared expansion and local edits against the real v0.2 fonts."""
    expected_points = {ord(character) for character in expected}
    regression_failures: list[str] = []
    try:
        expansion = charset["expansion"]
        if not isinstance(expansion, dict):
            raise ValueError("expansion must be an object")
        previous_count = expansion["previous_character_count"]
        if type(previous_count) is not int or previous_count < 1:
            raise ValueError("previous_character_count must be a positive integer")

        def character_field(data: dict, key: str) -> str:
            value = data[key]
            if not isinstance(value, str) or len(set(value)) != len(value):
                raise ValueError(f"{key} must be a string with no repeated characters")
            return value

        added_characters = character_field(expansion, "added_characters")
        refinement_characters = character_field(expansion, "refined_existing_characters")
        all_refined_characters = character_field(charset, "refined_characters")
        added_points = set(map(ord, added_characters))
        targets = set(map(ord, refinement_characters))
        all_refined_points = set(map(ord, all_refined_characters))
        if not added_points:
            regression_failures.append("Expansion declares no newly added characters")
        if not (added_points | targets | all_refined_points) <= expected_points:
            regression_failures.append("Expansion/refinement declarations contain characters outside the new character set")
        if added_points & targets:
            regression_failures.append("A newly added character cannot be declared as a refined existing character")
        if not targets <= all_refined_points:
            regression_failures.append("Refined existing characters are missing from cumulative refined_characters")
        if len(expected_points) != previous_count + len(added_points):
            regression_failures.append("New character count does not equal previous_character_count plus declared additions")
    except Exception as exc:
        message = f"Invalid expansion/refinement metadata: {type(exc).__name__}: {exc}"
        failures.append(message)
        return {"available": False, "ok": False, "failures": [message]}

    report = {
        "previous_character_count": previous_count,
        "added_characters": added_characters,
        "added_count": len(added_points),
        "cumulative_refined_characters": all_refined_characters,
        "cumulative_refined_count": len(all_refined_points),
        "expected_changed_characters": refinement_characters,
        "expected_changed_count": len(targets),
        "expected_unchanged_count": previous_count - len(targets),
        "expected_total_characters": len(expected_points),
        "expected_current_version": CURRENT_FONT_VERSION,
        "expected_previous_version": PREVIOUS_FONT_VERSION,
        "comparison_format": "WOFF2 decoded outline recordings and horizontal metrics",
        "variants": {},
    }

    for variant, (_stem, family) in VARIANTS.items():
        previous_path = project_dir / "fonts" / f"AincradUISc-v020-{variant}.woff2"
        current_path = project_dir / "fonts" / f"AincradUISc-{variant}.woff2"
        previous_summary, previous = inspect_font(
            previous_path, None, family, regression_failures,
            expected_version=PREVIOUS_FONT_VERSION,
        )
        current = comparisons.get(variant, {}).get("woff2", {})
        variant_result = {"previous_font": previous_summary, "available": bool(previous and current)}
        report["variants"][variant] = variant_result
        if not previous or not current:
            regression_failures.append(f"{variant}: targeted refinement regression is unavailable")
            continue
        previous_points = previous["cmap"]
        current_points = current["cmap"]
        if len(previous_points) != previous_count:
            regression_failures.append(f"{variant}: previous font character count disagrees with expansion metadata")
        if previous_points != expected_points - added_points:
            regression_failures.append(f"{variant}: declared additions do not match the new character set minus the previous font")
        if current_points != expected_points:
            regression_failures.append(f"{variant}: current cmap does not match the declared new character set")
        if not targets <= previous_points:
            regression_failures.append(f"{variant}: refined_existing_characters includes characters absent from the previous font")
        actual_added_points = current_points - previous_points
        if actual_added_points != added_points:
            regression_failures.append(f"{variant}: actual newly mapped characters differ from declared additions")
        cmap_unchanged = all(
            current["cmap_mapping"].get(point) == glyph
            for point, glyph in previous["cmap_mapping"].items()
        )
        if not cmap_unchanged:
            regression_failures.append(f"{variant}: previous cmap mappings were removed or changed")
        renderable_added = added_points & current["usable_characters"]
        if renderable_added != added_points:
            regression_failures.append(f"{variant}: newly added characters are missing usable mapped glyphs")

        # Do not compare font file hashes: version/name metadata is expected to change.
        shared = previous_points & previous["outlines"].keys() & current["outlines"].keys()
        changed = {point for point in shared if previous["outlines"][point] != current["outlines"][point]}
        unchanged = shared - changed
        unexpected_changes = changed - targets
        unchanged_targets = targets - changed
        advance_changes = {
            point for point in previous_points
            if previous["advances"].get(point) != current["advances"].get(point)
        }
        unrelated_metric_changes = {
            point for point in previous_points - targets
            if previous["horizontal_metrics"].get(point) != current["horizontal_metrics"].get(point)
        }
        line_metrics_unchanged = previous["line_metrics"] == current["line_metrics"]
        upm_unchanged = previous["upm"] == current["upm"]
        if unexpected_changes:
            regression_failures.append(
                f"{variant}: unexpected outline changes: "
                + ", ".join(label(chr(point)) for point in sorted(unexpected_changes))
            )
        if unchanged_targets:
            regression_failures.append(
                f"{variant}: target outlines were not refined: "
                + ", ".join(label(chr(point)) for point in sorted(unchanged_targets))
            )
        if advance_changes:
            regression_failures.append(
                f"{variant}: advance changes: "
                + ", ".join(label(chr(point)) for point in sorted(advance_changes))
            )
        if unrelated_metric_changes:
            regression_failures.append(
                f"{variant}: unrelated horizontal metrics changed: "
                + ", ".join(label(chr(point)) for point in sorted(unrelated_metric_changes))
            )
        if not line_metrics_unchanged or not upm_unchanged:
            regression_failures.append(f"{variant}: vertical line metrics or unitsPerEm changed")
        unreasonable_target_bounds = []
        for character in all_refined_characters:
            point = ord(character)
            bounds = current["bounds"].get(point)
            advance = current["advances"].get(point)
            if bounds is None or advance is None:
                unreasonable_target_bounds.append(character)
                continue
            left, bottom, right, top = bounds
            if (
                right <= left or top <= bottom
                or left < -current["upm"] * 0.1
                or right > advance + current["upm"] * 0.1
            ):
                unreasonable_target_bounds.append(character)
        if unreasonable_target_bounds:
            regression_failures.append(
                f"{variant}: target outlines have unreasonable bounds: "
                + ", ".join(map(label, unreasonable_target_bounds))
            )
        variant_result.update(
            {
                "cmap_unchanged": cmap_unchanged,
                "previous_cmap_preserved": cmap_unchanged,
                "actual_added_characters": "".join(chr(point) for point in sorted(actual_added_points)),
                "actual_added_count": len(actual_added_points),
                "added_usable_glyph_count": len(renderable_added),
                "compared_characters": len(shared),
                "changed_count": len(changed),
                "changed_characters": (
                    "".join(character for character in refinement_characters if ord(character) in changed)
                    + "".join(chr(point) for point in sorted(unexpected_changes))
                ),
                "unchanged_count": len(unchanged),
                "unexpected_changes": "".join(chr(point) for point in sorted(unexpected_changes)),
                "unchanged_target_characters": "".join(
                    character for character in refinement_characters if ord(character) in unchanged_targets
                ),
                "advance_changes": "".join(chr(point) for point in sorted(advance_changes)),
                "unrelated_horizontal_metric_changes": "".join(chr(point) for point in sorted(unrelated_metric_changes)),
                "line_metrics_unchanged": line_metrics_unchanged,
                "units_per_em_unchanged": upm_unchanged,
                "unreasonable_target_bounds": "".join(unreasonable_target_bounds),
                "target_bounds": {
                    character: {
                        "previous": previous["bounds"].get(ord(character)),
                        "current": current["bounds"].get(ord(character)),
                    }
                    for character in refinement_characters
                },
                "ink_diagnostics": ink_diagnostics(previous_path, current_path, refinement_characters),
            }
        )
    report["available"] = all(item.get("available", False) for item in report["variants"].values())
    report["ok"] = not regression_failures
    report["failures"] = regression_failures
    failures.extend(regression_failures)
    return report


def verify_vocabulary_coverage(
    project_dir: Path,
    expected: list[str],
    comparisons: dict[str, dict[str, dict]],
    failures: list[str],
) -> dict:
    """Check each declared UI phrase against usable glyphs, without fallback."""
    path = project_dir / "data" / "ui-vocabulary.json"
    try:
        corpus = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(corpus.get("version"), str) or not corpus["version"]:
            raise ValueError("version must be a nonempty string")
        categories = corpus["categories"]
        if not isinstance(categories, list) or not categories:
            raise ValueError("categories must be a nonempty list")
        ids = set()
        for category in categories:
            if not isinstance(category, dict):
                raise ValueError("each category must be an object")
            category_id = category["id"]
            if not isinstance(category_id, str) or not category_id or category_id in ids:
                raise ValueError("category ids must be distinct nonempty strings")
            ids.add(category_id)
            if not isinstance(category.get("title"), str) or not category["title"]:
                raise ValueError(f"category {category_id}: title must be a nonempty string")
            phrases = category["phrases"]
            if not isinstance(phrases, list) or not phrases or any(
                not isinstance(phrase, str) or not phrase for phrase in phrases
            ):
                raise ValueError(f"category {category_id}: phrases must be nonempty strings")
    except Exception as exc:
        message = f"Cannot inspect UI vocabulary {path}: {type(exc).__name__}: {exc}"
        failures.append(message)
        return {"available": False, "ok": False, "failures": [message]}

    all_phrases = [phrase for category in categories for phrase in category["phrases"]]
    all_text = "".join(all_phrases)
    ordered_characters = "".join(dict.fromkeys(all_text))
    expected_characters = set(expected)
    undeclared = "".join(character for character in ordered_characters if character not in expected_characters)
    coverage_failures = []
    if undeclared:
        coverage_failures.append("Vocabulary characters are absent from the declared charset: " + ", ".join(map(label, undeclared)))
    report = {
        "available": True,
        "file": "data/ui-vocabulary.json",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "version": corpus["version"],
        "method": "Every phrase character, including spaces and Chinese punctuation, must map to a usable glyph in the actual variant WOFF2; font fallback is excluded",
        "category_count": len(categories),
        "phrase_count": len(all_phrases),
        "character_occurrences": len(all_text),
        "unique_character_count": len(ordered_characters),
        "declared_charset_missing_characters": undeclared,
        "variants": {},
        "categories": [],
    }

    def coverage(phrases: list[str], usable: set[int]) -> dict:
        text = "".join(phrases)
        characters = "".join(dict.fromkeys(text))
        missing = "".join(character for character in characters if ord(character) not in usable)
        missing_phrases = [
            {
                "phrase": phrase,
                "missing_characters": "".join(dict.fromkeys(
                    character for character in phrase if ord(character) not in usable
                )),
            }
            for phrase in phrases if any(ord(character) not in usable for character in phrase)
        ]
        covered_occurrences = sum(ord(character) in usable for character in text)
        return {
            "phrase_count": len(phrases),
            "covered_phrase_count": len(phrases) - len(missing_phrases),
            "phrase_coverage_percent": round(100 * (len(phrases) - len(missing_phrases)) / len(phrases), 4),
            "unique_character_count": len(characters),
            "covered_unique_character_count": len(characters) - len(missing),
            "unique_character_coverage_percent": round(100 * (len(characters) - len(missing)) / len(characters), 4),
            "character_occurrences": len(text),
            "covered_character_occurrences": covered_occurrences,
            "character_occurrence_coverage_percent": round(100 * covered_occurrences / len(text), 4),
            "missing_characters": missing,
            "missing_phrases": missing_phrases,
        }

    for variant in VARIANTS:
        current = comparisons.get(variant, {}).get("woff2", {})
        usable = current.get("usable_characters", set())
        totals = coverage(all_phrases, usable)
        totals["font_available"] = bool(current)
        report["variants"][variant] = totals
        if totals["missing_characters"]:
            coverage_failures.append(
                f"{variant}: UI vocabulary has {len(totals['missing_phrases'])} phrases with missing glyphs: "
                + ", ".join(map(label, totals["missing_characters"]))
            )
    for category in categories:
        report["categories"].append({
            "id": category["id"],
            "title": category["title"],
            "variants": {
                variant: coverage(
                    category["phrases"],
                    comparisons.get(variant, {}).get("woff2", {}).get("usable_characters", set()),
                )
                for variant in VARIANTS
            },
        })
    report["failures"] = coverage_failures
    report["ok"] = not coverage_failures
    failures.extend(coverage_failures)
    return report


def verify_basis_coverage(
    expected: list[str],
    charset: dict,
    comparisons: dict[str, dict[str, dict]],
    failures: list[str],
) -> dict:
    """Verify the reproducible common-Han coding region against real glyphs.

    Enumerate Unicode Han and use the codec's inverse mapping. This checks the
    intended coding region independently of the builder's byte-decoding loop.
    It does not assert complete coverage of GB2312 or arbitrary Chinese text.
    """
    required = set()
    for point in range(0x4E00, 0xA000):
        try:
            encoded = chr(point).encode("gb2312")
        except UnicodeEncodeError:
            continue
        if len(encoded) == 2 and 0xB0 <= encoded[0] <= 0xD7 and 0xA1 <= encoded[1] <= 0xFE:
            required.add(point)
    basis_failures = []
    if len(required) != 3755:
        basis_failures.append(f"Unexpected Python gb2312 common-Han coding region size: {len(required)}")
    basis = charset.get("basis")
    if not isinstance(basis, dict) or basis.get("basic_common_han_count") != len(required):
        basis_failures.append("charset.basis.basic_common_han_count does not match the actual codec region")
    undeclared = required - set(map(ord, expected))
    if undeclared:
        basis_failures.append("Basic common-Han coding region is missing from the declared charset")
    report = {
        "available": True,
        "method": "Enumerate Unicode U+4E00..U+9FFF and encode with Python gb2312; select two-byte codes with lead B0..D7 and trail A1..FE; verify every resulting character against real usable glyphs",
        "coverage_scope": "This selected common-Han coding region only; not complete GB2312, arbitrary Chinese prose, or all names",
        "required_character_count": len(required),
        "declared_charset_missing_characters": "".join(chr(point) for point in sorted(undeclared)),
        "variants": {},
    }
    for variant in VARIANTS:
        formats = {}
        report["variants"][variant] = formats
        for extension in FORMATS:
            current = comparisons.get(variant, {}).get(extension, {})
            missing = required - current.get("usable_characters", set())
            formats[extension] = {
                "font_available": bool(current),
                "required_character_count": len(required),
                "covered_character_count": len(required) - len(missing),
                "coverage_percent": round(100 * (len(required) - len(missing)) / len(required), 4),
                "missing_characters": "".join(chr(point) for point in sorted(missing)),
            }
            if missing:
                basis_failures.append(f"{variant} {extension}: {len(missing)} basic common-Han characters lack usable glyphs")
    report["failures"] = basis_failures
    report["ok"] = not basis_failures
    failures.extend(basis_failures)
    return report


def baseline_source_scope(
    project_dir: Path,
    expected: list[str],
    charset: dict,
    comparisons: dict[str, dict[str, dict]],
    failures: list[str],
) -> tuple[list[str], dict]:
    """Exclude only an explicitly declared, hash-verified original symbol set."""
    manifest_relative = "data/symbols-v030.json"
    manifest_path = project_dir / manifest_relative
    scope = {
        "description": "The Source Han comparison font covers genuine source glyphs only. Declared original symbols are excluded solely from this comparison font; every final OTF, TTF and WOFF2 is still checked against the full charset.",
        "total_character_count": len(expected),
        "expected_baseline_character_count": len(expected),
        "excluded_characters": "",
        "excluded_count": 0,
        "custom_symbols_declared": False,
        "provenance_verified": False,
        "ok": True,
        "failures": [],
    }
    try:
        provenance = json.loads((project_dir / "data" / "provenance.json").read_text(encoding="utf-8-sig"))
        if not isinstance(provenance, dict):
            raise ValueError("Provenance must be an object")
        declaration = provenance.get("custom_symbols")
        if declaration is None:
            if manifest_path.is_file():
                raise ValueError("Symbol manifest exists without provenance.custom_symbols; no baseline exclusion is authorized")
            return expected, scope
        scope["custom_symbols_declared"] = True
        if not isinstance(declaration, dict) or declaration.get("file") != manifest_relative:
            raise ValueError("custom_symbols must declare the exact data/symbols-v030.json manifest")
        payload = manifest_path.read_bytes()
        actual_sha256 = hashlib.sha256(payload).hexdigest()
        if declaration.get("sha256") != actual_sha256:
            raise ValueError("custom_symbols manifest SHA256 does not match provenance")
        manifest = json.loads(payload.decode("utf-8-sig"))
        if not isinstance(manifest, dict):
            raise ValueError("Symbol manifest must be an object")
        if manifest.get("version") != charset.get("version"):
            raise ValueError("Symbol manifest and charset versions differ")
        if type(manifest.get("upm")) is not int or manifest["upm"] != 1000:
            raise ValueError("Symbol manifest must explicitly use 1000 UPM")
        if manifest.get("license") != "SIL Open Font License 1.1":
            raise ValueError("Original symbol manifest is missing the declared OFL 1.1 license")
        if not isinstance(manifest.get("origin"), str) or not manifest["origin"].startswith("Original geometric outlines"):
            raise ValueError("Symbol manifest must explicitly identify original geometric outlines")
        glyphs = manifest.get("glyphs")
        if not isinstance(glyphs, dict) or not glyphs:
            raise ValueError("Symbol manifest glyphs must be a nonempty dictionary")
        if any(
            len(character) != 1 or not visible(character)
            or not isinstance(plan, dict) or not plan
            for character, plan in glyphs.items()
        ):
            raise ValueError("Each symbol must be a single visible character with a nonempty glyph plan")
        additional = declaration.get("additional_manifests", [])
        hexagram_relative = "data/hexagram-outlines-v030.json"
        if not isinstance(additional, list) or len(additional) > 1:
            raise ValueError("Invalid additional original-symbol manifests")
        if (project_dir / hexagram_relative).exists() and not additional:
            raise ValueError("Hexagram outline manifest exists without a hash-verified declaration")
        extra_records = []
        for item in additional:
            if not isinstance(item, dict) or item.get("file") != hexagram_relative:
                raise ValueError("Only the explicit hexagram outline manifest is allowed")
            extra_payload = (project_dir / hexagram_relative).read_bytes()
            extra_sha = hashlib.sha256(extra_payload).hexdigest()
            if item.get("sha256") != extra_sha or item.get("count") != 64:
                raise ValueError("Hexagram manifest hash or count differs from provenance")
            extra = json.loads(extra_payload.decode("utf-8-sig"))
            if (extra.get("version") != charset.get("version") or extra.get("upm") != 1000
                    or extra.get("license") != "SIL Open Font License 1.1"
                    or not str(extra.get("origin", "")).startswith("Original geometric outlines")):
                raise ValueError("Hexagram manifest lacks matching version, UPM or original OFL provenance")
            extra_glyphs = extra.get("glyphs")
            if (not isinstance(extra_glyphs, dict) or set(extra_glyphs) != {chr(p) for p in range(0x4DC0, 0x4E00)}
                    or set(glyphs) & set(extra_glyphs)
                    or any(not isinstance(plan, dict) or not plan for plan in extra_glyphs.values())):
                raise ValueError("Hexagram glyphs must be exactly the 64 unique Unicode hexagrams")
            glyphs.update(extra_glyphs)
            extra_records.append({"file": hexagram_relative, "sha256": extra_sha, "count": 64})
        excluded = set(glyphs)
        if not excluded <= set(expected):
            raise ValueError("Symbol manifest contains characters outside the full charset")
        for field in ("characters", "baseline_excluded_characters"):
            characters = declaration.get(field)
            if not isinstance(characters, str) or len(characters) != len(set(characters)) or set(characters) != excluded:
                raise ValueError(f"custom_symbols.{field} does not exactly match the manifest glyph set")
        if type(declaration.get("count")) is not int or declaration["count"] != len(excluded):
            raise ValueError("custom_symbols.count does not match the manifest glyph set")
        # Keep the historical78-symbol declaration intact. WAO adds exactly
        # eight independently drawn glyphs; its other16 symbols are genuine
        # Source Han outlines and must remain in the source comparison font.
        wao_relative = "data/wao-symbols-v030.json"
        wao_extension_relative = "data/wao-symbol-extension.json"
        wao_declaration = provenance.get("wao_symbols")
        wao_record = None
        if wao_declaration is None:
            if (project_dir / wao_relative).is_file() or (project_dir / wao_extension_relative).is_file():
                raise ValueError("WAO manifests exist without a hash-verified provenance.wao_symbols declaration")
        else:
            if not isinstance(wao_declaration, dict):
                raise ValueError("wao_symbols must be an object")
            if (wao_declaration.get("file") != wao_relative
                    or wao_declaration.get("extension_file") != wao_extension_relative):
                raise ValueError("wao_symbols must name the exact WAO outline and extension manifests")
            wao_payload = (project_dir / wao_relative).read_bytes()
            wao_extension_payload = (project_dir / wao_extension_relative).read_bytes()
            wao_sha = hashlib.sha256(wao_payload).hexdigest()
            wao_extension_sha = hashlib.sha256(wao_extension_payload).hexdigest()
            if (wao_declaration.get("sha256") != wao_sha
                    or wao_declaration.get("extension_sha256") != wao_extension_sha):
                raise ValueError("WAO outline or extension hash differs from provenance")
            wao = json.loads(wao_payload.decode("utf-8-sig"))
            wao_extension = json.loads(wao_extension_payload.decode("utf-8-sig"))
            requested_wao = set("◆◇●■□▲▼▶◀‹«»─│┌┐└┘‥⟨⟩※†‖")
            original_wao = set("─│┌┐└┘⟨⟩")
            source_wao = requested_wao - original_wao
            if (wao.get("version") != charset.get("version")
                    or wao_extension.get("version") != charset.get("version") or wao.get("upm") != 1000
                    or wao.get("license") != "SIL Open Font License 1.1"
                    or wao_declaration.get("upm") != 1000
                    or wao_declaration.get("license") != "SIL Open Font License 1.1"):
                raise ValueError("WAO outline declaration lacks matching version, UPM or OFL license")
            for field, points in (("characters", requested_wao),
                                  ("original_characters", original_wao),
                                  ("source_characters", source_wao)):
                for container in (wao_declaration, wao_extension):
                    text = container.get(field)
                    if not isinstance(text, str) or len(text) != len(points) or set(text) != points:
                        raise ValueError(f"WAO {field} does not match the exact requested origin group")
            wao_glyphs = wao.get("glyphs")
            if not isinstance(wao_glyphs, dict) or set(wao_glyphs) != requested_wao:
                raise ValueError("WAO outline manifest must contain exactly24 requested glyphs")
            for character, plan in wao_glyphs.items():
                origin = "original-geometry" if character in original_wao else "source-derived"
                if not isinstance(plan, dict) or plan.get("origin") != origin:
                    raise ValueError("WAO glyph origin differs from the explicit8/16 classification")
                variants = plan.get("variants")
                if (not isinstance(variants, dict) or set(variants) != set(VARIANTS)
                        or any(not isinstance(variants[style], dict)
                               or not variants[style].get("outline")
                               or type(variants[style].get("advance")) is not int
                               or variants[style]["advance"] <= 0 for style in VARIANTS)):
                    raise ValueError("WAO glyph lacks both final-unit outline and advance plans")
            if not requested_wao <= set(expected) or requested_wao & excluded:
                raise ValueError("WAO symbols overlap the historical originals or fall outside the charset")
            excluded.update(original_wao)
            wao_record = {"file": wao_relative, "sha256": wao_sha,
                          "extension_file": wao_extension_relative, "extension_sha256": wao_extension_sha,
                          "original_characters": "".join(sorted(original_wao, key=ord)),
                          "original_count": 8, "source_character_count": 16}
        for variant in VARIANTS:
            for extension in FORMATS:
                font_data = comparisons.get(variant, {}).get(extension, {})
                if font_data.get("upm") != manifest["upm"]:
                    raise ValueError(f"{variant} {extension}: font UPM differs from the symbol manifest")
        baseline_expected = [character for character in expected if character not in excluded]
        scope.update({
            "expected_baseline_character_count": len(baseline_expected),
            "excluded_characters": "".join(sorted(excluded, key=ord)),
            "excluded_count": len(excluded),
            "provenance_verified": True,
            "manifest": {
                "file": manifest_relative,
                "sha256": actual_sha256,
                "version": manifest["version"],
                "upm": manifest["upm"],
                "origin": manifest["origin"],
                "license": manifest["license"],
            },
            "additional_manifests": extra_records,
        })
        if wao_record is not None:
            scope["wao_manifest"] = wao_record
        return baseline_expected, scope
    except (OSError, ValueError, TypeError, KeyError) as exc:
        message = f"Invalid baseline source scope: {type(exc).__name__}: {exc}"
        scope["ok"] = False
        scope["failures"].append(message)
        failures.append(message)
        # Fail closed: malformed or undeclared exclusions never reduce coverage.
        return expected, scope


def verify_tabular_digits(comparisons: dict[str, dict[str, dict]], failures: list[str]) -> dict:
    digits = "0123456789"
    digit_failures = []
    report = {
        "digits": digits,
        "description": "All ten digits must share one positive advance within each font. Different variants may have different column widths.",
        "variants": {},
    }
    for variant in VARIANTS:
        entries = {}
        advances_for_variant = []
        for extension in FORMATS:
            data = comparisons.get(variant, {}).get(extension, {})
            metrics = data.get("advances", {})
            usable = data.get("usable_characters", set())
            missing = "".join(character for character in digits if ord(character) not in metrics or ord(character) not in usable)
            by_digit = {character: metrics.get(ord(character)) for character in digits}
            unique = sorted({value for value in by_digit.values() if value is not None})
            tabular = not missing and len(unique) == 1 and unique[0] > 0
            entries[extension] = {
                "units_per_em": data.get("upm"),
                "advances_by_digit": by_digit,
                "unique_advances": unique,
                "missing_digits": missing,
                "tabular": tabular,
            }
            if not tabular:
                digit_failures.append(f"{variant} {extension}: digits lack ten usable glyphs with one positive advance")
            else:
                advances_for_variant.append(unique[0])
        consistent = len(advances_for_variant) == len(FORMATS) and len(set(advances_for_variant)) == 1
        if not consistent:
            digit_failures.append(f"{variant}: digit column width is not consistent across formats")
        report["variants"][variant] = {"formats": entries, "consistent_across_formats": consistent}
    report["failures"] = digit_failures
    report["ok"] = not digit_failures
    failures.extend(digit_failures)
    return report


def verify(project_dir: Path) -> dict:
    failures: list[str] = []
    result: dict = {"project_dir": str(project_dir.resolve()), "variants": {}, "failures": failures}
    charset_path = project_dir / "data" / "charset.json"
    try:
        charset = json.loads(charset_path.read_text(encoding="utf-8-sig"))
        raw_characters = charset["characters"]
        if not isinstance(raw_characters, str) or not raw_characters:
            raise ValueError("characters must be a nonempty string")
        expected = list(dict.fromkeys(raw_characters))
        if len(expected) != len(raw_characters):
            failures.append("characters contains repeated codepoints")
        declared_han = charset.get("han_characters")
        if declared_han is not None and (
            not isinstance(declared_han, str)
            or set(declared_han) != {c for c in expected if is_han(c)}
        ):
            failures.append("Declared han_characters does not match the Han characters in characters")
        if not any(is_han(c) for c in expected):
            failures.append("The character set contains no Han characters")
        if "character_count" in charset and charset["character_count"] != len(expected):
            failures.append("Declared character_count differs from the character set")
        if "han_count" in charset and charset["han_count"] != sum(is_han(c) for c in expected):
            failures.append("Declared han_count differs from the Han character set")
        result["expected_characters"] = len(expected)
        result["expected_han_characters"] = sum(is_han(c) for c in expected)
    except Exception as exc:
        failures.append(f"Cannot read character set {charset_path}: {type(exc).__name__}: {exc}")
        result["ok"] = False
        return result

    comparisons: dict[str, dict[str, dict]] = {}
    for variant, (stem, family) in VARIANTS.items():
        summaries = []
        comparisons[variant] = {}
        for extension in FORMATS:
            summary, data = inspect_font(
                project_dir / "fonts" / f"{stem}.{extension}", expected, family, failures,
                expected_version=CURRENT_FONT_VERSION,
            )
            summaries.append(summary)
            comparisons[variant][extension] = data
        result["variants"][variant] = summaries
        reference = comparisons[variant].get("otf")
        for extension in ("ttf", "woff2"):
            candidate = comparisons[variant].get(extension)
            if not reference or not candidate:
                continue
            for key in ("upm", "cmap", "advances", "line_metrics"):
                if reference[key] != candidate[key]:
                    failures.append(f"{variant} {extension}: {key} differs from OTF")
            for point, bounds in reference["bounds"].items():
                other_bounds = candidate["bounds"].get(point)
                if (bounds is None) != (other_bounds is None) or (
                    bounds is not None
                    and other_bounds is not None
                    and any(abs(left - right) > 3 for left, right in zip(bounds, other_bounds))
                ):
                    failures.append(
                        f"{variant} {extension}: outline bounds differ from OTF for U+{point:04X}"
                    )

    regular = comparisons.get("Regular", {}).get("otf", {}).get("outlines", {})
    display = comparisons.get("Display", {}).get("otf", {}).get("outlines", {})
    changed = sum(
        regular[point] != display.get(point)
        for point in regular if point in display and is_han(chr(point))
    )
    result["han_outlines_different_between_variants"] = changed
    if regular and display and changed == 0:
        failures.append("Regular and Display have identical Han outlines")

    baseline_expected, source_scope = baseline_source_scope(
        project_dir, expected, charset, comparisons, failures
    )
    baseline_summary, baseline_data = inspect_font(
        project_dir / "fonts" / "SourceHanSansSC-Baseline.woff2", baseline_expected, None, failures
    )
    result["baseline"] = baseline_summary
    expected_baseline_points = set(map(ord, baseline_expected))
    actual_baseline_points = baseline_data.get("cmap", set())
    unexpected_baseline = actual_baseline_points - expected_baseline_points
    missing_baseline = expected_baseline_points - actual_baseline_points
    source_scope.update({
        "actual_baseline_character_count": len(actual_baseline_points),
        "unexpected_baseline_characters": "".join(chr(point) for point in sorted(unexpected_baseline)),
        "missing_baseline_characters": "".join(chr(point) for point in sorted(missing_baseline)),
    })
    if unexpected_baseline:
        message = "Source Han comparison cmap contains characters outside its declared source scope"
        source_scope["failures"].append(message)
        failures.append(message)
    source_scope["ok"] = source_scope["ok"] and baseline_summary["ok"] and not unexpected_baseline and not missing_baseline
    result["baseline_source_scope"] = source_scope
    result["targeted_refinement"] = verify_targeted_refinement(
        project_dir, expected, charset, comparisons, failures
    )
    result["vocabulary_coverage"] = verify_vocabulary_coverage(
        project_dir, expected, comparisons, failures
    )
    result["basis_coverage"] = verify_basis_coverage(expected, charset, comparisons, failures)
    result["tabular_digits"] = verify_tabular_digits(comparisons, failures)
    if os.name == "nt":
        import ctypes
        gdi = ctypes.WinDLL("gdi32", use_last_error=True)
        gdi.AddFontResourceExW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
        gdi.AddFontResourceExW.restype = ctypes.c_int
        gdi.RemoveFontResourceExW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
        gdi.RemoveFontResourceExW.restype = ctypes.c_int
        native = []
        for stem, _family in VARIANTS.values():
            for extension in ("otf", "ttf"):
                path = (project_dir / "fonts" / f"{stem}.{extension}").resolve()
                loaded, removed = 0, 0
                try:
                    loaded = gdi.AddFontResourceExW(str(path), 0x30, None)
                finally:
                    if loaded:
                        removed = gdi.RemoveFontResourceExW(str(path), 0x30, None)
                native.append({"file": path.name, "private_faces_loaded": loaded,
                               "released": bool(removed)})
                if loaded < 1 or not removed:
                    failures.append(f"Windows private font load/release failed: {path.name}")
        result["windows_font_engine"] = {
            "method": "GDI private process registration; removed immediately; no persistent installation",
            "fonts": native,
        }
    result["ok"] = not failures
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=(Path(__file__).resolve().parents[1] if
                 (Path(__file__).resolve().parents[1] / "specimen.html").is_file() else
                 Path(__file__).resolve().parents[1] / "design" / "aincrad-ui-sc"),
    )
    parser.add_argument("--report", type=Path, help="Also write the JSON result to this file")
    args = parser.parse_args()
    result = verify(args.project_dir)
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(output)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
