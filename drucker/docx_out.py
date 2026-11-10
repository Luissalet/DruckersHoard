"""A minimal .docx written by hand (no library): title, a note, headings and tagged lines. Same inputs, same bytes."""
from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

FIXED_TIME = (2020, 1, 1, 0, 0, 0)
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

CONTENT_TYPES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                 '<Default Extension="xml" ContentType="application/xml"/>'
                 '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                 '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                 '</Types>')
ROOT_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             f'<Relationship Id="rId1" Type="{REL}/officeDocument" Target="word/document.xml"/></Relationships>')
DOC_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{REL}/styles" Target="styles.xml"/></Relationships>')


def _style(sid, name, size, bold=False, italic=False, color=None, before=0, after=120):
    rpr = (f'<w:b/>' if bold else '') + (f'<w:i/>' if italic else '') + (f'<w:color w:val="{color}"/>' if color else '') + f'<w:sz w:val="{size}"/>'
    return (f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/><w:basedOn w:val="Normal"/>'
            f'<w:pPr><w:spacing w:before="{before}" w:after="{after}"/></w:pPr><w:rPr>{rpr}</w:rPr></w:style>')


STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' f'<w:styles xmlns:w="{W}">'
          '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>'
          '<w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/></w:rPr></w:style>'
          + _style("Title", "Title", 40, bold=True, after=200) + _style("Heading1", "heading 1", 28, bold=True, before=280, after=100)
          + _style("Note", "Note", 20, italic=True, color="666666", after=160) + '</w:styles>')


def _para(text, style=None, tag=None):
    runs = f'<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'
    if tag:
        runs += f'<w:r><w:rPr><w:b/><w:color w:val="666666"/><w:sz w:val="18"/></w:rPr><w:t xml:space="preserve">  [{escape(tag)}]</w:t></w:r>'
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ''
    return f'<w:p>{ppr}{runs}</w:p>'


def build(title, note, sections) -> bytes:
    """``sections``: [(heading, [(text, tag), ...]), ...]."""
    body = [_para(title, "Title"), _para(note, "Note")]
    for heading, lines in sections:
        body.append(_para(heading, "Heading1"))
        body += [_para(("• " + text), None, tag) for text, tag in lines]
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' f'<w:document xmlns:w="{W}"><w:body>' + "".join(body)
                + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1417" w:right="1417" w:bottom="1417" w:left="1417" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
                '</w:body></w:document>')
    parts = {"[Content_Types].xml": CONTENT_TYPES, "_rels/.rels": ROOT_RELS, "word/document.xml": document,
             "word/_rels/document.xml.rels": DOC_RELS, "word/styles.xml": STYLES}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in parts:
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, parts[name].encode("utf-8"))
    return buf.getvalue()
