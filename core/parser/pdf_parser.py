from pathlib import Path

import fitz

from core.parser.docx_parser import DocumentBlock


def parse_pdf(path: str | Path) -> list[DocumentBlock]:
    blocks = []
    with fitz.open(str(path)) as doc:
        index = 0
        for page in doc:
            for block in page.get_text("blocks"):
                text = (block[4] or "").strip()
                if not text:
                    continue
                blocks.append(DocumentBlock(index=index, text=text))
                index += 1
    return blocks
