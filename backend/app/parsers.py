import re
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Block:
    text: str
    page: int | None = None
    section: str = ""


def clean(text):
    return re.sub(r"[ \t]+", " ", text.replace("\x00", "")).strip()


def heading(text):
    return len(text) < 140 and bool(
        re.match(r"^(#{1,6}\s|第[一二三四五六七八九十百千\d]+[章节回条卷集部篇]|\d+(?:\.\d+)+\s)", text)
    )


def parse_document(path: Path, settings) -> list[Block]:
    suffix = path.suffix.lower()
    blocks = []
    section = ""
    total = 0

    def add(text, page=None, is_heading=False):
        nonlocal section, total
        text = clean(text)
        if not text:
            return
        total += len(text)
        if total > settings.max_parsed_chars:
            raise ValueError("文档解析后过大，请拆分后上传")
        if is_heading or heading(text):
            section = text.lstrip("# ")
        blocks.append(Block(text, page, section))

    if suffix == ".pdf":
        import pymupdf

        with pymupdf.open(path) as pdf:
            if pdf.needs_pass:
                raise ValueError("PDF 已加密，请先解密")
            if len(pdf) > settings.max_pdf_pages:
                raise ValueError("PDF 页数超过限制，请拆分")
            for i, page in enumerate(pdf):
                for block in page.get_text("blocks", sort=True):
                    if block[6] == 0:
                        add(block[4], i + 1)
    elif suffix == ".docx":
        from docx import Document
        from docx.text.paragraph import Paragraph

        # Reject excessive expanded ZIP sizes before python-docx reads the package.
        with zipfile.ZipFile(path) as archive:
            if sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError("DOCX 解压后过大")
        doc = Document(path)
        for item in doc.iter_inner_content():
            if isinstance(item, Paragraph):
                add(item.text, is_heading=bool(item.style and item.style.name.startswith("Heading")))
            else:
                for row in item.rows:
                    add(" | ".join(cell.text for cell in row.cells))
    elif suffix in {".md", ".txt"}:
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = raw.decode("gb18030")
            except UnicodeDecodeError as exc:
                raise ValueError("文本编码无法识别，请另存为 UTF-8") from exc
        if "\x00" in text:
            raise ValueError("文件包含二进制内容，请上传纯文本")
        for paragraph in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
            # Split headings even when Markdown/TXT omits a blank line below them.
            for part in re.split(
                r"(?m)(?=^(?:#{1,6}\s|第[一二三四五六七八九十百千\d]+[章节回条卷集部篇]|\d+(?:\.\d+)+\s))",
                paragraph,
            ):
                lines = part.splitlines()
                if lines and heading(lines[0]):
                    add(lines[0])
                    add("\n".join(lines[1:]))
                else:
                    add(part)
    else:
        raise ValueError("仅支持 PDF、DOCX、MD、TXT")
    if not blocks:
        raise ValueError("未提取到文本；扫描 PDF 请先进行 OCR 后再导入")
    return blocks
