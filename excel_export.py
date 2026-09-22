from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile


_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>
"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""

_WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
"""

_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>
"""


def _column_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _cell(row: ET.Element, ref: str, value, style: int = 0):
    attributes = {"r": ref}
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        attributes["t"] = "inlineStr"
    cell = ET.SubElement(row, "c", attributes)
    if style:
        cell.set("s", str(style))
    if attributes.get("t") == "inlineStr":
        inline = ET.SubElement(cell, "is")
        text = ET.SubElement(inline, "t")
        text.text = "" if value is None else str(value)
    else:
        ET.SubElement(cell, "v").text = str(value)


def members_to_excel(
    members: list,
    save_dir: Path,
    org_display_name: str,
    output_filename: str,
) -> str:
    """生成无需额外依赖、可被 Excel/WPS 打开的成员名单 xlsx 文件。"""
    save_dir.mkdir(parents=True, exist_ok=True)
    output_path = save_dir / output_filename
    temp_path = output_path.with_suffix(".tmp")

    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ET.register_namespace("", namespace)
    worksheet = ET.Element(f"{{{namespace}}}worksheet")
    sheet_views = ET.SubElement(worksheet, "sheetViews")
    sheet_view = ET.SubElement(sheet_views, "sheetView", {"workbookViewId": "0"})
    ET.SubElement(
        sheet_view,
        "pane",
        {"ySplit": "1", "topLeftCell": "A2", "activePane": "bottomLeft", "state": "frozen"},
    )
    columns = ET.SubElement(worksheet, "cols")
    for start, end, width in ((1, 1, 8), (2, 3, 24), (4, 4, 28), (5, 6, 12)):
        ET.SubElement(
            columns,
            "col",
            {"min": str(start), "max": str(end), "width": str(width), "customWidth": "1"},
        )

    sheet_data = ET.SubElement(worksheet, "sheetData")
    rows = [["序号", "游戏 ID", "昵称", "职位", "星级", "是否隐藏"]]
    for index, member in enumerate(members, start=1):
        hidden = bool(member.get("is_hidden", False))
        rows.append(
            [
                index,
                "" if hidden else member.get("handle", ""),
                "" if hidden else member.get("moniker", ""),
                member.get("rank", ""),
                member.get("stars", 0),
                "是" if hidden else "否",
            ]
        )

    for row_index, values in enumerate(rows, start=1):
        row = ET.SubElement(sheet_data, "row", {"r": str(row_index)})
        for column_index, value in enumerate(values, start=1):
            ref = f"{_column_name(column_index)}{row_index}"
            _cell(row, ref, value, style=1 if row_index == 1 else 0)

    ET.SubElement(worksheet, "autoFilter", {"ref": f"A1:F{len(rows)}"})

    safe_sheet_name = f"{org_display_name}成员"[:31].translate(
        str.maketrans({char: "_" for char in "[]:*?/\\"})
    )
    workbook = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="{_xml_attribute(safe_sheet_name)}" sheetId="1" r:id="rId1"/></sheets>
</workbook>
"""

    with ZipFile(temp_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _ROOT_RELS)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS)
        archive.writestr("xl/styles.xml", _STYLES)
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            ET.tostring(worksheet, encoding="utf-8", xml_declaration=True),
        )
    temp_path.replace(output_path)
    return str(output_path)


def _xml_attribute(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
