
import json
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 20
REQUEST_DELAY = 0.5
DEFAULT_MAX_PAGES = 20

KEYWORDS = [
    "verwalten",
    "hausverwaltung",
    "kontakt",
    "impressum",
    "team",
    "unternehmen",
    "karriere",
    "digital",
    "service",
    "leistungen",
    "verwaltung",
    "management",
    "geschaeftsfuehrung",
    "geschaftsfuehrung",
    "ansprechpartner",
    "mitarbeiter",
    "referenzen",
    "portfolio",
    "ueber-uns",
    "about",
    "team"
]

EXCLUDED_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif",
    ".svg", ".zip", ".doc", ".docx", ".xlsx"
)


# --------------------------------------------------
# URL HELPERS
# --------------------------------------------------

def normalize_url(url):
    """Remove fragments and trailing slashes from URLs."""

    url = urldefrag(url)[0]
    parsed = urlparse(url)

    return (
        parsed.scheme + "://" +
        parsed.netloc +
        parsed.path.rstrip("/")
    )


def get_domain(url):
    """Return the hostname without www."""

    return (
        urlparse(url)
        .netloc
        .lower()
        .removeprefix("www.")
    )


def is_valid_internal_url(url, base_url):
    """Check whether a URL belongs to the target website."""

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return False

    if get_domain(url) != get_domain(base_url):
        return False

    if parsed.path.lower().endswith(EXCLUDED_EXTENSIONS):
        return False

    return True


def normalize_base_url(url):
    """Prepare and validate a company website URL."""

    if not url or not url.strip():
        raise ValueError("Website URL cannot be empty.")

    url = url.strip()

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)

    if not parsed.netloc:
        raise ValueError(f"Invalid website URL: {url}")

    return normalize_url(url)


# --------------------------------------------------
# WEBPAGE EXTRACTION
# --------------------------------------------------

def get_page(url):
    """Download a webpage and extract readable text."""

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type", ""
        )

        if "text/html" not in content_type.lower():
            print("Skipping non-HTML page:", url)
            return None

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        # Remove irrelevant elements
        for element in soup([
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "noscript"
        ]):
            element.decompose()

        title = (
            soup.title.get_text(strip=True)
            if soup.title else "No title"
        )

        text = soup.get_text(
            separator=" ",
            strip=True
        )

        return {
            "url": response.url,
            "title": title,
            "content": text
        }

    except requests.RequestException as error:

        print(f"Failed: {url} - {error}")
        return None


# --------------------------------------------------
# LINK DISCOVERY
# --------------------------------------------------

def discover_links(base_url):
    """Find relevant internal links from the homepage."""

    try:

        response = requests.get(
            base_url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type", ""
        )

        if "text/html" not in content_type.lower():
            print("Homepage is not HTML:", base_url)
            return set()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        # Use the final URL after redirects as the reference.
        actual_base_url = response.url

        links = set()

        for anchor in soup.find_all("a", href=True):

            full_url = urljoin(
                actual_base_url,
                anchor["href"]
            )

            if not is_valid_internal_url(
                full_url,
                actual_base_url
            ):
                continue

            normalized_url = normalize_url(full_url)

            link_text = anchor.get_text(
                " ",
                strip=True
            ).lower()

            searchable_text = (
                normalized_url + " " + link_text
            ).lower()

            if any(
                keyword in searchable_text
                for keyword in KEYWORDS
            ):
                links.add(normalized_url)

        return links

    except requests.RequestException as error:

        print(f"Could not discover links: {error}")
        return set()


# --------------------------------------------------
# COMPANY WEBSITE CRAWLER
# --------------------------------------------------

def crawl_company_website(
    base_url,
    max_pages=DEFAULT_MAX_PAGES,
    output_file="website_data.json"
):
    """
    Crawl relevant pages from any company's website.

    Parameters:
        base_url: Company website URL.
        max_pages: Maximum number of pages to extract.
        output_file: JSON output path.

    Returns:
        List of extracted webpage dictionaries.
    """

    base_url = normalize_base_url(base_url)

    if max_pages < 1:
        raise ValueError("max_pages must be at least 1.")

    print("\nStarting company website crawler...")
    print("Website:", base_url)

    # Discover relevant pages
    discovered = discover_links(base_url)

    # Homepage is always included
    urls = [base_url]

    for url in sorted(discovered):

        if url not in urls:
            urls.append(url)

    urls = urls[:max_pages]

    print(f"\nDiscovered {len(urls)} pages")

    extracted_pages = []
    processed_urls = set()

    for url in urls:

        normalized_url = normalize_url(url)

        if normalized_url in processed_urls:
            continue

        processed_urls.add(normalized_url)

        print("\nExtracting:", url)

        page = get_page(url)

        if page:
            extracted_pages.append(page)

        time.sleep(REQUEST_DELAY)

    # Save extracted pages
    output_path = Path(output_file)
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with output_path.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            extracted_pages,
            file,
            ensure_ascii=False,
            indent=4
        )

    print("\n--------------------------------")
    print("Website extraction completed.")
    print("Pages saved:", len(extracted_pages))
    print("Output:", output_path.resolve())

    return extracted_pages


# --------------------------------------------------
# STANDALONE EXECUTION
# --------------------------------------------------

if __name__ == "__main__":

    print("=== Company Website Crawler ===")

    website = input(
        "Enter company website URL: "
    ).strip()

    crawl_company_website(
        base_url=website,
        max_pages=DEFAULT_MAX_PAGES,
        output_file="website_data.json"
    )
