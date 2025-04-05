#!/usr/bin/env python3
"""
Paper Collector CLI モジュール

このモジュールはコマンドラインからPaper Collectorを操作するためのインターフェースを提供します。
"""
import argparse
import sys
from typing import List, Optional, Dict, Any

try:
    # インストールされたパッケージとして実行する場合
    from paper_collector import __version__
    from paper_collector.app import run_app
except ImportError:
    # 開発環境で直接実行する場合（相対インポート）
    from . import __version__
    from .app import run_app

def parse_args(args: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    コマンドライン引数をパースします
    
    Args:
        args: コマンドライン引数（Noneの場合はsys.argvを使用）
    
    Returns:
        パースされた引数を含む辞書
    """
    parser = argparse.ArgumentParser(
        description="Paper Collector - 論文検索・管理ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--version', 
        action='version',
        version=f'Paper Collector v{__version__}'
    )
    
    parser.add_argument(
        '--transport',
        default='stdio',
        choices=['stdio', 'http'],
        help='MCPトランスポート方式 (デフォルト: stdio)'
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=8080,
        help='HTTPモード時のポート番号 (デフォルト: 8080)'
    )
    
    parsed_args = parser.parse_args(args)
    return vars(parsed_args)  # 名前空間オブジェクトを辞書に変換

def main(args: Optional[List[str]] = None) -> int:
    """
    メインエントリーポイント関数
    
    Args:
        args: コマンドライン引数（Noneの場合はsys.argvを使用）
    
    Returns:
        終了コード
    """
    config = parse_args(args)
    return run_app(config)

if __name__ == "__main__":
    sys.exit(main())