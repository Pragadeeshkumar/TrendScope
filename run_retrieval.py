import os
import sys
# Configure stdout to use UTF-8 to prevent UnicodeEncodeError on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import argparse
import logging
from dotenv import load_dotenv, set_key

def setup_logging(verbose: bool = False) -> None:
    log_level = logging.DEBUG if verbose else logging.INFO
    
    # Root logger config
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler("data/retrieval.log", mode="a", encoding="utf-8")
        ]
    )
    
    # Silence chatty third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("tenacity").setLevel(logging.WARNING)
    logging.getLogger("filelock").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

def check_or_prompt_credentials() -> None:
    """
    Checks if API credentials exist in environment or .env.
    If not, prompts the user to input them and writes them to the .env file.
    """
    env_file = ".env"
    load_dotenv(env_file)
    
    openalex_email = os.environ.get("OPENALEX_EMAIL")
    unpaywall_email = os.environ.get("UNPAYWALL_EMAIL")
    core_key = os.environ.get("CORE_API_KEY")
    
    updated = False
    
    if not openalex_email:
        print("OpenAlex email is required to identify your API requests.")
        openalex_email = input("Please enter your email for OpenAlex: ").strip()
        if openalex_email:
            set_key(env_file, "OPENALEX_EMAIL", openalex_email)
            os.environ["OPENALEX_EMAIL"] = openalex_email
            updated = True
            
    if not unpaywall_email:
        print("\nUnpaywall email is required to identify your API requests.")
        unpaywall_email = input("Please enter your email for Unpaywall: ").strip()
        if unpaywall_email:
            set_key(env_file, "UNPAYWALL_EMAIL", unpaywall_email)
            os.environ["UNPAYWALL_EMAIL"] = unpaywall_email
            updated = True
            
    if not core_key:
        print("\nCORE API key is required to query the CORE Search API.")
        core_key = input("Please enter your CORE API key: ").strip()
        if core_key:
            set_key(env_file, "CORE_API_KEY", core_key)
            os.environ["CORE_API_KEY"] = core_key
            updated = True
            
    if updated:
        print(f"\nCredentials saved to '{env_file}' successfully.")

def main() -> None:
    parser = argparse.ArgumentParser(
        description="TrendScope Multi-Agent Corpus Retrieval Stage: Retrieve and download full-text OA research papers."
    )
    parser.add_argument(
        "domain",
        type=str,
        help="The search domain / research query (e.g., 'Vision Transformers for medical image segmentation')."
    )
    parser.add_argument(
        "-t", "--target-size",
        type=int,
        default=150,
        help="The target number of resolved papers to collect (default: 150)."
    )
    parser.add_argument(
        "-d", "--db-path",
        type=str,
        default="data/trendscope.db",
        help="Path to the SQLite database file (default: data/trendscope.db)."
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=None,
        help="Earliest publication year to include (e.g., 2024)."
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=None,
        help="Latest publication year to include (e.g., 2026)."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable detailed debug logging."
    )
    
    args = parser.parse_args()
    
    # Ensure data directory exists for logs and DB
    os.makedirs("data", exist_ok=True)
    
    # Initialize logging
    setup_logging(args.verbose)
    
    # Ensure environment keys are set
    try:
        check_or_prompt_credentials()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)
        
    # Run the multi-agent corpus builder
    from retrieval.corpus import build_corpus
    build_corpus(
        domain=args.domain,
        target_size=args.target_size,
        db_path=args.db_path,
        start_year=args.start_year,
        end_year=args.end_year
    )

if __name__ == "__main__":
    main()
