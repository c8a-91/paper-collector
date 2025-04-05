"""
API clients for academic paper sources.

このモジュールは、ArXivやSemantic Scholarなどの学術論文ソースに
接続するためのクライアントを提供します。
"""

try:
    # インストールされたパッケージとして実行する場合
    from paper_collector.api.arxiv_client import ArxivClient
    from paper_collector.api.semantic_scholar_client import SemanticScholarClient
except ImportError:
    # 開発環境で直接実行する場合（相対インポート）
    from .arxiv_client import ArxivClient
    from .semantic_scholar_client import SemanticScholarClient

__all__ = ['ArxivClient', 'SemanticScholarClient']
