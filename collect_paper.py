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
        collected_date TEXT,
        citation_count INTEGER DEFAULT 0,
        venue TEXT,
        venue_impact_score REAL DEFAULT 0.0
    )
    ''')
    
    # 既存のテーブルに新しいカラムを追加
    try:
        c.execute("ALTER TABLE papers ADD COLUMN citation_count INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
        
    try:
        c.execute("ALTER TABLE papers ADD COLUMN venue TEXT")
    except sqlite3.OperationalError:
        pass
        
    try:
        c.execute("ALTER TABLE papers ADD COLUMN venue_impact_score REAL DEFAULT 0.0")
    except sqlite3.OperationalError:
        pass
    
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

# arXiv論文の引用情報を取得
async def get_arxiv_citation_data(arxiv_id: str) -> Dict[str, Any]:
    """arXiv IDを使ってSemantic Scholar APIから引用情報を取得"""
    url = f"https://api.semanticscholar.org/graph/v1/paper/arXiv:{arxiv_id}"
    params = {
        "fields": "citationCount,venue,influentialCitationCount"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        if response.status_code != 200:
            return {"citation_count": 0, "venue": "", "venue_impact_score": 0.0}
        
        data = response.json()
        return {
            "citation_count": data.get("citationCount", 0) or 0,
            "venue": data.get("venue", ""),
            "venue_impact_score": 0.0
        }

# Semantic Scholar APIを使った検索
async def search_semantic_scholar(query: str, limit: int = 5, min_citations: int = 0, sort_by: str = "relevance") -> List[Dict[str, Any]]:
    """Semantic Scholar APIを使って論文を検索"""
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    fields = "title,authors,abstract,url,year,venue,openAccessPdf,citationCount,venue,influentialCitationCount"
    
    params = {
        "query": query,
        "limit": limit * 2,
        "fields": fields
    }
    
    headers = {
        "Accept": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, headers=headers)
        if response.status_code != 200:
            return []
        
        data = response.json()
        all_results = []
        
        for paper in data.get("data", []):
            if not paper.get("abstract"):
                continue
                
            citation_count = paper.get("citationCount", 0) or 0
            
            if citation_count < min_citations:
                continue
                
            authors = [author.get("name", "") for author in paper.get("authors", [])]
            venue = paper.get("venue", "")
            
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
                "pdf_url": pdf_url,
                "published_date": paper.get("year", ""),
                "source": "Semantic Scholar",
                "keywords": query,
                "citation_count": citation_count,
                "venue": venue,
                "venue_impact_score": 0.0
            }
            
            # PDFが利用可能な場合はダウンロード
            pdf_path = None
            if pdf_url:
                pdf_path = await download_pdf(pdf_url, paper_data["paper_id"])
            
            paper_data["pdf_path"] = pdf_path
            paper_data["full_text_available"] = 1 if pdf_path else 0
            
            all_results.append(paper_data)
            
        if sort_by == "citations":
            all_results.sort(key=lambda x: x["citation_count"], reverse=True)
        
        return all_results[:limit]

# arXiv APIを使った検索
async def search_arxiv(query: str, limit: int = 5, min_citations: int = 0, sort_by: str = "relevance") -> List[Dict[str, Any]]:
    """arXiv APIを使って論文を検索"""
    client = arxiv.Client(
        page_size=limit * 2,
        delay_seconds=3.0,
        num_retries=3
    )
    
    search_criteria = arxiv.SortCriterion.Relevance
    if sort_by == "recency":
        search_criteria = arxiv.SortCriterion.SubmittedDate
    
    search = arxiv.Search(
        query=query,
        max_results=limit * 2,
        sort_by=search_criteria
    )
    
    results = []
    paper_tasks = []
    
    for paper in client.results(search):
        paper_id = paper.entry_id.split("/")[-1]
        arxiv_id = paper_id
        
        paper_data = {
            "paper_id": paper_id,
            "title": paper.title,
            "authors": ", ".join([author.name for author in paper.authors]),
            "abstract": paper.summary,
            "url": paper.entry_id,
            "pdf_url": paper.pdf_url,
            "published_date": paper.published.year if hasattr(paper.published, "year") else "",
            "source": "arXiv",
            "keywords": query,
            "arxiv_id": arxiv_id
        }
        
        # タスクリストに追加（非同期で引用データを取得するため）
        paper_tasks.append((paper_data, get_arxiv_citation_data(arxiv_id)))
    
    # 引用データを非同期で取得
    for paper_data, citation_task in paper_tasks:
        citation_info = await citation_task
        
        # 引用数の取得と最小引用数でのフィルタリング
        citation_count = citation_info.get("citation_count", 0)
        if citation_count < min_citations:
            continue
        
        # 引用情報の追加
        paper_data["citation_count"] = citation_count
        paper_data["venue"] = citation_info.get("venue", "")
        paper_data["venue_impact_score"] = citation_info.get("venue_impact_score", 0.0)
        
        # PDFをダウンロード
        pdf_path = await download_pdf(paper_data["pdf_url"], paper_data["paper_id"])
        
        paper_data["pdf_path"] = pdf_path
        paper_data["full_text_available"] = 1 if pdf_path else 0
        
        results.append(paper_data)
    
    # ソート
    if sort_by == "citations":
        results.sort(key=lambda x: x["citation_count"], reverse=True)
    
    # 指定された最大件数に絞る
    return results[:limit]

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
        existing_paper = c.fetchone()
        
        if existing_paper is None:
            # 新しい論文の場合、挿入
            paper["collected_date"] = datetime.now().strftime("%Y-%m-%d")
            
            c.execute('''
            INSERT INTO papers (
                paper_id, title, authors, abstract, url, pdf_path, 
                full_text_available, published_date, source, keywords, collected_date,
                citation_count, venue, venue_impact_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                paper["collected_date"],
                paper.get("citation_count", 0),
                paper.get("venue", ""),
                paper.get("venue_impact_score", 0.0)
            ))
            
            new_papers_count += 1
        else:
            # 既存の論文の場合、引用数と掲載先情報を更新
            c.execute('''
            UPDATE papers 
            SET citation_count = ?, venue = ?, venue_impact_score = ?
            WHERE paper_id = ?
            ''', (
                paper.get("citation_count", 0),
                paper.get("venue", ""),
                paper.get("venue_impact_score", 0.0),
                paper["paper_id"]
            ))
    
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

# MCPツール: 引用数による論文検索
@mcp.tool()
async def search_papers_by_citations(
    query: str, 
    min_citations: int = 10, 
    source: str = "both", 
    limit: int = 5, 
    sort_by: str = "citations"
) -> str:
    """
    引用数を考慮した論文検索を行い、結果をデータベースに保存します。
    
    Args:
        query: 検索キーワード
        min_citations: 最小引用数
        source: 論文ソース ("arxiv", "semantic_scholar", または "both")
        limit: 各ソースから取得する論文の最大数
        sort_by: ソート方法 ("relevance", "citations", "recency")
    
    Returns:
        検索結果の要約
    """
    papers = []
    
    if source.lower() in ["arxiv", "both"]:
        arxiv_papers = await search_arxiv(query, limit, min_citations, sort_by)
        papers.extend(arxiv_papers)
        
    if source.lower() in ["semantic_scholar", "both"]:
        semantic_papers = await search_semantic_scholar(query, limit, min_citations, sort_by)
        papers.extend(semantic_papers)
    
    if sort_by == "citations":
        papers.sort(key=lambda x: x.get("citation_count", 0), reverse=True)
        papers = papers[:limit]
    
    saved_count = save_to_database(papers)
    
    summary = f"検索キーワード「{query}」で最小引用数 {min_citations} 以上の論文が {len(papers)}件見つかりました。\n"
    summary += f"そのうち{saved_count}件が新規としてデータベースに保存されました。\n\n"
    
    if papers:
        summary += "検索結果:\n"
        for i, paper in enumerate(papers, 1):
            full_text = "（全文あり）" if paper.get("full_text_available", 0) == 1 else ""
            summary += f"{i}. {paper['title']} ({paper['source']})\n"
            summary += f"   著者: {paper['authors']}\n"
            summary += f"   引用数: {paper.get('citation_count', 0)}\n"
            if paper.get("venue"):
                summary += f"   掲載先: {paper.get('venue')}\n"
            summary += f"   URL: {paper['url']}\n"
            summary += f"   {full_text}\n\n"
    else:
        summary += "指定された条件に合致する論文は見つかりませんでした。"
    
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
        if paper["citation_count"] > 0:
            result += f"引用数: {paper['citation_count']}\n"
        if paper["venue"]:
            result += f"掲載先: {paper['venue']}\n"
        result += f"概要: {paper['abstract'][:200]}...\n"
        result += f"収集日: {paper['collected_date']}\n"
        result += "-" * 50 + "\n"
    
    conn.close()
    return result

# MCPツール: 引用数でランキング
@mcp.tool()
async def rank_papers_by_citations(keyword: str = "", limit: int = 10) -> str:
    """
    保存された論文を引用数でランキングして表示します。
    
    Args:
        keyword: 特定のキーワードでフィルタリング（オプション）
        limit: 表示する論文の最大数
    
    Returns:
        引用数ランキング
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    query = "SELECT * FROM papers"
    params = []
    
    if keyword:
        query += " WHERE (title LIKE ? OR abstract LIKE ? OR keywords LIKE ?)"
        keyword_param = f"%{keyword}%"
        params.extend([keyword_param, keyword_param, keyword_param])
    
    query += " ORDER BY citation_count DESC LIMIT ?"
    params.append(limit)
    
    c.execute(query, params)
    papers = c.fetchall()
    
    if not papers:
        conn.close()
        return "指定された条件に合致する論文は見つかりませんでした。"
    
    result = f"引用数ランキング（{keyword if keyword else '全て'}）:\n\n"
    
    for i, paper in enumerate(papers, 1):
        result += f"{i}. {paper['title']}\n"
        result += f"   著者: {paper['authors']}\n"
        result += f"   引用数: {paper['citation_count']}\n"
        if paper['venue']:
            result += f"   掲載先: {paper['venue']}\n"
        result += f"   ソース: {paper['source']}\n"
        result += f"   URL: {paper['url']}\n"
        result += f"   収集日: {paper['collected_date']}\n"
        result += "-" * 50 + "\n"
    
    conn.close()
    return result

# MCPツール: 掲載先（ジャーナルや会議）ごとの論文一覧
@mcp.tool()
async def list_papers_by_venue(venue: str = "", limit: int = 10) -> str:
    """
    特定の掲載先（ジャーナルや会議）の論文一覧を表示します。
    
    Args:
        venue: 掲載先の名前（部分一致）
        limit: 表示する論文の最大数
    
    Returns:
        論文一覧
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    query = "SELECT * FROM papers"
    params = []
    
    if venue:
        query += " WHERE venue LIKE ?"
        params.append(f"%{venue}%")
    else:
        query += " WHERE venue IS NOT NULL AND venue != ''"
    
    query += " ORDER BY citation_count DESC LIMIT ?"
    params.append(limit)
    
    c.execute(query, params)
    papers = c.fetchall()
    
    if not papers:
        conn.close()
        return "指定された掲載先の論文は見つかりませんでした。"
    
    venues = {}
    for paper in papers:
        v = paper['venue']
        if v not in venues:
            venues[v] = []
        venues[v].append(paper)
    
    result = f"掲載先別論文一覧（{venue if venue else '全て'}）:\n\n"
    
    for v, v_papers in venues.items():
        result += f"【{v}】- {len(v_papers)}件\n"
        for paper in v_papers:
            result += f"- {paper['title']}\n"
            result += f"  著者: {paper['authors']}\n"
            result += f"  引用数: {paper['citation_count']}\n"
            result += f"  URL: {paper['url']}\n"
        result += "-" * 50 + "\n"
    
    conn.close()
    return result

# MCPツール: トップの掲載先一覧
@mcp.tool()
async def list_top_venues(limit: int = 10) -> str:
    """
    データベースに保存されている論文のトップ掲載先一覧を表示します。
    
    Args:
        limit: 表示する掲載先の最大数
    
    Returns:
        掲載先一覧
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''
    SELECT 
        venue, 
        COUNT(*) as paper_count, 
        AVG(citation_count) as avg_citations,
        MAX(citation_count) as max_citations
    FROM 
        papers 
    WHERE 
        venue IS NOT NULL AND venue != ''
    GROUP BY 
        venue 
    ORDER BY 
        avg_citations DESC
    LIMIT ?
    ''', (limit,))
    
    venues = c.fetchall()
    conn.close()
    
    if not venues:
        return "掲載先情報がある論文がありません。"
    
    result = "トップ掲載先一覧（平均引用数順）:\n\n"
    
    for i, (venue, paper_count, avg_citations, max_citations) in enumerate(venues, 1):
        result += f"{i}. {venue}\n"
        result += f"   論文数: {paper_count}件\n"
        result += f"   平均引用数: {avg_citations:.1f}\n"
        result += f"   最大引用数: {max_citations}\n"
        result += "-" * 50 + "\n"
    
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
    
    if paper["citation_count"] > 0:
        result += f"引用数: {paper['citation_count']}\n"
    
    if paper["venue"]:
        result += f"掲載先: {paper['venue']}\n"
    
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
           full_text_available, pdf_path, collected_date,
           citation_count, venue
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