"""
core/url_extractor.py
=====================
Resilient Universal Web Article, GitHub Repository, and Research Paper Extractor.

Features:
- Web Articles & Quantitative Blogs (Medium, Substack, Bloomberg, CoinDesk, Investopedia, Wikipedia, etc.)
  Cleans boilerplate HTML, removes scripts/ads/navigation, extracts title, author, description, and structured body text.
- GitHub Repositories (github.com/owner/repo or github.com/owner/repo/blob/...)
  Extracts repository description and raw README.md or source code file.
- ArXiv Papers (arxiv.org/abs/... or arxiv.org/pdf/...)
  Extracts paper title, authors, abstract, and publication context.
- TradingView Ideas & PineScript Pages (tradingview.com/...)
  Extracts title, author, and strategy discussion.
- Resilient TLS / Header spoofing with graceful fallback to curl_cffi and urllib.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger("ai_quant_sentinel.url_extractor")

# Standard desktop browser user-agent to avoid blocking
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _clean_text(raw_text: str) -> str:
    """Normalizes excessive whitespace and newlines."""
    text = re.sub(r"\r\n|\r", "\n", raw_text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


class URLExtractor:
    """Master web and research URL extractor."""

    def __init__(self, timeout: float = 12.0):
        self.timeout = timeout

    def extract(self, url: str) -> dict[str, Any]:
        """
        Universal entrypoint for URL extraction.
        Returns a dictionary containing:
        - success: bool
        - url: canonical url
        - domain: hostname
        - source_type: ARTICLE, GITHUB, ARXIV, TRADINGVIEW
        - title: str
        - author_creator: str
        - summary: str
        - text_content: str
        - error: str (if failed)
        """
        if not url or not isinstance(url, str):
            return {"success": False, "error": "Empty or invalid URL."}

        clean_url = url.strip()
        if not clean_url.startswith(("http://", "https://")):
            clean_url = f"https://{clean_url}"

        try:
            parsed = urllib.parse.urlparse(clean_url)
            domain = parsed.netloc.lower()
        except Exception as e:
            return {"success": False, "error": f"Invalid URL formatting: {e}"}

        # Route by domain / platform
        if "github.com" in domain:
            return self._extract_github(clean_url, parsed)
        elif "arxiv.org" in domain:
            return self._extract_arxiv(clean_url, parsed)
        elif "tradingview.com" in domain:
            return self._extract_tradingview(clean_url, parsed)
        else:
            return self._extract_generic_article(clean_url, domain)

    def _fetch_html(self, url: str, timeout: float | None = None) -> str:
        """Fetches HTML with requests, falling back to curl_cffi or urllib."""
        to = timeout or self.timeout
        # Priority 1: requests
        try:
            import requests

            resp = requests.get(
                url,
                headers=DEFAULT_HEADERS,
                timeout=to,
                allow_redirects=True,
            )
            if resp.status_code == 200 and resp.text:
                return resp.text
        except Exception:
            pass

        # Priority 2: curl_cffi (impersonate browser)
        try:
            from curl_cffi import requests as curl_requests

            c_resp = curl_requests.get(
                url,
                impersonate="chrome120",
                headers=DEFAULT_HEADERS,
                timeout=to,
            )
            if c_resp.status_code == 200 and c_resp.text:
                return c_resp.text
        except Exception:
            pass

        # Priority 3: urllib.request
        try:
            import urllib.request

            req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
            with urllib.request.urlopen(req, timeout=to) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="ignore")
        except Exception as exc:
            raise RuntimeError(f"Could not reach {url}: {exc}") from exc

    def _extract_github(self, url: str, parsed: urllib.parse.ParseResult) -> dict[str, Any]:
        """Extracts content from a GitHub repository or file."""
        path_parts = [p for p in parsed.path.split("/") if p]
        if len(path_parts) < 2:
            return self._extract_generic_article(url, "github.com")

        owner = path_parts[0]
        repo = path_parts[1]
        source_title = f"GitHub: {owner}/{repo}"

        # If pointing to a specific file blob: /owner/repo/blob/branch/path/to/file
        if len(path_parts) >= 5 and path_parts[2] == "blob":
            branch = path_parts[3]
            file_path = "/".join(path_parts[4:])
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{file_path}"
            try:
                raw_content = self._fetch_html(raw_url)
                return {
                    "success": True,
                    "url": url,
                    "domain": "github.com",
                    "source_type": "CODE",
                    "title": f"GitHub File: {path_parts[-1]} ({owner}/{repo})",
                    "author_creator": owner,
                    "summary": f"Source code file '{file_path}' from repository {owner}/{repo}.",
                    "text_content": raw_content[:500_000],
                    "char_count": len(raw_content),
                }
            except Exception:
                pass

        # Otherwise attempt to fetch README.md
        for branch in ("main", "master", "HEAD"):
            for readme_name in ("README.md", "readme.md", "README.rst", "README.txt", "README"):
                raw_readme_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{readme_name}"
                try:
                    raw_content = self._fetch_html(raw_readme_url)
                    if raw_content and len(raw_content.strip()) > 20:
                        lines = [line.strip("# ").strip() for line in raw_content.splitlines() if line.strip()]
                        headline = lines[0] if lines else repo
                        return {
                            "success": True,
                            "url": url,
                            "domain": "github.com",
                            "source_type": "GITHUB",
                            "title": f"GitHub: {owner}/{repo} - {headline}",
                            "author_creator": owner,
                            "summary": f"GitHub repository {owner}/{repo} documentation and trading codebase.",
                            "text_content": raw_content[:500_000],
                            "char_count": len(raw_content),
                        }
                except Exception:
                    continue

        # Fallback to scraping the GitHub HTML page
        return self._extract_generic_article(url, "github.com")

    def _extract_arxiv(self, url: str, parsed: urllib.parse.ParseResult) -> dict[str, Any]:
        """Extracts title, authors, and abstract from an ArXiv paper URL."""
        # e.g., /abs/2301.12345 or /pdf/2301.12345.pdf
        path_parts = [p for p in parsed.path.split("/") if p]
        arxiv_id = path_parts[-1].replace(".pdf", "") if path_parts else ""

        html = self._fetch_html(f"https://arxiv.org/abs/{arxiv_id}")
        soup = BeautifulSoup(html, "html.parser")

        title_el = soup.find("h1", class_="title")
        raw_title = title_el.get_text(strip=True).replace("Title:", "").strip() if title_el else f"ArXiv Paper {arxiv_id}"

        authors_el = soup.find("div", class_="authors")
        raw_authors = authors_el.get_text(strip=True).replace("Authors:", "").strip() if authors_el else "ArXiv Researchers"

        abstract_el = soup.find("blockquote", class_="abstract")
        raw_abstract = abstract_el.get_text(strip=True).replace("Abstract:", "").strip() if abstract_el else ""

        full_text = f"ArXiv Quantitative Paper: {raw_title}\nAuthors: {raw_authors}\nArXiv ID: {arxiv_id}\n\nAbstract:\n{raw_abstract}"

        return {
            "success": True,
            "url": url,
            "domain": "arxiv.org",
            "source_type": "ARTICLE",
            "title": f"ArXiv [{arxiv_id}]: {raw_title}",
            "author_creator": raw_authors,
            "summary": raw_abstract[:500],
            "text_content": full_text,
            "char_count": len(full_text),
        }

    def _extract_tradingview(self, url: str, parsed: urllib.parse.ParseResult) -> dict[str, Any]:
        """Extracts trading idea or PineScript indicator from TradingView."""
        res = self._extract_generic_article(url, "tradingview.com")
        res["source_type"] = "TRADINGVIEW"
        return res

    def _extract_generic_article(self, url: str, domain: str) -> dict[str, Any]:
        """Extracts clean article text, title, author, and description from any webpage."""
        try:
            html = self._fetch_html(url)
        except Exception as e:
            return {
                "success": False,
                "url": url,
                "domain": domain,
                "error": f"Failed to download webpage: {e}",
            }

        soup = BeautifulSoup(html, "html.parser")

        # 1. Title Extraction
        title = ""
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = str(og_title["content"]).strip()
        elif soup.find("title"):
            title = soup.find("title").get_text(strip=True)
        elif soup.find("h1"):
            title = soup.find("h1").get_text(strip=True)
        else:
            title = f"Web Article from {domain}"

        # 2. Author Extraction
        author = "Web Author"
        author_meta = (
            soup.find("meta", attrs={"name": "author"})
            or soup.find("meta", property="article:author")
            or soup.find("meta", attrs={"name": "twitter:creator"})
        )
        if author_meta and author_meta.get("content"):
            author = str(author_meta["content"]).strip()
        else:
            author_tag = soup.find(class_=re.compile(r"author|byline", re.I))
            if author_tag:
                author = author_tag.get_text(strip=True)

        # 3. Description Extraction
        description = ""
        og_desc = (
            soup.find("meta", property="og:description")
            or soup.find("meta", attrs={"name": "description"})
        )
        if og_desc and og_desc.get("content"):
            description = str(og_desc["content"]).strip()

        # 4. Remove boilerplate tags
        for element in soup([
            "script", "style", "nav", "header", "footer", "aside",
            "noscript", "svg", "form", "button", "iframe"
        ]):
            element.decompose()

        # 5. Extract readable content
        article_elem = soup.find("article") or soup.find("main") or soup.find(class_=re.compile(r"post-content|article-content|entry-content", re.I))
        search_root = article_elem if article_elem else soup.body or soup

        paragraphs = []
        for p in search_root.find_all(["p", "h2", "h3", "h4", "li", "pre", "code"]):
            p_text = p.get_text(strip=True)
            if len(p_text) >= 25:
                paragraphs.append(p_text)

        if not paragraphs:
            # Fallback: get raw body text
            raw_body = search_root.get_text(separator="\n", strip=True)
            paragraphs = [line.strip() for line in raw_body.splitlines() if len(line.strip()) > 35]

        cleaned_body = _clean_text("\n\n".join(paragraphs))

        if not cleaned_body:
            cleaned_body = description or f"Web literature from {domain}: {title}"

        full_content = f"# {title}\nAuthor: {author}\nSource: {url}\n\n{cleaned_body}"

        return {
            "success": True,
            "url": url,
            "domain": domain,
            "source_type": "ARTICLE",
            "title": title,
            "author_creator": author,
            "summary": description[:400] if description else cleaned_body[:300],
            "text_content": full_content,
            "char_count": len(full_content),
        }


# Master Singleton
url_extractor = URLExtractor()
