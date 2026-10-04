import os
import logging
import requests
import xml.etree.ElementTree as ET
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger("trendscope.workers")

class WorkerRateLimitError(Exception):
    """Raised when an API worker encounters a 429 rate limit."""
    pass

# Standard retry strategy for workers
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    retry=retry_if_exception_type((requests.exceptions.RequestException, WorkerRateLimitError)),
    reraise=True
)
def fetch_url_with_retry(url: str, params: dict = None, headers: dict = None, timeout: float = 15.0) -> requests.Response:
    try:
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        if response.status_code == 429:
            logger.warning(f"Rate limited (429) on {url}. Retrying...")
            raise WorkerRateLimitError(f"Rate limit hit: {url}")
        
        # Raise for server/other errors to trigger retry
        if response.status_code >= 500:
            response.raise_for_status()
            
        return response
    except requests.exceptions.RequestException as e:
        logger.warning(f"Network error on {url}: {e}. Retrying...")
        raise e

def normalize_doi(doi_str: str) -> str:
    """Standardizes DOI representation by stripping URLs."""
    if not doi_str:
        return None
    doi_str = doi_str.lower().strip()
    prefixes = ["https://doi.org/", "http://doi.org/", "doi:"]
    for prefix in prefixes:
        if doi_str.startswith(prefix):
            doi_str = doi_str[len(prefix):]
    return doi_str

def normalize_arxiv_id(arxiv_url_or_id: str) -> str:
    """Extracts raw arXiv ID (e.g., 2305.12345) from URL or string."""
    if not arxiv_url_or_id:
        return None
    match = re.search(r'(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)', arxiv_url_or_id)
    if match:
        return match.group(1)
    # If it is already a plain versionless/versioned ID
    arxiv_url_or_id = arxiv_url_or_id.strip()
    if re.match(r'^\d{4}\.\d{4,5}(?:v\d+)?$', arxiv_url_or_id):
        return arxiv_url_or_id
    return None

import re  # needed for regex matching

class OpenAlexWorker:
    def __init__(self, email: str = None):
        self.email = email or os.environ.get("OPENALEX_EMAIL")
        
    def query(self, search_strategy: str, limit: int = 100, start_year: int = None, end_year: int = None) -> list[dict]:
        logger.info(f"[OpenAlexWorker] Searching: '{search_strategy}' (limit: {limit}, years: {start_year}-{end_year})")
        url = "https://api.openalex.org/works"
        
        filter_parts = ["is_oa:true", "type:article"]
        if start_year:
            filter_parts.append(f"from_publication_date:{start_year}-01-01")
        if end_year:
            filter_parts.append(f"to_publication_date:{end_year}-12-31")
            
        params = {
            "search": search_strategy,
            "filter": ",".join(filter_parts),
            "sort": "publication_date:desc",
            "per_page": min(limit, 200),
            "page": 1
        }
        if self.email:
            params["mailto"] = self.email
            
        records = []
        try:
            # Fetch first page
            response = fetch_url_with_retry(url, params=params)
            if response.status_code != 200:
                logger.error(f"[OpenAlexWorker] API error: {response.status_code}")
                return []
                
            data = response.json()
            results = data.get("results", [])
            
            for work in results:
                paper_id = work.get("id", "").split("/")[-1]
                title = work.get("title")
                
                # Reconstruct abstract
                abstract_index = work.get("abstract_inverted_index")
                abstract = ""
                if abstract_index:
                    try:
                        word_positions = []
                        for word, positions in abstract_index.items():
                            for pos in positions:
                                word_positions.append((pos, word))
                        word_positions.sort()
                        abstract = " ".join([word for pos, word in word_positions])
                    except Exception:
                        pass
                
                # Extract authors
                authors = [
                    auth.get("author", {}).get("display_name")
                    for auth in work.get("authorships", [])
                    if auth.get("author", {}).get("display_name")
                ]
                
                publication_year = work.get("publication_year")
                doi = normalize_doi(work.get("doi"))
                
                # Extract venue
                venue = None
                primary_loc = work.get("primary_location")
                if primary_loc and primary_loc.get("source"):
                    venue = primary_loc.get("source", {}).get("display_name")
                
                # Check for arXiv ID in external IDs
                arxiv_id = None
                extra_ids = work.get("ids", {})
                if "arxiv" in extra_ids:
                    arxiv_id = normalize_arxiv_id(extra_ids["arxiv"])
                
                records.append({
                    "paper_id": paper_id,
                    "title": title,
                    "abstract": abstract,
                    "authors": authors,
                    "publication_year": publication_year,
                    "doi": doi,
                    "arxiv_id": arxiv_id,
                    "openalex_id": paper_id,
                    "semantic_scholar_id": None,
                    "venue": venue,
                    "source": "openalex"
                })
        except Exception as e:
            logger.error(f"[OpenAlexWorker] Query failed for '{search_strategy}': {e}")
            
        logger.info(f"[OpenAlexWorker] Found {len(records)} papers for '{search_strategy}'")
        return records

class SemanticScholarWorker:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
        
    def query(self, search_strategy: str, limit: int = 100, start_year: int = None, end_year: int = None) -> list[dict]:
        logger.info(f"[SemanticScholarWorker] Searching: '{search_strategy}' (limit: {limit}, years: {start_year}-{end_year})")
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        
        params = {
            "query": search_strategy,
            "sort": "publicationDate:desc",
            "limit": min(limit, 100),
            "fields": "title,abstract,authors,year,externalIds,isOpenAccess,openAccessPdf,venue"
        }
        if start_year and end_year:
            params["year"] = f"{start_year}-{end_year}"
        elif start_year:
            params["year"] = f"{start_year}-"
        elif end_year:
            params["year"] = f"-{end_year}"
        
        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        else:
            # Semantic Scholar rejects unauthenticated API traffic with 429 rate limits
            logger.info("[SemanticScholarWorker] No API key configured. Skipping to preserve speed.")
            return []
            
        records = []
        try:
            response = fetch_url_with_retry(url, params=params, headers=headers)
            if response.status_code != 200:
                logger.error(f"[SemanticScholarWorker] API error: {response.status_code}")
                return []
                
            data = response.json()
            results = data.get("data", [])
            
            for paper in results:
                # We filter to keep only Open Access papers
                if not paper.get("isOpenAccess"):
                    continue
                    
                title = paper.get("title")
                abstract = paper.get("abstract", "")
                authors = [a.get("name") for a in paper.get("authors", []) if a.get("name")]
                publication_year = paper.get("year")
                
                ext_ids = paper.get("externalIds", {})
                doi = normalize_doi(ext_ids.get("DOI"))
                arxiv_id = normalize_arxiv_id(ext_ids.get("ArXiv"))
                
                ss_id = paper.get("paperId")
                paper_id = f"ss_{ss_id}"
                
                venue = paper.get("venue")
                
                records.append({
                    "paper_id": paper_id,
                    "title": title,
                    "abstract": abstract,
                    "authors": authors,
                    "publication_year": publication_year,
                    "doi": doi,
                    "arxiv_id": arxiv_id,
                    "openalex_id": None,
                    "semantic_scholar_id": ss_id,
                    "venue": venue,
                    "source": "semantic_scholar"
                })
        except Exception as e:
            logger.debug(f"[SemanticScholarWorker] Query failed for '{search_strategy}': {e}")
            
        logger.info(f"[SemanticScholarWorker] Found {len(records)} papers for '{search_strategy}'")
        return records

class ArxivWorker:
    def query(self, search_strategy: str, limit: int = 100, start_year: int = None, end_year: int = None) -> list[dict]:
        logger.info(f"[ArxivWorker] Searching: '{search_strategy}' (limit: {limit}, years: {start_year}-{end_year})")
        url = "http://export.arxiv.org/api/query"
        
        # arXiv query expects clean terms
        clean_strategy = re.sub(r'[^a-zA-Z0-9\s]', ' ', search_strategy)
        arxiv_query = " AND ".join([f'all:"{term}"' for term in clean_strategy.split() if term])
        
        params = {
            "search_query": arxiv_query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": min(limit, 100)
        }
        
        # ArXiv requests should be rate-limited politely
        time.sleep(1.0)
        
        records = []
        try:
            response = fetch_url_with_retry(url, params=params)
            if response.status_code != 200:
                logger.error(f"[ArxivWorker] API error: {response.status_code}")
                return []
                
            # Parse XML response
            root = ET.fromstring(response.content)
            
            # XML namespaces
            ns = {
                'atom': 'http://www.w3.org/2005/Atom',
                'arxiv': 'http://arxiv.org/schemas/atom'
            }
            
            for entry in root.findall('atom:entry', ns):
                title_elem = entry.find('atom:title', ns)
                title = " ".join(title_elem.text.split()) if title_elem is not None else None
                
                abstract_elem = entry.find('atom:summary', ns)
                abstract = " ".join(abstract_elem.text.split()) if abstract_elem is not None else ""
                
                # Extract raw authors
                authors = []
                for author_elem in entry.findall('atom:author', ns):
                    name_elem = author_elem.find('atom:name', ns)
                    if name_elem is not None:
                        authors.append(name_elem.text.strip())
                        
                published_elem = entry.find('atom:published', ns)
                publication_year = None
                if published_elem is not None and len(published_elem.text) >= 4:
                    try:
                        publication_year = int(published_elem.text[:4])
                    except ValueError:
                        pass
                
                # Year filtering
                if publication_year:
                    if start_year and publication_year < start_year:
                        continue
                    if end_year and publication_year > end_year:
                        continue
                
                # Extract arXiv ID from atom ID URL
                id_elem = entry.find('atom:id', ns)
                raw_arxiv_id = id_elem.text if id_elem is not None else None
                arxiv_id = normalize_arxiv_id(raw_arxiv_id)
                
                paper_id = f"arxiv_{arxiv_id}" if arxiv_id else None
                
                # Extract DOI if present
                doi_elem = entry.find('arxiv:doi', ns)
                doi = normalize_doi(doi_elem.text) if doi_elem is not None else None
                
                # Venue (usually journal_ref)
                venue_elem = entry.find('arxiv:journal_ref', ns)
                venue = venue_elem.text.strip() if venue_elem is not None else "arXiv"
                
                if paper_id:
                    records.append({
                        "paper_id": paper_id,
                        "title": title,
                        "abstract": abstract,
                        "authors": authors,
                        "publication_year": publication_year,
                        "doi": doi,
                        "arxiv_id": arxiv_id,
                        "openalex_id": None,
                        "semantic_scholar_id": None,
                        "venue": venue,
                        "source": "arxiv"
                    })
        except Exception as e:
            logger.error(f"[ArxivWorker] Query failed for '{search_strategy}': {e}")
            
        logger.info(f"[ArxivWorker] Found {len(records)} papers for '{search_strategy}'")
        return records

def execute_worker_queries(search_strategies: list[str], limit_per_source: int = 100, start_year: int = None, end_year: int = None) -> list[dict]:
    """
    Executes searches across OpenAlex, Semantic Scholar, and arXiv concurrently for
    all provided strategies. Returns a combined list of raw normalized records.
    """
    workers = [
        OpenAlexWorker(),
        SemanticScholarWorker(),
        ArxivWorker()
    ]
    
    results = []
    
    # We query concurrently using a ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for strategy in search_strategies:
            for worker in workers:
                futures.append(executor.submit(worker.query, strategy, limit_per_source, start_year, end_year))
                
        for future in as_completed(futures):
            try:
                records = future.result()
                results.extend(records)
            except Exception as e:
                logger.debug(f"Worker execution fallback: {e}")
                
    return results
