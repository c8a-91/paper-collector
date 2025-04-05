"""
Utility functions for the Paper Collector package.

このモジュールは、ファイル操作や設定管理などの
ユーティリティ機能を提供します。
"""

try:
    # インストールされたパッケージとして実行する場合
    from paper_collector.utils.file_utils import ensure_directory_exists
    from paper_collector.utils.config import config, get_config, set_config
except ImportError:
    # 開発環境で直接実行する場合（相対インポート）
    from .file_utils import ensure_directory_exists
    from .config import config, get_config, set_config

__all__ = ['ensure_directory_exists', 'config', 'get_config', 'set_config']
