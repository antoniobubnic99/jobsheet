"""Put real Excel checkboxes back into a workbook openpyxl has just written.

openpyxl cannot emit the Excel 365 native in-cell checkbox: it lives in a part
(`featurePropertyBag`) that openpyxl neither reads nor preserves, so every
`wb.save()` silently strips it. The only way to keep it is to post-process the
finished file as what it actually is -- a zip of XML parts.

Four edits are needed, and all four must land or Excel declares the file corrupt:

1. add `xl/featurePropertyBag/featurePropertyBag.xml`
2. register that part in `[Content_Types].xml`
3. relate it from `xl/_rels/workbook.xml.rels`
4. add a cell style carrying `xfComplement`, and stamp it on the target cells

This is undocumented, was worked out by unzipping a workbook Excel itself had
saved, and is the single most fragile thing in the project -- hence the tests.

Cells must already hold real booleans. A checkbox over a string renders as an
empty box that silently refuses to tick.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from openpyxl.utils import get_column_letter

__all__ = ["CheckboxError", "apply_native_checkboxes"]

FPB_PART = "xl/featurePropertyBag/featurePropertyBag.xml"
FPB_NS = "http://schemas.microsoft.com/office/spreadsheetml/2022/featurepropertybag"
FPB_REL_TYPE = "http://schemas.microsoft.com/office/2022/11/relationships/FeaturePropertyBag"
FPB_CONTENT_TYPE = "application/vnd.ms-excel.featurepropertybag+xml"

FPB_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
    f'<FeaturePropertyBags xmlns="{FPB_NS}">'
    '<bag type="Checkbox"/>'
    '<bag type="XFControls"><bagId k="CellControl">0</bagId></bag>'
    '<bag type="XFComplement"><bagId k="XFControls">1</bagId></bag>'
    '<bag type="XFComplements" extRef="XFComplementsMapperExtRef">'
    '<a k="MappedFeaturePropertyBags"><bagId>2</bagId></a></bag>'
    "</FeaturePropertyBags>"
)

FPB_OVERRIDE = f'<Override PartName="/{FPB_PART}" ContentType="{FPB_CONTENT_TYPE}"/>'

CHECKBOX_XF = (
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
    '<alignment horizontal="center"/><extLst>'
    '<ext uri="{C7286773-470A-42A8-94C5-96B5CB345126}" '
    f'xmlns:xfpb="{FPB_NS}">'
    '<xfpb:xfComplement i="0"/></ext></extLst></xf>'
)

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

_CELL_TAG = re.compile(r'<c r="([A-Z]+)(\d+)"([^>]*?)(/?)>')
_EXISTING_STYLE = re.compile(r'\s+s="\d+"')
_CELL_XFS_OPEN = re.compile(r'<cellXfs count="(\d+)"\s*>')


class CheckboxError(RuntimeError):
    """The workbook was not shaped the way this rewrite needs it to be."""


def _worksheet_part(parts: dict[str, bytes], sheet_name: str | None) -> str:
    """Locate the XML part backing a sheet, by name.

    The predecessor hard-coded `xl/worksheets/sheet1.xml`, which is right until
    the workbook has more than one sheet or the sheets were created out of order
    -- at which point the checkboxes land on the wrong sheet with no error.
    """
    # S314: these two parts come from a workbook openpyxl has already opened and
    # parsed with the same stdlib parser, so swapping in `defusedxml` here would
    # protect nothing that is not already exposed upstream. Python's ElementTree
    # has no external-entity support, so the residual risk is entity expansion in
    # a file the user chose to open themselves.
    workbook = ElementTree.fromstring(parts["xl/workbook.xml"])  # noqa: S314
    rels = ElementTree.fromstring(parts["xl/_rels/workbook.xml.rels"])  # noqa: S314

    targets = {
        rel.get("Id"): rel.get("Target", "")
        for rel in rels.findall(f"{{{_PKG_REL_NS}}}Relationship")
    }

    sheets = workbook.findall(f"{{{_MAIN_NS}}}sheets/{{{_MAIN_NS}}}sheet")
    if not sheets:
        raise CheckboxError("workbook declares no sheets")

    chosen = None
    for sheet in sheets:
        if sheet_name is None or sheet.get("name") == sheet_name:
            chosen = sheet
            break
    if chosen is None:
        raise CheckboxError(f"no sheet named {sheet_name!r}")

    target = targets.get(chosen.get(f"{{{_REL_NS}}}id", ""), "")
    if not target:
        raise CheckboxError("sheet has no relationship to a worksheet part")

    part = target[1:] if target.startswith("/") else f"xl/{target.lstrip('/')}"
    if part not in parts:
        raise CheckboxError(f"worksheet part missing from the archive: {part}")
    return part


def _add_checkbox_style(styles: str) -> tuple[str, int]:
    """Append the checkbox cell style, returning the updated XML and its index."""
    opening = _CELL_XFS_OPEN.search(styles)
    if not opening:
        raise CheckboxError("styles.xml has no <cellXfs> block")
    count = int(opening.group(1))
    styles = styles.replace(opening.group(0), f'<cellXfs count="{count + 1}">', 1)
    styles = styles.replace("</cellXfs>", CHECKBOX_XF + "</cellXfs>", 1)
    return styles, count


def _stamp_cells(sheet_xml: str, columns: set[str], first_row: int, style: int) -> str:
    """Point the target cells at the checkbox style, dropping any previous one."""

    def replace(found: re.Match[str]) -> str:
        column, row, rest, self_closing = found.groups()
        if column not in columns or int(row) < first_row:
            return found.group(0)
        rest = _EXISTING_STYLE.sub("", rest)
        return f'<c r="{column}{row}" s="{style}"{rest}{self_closing}>'

    return _CELL_TAG.sub(replace, sheet_xml)


def apply_native_checkboxes(
    path: Path | str,
    *,
    column_indices: list[int],
    sheet_name: str | None = None,
    first_row: int = 2,
) -> int:
    """Render the given columns as native Excel checkboxes.

    `column_indices` are 1-based, matching how the layout numbers its columns.
    Returns the style index that was applied, or -1 when there was nothing to do.
    """
    path = Path(path)
    if not column_indices:
        return -1

    with zipfile.ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}

    for required in ("[Content_Types].xml", "xl/styles.xml", "xl/_rels/workbook.xml.rels"):
        if required not in parts:
            raise CheckboxError(f"not a readable xlsx: missing {required}")

    sheet_part = _worksheet_part(parts, sheet_name)

    content_types = parts["[Content_Types].xml"].decode("utf-8")
    styles = parts["xl/styles.xml"].decode("utf-8")
    workbook_rels = parts["xl/_rels/workbook.xml.rels"].decode("utf-8")
    sheet_xml = parts[sheet_part].decode("utf-8")

    styles, style_index = _add_checkbox_style(styles)

    letters = {get_column_letter(index) for index in column_indices}
    sheet_xml = _stamp_cells(sheet_xml, letters, first_row, style_index)

    if FPB_CONTENT_TYPE not in content_types:
        content_types = content_types.replace("</Types>", FPB_OVERRIDE + "</Types>", 1)

    if FPB_REL_TYPE not in workbook_rels:
        used = set(re.findall(r'Id="(rId\d+)"', workbook_rels))
        number = 1
        while f"rId{number}" in used:
            number += 1
        relationship = (
            f'<Relationship Id="rId{number}" Type="{FPB_REL_TYPE}" '
            'Target="featurePropertyBag/featurePropertyBag.xml"/>'
        )
        workbook_rels = workbook_rels.replace(
            "</Relationships>", relationship + "</Relationships>", 1
        )

    parts["[Content_Types].xml"] = content_types.encode("utf-8")
    parts["xl/styles.xml"] = styles.encode("utf-8")
    parts["xl/_rels/workbook.xml.rels"] = workbook_rels.encode("utf-8")
    parts[sheet_part] = sheet_xml.encode("utf-8")
    parts[FPB_PART] = FPB_XML.encode("utf-8")

    # Write beside the original and swap atomically: a crash halfway through
    # rebuilding the archive would otherwise leave a truncated workbook where
    # the user's only copy of their notes used to be.
    temporary = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in parts.items():
            archive.writestr(name, payload)
    temporary.replace(path)
    return style_index
