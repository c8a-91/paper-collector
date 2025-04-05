"""
PDF handling functions for extracting text and metadata.

このモジュールはPDFファイルからテキストや
メタデータを抽出するための機能を提供します。
"""

try:
    # インストールされたパッケージとして実行する場合
    from paper_collector.pdf.pdf_handler import extract_text_from_pdf
except ImportError:
    # 開発環境で直接実行する場合（相対インポート）
    from .pdf_handler import extract_text_from_pdf

__all__ = ['extract_text_from_pdf']
