"""
MCP (Model Context Protocol) tools for integrating with Claude for Desktop.

このモジュールはClaude for Desktopと連携するための
Model Context Protocol (MCP) ツールを提供します。
"""

try:
    # インストールされたパッケージとして実行する場合
    from paper_collector.tools.mcp_tools import mcp
except ImportError:
    # 開発環境で直接実行する場合（相対インポート）
    from .mcp_tools import mcp

__all__ = ['mcp']