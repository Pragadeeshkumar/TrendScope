import os
import logging
import requests
import json
import re
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from retrieval.workers import fetch_url_with_retry, normalize_doi

logger = logging.getLogger("trendscope.resolver")

class DownloadFailure(Exception):
    """Exception raised when a PDF download fails with a specific error type."""
    def __init__(self, failure_type: str, message: str = ""):
        self.failure_type = failure_type
        super().__init__(message or failure_type)

def validate_and_download_pdf(url: str, filepath: str, timeout: float = 10.0) -> str:
    """
    Downloads a file streamingly. Inspects HTTP status, redirects, Content-Type,
    and checks if the file starts with the %PDF- magic bytes.
    Raises DownloadFailure on error.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    domain = urlparse(url).netloc or "unknown"
    
    try:
        response = requests.get(url, headers=headers, timeout=timeout, stream=True)
    except requests.exceptions.Timeout:
        raise DownloadFailure("TIMEOUT", f"Timeout connecting to {url}")
    except requests.exceptions.RequestException as e:
        # Check if we can identify status code from response inside exception
        if e.response is not None:
            status = e.response.status_code
            if status == 403:
                raise DownloadFailure("HTTP_403")
            elif status == 404:
                raise DownloadFailure("HTTP_404")
            elif status == 429:
                raise DownloadFailure("HTTP_429")
            elif status >= 500:
                raise DownloadFailure("HTTP_5XX")
        raise DownloadFailure("DOWNLOAD_FAILURE", str(e))
        
    status = response.status_code
    if status != 200:
        if status == 403:
            raise DownloadFailure("HTTP_403")
        elif status == 404:
            raise DownloadFailure("HTTP_404")
        elif status == 429:
            raise DownloadFailure("HTTP_429")
        elif status >= 500:
            raise DownloadFailure("HTTP_5XX")
        else:
            raise DownloadFailure(f"HTTP_{status}")
            
    # Check headers (optional validation but magic bytes is primary)
    content_type = response.headers.get("Content-Type", "")
    
    # Read the first chunk to verify PDF magic bytes
    chunk_iterator = response.iter_content(chunk_size=1024)
    try:
        first_chunk = next(chunk_iterator)
    except StopIteration:
        raise DownloadFailure("INVALID_CONTENT", "Downloaded file is empty")
        
    if not first_chunk.startswith(b'%PDF'):
        raise DownloadFailure("INVALID_PDF", f"File from {url} does not start with %PDF magic bytes")
        
    # Write to file
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "wb") as f:
            f.write(first_chunk)
            for chunk in chunk_iterator:
                if chunk:
                    f.write(chunk)
    except Exception as e:
        raise DownloadFailure("PARSE_FAILURE", f"Failed to save PDF to disk: {e}")
        
    return filepath

def get_openalex_pdf_url(openalex_id: str, email: str = None) -> str:
    """Queries OpenAlex work details endpoint to extract direct PDF url."""
    if not openalex_id:
        return None
    url = f"https://api.openalex.org/works/{openalex_id}"
    params = {}
    if email:
        params["mailto"] = email
        
    try:
        # 5 seconds timeout since this is detail fetch
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            best_oa = data.get("best_oa_location")
            if best_oa and best_oa.get("pdf_url"):
                return best_oa.get("pdf_url")
    except Exception:
        pass
    return None

def get_unpaywall_pdf_url(doi: str, email: str = None) -> str:
    """Queries Unpaywall for a working PDF link using DOI."""
    if not doi or not email:
        return None
    url = f"https://api.unpaywall.org/v2/{doi}"
    params = {"email": email}
    try:
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            best_loc = data.get("best_oa_location")
            if best_loc and best_loc.get("url_for_pdf"):
                return best_loc.get("url_for_pdf")
            for loc in data.get("oa_locations", []):
                if loc.get("url_for_pdf"):
                    return loc.get("url_for_pdf")
    except Exception:
        pass
    return None

def get_core_pdf_url(title: str, doi: str = None, api_key: str = None) -> str:
    """Queries CORE search works API for a download link."""
    if not api_key:
        return None
    url = "https://api.core.ac.uk/v3/search/works"
    
    # DOI search is highly precise, fall back to cleaned title search
    if doi:
        query_str = f'doi:"{doi}"'
    else:
        # Clean title using alphanumeric regex to bypass 500 errors
        cleaned_title = re.sub(r'[^a-zA-Z0-9\s]', ' ', title)
        query_str = f'title:"{" ".join(cleaned_title.split())}"'
        
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"q": query_str, "limit": 3}
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            for res in results:
                if res.get("downloadUrl"):
                    return res.get("downloadUrl")
    except Exception:
        pass
    return None

def resolve_single_paper(paper: dict, pdf_dir: str = "data/pdfs") -> dict:
    """
    Attempts to download the PDF for a paper using fallback tiers.
    Mutates paper dictionary in place with PDF status.
    """
    paper_id = paper.get("paper_id")
    doi = paper.get("doi")
    arxiv_id = paper.get("arxiv_id")
    title = paper.get("title")
    openalex_id = paper.get("openalex_id")
    
    openalex_email = os.environ.get("OPENALEX_EMAIL")
    unpaywall_email = os.environ.get("UNPAYWALL_EMAIL")
    core_key = os.environ.get("CORE_API_KEY")
    
    filepath = os.path.join(pdf_dir, f"{paper_id}.pdf")
    
    # Fallback Tiers:
    # 1. arXiv ID direct PDF
    if arxiv_id:
        arxiv_pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        try:
            logger.debug(f"[{paper_id}] Trying arXiv direct PDF: {arxiv_pdf_url}")
            validate_and_download_pdf(arxiv_pdf_url, filepath, timeout=5.0)
            paper["pdf_path"] = filepath
            paper["fulltext_resolved"] = True
            paper["resolution_method"] = "arxiv_direct"
            return paper
        except DownloadFailure as e:
            logger.debug(f"[{paper_id}] arXiv direct failed ({e.failure_type})")
            
    # 2. OpenAlex Direct PDF
    if openalex_id:
        pdf_url = get_openalex_pdf_url(openalex_id, openalex_email)
        if pdf_url:
            try:
                logger.debug(f"[{paper_id}] Trying OpenAlex direct PDF: {pdf_url}")
                validate_and_download_pdf(pdf_url, filepath, timeout=5.0)
                paper["pdf_path"] = filepath
                paper["fulltext_resolved"] = True
                paper["resolution_method"] = "openalex_direct"
                return paper
            except DownloadFailure as e:
                logger.debug(f"[{paper_id}] OpenAlex direct failed ({e.failure_type})")
                
    # 3. Unpaywall PDF
    if doi and unpaywall_email:
        pdf_url = get_unpaywall_pdf_url(doi, unpaywall_email)
        if pdf_url:
            try:
                logger.debug(f"[{paper_id}] Trying Unpaywall PDF: {pdf_url}")
                validate_and_download_pdf(pdf_url, filepath, timeout=5.0)
                paper["pdf_path"] = filepath
                paper["fulltext_resolved"] = True
                paper["resolution_method"] = "unpaywall"
                return paper
            except DownloadFailure as e:
                logger.debug(f"[{paper_id}] Unpaywall failed ({e.failure_type})")
                
    # 4. CORE API PDF
    if core_key:
        pdf_url = get_core_pdf_url(title, doi, core_key)
        if pdf_url:
            try:
                logger.debug(f"[{paper_id}] Trying CORE PDF: {pdf_url}")
                validate_and_download_pdf(pdf_url, filepath, timeout=5.0)
                paper["pdf_path"] = filepath
                paper["fulltext_resolved"] = True
                paper["resolution_method"] = "core"
                return paper
            except DownloadFailure as e:
                logger.debug(f"[{paper_id}] CORE failed ({e.failure_type})")
                
    # If we get here, all resolution methods failed
    paper["pdf_path"] = None
    paper["fulltext_resolved"] = False
    paper["resolution_method"] = "unresolved"
    return paper

def resolve_corpus_pdfs(selected_papers: list[dict], pdf_dir: str = "data/pdfs", max_workers: int = 10) -> list[dict]:
    """
    Downloads PDFs concurrently for a selected list of papers using a ThreadPoolExecutor.
    """
    logger.info(f"Resolving PDFs concurrently for {len(selected_papers)} papers using {max_workers} threads...")
    os.makedirs(pdf_dir, exist_ok=True)
    
    resolved_papers = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(resolve_single_paper, paper, pdf_dir): paper for paper in selected_papers}
        
        for future in as_completed(futures):
            try:
                paper = future.result()
                resolved_papers.append(paper)
                if paper.get("fulltext_resolved"):
                    logger.info(f"Resolved [{paper.get('resolution_method')}]: {paper.get('title')[:50]}")
                else:
                    logger.warning(f"Failed to resolve: {paper.get('title')[:50]}")
            except Exception as e:
                logger.error(f"Paper resolution failed unexpectedly: {e}")
                
    return resolved_papers
