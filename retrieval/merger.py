import logging
from retrieval.deduplicator import deduplicate_records

logger = logging.getLogger("trendscope.merger")

def merge_and_deduplicate(raw_records: list) -> tuple[list[dict], list[dict]]:
    """
    Takes lists of raw PaperRecords from multiple sources, merges them,
    and returns a deduplicated list of canonical papers along with duplicate matching logs.
    """
    logger.info(f"Merging {len(raw_records)} records collected from search workers...")
    
    # Run the deterministic deduplicator
    canonical_records, deduplication_logs = deduplicate_records(raw_records)
    
    return canonical_records, deduplication_logs
