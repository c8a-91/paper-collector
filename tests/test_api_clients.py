"""
API クライアント関連のテストコード
"""
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import json
from datetime import datetime
import asyncio

import pytest

from paper_collector.api.arxiv_client import ArxivClient
from paper_collector.api.semantic_scholar_client import SemanticScholarClient

class TestArxivClient(unittest.TestCase):
    """ArxivClient クラスのテスト"""
    
    def setUp(self):
        """テスト準備"""
        self.temp_dir = tempfile.mkdtemp()
        self.arxiv_client = ArxivClient(self.temp_dir, 0.01)  # API遅延は最小にする
        
        # モック用の論文データ
        self.mock_arxiv_entry = MagicMock()
        self.mock_arxiv_entry.entry_id = "http://arxiv.org/abs/1234.5678v1"
        self.mock_arxiv_entry.title = "テスト論文タイトル"
        self.mock_arxiv_entry.authors = [MagicMock(name="著者1"), MagicMock(name="著者2")]
        self.mock_arxiv_entry.summary = "これはテスト用の概要です。"
        self.mock_arxiv_entry.pdf_url = "http://arxiv.org/pdf/1234.5678v1"
        self.mock_arxiv_entry.published = datetime(2025, 1, 1)
        self.mock_arxiv_entry.comment = "テストコメント"
        
        for author in self.mock_arxiv_entry.authors:
            author.name = author.name
    
    def tearDown(self):
        """テスト後のクリーンアップ"""
        for root, dirs, files in os.walk(self.temp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.temp_dir)
    
    @pytest.mark.asyncio
    @patch("paper_collector.api.arxiv_client.arxiv.Search")
    async def test_search(self, mock_search):
        """検索機能のテスト"""
        # モックの設定
        mock_search.return_value = [self.mock_arxiv_entry]
        
        # 検索実行
        papers = await self.arxiv_client.search("テストクエリ", 10)
        
        # 結果確認
        self.assertEqual(len(papers), 1)
        paper = papers[0]
        self.assertEqual(paper["paper_id"], "1234.5678v1")
        self.assertEqual(paper["title"], "テスト論文タイトル")
        self.assertEqual(paper["authors"], "著者1, 著者2")
        self.assertEqual(paper["source"], "arxiv")
        
    @pytest.mark.asyncio
    @patch("paper_collector.api.arxiv_client.arxiv.Search")
    async def test_search_by_date(self, mock_search):
        """日付範囲検索のテスト"""
        # モックの設定
        mock_search.return_value = [self.mock_arxiv_entry]
        
        # 検索実行
        papers = await self.arxiv_client.search_by_date("テストクエリ", "20250101", "20250131", 10)
        
        # 結果確認
        self.assertEqual(len(papers), 1)
        paper = papers[0]
        self.assertEqual(paper["paper_id"], "1234.5678v1")
        self.assertEqual(paper["published_date"], "2025-01-01")
        
    @pytest.mark.asyncio
    @patch("paper_collector.api.arxiv_client.requests.get")
    async def test_download_pdf(self, mock_get):
        """PDF ダウンロード機能のテスト"""
        # モックの設定
        mock_response = MagicMock()
        mock_response.content = b"PDF content"
        mock_get.return_value = mock_response
        
        # ダウンロード実行
        pdf_path = await self.arxiv_client.download_pdf(self.mock_arxiv_entry.pdf_url, "1234.5678v1")
        
        # 結果確認
        expected_path = os.path.join(self.temp_dir, "1234.5678v1.pdf")
        self.assertEqual(pdf_path, expected_path)
        self.assertTrue(os.path.exists(pdf_path))
        
        # ファイル内容を確認
        with open(pdf_path, "rb") as f:
            content = f.read()
            self.assertEqual(content, b"PDF content")


class TestSemanticScholarClient(unittest.TestCase):
    """SemanticScholarClient クラスのテスト"""
    
    def setUp(self):
        """テスト準備"""
        self.temp_dir = tempfile.mkdtemp()
        self.ss_client = SemanticScholarClient(self.temp_dir, 0.01)  # API遅延は最小にする
        
        # モック用の論文データ
        self.mock_ss_paper = {
            "paperId": "semantic123",
            "title": "セマンティックスカラー論文",
            "authors": [{"name": "研究者1"}, {"name": "研究者2"}],
            "abstract": "これはセマンティックスカラーのテスト用概要です。",
            "url": "https://semanticscholar.org/paper/semantic123",
            "venue": "AI Conference",
            "year": 2025,
            "citationCount": 100,
            "openAccessPdf": {"url": "https://semanticscholar.org/pdf/semantic123.pdf"},
            "fieldsOfStudy": ["Computer Science", "Artificial Intelligence"]
        }
        
        # モック用のレスポンス
        self.mock_ss_response = {
            "total": 1,
            "offset": 0,
            "next": 0,
            "data": [self.mock_ss_paper]
        }
    
    def tearDown(self):
        """テスト後のクリーンアップ"""
        for root, dirs, files in os.walk(self.temp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.temp_dir)
    
    @pytest.mark.asyncio
    @patch("paper_collector.api.semantic_scholar_client.httpx.AsyncClient.get")
    async def test_search(self, mock_get):
        """検索機能のテスト"""
        # モック応答の設定
        mock_response = AsyncMock()
        mock_response.json.return_value = self.mock_ss_response
        mock_response.status_code = 200
        mock_get.return_value.__aenter__.return_value = mock_response
        
        # 検索実行
        papers = await self.ss_client.search("テストクエリ", 10)
        
        # 結果確認
        self.assertEqual(len(papers), 1)
        paper = papers[0]
        self.assertEqual(paper["paper_id"], "semantic123")
        self.assertEqual(paper["title"], "セマンティックスカラー論文")
        self.assertEqual(paper["authors"], "研究者1, 研究者2")
        self.assertEqual(paper["source"], "semantic_scholar")
        self.assertEqual(paper["citation_count"], 100)
        self.assertEqual(paper["venue"], "AI Conference")
        
    @pytest.mark.asyncio
    @patch("paper_collector.api.semantic_scholar_client.httpx.AsyncClient.get")
    async def test_search_with_citations(self, mock_get):
        """引用数を含む検索のテスト"""
        # モック応答の設定
        mock_response = AsyncMock()
        mock_response.json.return_value = self.mock_ss_response
        mock_response.status_code = 200
        mock_get.return_value.__aenter__.return_value = mock_response
        
        # 検索実行
        papers = await self.ss_client.search("テストクエリ", 10, min_citations=50)
        
        # 結果確認
        self.assertEqual(len(papers), 1)  # モック応答では引用数100なので条件を満たす
        
        # 最小引用数を超えないケース
        papers = await self.ss_client.search("テストクエリ", 10, min_citations=200)
        self.assertEqual(len(papers), 0)  # モック応答では引用数100なので条件を満たさない
        
    @pytest.mark.asyncio
    @patch("paper_collector.api.semantic_scholar_client.httpx.AsyncClient.get")
    async def test_search_by_date(self, mock_get):
        """日付範囲検索のテスト"""
        # モック応答の設定
        mock_response = AsyncMock()
        mock_response.json.return_value = self.mock_ss_response
        mock_response.status_code = 200
        mock_get.return_value.__aenter__.return_value = mock_response
        
        # 検索実行
        papers = await self.ss_client.search_by_date("テストクエリ", 2025, 2025, 10)
        
        # 結果確認
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["published_date"], "2025")
        
    @pytest.mark.asyncio
    @patch("paper_collector.api.semantic_scholar_client.requests.get")
    async def test_download_pdf(self, mock_get):
        """PDF ダウンロード機能のテスト"""
        # モックの設定
        mock_response = MagicMock()
        mock_response.content = b"PDF content from semantic scholar"
        mock_get.return_value = mock_response
        
        # ダウンロード実行
        pdf_url = "https://semanticscholar.org/pdf/semantic123.pdf"
        pdf_path = await self.ss_client.download_pdf(pdf_url, "semantic123")
        
        # 結果確認
        expected_path = os.path.join(self.temp_dir, "semantic123.pdf")
        self.assertEqual(pdf_path, expected_path)
        self.assertTrue(os.path.exists(pdf_path))
        
        # ファイル内容を確認
        with open(pdf_path, "rb") as f:
            content = f.read()
            self.assertEqual(content, b"PDF content from semantic scholar")

if __name__ == "__main__":
    unittest.main()