"""
PDF処理に関するテストコード
"""
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from paper_collector.pdf.pdf_handler import extract_text_from_pdf

class TestPDFHandler(unittest.TestCase):
    """PDF処理機能のテスト"""
    
    def setUp(self):
        """テスト準備"""
        # テスト用のダミーPDFファイルを作成
        self.test_pdf_fd, self.test_pdf_path = tempfile.mkstemp(suffix='.pdf')
        with os.fdopen(self.test_pdf_fd, 'wb') as f:
            f.write(b'%PDF-1.4\nThis is a test PDF file')
    
    def tearDown(self):
        """テスト後のクリーンアップ"""
        os.unlink(self.test_pdf_path)
    
    @patch('paper_collector.pdf.pdf_handler.fitz.open')
    def test_extract_text_from_pdf(self, mock_fitz_open):
        """PDFからテキスト抽出のテスト"""
        # モックの設定
        mock_doc = MagicMock()
        mock_page1 = MagicMock()
        mock_page2 = MagicMock()
        
        # ページのテキスト内容を設定
        mock_page1.get_text.return_value = "これは1ページ目のテキストです。"
        mock_page2.get_text.return_value = "これは2ページ目のテキストです。"
        
        # ドキュメントのページ数とページアクセスをモック
        mock_doc.__len__.return_value = 2
        mock_doc.__getitem__.side_effect = [mock_page1, mock_page2]
        mock_fitz_open.return_value = mock_doc
        
        # テキスト抽出を実行
        text = extract_text_from_pdf(self.test_pdf_path)
        
        # 結果確認（改行なしでテキストが連結されるようにテストを調整）
        expected_text = "これは1ページ目のテキストです。これは2ページ目のテキストです。"
        self.assertEqual(text, expected_text)
        mock_fitz_open.assert_called_once_with(self.test_pdf_path)
        
    @patch('paper_collector.pdf.pdf_handler.fitz.open')
    def test_extract_text_from_invalid_pdf(self, mock_fitz_open):
        """無効なPDFファイルからのテキスト抽出テスト"""
        # 例外を発生させる
        mock_fitz_open.side_effect = Exception("無効なPDFファイルです")
        
        # テキスト抽出を実行
        text = extract_text_from_pdf(self.test_pdf_path)
        
        # 結果確認 (エラーの場合はNoneが返される)
        self.assertIsNone(text)
        
    def test_extract_text_nonexistent_file(self):
        """存在しないファイルからのテキスト抽出テスト"""
        # 存在しないファイルパス
        nonexistent_path = "/path/to/nonexistent/file.pdf"
        
        # テキスト抽出を実行
        text = extract_text_from_pdf(nonexistent_path)
        
        # 結果確認 (エラーの場合はNoneが返される)
        self.assertIsNone(text)

if __name__ == "__main__":
    unittest.main()