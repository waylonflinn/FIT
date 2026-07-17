"""Fence-aware scanning and CommonMark conversion for supported Mintlify MDX."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from markdown_it import MarkdownIt


TagCategory = Literal["structural", "content"]


@dataclass(frozen=True)
class TagSpec:
    """Declarative syntax and rendering policy for one supported component."""

    name: str
    category: TagCategory
    handler: str
    required_attributes: frozenset[str] = frozenset()
    semantic_attributes: frozenset[str] = frozenset()
    presentation_attributes: frozenset[str] = frozenset()
    body_required: bool = False


def _spec(
    name: str,
    category: TagCategory,
    handler: str,
    *,
    required: tuple[str, ...] = (),
    semantic: tuple[str, ...] = (),
    presentation: tuple[str, ...] = (),
    body_required: bool = False,
) -> TagSpec:
    return TagSpec(
        name,
        category,
        handler,
        frozenset(required),
        frozenset(semantic),
        frozenset(presentation),
        body_required,
    )


TAGS: dict[str, TagSpec] = {
    "section": _spec("section", "structural", "heading", required=("title",), semantic=("title",)),
    "CodeGroup": _spec("CodeGroup", "structural", "transparent"),
    "Tabs": _spec("Tabs", "structural", "transparent"),
    "Tab": _spec("Tab", "structural", "heading", required=("title",), semantic=("title",)),
    "AccordionGroup": _spec("AccordionGroup", "structural", "transparent"),
    "Accordion": _spec("Accordion", "structural", "heading", required=("title",), semantic=("title",)),
    "Steps": _spec("Steps", "structural", "steps"),
    "Step": _spec("Step", "structural", "step", required=("title",), semantic=("title",), body_required=True),
    "CardGroup": _spec("CardGroup", "structural", "transparent", presentation=("cols",)),
    "Card": _spec(
        "Card", "structural", "heading", required=("title",), semantic=("title",),
        presentation=("icon", "horizontal"),
    ),
    "Tip": _spec("Tip", "content", "admonition"),
    "Note": _spec("Note", "content", "admonition"),
    "Warning": _spec("Warning", "content", "admonition"),
    "Info": _spec("Info", "content", "admonition"),
    "Danger": _spec("Danger", "content", "admonition"),
    "Frame": _spec("Frame", "content", "transparent"),
    "ResponseField": _spec(
        "ResponseField", "content", "response_field", required=("name", "type"),
        semantic=("name", "type"), body_required=True,
    ),
    "ParamField": _spec(
        "ParamField", "content", "param_field", required=("body", "type"),
        semantic=("body", "type", "required"), body_required=True,
    ),
}


@dataclass(frozen=True)
class SourceSpan:
    start: int
    end: int
    line: int
    column: int


@dataclass
class ComponentNode:
    name: str
    spec: TagSpec
    open_span: SourceSpan
    attributes: dict[str, str | bool]
    self_closing: bool
    indent: int
    close_span: SourceSpan | None = None
    children: list["ComponentNode"] = field(default_factory=list)

    @property
    def end(self) -> int:
        return (self.close_span or self.open_span).end


@dataclass(frozen=True)
class PreprocessDiagnostic:
    message: str
    line: int | None = None
    column: int | None = None

    def __str__(self) -> str:
        if self.line is None:
            return self.message
        return f"line {self.line}, column {self.column}: {self.message}"


class MdxPreprocessError(Exception):
    """Raised when source cannot be converted without risking content loss."""

    def __init__(self, diagnostics: list[PreprocessDiagnostic] | PreprocessDiagnostic | str):
        if isinstance(diagnostics, str):
            diagnostics = [PreprocessDiagnostic(diagnostics)]
        elif isinstance(diagnostics, PreprocessDiagnostic):
            diagnostics = [diagnostics]
        self.diagnostics = diagnostics
        super().__init__("; ".join(str(item) for item in diagnostics))


@dataclass
class ScanResult:
    roots: list[ComponentNode] = field(default_factory=list)
    structural: Counter[str] = field(default_factory=Counter)
    content: Counter[str] = field(default_factory=Counter)
    unknown: Counter[str] = field(default_factory=Counter)
    discarded_attributes: Counter[str] = field(default_factory=Counter)
    diagnostics: list[PreprocessDiagnostic] = field(default_factory=list)


@dataclass
class RenderContext:
    heading_depth: int | None = None
    step_number: int = 0


_TAG_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]*")
_MARKDOWN = MarkdownIt("commonmark")


def _fenced_ranges(text: str) -> list[tuple[int, int]]:
    """Return code-fence ranges, accepting component-relative indentation."""
    ranges: list[tuple[int, int]] = []
    active: tuple[str, int, int] | None = None
    offset = 0
    for line in text.splitlines(keepends=True):
        match = re.match(r"^(?:[ \t]*>[ \t]?)*[ \t]*(`{3,}|~{3,})", line)
        if match:
            marker = match.group(1)
            if active is None:
                active = (marker[0], len(marker), offset)
            elif (
                marker[0] == active[0]
                and len(marker) >= active[1]
                and line[match.end():].strip() == ""
            ):
                ranges.append((active[2], offset + len(line)))
                active = None
        offset += len(line)
    if active is not None:
        ranges.append((active[2], len(text)))
    return ranges


def _code_span_ranges(
    text: str,
    fenced_ranges: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Return CommonMark backtick-code ranges outside fenced code."""
    ranges: list[tuple[int, int]] = []
    region_start = 0
    regions: list[tuple[int, int]] = []
    for start, end in fenced_ranges:
        regions.append((region_start, start))
        region_start = end
    regions.append((region_start, len(text)))

    for start, end in regions:
        i = start
        while i < end:
            if text[i] != "`":
                i += 1
                continue
            opener_end = i + 1
            while opener_end < end and text[opener_end] == "`":
                opener_end += 1
            opener_length = opener_end - i
            j = opener_end
            while j < end:
                if text[j] != "`":
                    j += 1
                    continue
                closer_end = j + 1
                while closer_end < end and text[closer_end] == "`":
                    closer_end += 1
                if closer_end - j == opener_length:
                    ranges.append((i, closer_end))
                    i = closer_end
                    break
                j = closer_end
            else:
                i = opener_end
    return ranges


def _read_tag(text: str, start: int) -> tuple[int, bool, bool, str, str] | None:
    """Read one quote-aware JSX-like tag starting at ``start``."""
    i = start + 1
    closing = i < len(text) and text[i] == "/"
    if closing:
        i += 1
    match = _TAG_NAME_RE.match(text, i)
    if not match:
        return None
    name = match.group(0)
    name_end = match.end()
    quote: str | None = None
    i = name_end
    while i < len(text):
        char = text[i]
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == ">":
            raw_attrs = text[name_end:i]
            self_closing = not closing and raw_attrs.rstrip().endswith("/")
            if self_closing:
                raw_attrs = raw_attrs.rstrip()[:-1]
            return i + 1, closing, self_closing, name, raw_attrs
        i += 1
    return None


def _parse_attributes(raw: str, name: str, span: SourceSpan) -> tuple[dict[str, str | bool], list[PreprocessDiagnostic]]:
    attrs: dict[str, str | bool] = {}
    diagnostics: list[PreprocessDiagnostic] = []
    i = 0
    while i < len(raw):
        while i < len(raw) and raw[i].isspace():
            i += 1
        if i == len(raw):
            break
        if raw.startswith("{...", i):
            diagnostics.append(PreprocessDiagnostic("spread attributes are unsupported", span.line, span.column))
            break
        if raw.startswith("{/*", i) or raw[i] == "{":
            diagnostics.append(PreprocessDiagnostic("JSX expressions and comments are unsupported", span.line, span.column))
            break
        match = re.match(r"[A-Za-z_:][A-Za-z0-9_.:-]*", raw[i:])
        if not match:
            diagnostics.append(PreprocessDiagnostic(f"unsupported attribute syntax on <{name}>", span.line, span.column))
            break
        attr = match.group(0)
        i += len(attr)
        while i < len(raw) and raw[i].isspace():
            i += 1
        value: str | bool = True
        if i < len(raw) and raw[i] == "=":
            i += 1
            while i < len(raw) and raw[i].isspace():
                i += 1
            if i >= len(raw) or raw[i] not in "\"'":
                diagnostics.append(PreprocessDiagnostic(f"JSX expression or unquoted value for attribute '{attr}' is unsupported", span.line, span.column))
                break
            quote = raw[i]
            end = raw.find(quote, i + 1)
            if end < 0:
                diagnostics.append(PreprocessDiagnostic(f"unterminated value for attribute '{attr}'", span.line, span.column))
                break
            value = raw[i + 1:end]
            i = end + 1
        if attr in attrs:
            diagnostics.append(PreprocessDiagnostic(f"duplicate attribute '{attr}' on <{name}>", span.line, span.column))
        attrs[attr] = value
    return attrs, diagnostics


def _is_unknown_jsx(
    text: str,
    end: int,
    name: str,
    raw_attrs: str,
    self_closing: bool,
) -> bool:
    """Distinguish JSX evidence from ambiguous all-caps prose placeholders."""
    if not name[0].isupper():
        return False
    if self_closing or raw_attrs.strip() or any(char.islower() for char in name):
        return True
    closing_tag = re.compile(rf"</{re.escape(name)}\s*>")
    return closing_tag.search(text, end) is not None


def _scan(text: str) -> ScanResult:
    result = ScanResult()
    fences = _fenced_ranges(text)
    ignored_ranges = sorted(fences + _code_span_ranges(text, fences))
    ignored_index = 0
    stack: list[ComponentNode] = []
    i = 0
    line = 1
    line_start = 0

    def advance(end: int) -> None:
        nonlocal i, line, line_start
        fragment = text[i:end]
        newline_count = fragment.count("\n")
        if newline_count:
            line += newline_count
            line_start = i + fragment.rfind("\n") + 1
        i = end

    while i < len(text):
        while ignored_index < len(ignored_ranges) and i >= ignored_ranges[ignored_index][1]:
            ignored_index += 1
        if (
            ignored_index < len(ignored_ranges)
            and ignored_ranges[ignored_index][0] <= i < ignored_ranges[ignored_index][1]
        ):
            advance(ignored_ranges[ignored_index][1])
            continue
        if text[i] != "<":
            advance(i + 1)
            continue
        parsed = _read_tag(text, i)
        if parsed is None:
            advance(i + 1)
            continue
        end, closing, self_closing, name, raw_attrs = parsed
        spec = TAGS.get(name)
        if spec is None:
            if (
                not closing
                and _is_unknown_jsx(text, end, name, raw_attrs, self_closing)
            ):
                result.unknown[name] += 1
            advance(end)
            continue
        column = i - line_start + 1
        prefix = text[line_start:i]
        indent = len(prefix) if prefix.strip() == "" else -1
        span = SourceSpan(i, end, line, column)
        if indent < 0 and not closing:
            result.diagnostics.append(PreprocessDiagnostic(f"mid-line <{name}> component is unsupported", line, column))
        if closing:
            if not stack:
                result.diagnostics.append(PreprocessDiagnostic(f"unexpected closing </{name}> tag", line, column))
            elif stack[-1].name != name:
                result.diagnostics.append(PreprocessDiagnostic(f"tag mismatch: expected </{stack[-1].name}> but found </{name}>", line, column))
            else:
                stack.pop().close_span = span
            advance(end)
            continue
        attrs, attr_diagnostics = _parse_attributes(raw_attrs, name, span)
        result.diagnostics.extend(attr_diagnostics)
        allowed = spec.semantic_attributes | spec.presentation_attributes
        for attr in attrs.keys() - allowed:
            result.diagnostics.append(PreprocessDiagnostic(f"unsupported attribute '{attr}' on <{name}>", line, column))
        result.discarded_attributes.update(attrs.keys() & spec.presentation_attributes)
        for attr in spec.required_attributes - attrs.keys():
            result.diagnostics.append(PreprocessDiagnostic(f"required attribute '{attr}' missing from <{name}>", line, column))
        node = ComponentNode(name, spec, span, attrs, self_closing, max(indent, 0))
        (result.structural if spec.category == "structural" else result.content)[name] += 1
        if stack:
            stack[-1].children.append(node)
        else:
            result.roots.append(node)
        if self_closing:
            if spec.body_required:
                result.diagnostics.append(PreprocessDiagnostic(f"self-closing <{name}> requires body content", line, column))
            elif spec.handler == "heading":
                result.diagnostics.append(PreprocessDiagnostic(f"self-closing <{name}> heading wrapper is unsupported", line, column))
        else:
            stack.append(node)
        advance(end)
    for node in stack:
        result.diagnostics.append(PreprocessDiagnostic(f"unclosed <{node.name}> tag", node.open_span.line, node.open_span.column))
    return result


def _extent_end(text: str, node: ComponentNode) -> int:
    end = node.end
    line_end = text.find("\n", end)
    if line_end >= 0 and text[end:line_end].strip() == "":
        return line_end + 1
    return end


def _normalize_indented_roots(text: str, scan: ScanResult) -> str:
    replacements: list[tuple[int, int, str]] = []
    for node in scan.roots:
        if node.indent < 4:
            continue
        if node.close_span is not None and node.close_span.column - 1 != node.indent:
            raise MdxPreprocessError(PreprocessDiagnostic(f"inconsistent indentation for <{node.name}>", node.close_span.line, node.close_span.column))
        line_start = text.rfind("\n", 0, node.open_span.start) + 1
        extent_end = _extent_end(text, node)
        extent = text[line_start:extent_end]
        prefix = " " * node.indent
        normalized: list[str] = []
        for line in extent.splitlines(keepends=True):
            if line.strip() and not line.startswith(prefix):
                raise MdxPreprocessError(PreprocessDiagnostic(f"inconsistent indentation inside <{node.name}>", node.open_span.line, node.open_span.column))
            normalized.append(line[node.indent:] if line.startswith(prefix) else line)
        replacements.append((line_start, extent_end, "".join(normalized)))
    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    return text


def _without_opening_newline(body: str) -> str:
    if body.startswith("\r\n"):
        return body[2:]
    return body[1:] if body.startswith("\n") else body


def _body_lines(body: str) -> list[str]:
    return body.rstrip("\r\n").splitlines() if body else []


def _ensure_newline(text: str) -> str:
    return text if not text or text.endswith("\n") else text + "\n"


def _update_heading(context: RenderContext, text: str) -> None:
    headings = [token for token in _MARKDOWN.parse(text) if token.type == "heading_open"]
    if headings:
        context.heading_depth = int(headings[-1].tag[1:])


def _render_region(text: str, start: int, end: int, children: list[ComponentNode], context: RenderContext) -> str:
    output: list[str] = []
    cursor = start
    for child in children:
        plain = text[cursor:child.open_span.start]
        output.append(plain)
        _update_heading(context, plain)
        output.append(_render_node(text, child, context))
        cursor = _extent_end(text, child)
    plain = text[cursor:end]
    output.append(plain)
    _update_heading(context, plain)
    return "".join(output)


def _render_node(text: str, node: ComponentNode, context: RenderContext) -> str:
    if node.self_closing:
        body = ""
    else:
        assert node.close_span is not None
        handler = node.spec.handler
        old_depth = context.heading_depth
        old_step = context.step_number
        synthetic_depth: int | None = None
        if handler == "heading":
            synthetic_depth = 2 if old_depth is None else old_depth + 1
            context.heading_depth = min(synthetic_depth, 6)
        elif handler == "steps":
            context.step_number = 0
        body = _render_region(text, node.open_span.end, node.close_span.start, node.children, context)
        if handler == "heading":
            context.heading_depth = old_depth
        elif handler == "steps":
            context.step_number = old_step
    body = _without_opening_newline(body)
    handler = node.spec.handler
    if handler == "transparent":
        return _ensure_newline(body)
    if handler == "heading":
        title = str(node.attributes["title"])
        depth = 2 if context.heading_depth is None else context.heading_depth + 1
        # The containing depth was restored above; use it to render the title.
        heading = f"{'#' * depth} {title}" if depth <= 6 else f"**{title}**"
        return f"{heading}\n\n{_ensure_newline(body)}"
    if handler == "admonition":
        lines = _body_lines(body)
        quoted = "\n".join(">" if line == "" else f"> {line}" for line in lines)
        suffix = f"\n{quoted}" if quoted else ""
        return f"> **{node.name}:**\n>{suffix}\n"
    if handler == "steps":
        return body.rstrip("\n") + "\n" if body else ""
    if handler == "step":
        context.step_number += 1
        title = node.attributes["title"]
        lines = _body_lines(body)
        indented = "\n".join("" if line == "" else f"   {line}" for line in lines)
        return f"{context.step_number}. **{title}**\n\n{indented}\n\n"
    if handler in {"param_field", "response_field"}:
        label_name = "body" if handler == "param_field" else "name"
        metadata = f"`{node.attributes['type']}`"
        if handler == "param_field" and "required" in node.attributes:
            metadata += ", required"
        lines = _body_lines(body)
        indented = "\n".join("" if line == "" else f"  {line}" for line in lines)
        return f"- **{node.attributes[label_name]}** ({metadata})\n\n{indented}\n"
    raise AssertionError(f"unknown MDX handler: {handler}")


class MdxDocument:
    """Scanned MDX source with a pure, validated preprocessing operation."""

    def __init__(self, text: str):
        self.text = text
        self._scan = _scan(text)
        self.structural_tags = dict(sorted(self._scan.structural.items()))
        self.content_wrapper_tags = dict(sorted(self._scan.content.items()))
        self.unknown_components = dict(sorted(self._scan.unknown.items()))
        self.discarded_attributes: dict[str, int] = {}
        self.summary: dict[str, int] = {}

    @property
    def has_structural_tags(self) -> bool:
        return bool(self.structural_tags)

    @property
    def has_content_wrappers(self) -> bool:
        return bool(self.content_wrapper_tags)

    @property
    def has_unknown_components(self) -> bool:
        return bool(self.unknown_components)

    def format_findings(self) -> str:
        sections: list[str] = []
        for title, findings in (
            ("Structural", self.structural_tags),
            ("Content wrappers", self.content_wrapper_tags),
            ("Unknown JSX", self.unknown_components),
        ):
            if findings:
                sections.append(title + ":\n" + "\n".join(f"  {name}: {count}" for name, count in findings.items()))
        return "\n".join(sections)

    def preprocess(self) -> str:
        diagnostics = list(self._scan.diagnostics)
        diagnostics.extend(
            PreprocessDiagnostic(f"unknown JSX component <{name}>")
            for name in self.unknown_components
        )
        if diagnostics:
            raise MdxPreprocessError(diagnostics)
        normalized = _normalize_indented_roots(self.text, self._scan)
        scan = _scan(normalized)
        if scan.diagnostics:
            raise MdxPreprocessError(scan.diagnostics)
        transformed = _render_region(normalized, 0, len(normalized), scan.roots, RenderContext())
        postcondition = _scan(transformed)
        if postcondition.structural or postcondition.content or postcondition.unknown or postcondition.diagnostics:
            details = postcondition.diagnostics or [PreprocessDiagnostic("postcondition failed: JSX component survived preprocessing")]
            raise MdxPreprocessError(details)
        self.summary = dict(sorted((scan.structural + scan.content).items()))
        self.discarded_attributes = dict(sorted(scan.discarded_attributes.items()))
        return transformed
