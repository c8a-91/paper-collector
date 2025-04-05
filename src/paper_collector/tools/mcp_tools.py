"""
Model Context Protocol (MCP) ツール関数を定義するモジュール。
論文の検索、表示、エクスポートなどの機能を提供する。
"""
from typing import Any, List, Dict, Optional
import os
import json
import pandas as pd
import asyncio
from mcp.server.fastmcp import FastMCP
from datetime import datetime
from pathlib import Path

try:
    # インストールされたパッケージとして実行する場合
    from paper_collector.db.database import PaperDatabase
    from paper_collector.pdf.pdf_handler import extract_text_from_pdf
    from paper_collector.api.arxiv_client import ArxivClient
    from paper_collector.api.semantic_scholar_client import SemanticScholarClient
    from paper_collector.utils.file_utils import ensure_directory_exists
    from paper_collector.utils.config import config
except ImportError:
    # 開発環境で直接実行する場合（相対インポート）
    from ..db.database import PaperDatabase
    from ..pdf.pdf_handler import extract_text_from_pdf
    from ..api.arxiv_client import ArxivClient
    from ..api.semantic_scholar_client import SemanticScholarClient
    from ..utils.file_utils import ensure_directory_exists
    from ..utils.config import config

# MCPサーバーの初期化
mcp = FastMCP("paper-collector")

# 設定からパスとパラメータを取得
DATA_DIR = config.get_data_dir()
PAPERS_DIR = config.get_papers_dir()
DB_PATH = config.get_db_path()
API_DELAY = config.get("api_delay", 1.0)

# ディレクトリの存在を確認
ensure_directory_exists(DATA_DIR)
ensure_directory_exists(PAPERS_DIR)

# クライアントの初期化
paper_db = PaperDatabase(DB_PATH)
arxiv_client = ArxivClient(PAPERS_DIR, API_DELAY)
semantic_scholar_client = SemanticScholarClient(PAPERS_DIR, API_DELAY)

# ログユーティリティ
def log_info(message: str) -> None:
    """情報ログを出力します"""
    print(f"[INFO] {message}")

def log_error(message: str) -> None:
    """エラーログを出力します"""
    print(f"[ERROR] {message}")

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
    try:
        papers = []
        
        if source.lower() in ["arxiv", "both"]:
            log_info(f"ArXivで検索: {query}")
            arxiv_papers = await arxiv_client.search(query, limit)
            papers.extend(arxiv_papers)
            
        if source.lower() in ["semantic_scholar", "both"]:
            log_info(f"Semantic Scholarで検索: {query}")
            semantic_papers = await semantic_scholar_client.search(query, limit)
            papers.extend(semantic_papers)
        
        saved_count = paper_db.save_papers(papers)
        
        summary = f"検索キーワード「{query}」で{len(papers)}件の論文が見つかりました。\n"
        summary += f"そのうち{saved_count}件が新規としてデータベースに保存されました。\n\n"
        
        full_text_count = sum(1 for paper in papers if paper.get("full_text_available", 0) == 1)
        summary += f"全文が利用可能な論文: {full_text_count}件\n\n"
        
        if saved_count > 0:
            summary += "新規追加された論文:\n"
            seen_ids = set()
            
            for paper in papers:
                paper_id = paper["paper_id"]
                if paper_id not in seen_ids:
                    seen_ids.add(paper_id)
                    
                    db_paper = paper_db.get_paper_by_id(paper_id)
                    if db_paper and db_paper["collected_date"] == datetime.now().strftime("%Y-%m-%d"):
                        full_text = "（全文あり）" if paper.get("full_text_available", 0) == 1 else ""
                        summary += f"- {paper['title']} ({paper['source']}) {full_text}\n"
        
        return summary
    except Exception as e:
        log_error(f"論文検索中にエラーが発生しました: {e}")
        return f"論文検索中にエラーが発生しました: {e}"

@mcp.tool()
async def search_papers_by_citations(
    query: str, 
    min_citations: int = 0, 
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
    try:
        papers = []
        
        if source.lower() in ["arxiv", "both"]:
            log_info(f"ArXivで引用数検索: {query} (最小引用数: {min_citations})")
            arxiv_papers = await arxiv_client.search(query, limit, min_citations, sort_by)
            papers.extend(arxiv_papers)
            
        if source.lower() in ["semantic_scholar", "both"]:
            log_info(f"Semantic Scholarで引用数検索: {query} (最小引用数: {min_citations})")
            semantic_papers = await semantic_scholar_client.search(query, limit, min_citations, sort_by)
            papers.extend(semantic_papers)
        
        if sort_by == "citations":
            papers.sort(key=lambda x: x.get("citation_count", 0), reverse=True)
            papers = papers[:limit]
        
        saved_count = paper_db.save_papers(papers)
        
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
    except Exception as e:
        log_error(f"引用数による論文検索中にエラーが発生しました: {e}")
        return f"引用数による論文検索中にエラーが発生しました: {e}"

@mcp.tool()
async def list_saved_papers(
    keyword: str = "", 
    source: str = "", 
    limit: int = 10, 
    sort_by: str = "date", 
    sort_order: str = "desc",
    filter_has_fulltext: bool = False,
    min_citations: int = 0,
    format: str = "detailed",
    venue: str = "",
    date_from: str = "",
    date_to: str = ""
) -> str:
    """
    保存された論文の一覧を表示します。
    
    Args:
        keyword: 特定のキーワードでフィルタリング（オプション）
        source: 特定のソースでフィルタリング（オプション）
        limit: 表示する論文の最大数
        sort_by: ソート順（"date", "citations", "title"）
        sort_order: ソート方向（"asc", "desc"）
        filter_has_fulltext: 全文が利用可能な論文のみを表示
        min_citations: 最小引用数
        format: 表示形式（"detailed", "compact", "csv"）
        venue: 特定の掲載先でフィルタリング
        date_from: この日付以降に発表された論文（YYYY-MM-DD形式）
        date_to: この日付以前に発表された論文（YYYY-MM-DD形式）
    
    Returns:
        保存された論文の一覧
    """
    try:
        log_info(f"保存された論文を一覧表示します。キーワード: '{keyword}', ソート: {sort_by} {sort_order}")
        
        # Get papers based on search criteria
        papers = paper_db.get_papers(
            keyword, source, limit, sort_by, sort_order,
            filter_has_fulltext, min_citations, venue, date_from, date_to
        )
        
        if not papers:
            return "指定された条件に合致する論文は見つかりませんでした。"
        
        # Format results based on requested format
        if format == "csv":
            return _format_papers_as_csv(papers)
        elif format == "compact":
            return _format_papers_as_compact(papers)
        else:
            return _format_papers_as_detailed(papers)
            
    except Exception as e:
        log_error(f"保存された論文の一覧表示中にエラーが発生しました: {e}")
        return f"保存された論文の一覧表示中にエラーが発生しました: {e}"

def _format_papers_as_csv(papers: List[Dict[str, Any]]) -> str:
    """論文リストをCSV形式でフォーマットします"""
    result = "paper_id,title,authors,source,url,citation_count,venue,published_date,collected_date,full_text_available\n"
    for paper in papers:
        result += f'"{paper["paper_id"]}","{paper["title"].replace("\"", "\"\"")}","{paper["authors"].replace("\"", "\"\"")}","{paper["source"]}","{paper["url"]}","{paper["citation_count"]}","{paper.get("venue", "").replace("\"", "\"\"")}","{paper["published_date"]}","{paper["collected_date"]}","{paper["full_text_available"]}"\n'
    return result

def _format_papers_as_compact(papers: List[Dict[str, Any]]) -> str:
    """論文リストをコンパクト形式でフォーマットします"""
    result = f"合計 {len(papers)} 件の論文:\n\n"
    for i, paper in enumerate(papers, 1):
        full_text = "📄" if paper["full_text_available"] else ""
        citations = f"[引用:{paper['citation_count']}]" if paper['citation_count'] > 0 else ""
        result += f"{i}. {paper['title']} {full_text} {citations}\n"
        result += f"   著者: {paper['authors'][:50]}{'...' if len(paper['authors']) > 50 else ''}\n"
        result += f"   発表: {paper['published_date']} | 収集: {paper['collected_date']}\n"
        result += f"   ソース: {paper['source']}\n\n"
    return result

def _format_papers_as_detailed(papers: List[Dict[str, Any]]) -> str:
    """論文リストを詳細形式でフォーマットします"""
    result = f"合計 {len(papers)} 件の論文:\n\n"
    
    for paper in papers:
        full_text = "（全文あり）" if paper["full_text_available"] else ""
        result += f"タイトル: {paper['title']} {full_text}\n"
        result += f"著者: {paper['authors']}\n"
        result += f"ソース: {paper['source']}\n"
        result += f"URL: {paper['url']}\n"
        
        if paper["citation_count"] > 0:
            result += f"引用数: {paper['citation_count']}\n"
        
        if paper.get("venue"):
            result += f"掲載先: {paper['venue']}\n"
        
        # 発表日を追加
        if paper.get("published_date"):
            result += f"発表日: {paper['published_date']}\n"
        
        # 概要は長すぎる場合は切り詰め
        if paper.get("abstract"):
            abstract_preview = paper["abstract"][:200].replace("\n", " ")
            result += f"概要: {abstract_preview}{'...' if len(paper['abstract']) > 200 else ''}\n"
        
        result += f"収集日: {paper['collected_date']}\n"
        result += f"ID: {paper['paper_id']}\n"
        result += "-" * 50 + "\n"
        
    return result

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
    try:
        log_info(f"論文の引用数ランキングを表示します。キーワード: '{keyword}'")
        papers = paper_db.get_papers(
            keyword=keyword,
            limit=limit,
            sort_by="citations",
            sort_order="desc"
        )
        
        if not papers:
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
        
        return result
    except Exception as e:
        log_error(f"引用数ランキング表示中にエラーが発生しました: {e}")
        return f"引用数ランキング表示中にエラーが発生しました: {e}"

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
    try:
        log_info(f"掲載先での論文検索: '{venue}'")
        papers = paper_db.get_papers_by_venue(venue, limit)
        
        if not papers:
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
        
        return result
    except Exception as e:
        log_error(f"掲載先別論文一覧表示中にエラーが発生しました: {e}")
        return f"掲載先別論文一覧表示中にエラーが発生しました: {e}"

# 残りの関数は同様にリファクタリングします
@mcp.tool()
async def list_top_venues(limit: int = 10) -> str:
    """
    データベースに保存されている論文のトップ掲載先一覧を表示します。
    
    Args:
        limit: 表示する掲載先の最大数
    
    Returns:
        掲載先一覧
    """
    try:
        log_info(f"トップ掲載先一覧を表示します。上位 {limit} 件")
        venues = paper_db.get_top_venues(limit)
        
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
    except Exception as e:
        log_error(f"トップ掲載先一覧表示中にエラーが発生しました: {e}")
        return f"トップ掲載先一覧表示中にエラーが発生しました: {e}"

@mcp.tool()
async def get_paper_details(paper_id: str) -> str:
    """
    特定の論文の詳細情報を表示します。paper_idまたは論文タイトルで検索できます。
    
    Args:
        paper_id: 論文のIDまたはタイトル
    
    Returns:
        論文の詳細情報
    """
    try:
        log_info(f"論文詳細を検索: '{paper_id}'")
        paper = paper_db.get_paper_by_id(paper_id)
        
        if not paper:
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
        
        if paper['keywords']:
            result += f"\nキーワード: {paper['keywords']}\n"
        
        return result
    except Exception as e:
        log_error(f"論文詳細表示中にエラーが発生しました: {e}")
        return f"論文詳細表示中にエラーが発生しました: {e}"

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
    try:
        log_info(f"論文全文を取得: '{paper_id}'")
        paper = paper_db.get_paper_by_id(paper_id)
        
        if not paper:
            return f"ID または タイトル '{paper_id}' の論文は見つかりませんでした。"
        
        if not paper["full_text_available"] or not paper["pdf_path"]:
            return f"論文 '{paper['title']}' のPDFファイルが見つかりませんでした。"
        
        full_text = paper["full_text"] if paper["full_text"] is not None else None
        
        if not full_text:
            log_info(f"PDFからテキストを抽出: {paper['pdf_path']}")
            full_text = extract_text_from_pdf(paper["pdf_path"])
            
            if full_text:
                paper_db.save_full_text(paper["paper_id"], full_text)
            else:
                return f"論文 '{paper['title']}' のPDFからテキストを抽出できませんでした。"
    
        if len(full_text) > max_length:
            full_text = full_text[:max_length] + f"\n\n... (テキストが長いため切り詰められました。全文は {len(full_text)} 文字あります)"
    
        return f"タイトル: {paper['title']}\n著者: {paper['authors']}\n\n全文:\n{full_text}"
    except Exception as e:
        log_error(f"論文全文取得中にエラーが発生しました: {e}")
        return f"論文全文取得中にエラーが発生しました: {e}"

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
    try:
        log_info(f"論文全文を検索: '{query}'")
        papers = paper_db.get_papers(filter_has_fulltext=True, limit=100)  # より多くの論文を取得して検索
        
        if not papers:
            return "全文が利用可能な論文がありません。"
        
        results = []
        
        for paper in papers:
            full_text = paper["full_text"] if paper["full_text"] is not None else None
            if not full_text and paper["pdf_path"]:
                full_text = extract_text_from_pdf(paper["pdf_path"])
                if full_text:
                    paper_db.save_full_text(paper["paper_id"], full_text)
            
            if full_text and query.lower() in full_text.lower():
                index = full_text.lower().find(query.lower())
                start = max(0, index - 100)
                end = min(len(full_text), index + len(query) + 100)
                
                context = full_text[start:end].replace("\n", " ")
                if start > 0:
                    context = "..." + context
                if end < len(full_text):
                    context = context + "..."
                
                results.append({
                    "paper_id": paper["paper_id"],
                    "title": paper["title"],
                    "authors": paper["authors"],
                    "context": context
                })
                
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
    except Exception as e:
        log_error(f"全文検索中にエラーが発生しました: {e}")
        return f"全文検索中にエラーが発生しました: {e}"

@mcp.tool()
async def export_summaries(format: str = "json") -> str:
    """
    保存された論文の要約をエクスポートします。
    
    Args:
        format: エクスポート形式 ("json" または "csv")
    
    Returns:
        エクスポートの結果
    """
    try:
        log_info(f"論文要約をエクスポート: 形式 = {format}")
        papers = paper_db.get_papers(limit=1000)  # 最大1000件の論文をエクスポート
        
        if not papers:
            return "データベースに論文がありません。"
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if format.lower() == "json":
            export_path = os.path.join(DATA_DIR, f"paper_summaries_{timestamp}.json")
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(papers, f, ensure_ascii=False, indent=2)
        else:
            export_path = os.path.join(DATA_DIR, f"paper_summaries_{timestamp}.csv")
            df = pd.DataFrame(papers)
            df.to_csv(export_path, index=False)
        
        return f"論文要約を {export_path} にエクスポートしました。"
    except Exception as e:
        log_error(f"要約エクスポート中にエラーが発生しました: {e}")
        return f"要約エクスポート中にエラーが発生しました: {e}"

@mcp.tool()
async def search_papers_by_date_range(
    query: str,
    start_date: str,
    end_date: str,
    source: str = "both",
    limit: int = 5
) -> str:
    """
    指定した日付範囲内に発表された論文を検索します。
    
    Args:
        query: 検索キーワード
        start_date: 開始日 (YYYY-MM-DD形式)
        end_date: 終了日 (YYYY-MM-DD形式)
        source: 論文ソース ("arxiv", "semantic_scholar", または "both")
        limit: 各ソースから取得する論文の最大数
    
    Returns:
        検索結果の要約
    """
    try:
        # 入力値の検証
        try:
            start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
            end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
            
            if start_datetime > end_datetime:
                return "エラー: 開始日が終了日より後になっています。"
            
            arxiv_start = start_datetime.strftime("%Y%m%d")
            arxiv_end = end_datetime.strftime("%Y%m%d")
        except ValueError:
            return "エラー: 日付形式が正しくありません。YYYY-MM-DD形式で指定してください。"
        
        log_info(f"日付範囲で論文検索: '{query}', 期間 = {start_date}～{end_date}")
        papers = []
        
        # 論文を検索
        if source.lower() in ["arxiv", "both"]:
            arxiv_papers = await arxiv_client.search_by_date(query, arxiv_start, arxiv_end, limit)
            papers.extend(arxiv_papers)
            
        if source.lower() in ["semantic_scholar", "both"]:
            semantic_papers = await semantic_scholar_client.search_by_date(
                query, start_datetime.year, end_datetime.year, limit)
            semantic_papers = semantic_scholar_client.filter_papers_by_date(
                semantic_papers, start_datetime, end_datetime)
            papers.extend(semantic_papers)
        
        if not papers:
            return f"検索キーワード「{query}」で日付範囲 {start_date} から {end_date} の間に発表された論文は見つかりませんでした。"
        
        saved_count = paper_db.save_papers(papers)
        
        summary = f"検索キーワード「{query}」で日付範囲 {start_date} から {end_date} の間に発表された論文が {len(papers)}件見つかりました。\n"
        summary += f"そのうち{saved_count}件が新規としてデータベースに保存されました。\n\n"
        
        if papers:
            summary += "検索結果:\n"
            for i, paper in enumerate(papers, 1):
                published_date = paper.get("published_date", "不明")
                full_text = "（全文あり）" if paper.get("full_text_available", 0) == 1 else ""
                summary += f"{i}. {paper['title']} ({paper['source']})\n"
                summary += f"   発表日: {published_date}\n"
                summary += f"   著者: {paper['authors']}\n"
                summary += f"   URL: {paper['url']}\n"
                summary += f"   {full_text}\n\n"
        
        return summary
    except Exception as e:
        log_error(f"日付範囲による論文検索中にエラーが発生しました: {e}")
        return f"日付範囲による論文検索中にエラーが発生しました: {e}"

@mcp.tool()
async def list_saved_papers_by_date(
    start_date: str,
    end_date: str,
    keyword: str = "",
    source: str = "",
    limit: int = 10
) -> str:
    """
    指定した日付範囲内に発表された保存済みの論文の一覧を表示します。
    
    Args:
        start_date: 開始日 (YYYY-MM-DD形式)
        end_date: 終了日 (YYYY-MM-DD形式)
        keyword: 特定のキーワードでフィルタリング（オプション）
        source: 特定のソースでフィルタリング（オプション）
        limit: 表示する論文の最大数
    
    Returns:
        保存された論文の一覧
    """
    try:
        # 入力値の検証
        try:
            start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
            end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
            
            if start_datetime > end_datetime:
                return "エラー: 開始日が終了日より後になっています。"
        except ValueError:
            return "エラー: 日付形式が正しくありません。YYYY-MM-DD形式で指定してください。"
        
        log_info(f"日付範囲で保存済み論文一覧: 期間 = {start_date}～{end_date}, キーワード = '{keyword}'")
        # 論文を検索
        papers = paper_db.get_papers(
            keyword=keyword,
            source=source,
            limit=limit,
            date_from=start_date,
            date_to=end_date,
            sort_by="date"
        )
        
        if not papers:
            return f"指定された日付範囲 {start_date} から {end_date} に合致する論文は見つかりませんでした。"
        
        result = f"日付範囲 {start_date} から {end_date} の論文: 合計 {len(papers)} 件\n\n"
        
        for paper in papers:
            full_text = "（全文あり）" if paper["full_text_available"] else ""
            result += f"タイトル: {paper['title']} {full_text}\n"
            result += f"著者: {paper['authors']}\n"
            result += f"発表日: {paper['published_date']}\n"
            result += f"ソース: {paper['source']}\n"
            result += f"URL: {paper['url']}\n"
            if paper["citation_count"] > 0:
                result += f"引用数: {paper['citation_count']}\n"
            if paper["venue"]:
                result += f"掲載先: {paper['venue']}\n"
            if "abstract" in paper:
                result += f"概要: {paper['abstract'][:200]}...\n"
            result += f"収集日: {paper['collected_date']}\n"
            result += "-" * 50 + "\n"
        
        return result
    except Exception as e:
        log_error(f"日付範囲による論文一覧表示中にエラーが発生しました: {e}")
        return f"日付範囲による論文一覧表示中にエラーが発生しました: {e}"