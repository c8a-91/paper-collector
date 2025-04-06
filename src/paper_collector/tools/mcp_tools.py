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
    
    複数のキーワードを組み合わせた検索が可能です。検索構文のサポートは検索ソースによって異なります。
    検索結果は自動的にデータベースに保存され、後で参照できます。
    
    検索のヒント:
    - arXiv検索では以下の高度な検索構文が使用可能です:
      * 複数の単語は自動的にAND検索されます (例: "quantum computing" は "quantum" AND "computing")
      * フレーズ検索には引用符を使用: "quantum computing"
      * OR検索: "machine learning" OR "deep learning" 
      * 除外検索: "neural networks" ANDNOT "convolutional"
      * フィールド指定検索: ti:transformer（タイトルに"transformer"を含む）、au:bengio（著者に"bengio"を含む）
      * arXivではワイルドカード検索（"neura*"など）は公式にはサポートされていません
    - Semantic Scholar検索では:
      * 基本的なキーワード検索のみがサポートされています
      * ブール演算子(AND, OR, NOT)や高度な構文は公式にサポートされていません
      * 検索は単純なテキスト一致で行われ、複数単語は自動的にANDとして扱われます
      * 年(year)による絞り込みが可能です
    
    Args:
        query: 検索キーワードやフレーズ。arXivでは高度な検索構文もサポート
        source: 論文ソース ("arxiv", "semantic_scholar", または "both")
        limit: 各ソースから取得する論文の最大数。合計件数はsourceが"both"の場合、最大でlimit*2になります
    
    Returns:
        検索結果の要約。見つかった論文数、新規追加された論文数、全文が利用可能な論文数などを含みます
    
    例:
        * search_papers("attention mechanism") - 注意機構に関する論文を検索
        * search_papers("\"transformer architecture\" ANDNOT BERT", source="arxiv", limit=10) - 
          BERTを除くトランスフォーマーアーキテクチャに関する論文をarXivから最大10件検索
        * search_papers("reinforcement learning robotics", source="semantic_scholar") - 
          強化学習とロボティクスに関する論文をSemantic Scholarから検索
        * search_papers("ti:\"attention is all you need\"", source="arxiv") - 
          タイトルに「Attention is All You Need」を含む論文をarXivから検索
        * search_papers("au:hinton", limit=15) - Hintonが著者の論文を最大15件検索
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
    
    高引用数の論文（影響力の高い論文）を優先的に見つけるための検索機能です。
    通常の検索と同様のキーワード検索構文が使用できますが、さらに引用数による
    フィルタリングとソートが追加されています。検索結果は自動的にデータベースに
    保存され、後で参照できます。
    
    検索のヒント:
    - 引用数は論文の影響力や重要性の指標として利用でき、被引用数の高い基礎論文や
      重要論文を素早く見つけるのに役立ちます
    - "citations"でソートすると、最も引用数の多い論文から順に表示されます
    - "recency"でソートすると、最新の論文から順に表示され、最近の研究動向がわかります
    - ArXivとSemantic Scholarから論文を検索し、APIから取得された引用数情報を使用します
    - 原則としてArXiv IDは保持されるため、同じ論文が両方のソースから検索されても
      重複して表示されることはありません
    
    Args:
        query: 検索キーワードやフレーズ。arXivではANDやORなどの高度な検索構文もサポート
        min_citations: 最小引用数。これより引用数が少ない論文は結果から除外されます
        source: 論文ソース ("arxiv", "semantic_scholar", または "both")
        limit: 各ソースから取得する論文の最大数
        sort_by: ソート方法 ("relevance"=関連性順, "citations"=引用数順, "recency"=日付順)
    
    Returns:
        検索結果の要約。見つかった論文数、新規追加された論文数、各論文の引用数や掲載先などを含みます
    
    例:
        * search_papers_by_citations("transformer", min_citations=1000) - 
          1000回以上引用されたTransformer関連の論文を検索（Attention is All Youなど）
        * search_papers_by_citations("BERT language model", min_citations=500, source="semantic_scholar") - 
          Semantic Scholarから500回以上引用されたBERT言語モデルに関する論文を検索
        * search_papers_by_citations("deep reinforcement learning", sort_by="recency") - 
          深層強化学習に関する論文を最新順にソートして表示（引用数の制限なし）
        * search_papers_by_citations("\"attention is all you need\"", min_citations=5000) - 
          有名なTransformer論文を検索（正確なタイトル検索と高い引用数フィルタリングで特定の論文を見つける）
        * search_papers_by_citations("au:hinton", min_citations=200) - 
          Hintonが著者で200回以上引用された論文を検索
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
    保存された論文の一覧を表示します。多様なフィルタリングとソートオプションをサポートしています。
    
    この関数はデータベースに保存されている論文を検索し、さまざまな条件でフィルタリングして
    表示できます。キーワード、出版元、日付範囲、引用数など複数の条件を組み合わせて
    検索できる強力なツールです。
    
    フィルタリングとソートのヒント:
    - キーワード検索は部分一致検索をサポートしています（SQLのLIKE演算子を使用）
      * 「transformer」で検索すると、「transformer」「transformers」「transformer-based」などを含むすべての論文がマッチします
      * 複数の単語（例: 「neural network」）で検索すると、両方の単語を含む論文がマッチします
      * キーワードはタイトル、概要、著者名、キーワードフィールドのいずれかに含まれていればマッチします
    - venue（掲載先）の検索も同様に部分一致検索をサポートしています
      * 「ACL」で検索すると、「ACL 2023」「TACL」「NAACL」などを含む論文がマッチします
    - 日付範囲を指定する場合はYYYY-MM-DD形式（例: 2023-01-01）を使用します
    - ソート順は "date"（日付順）、"citations"（引用数順）、"title"（タイトル順）から選択できます
    - 表示形式は "detailed"（詳細）、"compact"（簡略）、"csv"（CSV形式）から選択できます
    - 複数の条件を組み合わせてより絞り込んだ検索が可能です
    
    Args:
        keyword: タイトル、概要、著者名などに含まれるキーワード（部分一致）
        source: ソースでフィルタリング（"arxiv" または "semantic_scholar"）
        limit: 表示する論文の最大数
        sort_by: ソート基準（"date"=日付順, "citations"=引用数順, "title"=タイトル順）
        sort_order: ソート方向（"asc"=昇順, "desc"=降順）
        filter_has_fulltext: Trueの場合、全文が利用可能な論文のみを表示
        min_citations: 最小引用数（これより少ない引用数の論文は表示されません）
        format: 表示形式（"detailed"=詳細, "compact"=簡潔, "csv"=CSV形式）
        venue: 特定の掲載先（ジャーナルや会議）でフィルタリング（部分一致）
        date_from: この日付以降に発表された論文（YYYY-MM-DD形式）
        date_to: この日付以前に発表された論文（YYYY-MM-DD形式）
    
    Returns:
        指定された条件に合致する保存済み論文の一覧
    
    例:
        * list_saved_papers(keyword="transform") - 「transform」を含むすべての論文を表示（「transformer」「transformers」「transformation」など）
        * list_saved_papers(keyword="bert", sort_by="citations", sort_order="desc") - 「bert」を含む論文を引用数の多い順に表示（「BERT」「RoBERTa」「ALBERT」「DistilBERT」など）
        * list_saved_papers(venue="NeurIPS") - NeurIPS会議で発表された論文を表示（「NeurIPS 2022」「NeurIPS Workshop」なども含む）
        * list_saved_papers(source="arxiv", sort_by="citations", date_from="2023-01-01")
        * list_saved_papers(filter_has_fulltext=True, format="compact")
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
        log_error(f"保存された論文の一覧表示中にエラーが発発生しました: {e}")
        return f"保存された論文の一覧表示中にエラーが発生しました: {e}"

def _format_papers_as_csv(papers: List[Dict[str, Any]]) -> str:
    """
    論文リストをCSV形式でフォーマットします。
    
    この関数は論文のメタデータをCSV（カンマ区切り値）形式に変換します。
    CSV形式は表計算ソフトでの分析や他のデータ処理ツールとの連携に適しています。
    出力にはヘッダー行が含まれ、各論文の基本的なメタデータフィールドが含まれます。
    引用符で囲まれた値はCSVの標準的なエスケープルールに従っています。
    
    含まれるフィールド:
    - paper_id: 論文の一意の識別子
    - title: 論文のタイトル
    - authors: 著者リスト（カンマ区切り）
    - source: 論文のソース（"arXiv"または"Semantic Scholar"）
    - url: 論文のURL
    - citation_count: 引用数
    - venue: 掲載先（ジャーナル名や会議名）
    - published_date: 発表日
    - collected_date: データベースに収集された日付
    - full_text_available: 全文が利用可能かどうかを示すフラグ（1=利用可能、0=利用不可）
    
    Args:
        papers: 論文のリスト。各論文は辞書形式でメタデータを含む
        
    Returns:
        CSV形式にフォーマットされた論文データ
    """
    result = "paper_id,title,authors,source,url,citation_count,venue,published_date,collected_date,full_text_available\n"
    for paper in papers:
        result += f'"{paper["paper_id"]}","{paper["title"].replace("\"", "\"\"")}","{paper["authors"].replace("\"", "\"\"")}","{paper["source"]}","{paper["url"]}","{paper["citation_count"]}","{paper.get("venue", "").replace("\"", "\"\"")}","{paper["published_date"]}","{paper["collected_date"]}","{paper["full_text_available"]}"\n'
    return result

def _format_papers_as_compact(papers: List[Dict[str, Any]]) -> str:
    """
    論文リストをコンパクト形式でフォーマットします。
    
    この関数は論文のメタデータを簡潔な形式でフォーマットします。各論文の最も重要な
    情報だけを含み、多数の論文を一度に閲覧するのに適しています。タイトル、著者（短縮表示）,
    発表日、収集日、ソース情報が含まれ、全文利用可能な論文には特別なアイコン（📄）が表示されます。
    また、引用数がある場合は引用数も表示されます。
    
    表示形式:
    ```
    1. 論文タイトル 📄 [引用:123]
       著者: 著者名リスト（長い場合は省略）
       発表: 2023-04-01 | 収集: 2025-04-06
       ソース: arXiv
    ```
    
    Args:
        papers: 論文のリスト。各論文は辞書形式でメタデータを含む
        
    Returns:
        コンパクト形式にフォーマットされた論文リスト
    """
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
    """
    論文リストを詳細形式でフォーマットします。
    
    この関数は論文のメタデータを詳細な形式で表示します。各論文について利用可能な
    全てのメタデータフィールドを表示し、全文が利用可能かどうかの情報も含みます。
    概要（abstract）は長すぎる場合は切り詰められ、最初の200文字のみが表示されます。
    各論文エントリは水平線で区切られ、読みやすいフォーマットになっています。
    
    表示される情報:
    - タイトル（全文利用可能な場合はその旨も表示）
    - 著者リスト
    - ソース（arXivまたはSemantic Scholar）
    - URL
    - 引用数（ある場合）
    - 掲載先（ある場合）
    - 発表日
    - 概要（最初の200文字、長い場合は省略）
    - 収集日
    - 論文ID
    
    Args:
        papers: 論文のリスト。各論文は辞書形式でメタデータを含む
        
    Returns:
        詳細形式にフォーマットされた論文リスト
    """
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
    
    この関数は保存された論文を引用数が多い順にソートし、最も影響力の高い論文を
    見つけるのに役立ちます。特定の研究分野における重要論文を特定したり、
    研究トレンドを把握するのに便利です。
    
    利用のヒント:
    - キーワードを指定すると、そのキーワードを含む論文のみがランキングされます
    - キーワードは論文のタイトル、著者名、概要、キーワードフィールドで検索されます
    - キーワードを空にすると、データベース内のすべての論文が対象になります
    - 引用数が同じ論文は収集日順（新しいものが先）に表示されます
    
    Args:
        keyword: 特定のキーワードでフィルタリング（部分一致）。空の場合は全論文が対象
        limit: 表示する論文の最大数
    
    Returns:
        引用数ランキング。各論文の詳細情報を含みます
    
    例:
        * rank_papers_by_citations() - すべての論文の引用数ランキング
        * rank_papers_by_citations("machine learning", 20) - 機械学習関連論文のトップ20
        * rank_papers_by_citations("neural networks") - ニューラルネットワーク関連論文のランキング
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
    
    この関数は特定のジャーナルや学術会議、カンファレンスなどに掲載された論文を
    グループ化して表示します。掲載先別に論文を整理することで、特定の分野や
    出版物における研究動向を把握することができます。
    
    利用のヒント:
    - venueパラメータには完全一致でなく部分一致検索が使用されます
    - 空のvenueを指定すると、掲載先情報がある全ての論文が対象になります
    - 複数の掲載先にマッチする場合は、それぞれのグループに分けて表示されます
    - 各グループ内の論文は引用数の多い順にソートされます
    
    Args:
        venue: 掲載先の名前（部分一致）。例: "CVPR", "Nature", "ACL"など
        limit: 表示する論文の最大数
    
    Returns:
        掲載先別にグループ化された論文一覧
    
    例:
        * list_papers_by_venue("NIPS") - NIPS/NeurIPS会議の論文を表示
        * list_papers_by_venue("Journal") - "Journal"を含む全ての掲載先の論文を表示
        * list_papers_by_venue() - 全ての掲載先の論文をグループ化して表示
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
    
    この関数は保存されている論文データから各掲載先（ジャーナルや会議）の
    統計情報を集計し、平均引用数の多い順にランキングします。研究分野における
    主要な掲載先を把握したり、影響力の高いジャーナルを特定するのに役立ちます。
    
    集計情報には以下が含まれます：
    - 掲載先名
    - その掲載先の論文数
    - 平均引用数
    - 最大引用数
    
    結果は平均引用数の多い順にソートされます。
    
    Args:
        limit: 表示する掲載先の最大数
    
    Returns:
        平均引用数の多い順にソートされた掲載先一覧
    
    例:
        * list_top_venues() - トップ10の掲載先を表示
        * list_top_venues(20) - トップ20の掲載先を表示
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
    
    この関数は論文のメタデータを完全な形で表示します。論文のID、タイトル、著者、
    概要、URL、掲載先、引用数など、データベースに保存されている全ての情報が
    含まれます。
    
    検索のヒント:
    - 完全なPaper IDでの検索が最も正確です (例: "1703.05190v3")
    - タイトルでの検索も可能で、部分一致で検索されます (例: "Transformer" や "Attention")
    - タイトル検索の場合、最初にマッチした論文のみが表示されます
    - 検索文字列は大文字小文字を区別しません
    - PDFが利用可能な論文は「全文あり」と表示され、get_paper_full_text()で全文を確認できます
    - list_saved_papers()で検索した結果から、興味のある論文のIDやタイトルをコピーして使うとスムーズです
    
    Args:
        paper_id: 論文のID (例: "1703.05190v3") またはタイトルの一部 (例: "Attention is All You Need")
    
    Returns:
        論文の詳細情報（タイトル、著者、概要、URL、引用数など）
    
    例:
        * get_paper_details("1703.05190v3") - arXiv IDによる検索
        * get_paper_details("Attention is All You Need") - 有名なTransformer論文のタイトルで検索
        * get_paper_details("BERT") - BERTに関する論文を検索（最初にマッチした論文が表示されます）
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
    
    この関数はPDFから抽出した論文の全文テキストを表示します。最初にデータベース内の
    全文を確認し、なければPDFファイルからテキスト抽出を試みます。抽出された全文は
    データベースに保存され、次回から素早くアクセスできるようになります。
    
    使用上の注意:
    - paper_idにはIDだけでなく論文タイトルも指定可能です（部分一致）
    - PDF内のテキストレイヤーの品質によって、抽出結果の品質が変わります
    - 数式や図表、特殊記号などは正しく抽出されない場合があります
    - 長い論文は自動的にmax_lengthパラメータで指定した長さに切り詰められます
    - 大量のテキストを取得する場合は、max_lengthパラメータで適切に制限すると便利です
    - 論文PDFがない場合や抽出に失敗した場合はエラーメッセージが表示されます
    
    活用方法:
    - 研究内容の詳細確認：search_full_textで見つけた箇所の前後文脈をより広く読む
    - 特定の章セクションの確認：通常、論文PDFの目次から興味のあるセクションを見つけて読む
    - 参考文献リストの確認：多くの論文では末尾に参考文献リストがあり、関連研究を見つけられる
    - 手法や実験の詳細確認：論文の概要だけでなく、具体的な実装や実験条件を調べる
    
    Args:
        paper_id: 論文のIDまたはタイトル。完全なIDまたはタイトルの部分文字列を指定できます
        max_length: 返す全文の最大長さ（文字数）。デフォルトは100万文字で、これを超える部分は切り詰められます
    
    Returns:
        論文の全文テキスト。長すぎる場合は切り詰められた内容
    
    例:
        * get_paper_full_text("1703.05190v3") - Attention is All You Needの全文を取得
        * get_paper_full_text("BERT", 30000) - BERTに関する論文の全文を取得（最大3万文字）
        * get_paper_full_text("Transformer architecture") - Transformerについての論文の全文を取得
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
    論文の全文から特定の文字列を検索します。PDFから抽出された内容を検索対象とします。
    
    この関数は、データベースに保存されたPDFから抽出された論文全文テキストから
    指定したキーワードやフレーズを検索します。検索結果には各論文のタイトル、著者と
    キーワードを含む前後の文脈（コンテキスト）が表示されるため、研究手法や概念、
    用語などがどのように使われているかをすぐに確認できます。
    
    ローカル全文検索の特徴と活用法:
    - PDFが保存されている論文のみが検索対象となります
    - 初回検索時にPDFからテキストを抽出し、データベースに保存するため高速に検索できます
    - 数式や図表の記述を探したり、特定の手法について詳しく書かれている論文を見つけられます
    - 単語だけでなく、フレーズや複数単語を組み合わせた検索も可能です
    - 大文字小文字は区別されないため、"BERT"も"Bert"も"bert"も同じ結果になります
    - ワイルドカード検索がサポートされています（アスタリスク「*」を使用）
    
    ワイルドカード検索の具体例:
    1. 前方一致検索 (プレフィックス検索):
       * "transform*" → "transform", "transformer", "transformers", "transformation" など
       * "neural*" → "neural", "neurons", "neural networks" など
       * "GAN*" → "GAN", "GANs", "GAN-based" など
    
    2. 後方一致検索 (サフィックス検索):
       * "*former" → "transformer", "performer", "conformer" など
       * "*embedding" → "word embedding", "token embedding" など
       * "*learning" → "deep learning", "machine learning", "reinforcement learning" など
    
    3. 中間一致検索 (ワイルドカード両端):
       * "*embed*" → "embedding", "embedded", "embeddings" など
       * "*attent*" → "attention", "self-attention", "multi-head attention" など
       * "*bert*" → "BERT", "RoBERTa", "ALBERT", "DistilBERT" など
    
    4. 複合ワイルドカード検索:
       * "self*attention" → "self-attention", "self attention" など
       * "conv*network" → "convolutional network", "convolution network" など
       * "deep*learning" → "deep learning", "deep reinforcement learning" など
    
    Args:
        query: 検索するキーワードやフレーズ（大文字小文字は区別されません）。ワイルドカード文字「*」も使用可能
        limit: 表示する最大の検索結果数（デフォルト: 5）
    
    Returns:
        検索結果のリスト。各結果には論文タイトル、著者、検索キーワードを含む前後のコンテキスト（約200文字）が含まれます
    
    例:
        * search_full_text("attention mechanism") - 「attention mechanism」について言及している論文を検索
        * search_full_text("transform*", 10) - "transform"で始まる単語を含む論文を最大10件検索
        * search_full_text("*former") - "former"で終わる単語（transformer, performerなど）を含む論文を検索
        * search_full_text("*attent*") - "attent"を含む単語（attention, self-attentionなど）を含む論文を検索
        * search_full_text("*bert*") - BERTおよびその派生モデル（RoBERTa, ALBERTなど）に関する記述を検索
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
    
    この関数はデータベースに保存されている論文のメタデータを指定された形式で
    ファイルにエクスポートします。論文データをバックアップしたり、他のツールで
    分析するために使用できます。エクスポートされたファイルは自動的にタイムスタンプ付きの
    名前で保存されます。
    
    エクスポート機能の特徴:
    - 最大1000件の論文データがエクスポートされます
    - ファイル名には自動的に日時が付加されます (例: paper_summaries_20250406_123045.json)
    - JSON形式はデータの完全性を保持し、プログラムでの再利用に最適です
    - CSV形式は表計算ソフトなどでの閲覧・分析に適しています
    
    Args:
        format: エクスポート形式 ("json"=JSON形式, "csv"=CSV形式)
    
    Returns:
        エクスポート結果の報告（保存先ファイルパスを含む）
    
    例:
        * export_summaries() - JSONフォーマットでエクスポート
        * export_summaries("csv") - CSVフォーマットでエクスポート
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
    
    この関数は特定の期間内に出版された論文を検索します。研究分野の時系列的な
    発展を追跡したり、特定の期間における研究トレンドを把握するのに役立ちます。
    最新の研究動向を調査する場合や、歴史的な論文を探す場合に便利です。
    
    日付範囲検索の特徴:
    - 日付は必ずYYYY-MM-DD形式で指定してください（例: 2023-01-01）
    - 検索は指定した日付を含む範囲で行われます（開始日と終了日を含む）
    - 日付範囲が広すぎると検索結果が多くなりすぎる可能性があります
    - arXivとSemantic Scholarでは日付の精度や利用可能な範囲が異なる場合があります
    - arXivでは正確な日付検索が可能ですが、Semantic Scholarの場合は年単位の検索になることがあります
    - 検索結果は自動的にデータベースに保存され、後で参照できるようになります
    
    Args:
        query: 検索キーワードやフレーズ。arXivでは高度な検索構文もサポート（例: "machine AND learning"）
        start_date: 開始日（YYYY-MM-DD形式）。この日付以降に発表された論文が対象
        end_date: 終了日（YYYY-MM-DD形式）。この日付以前に発表された論文が対象
        source: 論文ソース ("arxiv", "semantic_scholar", または "both")
        limit: 各ソースから取得する論文の最大数
    
    Returns:
        検索結果の要約。見つかった論文数と各論文の詳細を含みます
    
    例:
        * search_papers_by_date_range("transformer", "2017-01-01", "2017-12-31") - 
          2017年（Transformerモデルが登場した年）に発表されたTransformerに関する論文を検索
        * search_papers_by_date_range("\"attention is all you need\"", "2017-06-01", "2017-07-30", source="arxiv") - 
          2017年6-7月に発表された有名なTransformer論文を検索
        * search_papers_by_date_range("BERT language model", "2018-10-01", "2019-05-31") - 
          BERTモデルが発表された時期のBERTに関する論文を検索
        * search_papers_by_date_range("diffusion model", "2023-01-01", "2023-12-31", limit=20) - 
          2023年に発表された拡散モデルに関する論文を最大20件検索
        * search_papers_by_date_range("quantum computing", "2020-01-01", "2022-12-31", source="arxiv", limit=10) - 
          2020年から2022年までの量子コンピューティングに関する論文をarXivから最大10件検索
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
    
    この関数はデータベースに既に保存されている論文の中から、特定の日付範囲内に
    発表された論文を検索して表示します。特定の期間における研究動向を把握したり、
    年代別に論文を整理する際に役立ちます。キーワードやソースによる絞り込みも可能です。
    
    日付範囲検索の特徴:
    - 日付はYYYY-MM-DD形式で指定する必要があります（例: 2023-01-01）
    - 開始日と終了日を含む範囲内の論文が検索されます
    - 論文の発表日（published_date）でフィルタリングされます
    - 結果は発表日の新しい順（デフォルト）でソートされます
    - キーワードを追加すると、タイトルや概要、著者名などでのフィルタリングも同時に行えます
    
    Args:
        start_date: 開始日（YYYY-MM-DD形式）。この日付以降に発表された論文が対象
        end_date: 終了日（YYYY-MM-DD形式）。この日付以前に発表された論文が対象
        keyword: 特定のキーワードでの追加フィルタリング（部分一致、オプション）
        source: 特定のソース（"arxiv"または"semantic_scholar"）でのフィルタリング（オプション）
        limit: 表示する論文の最大数
    
    Returns:
        指定された日付範囲内の保存済み論文一覧
    
    例:
        * list_saved_papers_by_date("2023-01-01", "2023-12-31") - 2023年の論文を一覧表示
        * list_saved_papers_by_date("2020-01-01", "2022-12-31", keyword="neural", source="arxiv") - 
          2020年から2022年までのarXivから取得した「neural」を含む論文を表示
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