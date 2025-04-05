"""
設定ファイル管理モジュール

このモジュールは設定ファイルの読み込みと管理を行います。
"""
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional

# デフォルト設定
DEFAULT_CONFIG = {
    "data_dir": "./data",
    "papers_dir": "./data/papers",
    "db_path": "./data/papers_database.db",
    "api_delay": 1.0,
    "default_limit": 10
}

class Config:
    """設定管理クラス"""
    
    def __init__(self):
        self.config_dir = self._get_config_dir()
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.config = self._load_config()
    
    def _get_config_dir(self) -> str:
        """
        設定ファイルディレクトリを取得します
        
        Returns:
            設定ファイルディレクトリのパス
        """
        # ホームディレクトリ配下の .paper_collector ディレクトリ
        home_dir = str(Path.home())
        config_dir = os.path.join(home_dir, ".paper_collector")
        
        # ディレクトリがなければ作成
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        
        return config_dir
    
    def _load_config(self) -> Dict[str, Any]:
        """
        設定ファイルを読み込みます
        
        Returns:
            設定データの辞書
        """
        # 設定ファイルがなければデフォルト設定を保存
        if not os.path.exists(self.config_file):
            self._save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()
        
        # 設定ファイルを読み込み
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # デフォルト設定との統合（新しい設定項目がある場合に対応）
            updated = False
            for key, value in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = value
                    updated = True
            
            # 更新があれば保存
            if updated:
                self._save_config(config)
            
            return config
        except Exception as e:
            print(f"設定ファイルの読み込みに失敗しました: {e}")
            return DEFAULT_CONFIG.copy()
    
    def _save_config(self, config: Dict[str, Any]) -> None:
        """
        設定ファイルを保存します
        
        Args:
            config: 設定データ
        """
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"設定ファイルの保存に失敗しました: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        設定値を取得します
        
        Args:
            key: 設定キー
            default: キーが存在しない場合のデフォルト値
        
        Returns:
            設定値
        """
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """
        設定値を更新します
        
        Args:
            key: 設定キー
            value: 設定値
        """
        self.config[key] = value
        self._save_config(self.config)
    
    def get_data_dir(self) -> str:
        """
        データディレクトリのパスを取得します
        
        Returns:
            データディレクトリの絶対パス
        """
        data_dir = self.get("data_dir")
        
        # 相対パスの場合は絶対パスに変換
        if not os.path.isabs(data_dir):
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            data_dir = os.path.join(base_dir, data_dir)
        
        # ディレクトリがなければ作成
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        
        return data_dir
    
    def get_papers_dir(self) -> str:
        """
        論文PDFディレクトリのパスを取得します
        
        Returns:
            論文PDFディレクトリの絶対パス
        """
        papers_dir = self.get("papers_dir")
        
        # 相対パスの場合は絶対パスに変換
        if not os.path.isabs(papers_dir):
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            papers_dir = os.path.join(base_dir, papers_dir)
        
        # ディレクトリがなければ作成
        if not os.path.exists(papers_dir):
            os.makedirs(papers_dir)
        
        return papers_dir
    
    def get_db_path(self) -> str:
        """
        データベースファイルのパスを取得します
        
        Returns:
            データベースファイルの絶対パス
        """
        db_path = self.get("db_path")
        
        # 相対パスの場合は絶対パスに変換
        if not os.path.isabs(db_path):
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            db_path = os.path.join(base_dir, db_path)
        
        # ディレクトリがなければ作成
        db_dir = os.path.dirname(db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
        
        return db_path

# シングルトンインスタンス
config = Config()

# モジュールレベルの関数としても提供
def get_config(key: str, default: Any = None) -> Any:
    """
    設定値を取得します
    
    Args:
        key: 設定キー
        default: キーが存在しない場合のデフォルト値
    
    Returns:
        設定値
    """
    return config.get(key, default)

def set_config(key: str, value: Any) -> None:
    """
    設定値を更新します
    
    Args:
        key: 設定キー
        value: 設定値
    """
    config.set(key, value)