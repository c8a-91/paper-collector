#!/usr/bin/env python3
"""
Paper Collector のメインエントリーポイント

このモジュールは `python -m paper_collector` コマンドで
実行されたときのエントリーポイントです。
"""
import sys

try:
    # インストールされたパッケージとして実行する場合
    from paper_collector.cli import main
except ImportError:
    # 開発環境で直接実行する場合（相対インポート）
    from .cli import main

if __name__ == "__main__":
    """
    パッケージとして実行された場合のエントリーポイント
    """
    sys.exit(main())