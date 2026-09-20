"""文档解析工具：支持 PDF / Word / TXT。"""

from pathlib import Path

from docx import Document as DocxDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from app.config.settings import settings


class DocumentParser:
    """文档解析与分块。"""

    def __init__(self) -> None:
        self._splitter: RecursiveCharacterTextSplitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            separators=["\n\n", "\n", "。", "；", "，", " ", ""],
        )

    def parse(self, file_path: str, file_type: str) -> str:
        """解析文档为纯文本。"""

        path: Path = Path(file_path)
        if file_type == "pdf":
            return self._parse_pdf(path)
        if file_type in ("docx", "doc"):
            return self._parse_docx(path)
        if file_type == "txt":
            return self._parse_txt(path)
        raise ValueError(f"不支持的文件类型: {file_type}")

    def split(self, text: str) -> list[str]:
        """将文本分块。"""

        chunks: list[str] = self._splitter.split_text(text)
        return [chunk.strip() for chunk in chunks if chunk.strip()]

    def _parse_pdf(self, path: Path) -> str:
        """解析 PDF 文件。"""

        reader: PdfReader = PdfReader(str(path))
        pages: list[str] = []
        for page in reader.pages:
            text: str = page.extract_text() or ""
            pages.append(text)
        return "\n\n".join(pages)

    def _parse_docx(self, path: Path) -> str:
        """解析 Word 文件。"""

        document: DocxDocument = DocxDocument(str(path))
        paragraphs: list[str] = [p.text for p in document.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)

    def _parse_txt(self, path: Path) -> str:
        """解析 TXT 文件（尝试常见编码）。"""

        data: bytes = path.read_bytes()
        for encoding in ("utf-8", "gbk", "gb18030", "big5"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")


document_parser: DocumentParser = DocumentParser()
