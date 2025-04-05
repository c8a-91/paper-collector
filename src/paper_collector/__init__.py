"""
Paper Collector package for managing academic papers.

このパッケージは学術論文の検索・収集・管理のための機能を提供します。
ArXivやSemantic Scholarなどの学術データベースから論文を検索し、
ローカルに保存して管理することができます。

Example:
    >>> from paper_collector import PaperDatabase
    >>> db = PaperDatabase("papers.db")
    >>> papers = db.get_papers(keyword="machine learning")
    
    または、アプリケーションを実行:
    >>> from paper_collector.app import run_app
    >>> run_app({"transport": "stdio"})
"""

__version__ = "0.1.0"

# バージョン情報
__author__ = "c8a"
__email__ = ""

try:
    # インストールされたパッケージとして実行する場合
    from paper_collector.db.database import PaperDatabase
    from paper_collector.api.arxiv_client import ArxivClient
    from paper_collector.api.semantic_scholar_client import SemanticScholarClient
    from paper_collector.pdf.pdf_handler import extract_text_from_pdf
    from paper_collector.app import run_app
except ImportError:
    # 開発環境で直接実行する場合（相対インポート）
    from .db.database import PaperDatabase
    from .api.arxiv_client import ArxivClient
    from .api.semantic_scholar_client import SemanticScholarClient
    from .pdf.pdf_handler import extract_text_from_pdf
    from .app import run_app

__all__ = [
    'PaperDatabase',
    'ArxivClient',
    'SemanticScholarClient',
    'extract_text_from_pdf',
    'run_app'
]
