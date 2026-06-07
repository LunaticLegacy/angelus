import base64
import binascii
import codecs
import hashlib
import os
import re
import urllib.parse
from pathlib import Path
from typing import Any, List, Optional

from ..tool import Tool
from ..rag_module.knowledge import KnowledgeBase

def create_knowledge_tools(knowledge_base: KnowledgeBase | None = None):
    """Create knowledge base search and retrieval tools.
    
    Args:
        knowledge_base: KnowledgeBase instance for searching and retrieving documents.
                       If None, returns empty list.
    
    Returns:
        List of Tool objects for knowledge base interaction.
    """
    if knowledge_base is None:
        return []
    
    kb = knowledge_base
    
    async def _search_knowledge(**kwargs: Any) -> str:
        """Search the knowledge base and return ranked results with excerpts."""
        query = str(kwargs.get("query", "")).strip()
        limit = min(int(kwargs.get("limit", 5)), 10)
        
        if not query:
            return "Error: query parameter is required"
        
        try:
            hits = kb.search(query, limit=limit)
            if not hits:
                return f"No knowledge entries found for query: {query}"
            
            lines = [f"Found {len(hits)} knowledge entries for query: {query}\n"]
            for i, hit in enumerate(hits, 1):
                lines.append(f"{i}. [{hit.score:.1f}] {hit.title}")
                lines.append(f"   Path: {hit.path}")
                lines.append(f"   Excerpt: {hit.excerpt}")
                lines.append(f"   Keyword Score: {hit.keyword_score:.1f}, Vector Score: {hit.vector_score:.1f}")
                lines.append("")
            
            lines.append("\nTo read full content, use read_knowledge_full with the path.")
            return "\n".join(lines)
        except Exception as exc:
            return f"Error searching knowledge base: {exc}"
    
    async def _read_knowledge_full(**kwargs: Any) -> str:
        """Read the full content of a knowledge document by its path."""
        path = str(kwargs.get("path", "")).strip()
        
        if not path:
            return "Error: path parameter is required"
        
        try:
            content = kb.get_full_text(path)
            if content is None:
                return f"Error: document not found or cannot be loaded: {path}"
            
            # Truncate if too long to avoid overwhelming context
            max_chars = 15000
            truncated = len(content) > max_chars
            display_content = content[:max_chars] if truncated else content
            
            lines = [
                f"Document: {path}",
                f"Length: {len(content)} characters",
                f"{'[TRUNCATED - showing first 15000 chars]' if truncated else '[FULL CONTENT]'}",
                "",
                "=" * 80,
                display_content,
            ]
            
            if truncated:
                lines.append("")
                lines.append("=" * 80)
                lines.append(f"[Content truncated. Total length: {len(content)} chars]")
            
            return "\n".join(lines)
        except Exception as exc:
            return f"Error reading knowledge document: {exc}"
    
    return [
        Tool(
            name="search_knowledge",
            description="Search the local knowledge base by query text. Returns ranked results with titles, paths, and excerpts. Use this to find relevant strategy documents or technical references.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query text"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5, "description": "Maximum number of results (1-10)"},
                },
                "required": ["query"],
            },
            handler=_search_knowledge,
        ),
        Tool(
            name="read_knowledge_full",
            description="Read the full content of a knowledge document by its repository-relative path. Use this after search_knowledge to get complete details from a promising result.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Repository-relative path from search results (e.g., 'reversing/README.md' or 'strategy/re-segmented-decode-short-circuit.md')"},
                },
                "required": ["path"],
            },
            handler=_read_knowledge_full,
        ),
    ]

