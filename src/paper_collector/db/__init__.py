"""
Database operations for paper management.

このモジュールは論文のメタデータと全文を保存・管理するための
データベース操作機能を提供します。
"""

try:
    # インストールされたパッケージとして実行する場合
    from paper_collector.db.database import PaperDatabase
except ImportError:
    # 開発環境で直接実行する場合（相対インポート）
    from .database import PaperDatabase

__all__ = ['PaperDatabase']
