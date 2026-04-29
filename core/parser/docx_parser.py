from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.document import Document as DocumentObject
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import _Cell, Table
from docx.text.paragraph import Paragraph


@dataclass(frozen=True)
class DocumentBlock:
    index: int
    text: str


def iter_docx_paragraphs(parent):
    if isinstance(parent, DocumentObject):
        parent_elm = parent.element.body
    elif isinstance(parent, _Cell):
        parent_elm = parent._tc
    else:
        parent_elm = parent._element

    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            table = Table(child, parent)
            for row in table.rows:
                for cell in row.cells:
                    yield from iter_docx_paragraphs(cell)


def parse_docx(path: str | Path) -> list[DocumentBlock]:
    """Return document paragraphs with stable indexes for later annotation."""
    doc = Document(str(path))
    return [
        DocumentBlock(index=i, text=paragraph.text or "")
        for i, paragraph in enumerate(iter_docx_paragraphs(doc))
    ]
