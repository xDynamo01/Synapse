"""Trusted fixed checks for staged UTF-8 deliverables. No candidate is imported."""

import csv
import io
import json
import math
from pathlib import Path
import re
import sys
import tomllib


def require(condition, diagnostic):
    if not condition:
        raise ValueError(diagnostic)


def unique_object(pairs):
    result = dict(pairs)
    require(len(result) == len(pairs), "duplicate JSON key")
    return result


def finite_number(number):
    value = float(number)
    require(math.isfinite(value), "nonfinite JSON number")
    return value


def validate_json(text):
    value = json.loads(text, object_pairs_hook=unique_object, parse_float=finite_number,
                       parse_constant=finite_number)
    require(isinstance(value, (dict, list)), "JSON root must be an object or array")
    return value


def validate_game_level(text):
    level = validate_json(text)
    require(isinstance(level, dict) and set(level) == {"width", "height", "tiles"},
            "tile map requires width, height and tiles")
    width, height, tiles = (level[key] for key in ("width", "height", "tiles"))
    require(all(type(value) is int and 1 <= value <= 64 for value in (width, height)),
            "tile dimensions must be integers from 1 to 64")
    require(isinstance(tiles, list) and len(tiles) == height, "tile map height mismatch")
    for row in tiles:
        require(isinstance(row, list) and len(row) == width, "tile map width mismatch")
        require(all(type(tile) is int and 0 <= tile <= 65535 for tile in row), "invalid tile ID")


def validate_toml(text):
    document = tomllib.loads(text)
    require(bool(document), "empty TOML document")
    return document


PACKAGE_NAME = r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"
RELEASE = r"[0-9]+(?:\.[0-9]+)+"
PACKAGE_PIN = re.compile(rf"({PACKAGE_NAME})==({RELEASE})")


def validate_python_manifest(text):
    project = validate_toml(text).get("project")
    require(isinstance(project, dict), "Python manifest requires a project table")
    name, version = (project.get(key) for key in ("name", "version"))
    require(isinstance(name, str) and re.fullmatch(PACKAGE_NAME, name) is not None,
            "invalid Python project name")
    require(isinstance(version, str) and re.fullmatch(RELEASE, version) is not None,
            "Python project version must be a dotted release")
    dependencies = project.get("dependencies", [])
    require(isinstance(dependencies, list), "project dependencies must be a list")
    seen = set()
    for dependency in dependencies:
        pin = PACKAGE_PIN.fullmatch(dependency) if isinstance(dependency, str) else None
        require(pin is not None, "dependency must use an exact name==version pin")
        normalized = re.sub(r"[._-]+", "-", pin[1]).lower()
        require(normalized not in seen, "duplicate Python dependency")
        seen.add(normalized)


def validate_csv(text):
    rows = csv.reader(io.StringIO(text, newline=""), strict=True)
    header = [cell.strip() for cell in next(rows, [])]
    require(header and all(header) and len(header) == len(set(header)), "invalid CSV header")
    count = 0
    for row in rows:
        require(len(row) == len(header), "CSV row does not match header width")
        count += 1
    require(count > 0, "CSV has no data rows")


def validate_markdown(text):
    fence = None
    titles = 0
    has_body = False
    for line in text.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence is not None:
            if (marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence)
                    and not marker[2].strip()):
                fence = None
            elif line.strip():
                has_body = True
        elif marker:
            fence = marker[1]
        elif re.match(r"^ {0,3}#\s+\S", line):
            titles += 1
        elif line.strip() and not re.match(r"^ {0,3}#{1,6}\s", line):
            has_body = True
    require(fence is None, "unclosed Markdown fence")
    require(titles == 1 and has_body, "Markdown requires one title and body content")


SVG_TAG = re.compile(r"<(/?)([A-Za-z]+)((?:\s+[A-Za-z][A-Za-z0-9-]*\s*=\s*(?:\"[^\"<&]*\"|'[^'<&]*'))*)\s*(/?)>")
SVG_ATTRIBUTE = re.compile(r"([A-Za-z][A-Za-z0-9-]*)\s*=\s*(?:\"([^\"<&]*)\"|'([^'<&]*)')")
SVG_TAGS = frozenset("svg g rect circle ellipse line polyline polygon path text tspan title desc".split())
SVG_ATTRS = frozenset("xmlns viewBox width height id x y x1 x2 y1 y2 cx cy r rx ry points d fill stroke stroke-width opacity fill-opacity stroke-opacity transform font-family font-size text-anchor".split())
SVG_GRAPHICS = SVG_TAGS - {"svg", "g", "title", "desc", "tspan"}


def positive_extent(value):
    if not re.fullmatch(r"[+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:px)?", value):
        return False
    extent = float(value.removesuffix("px"))
    return math.isfinite(extent) and extent > 0


def svg_dimensions(attrs):
    if "viewBox" not in attrs:
        return all(positive_extent(attrs.get(axis, "")) for axis in ("width", "height"))
    parts = re.split(r"[ ,\t\r\n]+", attrs["viewBox"].strip())
    return len(parts) == 4 and all(math.isfinite(float(part)) for part in parts) and all(
        float(part) > 0 for part in parts[2:])


def validate_svg(text):
    # Deliberately restricted to a portable static subset with no URI-bearing
    # attributes, style, DTD, entity declarations or active elements.
    root_seen = False
    graphics_seen = False
    stack = []
    for token in re.findall(r"<[^>]*>|[^<]+|<", text):
        if not token.startswith("<"):
            require(not token.strip() or (stack and stack[-1] in {"text", "tspan", "title", "desc"}),
                    "unexpected SVG text")
            require(not re.search(r"&(?!amp;|lt;|gt;|quot;|apos;)", token), "unsupported SVG entity")
            continue
        match = SVG_TAG.fullmatch(token)
        require(match is not None, "unsupported SVG syntax")
        closing, tag, raw_attributes, self_closing = match.groups()
        require(tag in SVG_TAGS, "unsupported SVG element")
        if closing:
            require(not raw_attributes and not self_closing and stack and stack[-1] == tag,
                    "unbalanced SVG element")
            stack.pop()
            continue
        pairs = [(name, first if first != "" else second)
                 for name, first, second in SVG_ATTRIBUTE.findall(raw_attributes)]
        attrs = dict(pairs)
        require(len(attrs) == len(pairs) and set(attrs) <= SVG_ATTRS, "unsupported SVG attribute")
        require(not any("\\" in value or re.search(r"url\s*\(", value, re.I) for value in attrs.values()),
                "SVG resource references are not allowed")
        if not stack:
            require(not root_seen and tag == "svg" and attrs.get("xmlns") == "http://www.w3.org/2000/svg",
                    "SVG requires one namespaced root")
            require(svg_dimensions(attrs), "SVG requires positive dimensions")
            root_seen = True
        else:
            require(tag != "svg" and "xmlns" not in attrs, "nested SVG namespace")
            graphics_seen |= tag in SVG_GRAPHICS
        if not self_closing:
            stack.append(tag)
    require(root_seen and graphics_seen and not stack, "SVG requires balanced visible graphics")


TIMESTAMP = r"(?:\d{2,}:)?[0-5]\d:[0-5]\d\.\d{3}"
TIMING = re.compile(rf"^({TIMESTAMP})[ \t]+-->[ \t]+({TIMESTAMP})$", re.ASCII)


def milliseconds(value):
    pieces = value.replace(".", ":").split(":")
    return sum(int(part) * unit for part, unit in zip(reversed(pieces), [1, 1000, 60000, 3600000]))


def validate_webvtt(text):
    lines = text.splitlines()
    require(lines and lines[0].strip() == "WEBVTT" and len(lines) > 2 and not lines[1].strip(),
            "WebVTT requires a header and a blank line")
    blocks = re.split(r"\n[ \t]*\n(?:[ \t]*\n)*", "\n".join(lines[2:]).strip())
    previous = 0
    for block in blocks:
        cue = block.splitlines()
        if cue and "-->" not in cue[0]:
            cue = cue[1:]
        require(len(cue) >= 2 and any(line.strip() for line in cue[1:]), "empty WebVTT cue")
        timing = TIMING.fullmatch(cue[0].strip())
        require(timing is not None, "invalid WebVTT timestamp")
        start, end = map(milliseconds, timing.groups())
        require(previous <= start < end, "WebVTT cue times are out of order")
        previous = start


CHECKS = {"json": validate_json, "game_level": validate_game_level, "toml": validate_toml, "python_manifest": validate_python_manifest, "csv": validate_csv,
          "md": validate_markdown, "svg": validate_svg, "vtt": validate_webvtt}


def main():
    check, source = sys.argv[1:]
    try:
        text = Path(source).read_bytes().decode("utf-8-sig")
        require("\0" not in text, "NUL in UTF-8 document")
        CHECKS[check](text)
    except (ValueError, csv.Error, RecursionError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
