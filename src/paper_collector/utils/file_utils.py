"""
File utility functions for the paper collector.
"""
import re
from pathlib import Path
from typing import Optional


def sanitize_filename(filename: str) -> str:
    """
    Convert a string to a safe filename by removing unsafe characters.
    
    Args:
        filename: The original filename
        
    Returns:
        A sanitized filename
    """
    unsafe_chars = r'[<>:"/\\|?*]'
    safe_filename = re.sub(unsafe_chars, '_', filename)
    if len(safe_filename) > 200:
        safe_filename = safe_filename[:200]
    return safe_filename


def ensure_directory_exists(directory_path: str) -> None:
    """
    Ensure that a directory exists, creating it if necessary.
    
    Args:
        directory_path: Path to the directory
    """
    Path(directory_path).mkdir(parents=True, exist_ok=True)
