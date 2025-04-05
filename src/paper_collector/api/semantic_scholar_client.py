"""
Semantic Scholar API client for fetching academic papers.
"""
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from ..pdf.pdf_handler import download_pdf


class SemanticScholarClient:
    """Client for interacting with the Semantic Scholar API."""
    
    def __init__(self, papers_dir: str, api_delay: float = 1.0):
        """
        Initialize the Semantic Scholar client.
        
        Args:
            papers_dir: Directory to save downloaded PDFs
            api_delay: Delay between API calls in seconds
        """
        self.papers_dir = papers_dir
        self.api_delay = api_delay
        self.api_base_url = "https://api.semanticscholar.org/graph/v1"
        self.headers = {
            "Accept": "application/json"
        }
    
    async def search(self, query: str, limit: int = 5, min_citations: int = 0, 
                   sort_by: str = "relevance") -> List[Dict[str, Any]]:
        """
        Search for papers on Semantic Scholar.
        
        Args:
            query: Search query
            limit: Maximum number of results
            min_citations: Minimum number of citations
            sort_by: Sort criteria ("relevance", "citations", "recency")
            
        Returns:
            List of paper dictionaries
        """
        url = f"{self.api_base_url}/paper/search"
        fields = "title,authors,abstract,url,year,venue,openAccessPdf,citationCount,venue,influentialCitationCount"
        
        params = {
            "query": query,
            "limit": limit * 2,  # Request more to filter by citations
            "fields": fields
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params, headers=self.headers)
                if response.status_code != 200:
                    if response.status_code == 429:
                        print("Reached Semantic Scholar API rate limit. Waiting...")
                        await asyncio.sleep(5)
                    else:
                        print(f"Semantic Scholar API search error: status code {response.status_code}")
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
                    
                    pdf_path = None
                    if pdf_url:
                        pdf_path = await download_pdf(pdf_url, paper_data["paper_id"], self.papers_dir)
                    
                    paper_data["pdf_path"] = pdf_path
                    paper_data["full_text_available"] = 1 if pdf_path else 0
                    
                    all_results.append(paper_data)
                
                if sort_by == "citations":
                    all_results.sort(key=lambda x: x["citation_count"], reverse=True)
                
                return all_results[:limit]
        except Exception as e:
            print(f"Semantic Scholar search error: {e}")
            return []
    
    async def search_by_date(self, query: str, start_year: int, end_year: int, 
                           limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search for papers published within a year range.
        
        Args:
            query: Search query
            start_year: Start year
            end_year: End year
            limit: Maximum number of results
            
        Returns:
            List of paper dictionaries
        """
        try:
            all_results = []
            years_to_search = range(start_year, end_year + 1)
            
            # Calculate papers per year to maintain overall limit
            papers_per_year = max(1, limit // len(years_to_search)) if years_to_search else limit
            
            for year in years_to_search:
                url = f"{self.api_base_url}/paper/search"
                fields = "title,authors,abstract,url,year,venue,openAccessPdf,citationCount,venue,influentialCitationCount"
                
                params = {
                    "query": query,
                    "limit": papers_per_year * 2,  # Request more to account for filtering
                    "fields": fields,
                    "year": year
                }
                
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(url, params=params, headers=self.headers)
                    if response.status_code != 200:
                        if response.status_code == 429:
                            print("Reached Semantic Scholar API rate limit. Waiting...")
                            await asyncio.sleep(5)
                        else:
                            print(f"Semantic Scholar API search error: status code {response.status_code}")
                        continue
                    
                    data = response.json()
                    
                    for paper in data.get("data", []):
                        if not paper.get("abstract"):
                            continue
                            
                        authors = [author.get("name", "") for author in paper.get("authors", [])]
                        venue = paper.get("venue", "")
                        
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
                            "published_date": str(paper.get("year", "")),
                            "source": "Semantic Scholar",
                            "keywords": query,
                            "citation_count": paper.get("citationCount", 0) or 0,
                            "venue": venue,
                            "venue_impact_score": 0.0
                        }
                        
                        pdf_path = None
                        if pdf_url:
                            pdf_path = await download_pdf(pdf_url, paper_data["paper_id"], self.papers_dir)
                        
                        paper_data["pdf_path"] = pdf_path
                        paper_data["full_text_available"] = 1 if pdf_path else 0
                        
                        all_results.append(paper_data)
                
                # Add a delay between year queries to avoid rate limiting
                await asyncio.sleep(self.api_delay)
            
            # Sort by citation count and limit results
            all_results.sort(key=lambda x: x["citation_count"], reverse=True)
            return all_results[:limit]
        except Exception as e:
            print(f"Semantic Scholar date range search error: {e}")
            return []
    
    def filter_papers_by_date(self, papers: List[Dict[str, Any]], 
                             start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """
        Filter papers by publication date.
        
        Args:
            papers: List of paper dictionaries
            start_date: Minimum publication date
            end_date: Maximum publication date
            
        Returns:
            Filtered list of paper dictionaries
        """
        filtered_papers = []
        
        for paper in papers:
            published_date_str = paper.get("published_date", "")
            
            # Handle year-only dates
            if published_date_str and published_date_str.isdigit() and len(published_date_str) == 4:
                published_date_str = f"{published_date_str}-01-01"
            
            try:
                if published_date_str:
                    published_date = datetime.strptime(published_date_str, "%Y-%m-%d")
                    if start_date <= published_date <= end_date:
                        filtered_papers.append(paper)
            except ValueError:
                continue
        
        return filtered_papers
