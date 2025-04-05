#!/usr/bin/env python3
"""
Paper Collector アプリケーションのメインロジック

このモジュールは Paper Collector アプリケーションの
コアロジックを提供し、MCP サーバーを実行します。
"""
import sys
from typing import Optional, Dict, Any

try:
    # インストールされたパッケージとして実行する場合
    from paper_collector import __version__
    from paper_collector.tools import mcp
except ImportError:
    # 開発環境で直接実行する場合（相対インポート）
    from . import __version__
    from .tools import mcp

def run_app(config: Dict[str, Any]) -> int:
    """
    Paper Collector アプリケーションを実行します。

    Args:
        config: アプリケーション設定（transport, port などを含む）

    Returns:
        終了コード（0: 成功、1: エラー）
    """
    try:
        transport = config.get("transport", "stdio")
        port = config.get("port", 8080)
        
        print(f"Paper Collector v{__version__} を起動しています...")
        print(f"トランスポート: {transport}")
        
        if transport == "http":
            print(f"ポート: {port}")
            mcp.run(transport='http', port=port)
        else:
            mcp.run(transport='stdio')
        return 0
    except KeyboardInterrupt:
        print("\nPaper Collector を終了します")
        return 0
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        return 1