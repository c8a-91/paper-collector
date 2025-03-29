from typing import Any, List, Dict, Optional
import os
import json
import pandas as pd
import httpx
import arxiv
import sqlite3
import asyncio
from mcp.server.fastmcp import FastMCP
from datetime import datetime
from pathlib import Path
import fitz  # PyMuPDF for PDF text extraction

# FastMCPサーバーの初期化
mcp = FastMCP("paper-collector")

# データ保存ディレクトリの作成
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PAPERS_DIR = os.path.join(DATA_DIR, "papers")  # PDF保存用ディレクトリ
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PAPERS_DIR, exist_ok=True)

# SQLiteデータベースファイルパス
DB_PATH = os.path.join(DATA_DIR, "papers_database.db")

# データベースの初期化
def initialize_database():
    """SQLiteデータベースの初期化"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 論文テーブルの作成
    c.execute('''
    CREATE TABLE IF NOT EXISTS papers (
        paper_id TEXT PRIMARY KEY,
        title TEXT,
        authors TEXT,
        abstract TEXT,
        url TEXT,
        pdf_path TEXT,
        full_text_available INTEGER DEFAULT 0,
        full_text TEXT,
        published_date TEXT,
        source TEXT,
        keywords TEXT,
        collected_date TEXT
    )
    ''')
    
    conn.commit()
    conn.close()

# PDFのダウンロード
async def download_pdf(url: str, paper_id: str) -> Optional[str]:
    """論文PDFをダウンロードして保存し、ファイルパスを返す"""
    # ソースごとに適切なファイル名を設定
    filename = f"{paper_id.replace('/', '_')}.pdf"
    file_path = os.path.join(PAPERS_DIR, filename)
    
    # 既にダウンロード済みの場合はパスを返す
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        return file_path
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            if response.status_code == 200:
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                return file_path
    except Exception as e:
        print(f"PDFダウンロードエラー: {e}")
    
    return None

# PDFから全文テキストを抽出
def extract_text_from_pdf(pdf_path: str) -> Optional[str]:
    """PDFファイルから全文テキストを抽出する"""
    if not pdf_path or not os.path.exists(pdf_path):
        return None
    
    try:
        # PyMuPDFを使用してPDFからテキストを抽出
        doc = fitz.open(pdf_path)
        text = ""
        
        for page in doc:
            text += page.get_text()
        
        doc.close()
        return text
    except Exception as e:
        print(f"PDFテキスト抽出エラー: {e}")
        return None

# PDF全文テキストをデータベースに保存
def save_full_text_to_db(paper_id: str, full_text: str) -> bool:
    """抽出した全文テキストをデータベースに保存する"""
    if not full_text:
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute(
            "UPDATE papers SET full_text = ? WHERE paper_id = ?",
            (full_text, paper_id)
        )
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"全文テキスト保存エラー: {e}")
        return False

# Semantic Scholar APIを使った検索
async def search_semantic_scholar(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Semantic Scholar APIを使って論文を検索"""
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": limit,
        "fields": "title,authors,abstract,url,year,venue,openAccessPdf"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        if response.status_code != 200:
            return []
        
        data = response.json()
        results = []
        
        for paper in data.get("data", []):
            if not paper.get("abstract"):
                continue
                
            authors = [author.get("name", "") for author in paper.get("authors", [])]
            
            # PDFのURLを取得（openAccessPdfフィールドから）
            pdf_url = None
            if "openAccessPdf" in paper and paper["openAccessPdf"]:
                pdf_url = paper["openAccessPdf"].get("url")
            
            paper_data = {
                "paper_id": paper.get("paperId", ""),
                "title": paper.get("title", ""),
                "authors": ", ".join(authors),
                "abstract": paper.get("abstract", ""),
                "url": paper.get("url", ""),
                "pdf_url": pdf_url,  # PDFのURL
                "published_date": paper.get("year", ""),
                "source": "Semantic Scholar",
                "keywords": query
            }
            
            # PDFが利用可能な場合はダウンロード
            pdf_path = None
            if pdf_url:
                pdf_path = await download_pdf(pdf_url, paper_data["paper_id"])
            
            paper_data["pdf_path"] = pdf_path
            paper_data["full_text_available"] = 1 if pdf_path else 0
            
            results.append(paper_data)
            
        return results

# arXiv APIを使った検索
async def search_arxiv(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """arXiv APIを使って論文を検索"""
    client = arxiv.Client(
        page_size=limit,
        delay_seconds=3.0,
        num_retries=3
    )
    
    search = arxiv.Search(
        query=query,
        max_results=limit,
        sort_by=arxiv.SortCriterion.Relevance
    )
    
    results = []
    for paper in client.results(search):
        paper_id = paper.entry_id.split("/")[-1]
        
        paper_data = {
            "paper_id": paper_id,
            "title": paper.title,
            "authors": ", ".join([author.name for author in paper.authors]),
            "abstract": paper.summary,
            "url": paper.entry_id,
            "pdf_url": paper.pdf_url,  # PDFのURL
            "published_date": paper.published.year if hasattr(paper.published, "year") else "",
            "source": "arXiv",
            "keywords": query
        }
        
        # PDFをダウンロード
        pdf_path = await download_pdf(paper.pdf_url, paper_id)
        
        paper_data["pdf_path"] = pdf_path
        paper_data["full_text_available"] = 1 if pdf_path else 0
        
        results.append(paper_data)
        
    return results

# データベースへの保存
def save_to_database(papers: List[Dict[str, Any]]) -> int:
    """論文をSQLiteデータベースに保存し、追加された論文数を返す"""
    if not papers:
        return 0
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 新しい論文の数をカウント
    new_papers_count = 0
    
    for paper in papers:
        # 既存の論文をチェック
        c.execute("SELECT paper_id FROM papers WHERE paper_id = ?", (paper["paper_id"],))
        if c.fetchone() is None:
            # 新しい論文の場合、挿入
            paper["collected_date"] = datetime.now().strftime("%Y-%m-%d")
            
            c.execute('''
            INSERT INTO papers (
                paper_id, title, authors, abstract, url, pdf_path, 
                full_text_available, published_date, source, keywords, collected_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                paper["paper_id"], 
                paper["title"], 
                paper["authors"], 
                paper["abstract"], 
                paper["url"], 
                paper.get("pdf_path", None),
                paper.get("full_text_available", 0),
                paper["published_date"], 
                paper["source"], 
                paper["keywords"], 
                paper["collected_date"]
            ))
            
            new_papers_count += 1
    
    conn.commit()
    conn.close()
    
    return new_papers_count

# MCPツール: 論文検索
@mcp.tool()
async def search_papers(query: str, source: str = "both", limit: int = 5) -> str:
    """
    キーワードによる論文検索を行い、結果をデータベースに保存します。
    
    Args:
        query: 検索キーワード
        source: 論文ソース ("arxiv", "semantic_scholar", または "both")
        limit: 各ソースから取得する論文の最大数
    
    Returns:
        検索結果の要約
    """
    papers = []
    
    if source.lower() in ["arxiv", "both"]:
        arxiv_papers = await search_arxiv(query, limit)
        papers.extend(arxiv_papers)
        
    if source.lower() in ["semantic_scholar", "both"]:
        semantic_papers = await search_semantic_scholar(query, limit)
        papers.extend(semantic_papers)
    
    # データベースに保存
    saved_count = save_to_database(papers)
    
    # 結果のサマリーを作成
    summary = f"検索キーワード「{query}」で{len(papers)}件の論文が見つかりました。\n"
    summary += f"そのうち{saved_count}件が新規としてデータベースに保存されました。\n\n"
    
    full_text_count = sum(1 for paper in papers if paper.get("full_text_available", 0) == 1)
    summary += f"全文が利用可能な論文: {full_text_count}件\n\n"
    
    if saved_count > 0:
        summary += "新規追加された論文:\n"
        new_papers = []
        seen_ids = set()
        
        for paper in papers:
            paper_id = paper["paper_id"]
            if paper_id not in seen_ids:
                seen_ids.add(paper_id)
                
                # 新しく追加された論文のみ表示
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("SELECT collected_date FROM papers WHERE paper_id = ?", (paper_id,))
                result = c.fetchone()
                conn.close()
                
                if result and result[0] == datetime.now().strftime("%Y-%m-%d"):
                    full_text = "（全文あり）" if paper.get("full_text_available", 0) == 1 else ""
                    summary += f"- {paper['title']} ({paper['source']}) {full_text}\n"
    
    return summary

# MCPツール: 保存された論文の一覧
@mcp.tool()
async def list_saved_papers(keyword: str = "", source: str = "", limit: int = 10) -> str:
    """
    保存された論文の一覧を表示します。
    
    Args:
        keyword: 特定のキーワードでフィルタリング（オプション）
        source: 特定のソースでフィルタリング（オプション）
        limit: 表示する論文の最大数
    
    Returns:
        保存された論文の一覧
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # 基本クエリ
    query = "SELECT * FROM papers"
    params = []
    
    # 条件の追加
    conditions = []
    if keyword:
        keyword_param = f"%{keyword}%"
        conditions.append("(title LIKE ? OR abstract LIKE ? OR keywords LIKE ?)")
        params.extend([keyword_param, keyword_param, keyword_param])
    
    if source:
        conditions.append("source = ?")
        params.append(source)
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    # 並び替えと制限
    query += " ORDER BY collected_date DESC LIMIT ?"
    params.append(limit)
    
    # クエリ実行
    c.execute(query, params)
    papers = c.fetchall()
    
    if not papers:
        conn.close()
        return "指定された条件に合致する論文は見つかりませんでした。"
    
    result = f"合計 {len(papers)} 件の論文:\n\n"
    
    for paper in papers:
        full_text = "（全文あり）" if paper["full_text_available"] else ""
        result += f"タイトル: {paper['title']} {full_text}\n"
        result += f"著者: {paper['authors']}\n"
        result += f"ソース: {paper['source']}\n"
        result += f"URL: {paper['url']}\n"
        result += f"概要: {paper['abstract'][:200]}...\n"
        result += f"収集日: {paper['collected_date']}\n"
        result += "-" * 50 + "\n"
    
    conn.close()
    return result

# MCPツール: 論文の詳細表示
@mcp.tool()
async def get_paper_details(paper_id: str) -> str:
    """
    特定の論文の詳細情報を表示します。paper_idまたは論文タイトルで検索できます。
    
    Args:
        paper_id: 論文のIDまたはタイトル
    
    Returns:
        論文の詳細情報
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # paper_idによる完全一致検索
    c.execute("SELECT * FROM papers WHERE paper_id = ?", (paper_id,))
    paper = c.fetchone()
    
    # 完全一致がなければタイトルの部分一致で検索
    if not paper:
        c.execute("SELECT * FROM papers WHERE title LIKE ?", (f"%{paper_id}%",))
        paper = c.fetchone()
    
    if not paper:
        conn.close()
        return f"ID または タイトル '{paper_id}' の論文は見つかりませんでした。"
    
    full_text = "（全文あり）" if paper["full_text_available"] else "（全文なし）"
    result = f"タイトル: {paper['title']} {full_text}\n"
    result += f"著者: {paper['authors']}\n"
    result += f"出版年: {paper['published_date']}\n"
    result += f"ソース: {paper['source']}\n"
    result += f"URL: {paper['url']}\n"
    
    if paper["full_text_available"] and paper["pdf_path"]:
        result += f"PDF: {paper['pdf_path']}\n"
    
    result += f"収集日: {paper['collected_date']}\n"
    result += f"\n概要:\n{paper['abstract']}\n"
    
    # キーワードも表示
    if paper['keywords']:
        result += f"\nキーワード: {paper['keywords']}\n"
    
    conn.close()
    return result

# MCPツール: PDF全文取得
@mcp.tool()
async def get_paper_full_text(paper_id: str, max_length: int = 1000000) -> str:
    """
    保存されたPDFから論文の全文を取得します。
    
    Args:
        paper_id: 論文のIDまたはタイトル
        max_length: 返すテキストの最大長さ（デフォルト: 1000000文字）
    
    Returns:
        論文の全文テキスト
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # paper_idによる完全一致検索
    c.execute("SELECT * FROM papers WHERE paper_id = ?", (paper_id,))
    paper = c.fetchone()
    
    # 完全一致がなければタイトルの部分一致で検索
    if not paper:
        c.execute("SELECT * FROM papers WHERE title LIKE ?", (f"%{paper_id}%",))
        paper = c.fetchone()
    
    if not paper:
        conn.close()
        return f"ID または タイトル '{paper_id}' の論文は見つかりませんでした。"
    
    # PDFが存在するか確認
    if not paper["full_text_available"] or not paper["pdf_path"]:
        conn.close()
        return f"論文 '{paper['title']}' のPDFファイルが見つかりませんでした。"
    
    # データベースに既に全文が保存されているか確認
    full_text = paper["full_text"] if paper["full_text"] is not None else None
    
    # 全文がデータベースにない場合、PDFから抽出
    if not full_text:
        full_text = extract_text_from_pdf(paper["pdf_path"])
        
        if full_text:
            # 抽出したテキストをデータベースに保存
            save_full_text_to_db(paper["paper_id"], full_text)
        else:
            conn.close()
            return f"論文 '{paper['title']}' のPDFからテキストを抽出できませんでした。"
    
    conn.close()
    
    # テキストが長すぎる場合は切り詰める
    if len(full_text) > max_length:
        full_text = full_text[:max_length] + f"\n\n... (テキストが長いため切り詰められました。全文は {len(full_text)} 文字あります)"
    
    return f"タイトル: {paper['title']}\n著者: {paper['authors']}\n\n全文:\n{full_text}"

# MCPツール: 全文検索
@mcp.tool()
async def search_full_text(query: str, limit: int = 5) -> str:
    """
    論文の全文から特定の文字列を検索します。
    
    Args:
        query: 検索キーワード
        limit: 表示する最大結果数
    
    Returns:
        検索結果
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # データベース内の全文を検索
    c.execute("""
    SELECT paper_id, title, authors, pdf_path, full_text
    FROM papers 
    WHERE full_text_available = 1
    ORDER BY collected_date DESC
    """)
    
    papers = c.fetchall()
    conn.close()
    
    if not papers:
        return "全文が利用可能な論文がありません。"
    
    # 検索結果
    results = []
    
    for paper in papers:
        # 全文がまだ抽出されていない場合、抽出を試みる
        full_text = paper["full_text"] if paper["full_text"] is not None else None
        if not full_text and paper["pdf_path"]:
            full_text = extract_text_from_pdf(paper["pdf_path"])
            if full_text:
                save_full_text_to_db(paper["paper_id"], full_text)
        
        # 全文内にクエリが含まれているか確認
        if full_text and query.lower() in full_text.lower():
            # マッチした部分の前後のコンテキストを取得（最大200文字）
            index = full_text.lower().find(query.lower())
            start = max(0, index - 100)
            end = min(len(full_text), index + len(query) + 100)
            
            # コンテキストを取得
            context = full_text[start:end].replace("\n", " ")
            if start > 0:
                context = "..." + context
            if end < len(full_text):
                context = context + "..."
            
            # 結果に追加
            results.append({
                "paper_id": paper["paper_id"],
                "title": paper["title"],
                "authors": paper["authors"],
                "context": context
            })
            
            # 制限に達したら終了
            if len(results) >= limit:
                break
    
    if not results:
        return f"キーワード '{query}' を含む論文は見つかりませんでした。"
    
    result_text = f"キーワード '{query}' を含む論文: {len(results)}件\n\n"
    
    for i, res in enumerate(results, 1):
        result_text += f"{i}. タイトル: {res['title']}\n"
        result_text += f"   著者: {res['authors']}\n"
        result_text += f"   コンテキスト: {res['context']}\n"
        result_text += f"   (Paper ID: {res['paper_id']})\n\n"
    
    return result_text

# MCPツール: 要約のエクスポート
@mcp.tool()
async def export_summaries(format: str = "json") -> str:
    """
    保存された論文の要約をエクスポートします。
    
    Args:
        format: エクスポート形式 ("json" または "csv")
    
    Returns:
        エクスポートの結果
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute('''
    SELECT paper_id, title, authors, abstract, url, source, 
           full_text_available, pdf_path, collected_date 
    FROM papers
    ''')
    
    papers = c.fetchall()
    conn.close()
    
    if not papers:
        return "データベースに論文がありません。"
    
    # 辞書のリストに変換
    papers_list = [{key: item[key] for key in item.keys()} for item in papers]
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if format.lower() == "json":
        export_path = os.path.join(DATA_DIR, f"paper_summaries_{timestamp}.json")
        with open(export_path, 'w', encoding='utf-8') as f:
            json.dump(papers_list, f, ensure_ascii=False, indent=2)
    else:  # csv
        export_path = os.path.join(DATA_DIR, f"paper_summaries_{timestamp}.csv")
        df = pd.DataFrame(papers_list)
        df.to_csv(export_path, index=False)
    
    return f"論文要約を {export_path} にエクスポートしました。"

initialize_database()

if __name__ == "__main__":
    mcp.run(transport='stdio')