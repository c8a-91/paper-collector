"""
PDF handling utilities for downloading and extracting text from academic papers.
"""
import os
from typing import Optional

import fitz
import httpx
from pathlib import Path

from ..utils.file_utils import sanitize_filename


async def download_pdf(url: str, paper_id: str, papers_dir: str) -> Optional[str]:
    """
    Download a paper PDF and save it, returning the file path.
    
    Args:
        url: URL of the PDF
        paper_id: Identifier for the paper
        papers_dir: Directory to save PDFs
        
    Returns:
        Path to the downloaded PDF file or None if download failed
    """
    safe_id = sanitize_filename(paper_id)
    filename = f"{safe_id}.pdf"
    file_path = os.path.join(papers_dir, filename)
    
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        return file_path
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                return file_path
            else:
                print(f"PDF download HTTP error: status code {response.status_code}")
                return None
    except Exception as e:
        print(f"PDF download error: {e}")
        return None


def extract_text_from_pdf(pdf_path: str, max_pages: int = 500) -> Optional[str]:
    """
    Extract full text from a PDF file.
    
    Args:
        pdf_path: Path to the PDF file
        max_pages: Maximum number of pages to process
        
    Returns:
        Extracted text or None if extraction failed
    """
    if not pdf_path or not os.path.exists(pdf_path):
        return None
    
    try:
        doc = fitz.open(pdf_path)
        text = ""
        
        if len(doc) > max_pages:
            print(f"Warning: PDF has too many pages ({len(doc)}). Processing only the first {max_pages} pages.")
            pages = range(min(max_pages, len(doc)))
        else:
            pages = range(len(doc))
        
        for page_num in pages:
            try:
                page = doc[page_num]
                text += page.get_text()
            except Exception as e:
                print(f"Text extraction error on page {page_num}: {e}")
                continue
        
        doc.close()
        return text
    except Exception as e:
        print(f"PDF text extraction error: {e}")
        return None
