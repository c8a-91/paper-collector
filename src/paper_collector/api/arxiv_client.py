"""
arXiv API client for fetching academic papers.
"""
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import arxiv

from ..pdf.pdf_handler import download_pdf


class ArxivClient:
    """Client for interacting with the arXiv API."""
    
    def __init__(self, papers_dir: str, api_delay: float = 1.0):
        """
        Initialize the arXiv client.
        
        Args:
            papers_dir: Directory to save downloaded PDFs
            api_delay: Delay between API calls in seconds
        """
        self.papers_dir = papers_dir
        self.api_delay = api_delay
    
    async def search(self, query: str, limit: int = 5, min_citations: int = 0, 
                   sort_by: str = "relevance") -> List[Dict[str, Any]]:
        """
        Search for papers on arXiv.
        
        Args:
            query: Search query
            limit: Maximum number of results
            min_citations: Minimum number of citations
            sort_by: Sort criteria ("relevance", "recency", "citations")
            
        Returns:
            List of paper dictionaries
        """
        try:
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
            
            arxiv_papers = []
            citation_tasks = []
            
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
                
                arxiv_papers.append(paper_data)
                citation_tasks.append(self._get_citation_data(arxiv_id))
            
            if citation_tasks:
                batch_size = 5
                results = []
                
                for i in range(0, len(citation_tasks), batch_size):
                    batch = citation_tasks[i:i+batch_size]
                    batch_results = await asyncio.gather(*batch)
                    results.extend(batch_results)
                    if i + batch_size < len(citation_tasks):
                        await asyncio.sleep(self.api_delay)
            else:
                results = []
            
            final_results = []
            for paper_data, citation_info in zip(arxiv_papers, results):
                citation_count = citation_info.get("citation_count", 0)
                if citation_count < min_citations:
                    continue
                
                paper_data["citation_count"] = citation_count
                paper_data["venue"] = citation_info.get("venue", "")
                paper_data["venue_impact_score"] = citation_info.get("venue_impact_score", 0.0)
                
                pdf_path = await download_pdf(paper_data["pdf_url"], paper_data["paper_id"], self.papers_dir)
                
                paper_data["pdf_path"] = pdf_path
                paper_data["full_text_available"] = 1 if pdf_path else 0
                
                final_results.append(paper_data)
            
            if sort_by == "citations":
                final_results.sort(key=lambda x: x["citation_count"], reverse=True)
            
            return final_results[:limit]
        except Exception as e:
            print(f"arXiv search error: {e}")
            return []
    
    async def search_by_date(self, query: str, start_date: str, end_date: str, 
                           limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search for papers within a date range.
        
        Args:
            query: Search query
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            limit: Maximum number of results
            
        Returns:
            List of paper dictionaries
        """
        try:
            date_filter = f" AND submittedDate:[{start_date} TO {end_date}]"
            full_query = query + date_filter
            
            client = arxiv.Client(
                page_size=limit * 2,
                delay_seconds=3.0,
                num_retries=3
            )
            
            search = arxiv.Search(
                query=full_query,
                max_results=limit * 2,
                sort_by=arxiv.SortCriterion.SubmittedDate
            )
            
            arxiv_papers = []
            citation_tasks = []
            
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
                    "published_date": paper.published.strftime("%Y-%m-%d") if hasattr(paper, "published") else "",
                    "source": "arXiv",
                    "keywords": query,
                    "arxiv_id": arxiv_id
                }
                
                arxiv_papers.append(paper_data)
                citation_tasks.append(self._get_citation_data(arxiv_id))
            
            if citation_tasks:
                batch_size = 5
                results = []
                
                for i in range(0, len(citation_tasks), batch_size):
                    batch = citation_tasks[i:i+batch_size]
                    batch_results = await asyncio.gather(*batch)
                    results.extend(batch_results)
                    if i + batch_size < len(citation_tasks):
                        await asyncio.sleep(self.api_delay)
            else:
                results = []
            
            final_results = []
            for paper_data, citation_info in zip(arxiv_papers, results):
                paper_data["citation_count"] = citation_info.get("citation_count", 0)
                paper_data["venue"] = citation_info.get("venue", "")
                paper_data["venue_impact_score"] = citation_info.get("venue_impact_score", 0.0)
                
                pdf_path = await download_pdf(paper_data["pdf_url"], paper_data["paper_id"], self.papers_dir)
                
                paper_data["pdf_path"] = pdf_path
                paper_data["full_text_available"] = 1 if pdf_path else 0
                
                final_results.append(paper_data)
            
            return final_results
        except Exception as e:
            print(f"arXiv date range search error: {e}")
            return []
    
    async def _get_citation_data(self, arxiv_id: str) -> Dict[str, Any]:
        """
        Get citation data for an arXiv paper from Semantic Scholar.
        
        Args:
            arxiv_id: arXiv ID
            
        Returns:
            Dictionary with citation information
        """
        import httpx
        
        url = f"https://api.semanticscholar.org/graph/v1/paper/arXiv:{arxiv_id}"
        params = {
            "fields": "citationCount,venue,influentialCitationCount"
        }
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "citation_count": data.get("citationCount", 0) or 0,
                        "venue": data.get("venue", ""),
                        "venue_impact_score": 0.0
                    }
                elif response.status_code == 429:
                    print("Reached Semantic Scholar API rate limit. Waiting...")
                    await asyncio.sleep(5)
                    return {"citation_count": 0, "venue": "", "venue_impact_score": 0.0}
                else:
                    print(f"Semantic Scholar API call error: status code {response.status_code}")
                    return {"citation_count": 0, "venue": "", "venue_impact_score": 0.0}
        except Exception as e:
            print(f"Citation data retrieval error: {e}")
            return {"citation_count": 0, "venue": "", "venue_impact_score": 0.0}
