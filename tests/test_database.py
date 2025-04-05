"""
データベース操作に関するテストコード
"""
import os
import tempfile
import unittest
import sqlite3
from datetime import datetime

from paper_collector.db.database import PaperDatabase

class TestPaperDatabase(unittest.TestCase):
    """PaperDatabase クラスのテスト"""
    
    def setUp(self):
        """テスト用の一時データベースを作成"""
        self.test_db_fd, self.test_db_path = tempfile.mkstemp()
        # SQLite接続を閉じるようにする
        os.close(self.test_db_fd)
        self.db = PaperDatabase(self.test_db_path)
        
        # サンプル論文データ
        self.sample_paper = {
            "paper_id": "test123",
            "title": "テスト論文タイトル",
            "authors": "テスト著者",
            "abstract": "これはテスト用の概要です。",
            "url": "https://example.com/paper",
            "pdf_path": None,
            "published_date": "2025-01-01",
            "venue": "テスト会議",
            "citation_count": 42,
            "source": "arxiv",
            "keywords": "テスト, 論文",
            "full_text_available": 0,
            "full_text": None,
            "collected_date": datetime.now().strftime("%Y-%m-%d")
        }
    
    def tearDown(self):
        """テスト用の一時データベースを削除"""
        # データベース接続を明示的に閉じる
        self.db.close()
        try:
            os.unlink(self.test_db_path)
        except (PermissionError, FileNotFoundError):
            # Windowsではファイルがロックされていることがあるため、
            # エラーをキャッチして無視する
            pass
    
    def test_paper_save_and_get(self):
        """論文の保存と取得をテスト"""
        # 論文を保存
        saved = self.db.save_papers([self.sample_paper])
        self.assertEqual(saved, 1, "1件の論文が保存されるべき")
        
        # 保存した論文を取得
        paper = self.db.get_paper_by_id("test123")
        self.assertIsNotNone(paper, "保存した論文が取得できるべき")
        self.assertEqual(paper["title"], "テスト論文タイトル")
        self.assertEqual(paper["citation_count"], 42)
        
        # 同じ論文を再度保存しても新規カウントされない
        saved_again = self.db.save_papers([self.sample_paper])
        self.assertEqual(saved_again, 0, "同じ論文は新規としてカウントされないべき")
        
    def test_paper_update(self):
        """論文情報の更新をテスト"""
        # 論文を保存
        self.db.save_papers([self.sample_paper])
        
        # 同じ ID で内容を変更した論文を保存
        updated_paper = self.sample_paper.copy()
        updated_paper["title"] = "更新されたタイトル"
        updated_paper["citation_count"] = 100
        
        self.db.save_papers([updated_paper])
        
        # 更新された内容を取得
        paper = self.db.get_paper_by_id("test123")
        self.assertEqual(paper["title"], "更新されたタイトル", "タイトルが更新されるべき")
        self.assertEqual(paper["citation_count"], 100, "引用数が更新されるべき")
    
    def test_get_papers(self):
        """論文一覧取得をテスト"""
        # 複数の論文を保存
        papers = [
            self.sample_paper,
            {
                "paper_id": "test456",
                "title": "機械学習に関する研究",
                "authors": "ML研究者",
                "abstract": "機械学習についての概要",
                "url": "https://example.com/ml-paper",
                "pdf_path": None,
                "published_date": "2025-02-01",
                "venue": "AI会議",
                "citation_count": 100,
                "source": "semantic_scholar",
                "keywords": "機械学習, AI",
                "full_text_available": 1,
                "full_text": None,
                "collected_date": datetime.now().strftime("%Y-%m-%d")
            }
        ]
        self.db.save_papers(papers)
        
        # 全ての論文を取得
        all_papers = self.db.get_papers()
        self.assertEqual(len(all_papers), 2, "2件の論文が取得できるべき")
        
        # キーワード検索
        ml_papers = self.db.get_papers(keyword="機械学習")
        self.assertEqual(len(ml_papers), 1, "1件の論文が取得できるべき")
        self.assertEqual(ml_papers[0]["paper_id"], "test456")
        
        # ソース検索
        arxiv_papers = self.db.get_papers(source="arxiv")
        self.assertEqual(len(arxiv_papers), 1)
        self.assertEqual(arxiv_papers[0]["paper_id"], "test123")
        
        # 引用数でソート (降順)
        sorted_papers = self.db.get_papers(sort_by="citations", sort_order="desc")
        self.assertEqual(len(sorted_papers), 2)
        self.assertEqual(sorted_papers[0]["paper_id"], "test456")  # 引用数100
        
        # 全文利用可能な論文のみ
        fulltext_papers = self.db.get_papers(filter_has_fulltext=True)
        self.assertEqual(len(fulltext_papers), 1)
        self.assertEqual(fulltext_papers[0]["paper_id"], "test456")
        
    def test_save_full_text(self):
        """全文テキストの保存をテスト"""
        # 論文を保存
        self.db.save_papers([self.sample_paper])
        
        # 全文を保存
        full_text = "これはテスト論文の全文です。内容は長いテキストが続きます。"
        self.db.save_full_text("test123", full_text)
        
        # 全文が保存されていることを確認
        paper = self.db.get_paper_by_id("test123")
        self.assertEqual(paper["full_text"], full_text)
        self.assertEqual(paper["full_text_available"], 1)

if __name__ == "__main__":
    unittest.main()