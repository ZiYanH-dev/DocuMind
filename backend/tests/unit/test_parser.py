"""文档解析与分块单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config.settings import settings
from app.utils.document_parser import DocumentParser, document_parser


@pytest.fixture()
def parser() -> DocumentParser:
    """独立的解析器实例，避免复用全局单例带来的配置耦合。"""

    return DocumentParser()


# ── 分块 ──────────────────────────────────────────────────────


def test_short_text_returns_single_chunk(parser: DocumentParser) -> None:
    """短文本不切分。"""

    assert parser.split("线程是调度单位") == ["线程是调度单位"]


def test_long_text_is_split_into_multiple_chunks(parser: DocumentParser) -> None:
    """超过 chunk_size 的长文本必须切成多块，否则向量化会截断丢内容。"""

    text: str = "操作系统的线程调度策略。" * 500

    chunks: list[str] = parser.split(text)

    assert len(chunks) > 1
    assert sum(len(c) for c in chunks) > 0


def test_each_chunk_respects_size_limit(parser: DocumentParser) -> None:
    """单块长度不应显著超过 chunk_size（重叠部分除外）。"""

    text: str = "线程调度策略说明。" * 500

    for chunk in parser.split(text):
        assert len(chunk) <= settings.chunk_size + settings.chunk_overlap


def test_blank_text_returns_empty(parser: DocumentParser) -> None:
    """空文本或纯空白返回空列表，上层据此判定「文档内容为空」。"""

    assert parser.split("") == []
    assert parser.split("   \n\n  \t ") == []


def test_chunks_are_stripped(parser: DocumentParser) -> None:
    """切出的块去掉首尾空白，避免把空块写进库。"""

    chunks: list[str] = parser.split("第一段。\n\n\n   第二段。")

    assert all(c == c.strip() for c in chunks)
    assert all(c for c in chunks)


# ── TXT 解析 ──────────────────────────────────────────────────


def test_parse_txt_utf8(tmp_path: Path, parser: DocumentParser) -> None:
    """UTF-8 文本正常解析。"""

    path: Path = tmp_path / "a.txt"
    path.write_text("线程是 CPU 调度的基本单位", encoding="utf-8")

    assert parser.parse(str(path), "txt") == "线程是 CPU 调度的基本单位"


def test_parse_txt_gbk(tmp_path: Path, parser: DocumentParser) -> None:
    """GBK 编码的文本要能兜住，中文 Windows 用户常见。"""

    path: Path = tmp_path / "a.txt"
    path.write_text("线程是调度单位", encoding="gbk")

    assert parser.parse(str(path), "txt") == "线程是调度单位"


def test_parse_txt_unknown_encoding_does_not_crash(tmp_path: Path, parser: DocumentParser) -> None:
    """全部编码都失败时用 replace 兜底，不能因一个坏文件拖垮上传。"""

    path: Path = tmp_path / "a.txt"
    path.write_bytes(b"\xff\xfe\x00\x01bad bytes")

    assert isinstance(parser.parse(str(path), "txt"), str)


# ── 类型分派 ──────────────────────────────────────────────────


@pytest.mark.parametrize("file_type", ["pdf", "docx", "doc"])
def test_parse_dispatches_by_type(tmp_path: Path, parser: DocumentParser, file_type: str) -> None:
    """已支持的类型按后缀分派到对应解析器（这里只验证不误报不支持）。"""

    path: Path = tmp_path / f"a.{file_type}"
    path.write_bytes(b"")

    # 文件内容为空会因解析失败抛出具体库异常，但不应是「不支持的文件类型」
    with pytest.raises(Exception) as exc_info:
        parser.parse(str(path), file_type)

    assert "不支持的文件类型" not in str(exc_info.value)


def test_unsupported_type_raises(tmp_path: Path, parser: DocumentParser) -> None:
    """白名单之外的类型必须明确报错。"""

    path: Path = tmp_path / "a.exe"
    path.write_text("x")

    with pytest.raises(ValueError, match="不支持的文件类型"):
        parser.parse(str(path), "exe")


# ── 全局单例 ──────────────────────────────────────────────────


def test_module_level_singleton_is_usable() -> None:
    """模块级单例可被业务代码直接使用。"""

    assert isinstance(document_parser, DocumentParser)
    assert document_parser.split("线程调度") == ["线程调度"]
