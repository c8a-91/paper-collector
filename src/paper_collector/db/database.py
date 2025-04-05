"""
Database operations for the paper collector.
"""
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime


class PaperDatabase:
    """Handles database operations for paper storage and retrieval."""
    
    def __init__(self, db_path: str):
        """
        Initialize the database handler.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self.connection = None
        self.initialize()
    
    def initialize(self) -> None:
        """Initialize the database schema if it doesn't exist."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                
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
                
                # Add columns if they don't exist
                self._add_column_if_not_exists(c, "papers", "citation_count", "INTEGER DEFAULT 0")
                self._add_column_if_not_exists(c, "papers", "venue", "TEXT")
                self._add_column_if_not_exists(c, "papers", "venue_impact_score", "REAL DEFAULT 0.0")
                
                # Create indexes for improved query performance
                c.execute("CREATE INDEX IF NOT EXISTS idx_papers_title ON papers(title)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_papers_keywords ON papers(keywords)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_papers_citation_count ON papers(citation_count)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_papers_venue ON papers(venue)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_papers_source ON papers(source)")
                
                conn.commit()
        except sqlite3.Error as e:
            print(f"Database initialization error: {e}")

    def close(self) -> None:
        """
        Close any open database connections.
        This should be called when the database is no longer needed.
        """
        if self.connection is not None:
            try:
                self.connection.close()
                self.connection = None
            except sqlite3.Error as e:
                print(f"Database close error: {e}")
    
    def _add_column_if_not_exists(self, cursor: sqlite3.Cursor, table: str, column: str, 
                                column_type: str) -> None:
        """
        Add a column to a table if it doesn't exist.
        
        Args:
            cursor: SQLite cursor
            table: Table name
            column: Column name
            column_type: SQL column type definition
        """
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
        except sqlite3.OperationalError:
            # Column already exists
            pass

    def save_papers(self, papers: List[Dict[str, Any]]) -> int:
        """
        Save papers to the database, updating existing papers if needed.
        
        Args:
            papers: List of paper dictionaries
            
        Returns:
            Number of new papers added
        """
        if not papers:
            return 0
        
        new_papers_count = 0
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                
                for paper in papers:
                    c.execute("SELECT paper_id FROM papers WHERE paper_id = ?", (paper["paper_id"],))
                    existing_paper = c.fetchone()
                    
                    if existing_paper is None:
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
                        # Update existing paper with new information
                        c.execute('''
                        UPDATE papers 
                        SET title = ?, authors = ?, abstract = ?, url = ?, pdf_path = ?,
                            full_text_available = ?, published_date = ?, source = ?, keywords = ?,
                            citation_count = ?, venue = ?, venue_impact_score = ?
                        WHERE paper_id = ?
                        ''', (
                            paper["title"],
                            paper["authors"],
                            paper["abstract"],
                            paper["url"],
                            paper.get("pdf_path", None),
                            paper.get("full_text_available", 0),
                            paper["published_date"],
                            paper["source"],
                            paper["keywords"],
                            paper.get("citation_count", 0),
                            paper.get("venue", ""),
                            paper.get("venue_impact_score", 0.0),
                            paper["paper_id"]
                        ))
                
                conn.commit()
                return new_papers_count
        except sqlite3.Error as e:
            print(f"Database save error: {e}")
            return 0
    
    def save_full_text(self, paper_id: str, full_text: str) -> bool:
        """
        Save extracted full text to the database.
        
        Args:
            paper_id: Paper identifier
            full_text: Extracted text content
            
        Returns:
            True if successful, False otherwise
        """
        if not full_text:
            return False
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.execute(
                    "UPDATE papers SET full_text = ?, full_text_available = 1 WHERE paper_id = ?",
                    (full_text, paper_id)
                )
                conn.commit()
                return True
        except Exception as e:
            print(f"Full text save error: {e}")
            return False
    
    def get_papers(self, keyword: str = "", source: str = "", limit: int = 10, 
                  sort_by: str = "date", sort_order: str = "desc",
                  filter_has_fulltext: bool = False, min_citations: int = 0,
                  venue: str = "", date_from: str = "", date_to: str = "") -> List[Dict[str, Any]]:
        """
        Retrieve papers from the database based on filtering criteria.
        
        Args:
            keyword: Filter by keyword
            source: Filter by source
            limit: Maximum number of papers to retrieve
            sort_by: Sort field (date, citations, title)
            sort_order: Sort direction (asc, desc)
            filter_has_fulltext: Only include papers with full text
            min_citations: Minimum citation count
            venue: Filter by venue
            date_from: Start date filter (YYYY-MM-DD)
            date_to: End date filter (YYYY-MM-DD)
            
        Returns:
            List of paper dictionaries
        """
        try:
            # Validate and normalize input parameters
            sort_by = sort_by.lower()
            sort_order = sort_order.lower()
            
            if sort_by not in ["date", "citations", "title"]:
                sort_by = "date"
            
            if sort_order not in ["asc", "desc"]:
                sort_order = "desc"
            
            # Build the query
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                
                query = "SELECT * FROM papers"
                params = []
                conditions = []
                
                # Build filter conditions
                if keyword:
                    keyword_param = f"%{keyword}%"
                    conditions.append('''
                        (title LIKE ? OR abstract LIKE ? OR keywords LIKE ? OR authors LIKE ?)
                    ''')
                    params.extend([keyword_param, keyword_param, keyword_param, keyword_param])
                
                if source:
                    conditions.append("source = ?")
                    params.append(source)
                
                if filter_has_fulltext:
                    conditions.append("full_text_available = 1")
                
                if min_citations > 0:
                    conditions.append("citation_count >= ?")
                    params.append(min_citations)
                
                if venue:
                    conditions.append("venue LIKE ?")
                    params.append(f"%{venue}%")
                
                # Date range filtering
                if date_from:
                    try:
                        datetime.strptime(date_from, "%Y-%m-%d")
                        conditions.append("published_date >= ?")
                        params.append(date_from)
                    except ValueError:
                        pass
                
                if date_to:
                    try:
                        datetime.strptime(date_to, "%Y-%m-%d")
                        conditions.append("published_date <= ?")
                        params.append(date_to)
                    except ValueError:
                        pass
                
                # Add WHERE clause
                if conditions:
                    query += " WHERE " + " AND ".join(conditions)
                
                # Add sorting
                if sort_by == "date":
                    query += " ORDER BY collected_date"
                elif sort_by == "citations":
                    query += " ORDER BY citation_count"
                elif sort_by == "title":
                    query += " ORDER BY title"
                
                if sort_order == "desc":
                    query += " DESC"
                else:
                    query += " ASC"
                
                # Add limit
                query += " LIMIT ?"
                params.append(limit)
                
                # Execute query
                c.execute(query, params)
                papers = c.fetchall()
                
                # Convert to list of dictionaries
                return [dict(paper) for paper in papers]
        except Exception as e:
            print(f"Error retrieving papers: {e}")
            return []
    
    def get_paper_by_id(self, paper_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a paper by its ID or title.
        
        Args:
            paper_id: Paper ID or title
            
        Returns:
            Paper dictionary or None if not found
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                
                # Try exact match by ID
                c.execute("SELECT * FROM papers WHERE paper_id = ?", (paper_id,))
                paper = c.fetchone()
                
                # If not found, try partial match by title
                if not paper:
                    c.execute("SELECT * FROM papers WHERE title LIKE ?", (f"%{paper_id}%",))
                    paper = c.fetchone()
                
                if paper:
                    return dict(paper)
                return None
        except Exception as e:
            print(f"Error retrieving paper: {e}")
            return None
    
    def get_papers_by_venue(self, venue: str = "", limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get papers published in a specific venue.
        
        Args:
            venue: Venue name (partial match)
            limit: Maximum number of papers to retrieve
            
        Returns:
            List of paper dictionaries
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
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
                
                return [dict(paper) for paper in papers]
        except Exception as e:
            print(f"Error retrieving papers by venue: {e}")
            return []
    
    def get_top_venues(self, limit: int = 10) -> List[Tuple[str, int, float, int]]:
        """
        Get the top venues by average citation count.
        
        Args:
            limit: Maximum number of venues to retrieve
            
        Returns:
            List of (venue, paper_count, avg_citations, max_citations) tuples
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
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
                
                return c.fetchall()
        except Exception as e:
            print(f"Error retrieving top venues: {e}")
            return []
