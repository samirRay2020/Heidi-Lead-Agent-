
import json
import time
from datetime import datetime
from pathlib import Path
from ddgs import DDGS


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

MAX_RESULTS = 5

COMPANY_INPUT_FILE = "company_input.json"
OUTPUT_FILE = "external_search.json"

GROWTH_START_YEAR = 2021
GROWTH_END_YEAR = 2026

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 3
QUERY_DELAY_SECONDS = 2


# --------------------------------------------------
# COMPANY INPUT
# --------------------------------------------------

def load_company_input():

    path = Path(COMPANY_INPUT_FILE)

    if not path.exists():
        raise FileNotFoundError(
            f"Company input file not found: {COMPANY_INPUT_FILE}"
        )

    with path.open("r", encoding="utf-8") as file:
        company = json.load(file)

    company_name = company.get("company_name", "").strip()
    location = company.get("location", "").strip()

    if not company_name:
        raise ValueError("Company name cannot be empty.")

    return company_name, location


# --------------------------------------------------
# SEARCH QUERY GENERATION
# --------------------------------------------------

def build_queries(company_name, location="", years=None):

    if years is None:
        years = list(
            range(GROWTH_START_YEAR, GROWTH_END_YEAR + 1)
        )

    company = company_name.strip()
    location_text = f" {location}" if location else ""
    year_text = " ".join(str(year) for year in years)

    return {

        "employees": [
            f'{company}{location_text} Mitarbeiter',
            f'{company} employees company size',
            f'{company} employee count LinkedIn'
        ],

        "company_growth": [
            f'{company}{location_text} Wachstum Expansion {year_text}',
            f'{company} Übernahme Akquisition Portfolio {year_text}',
            f'{company} neue Immobilien verwaltete Einheiten {year_text}',
            f'{company} portfolio expansion acquisition {year_text}'
        ],

        "decision_makers": [
            f'{company} Geschäftsführer Geschäftsführung',
            f'{company} Management Prokurist',
            f'{company} LinkedIn management'
        ]
    }


# --------------------------------------------------
# SEARCH FUNCTION
# --------------------------------------------------

def search_query(query, max_results):

    for attempt in range(MAX_RETRIES):

        try:

            # Create a fresh search session for every query.
            with DDGS() as ddgs:

                results = list(
                    ddgs.text(
                        query,
                        max_results=max_results
                    )
                )

            return results

        except Exception as error:

            print(
                f"Attempt {attempt + 1} failed: "
                f"{type(error).__name__}: {error}"
            )

            if attempt < MAX_RETRIES - 1:

                wait_time = (
                    RETRY_DELAY_SECONDS * (attempt + 1)
                )

                print(
                    f"Retrying in {wait_time} seconds..."
                )

                time.sleep(wait_time)

    print(
        f"Search failed after {MAX_RETRIES} attempts."
    )

    return []


# --------------------------------------------------
# EXTERNAL RESEARCH
# --------------------------------------------------

def search_external_research(
    company_name,
    location="",
    years=None,
    max_results=MAX_RESULTS,
    output_path=OUTPUT_FILE
):

    if not company_name or not company_name.strip():
        raise ValueError("Company name cannot be empty.")

    if years is None:
        years = list(
            range(GROWTH_START_YEAR, GROWTH_END_YEAR + 1)
        )

    queries = build_queries(
        company_name,
        location,
        years
    )

    all_results = []
    seen_sources = set()

    print("\nStarting external research")
    print("Company:", company_name)
    print("Location:", location or "Not specified")
    print(
        "Growth research period:",
        f"{min(years)}–{max(years)}"
    )
    print("Backend: DDGS default")

    for field, field_queries in queries.items():

        print(f"\nResearch field: {field}")

        for query in field_queries:

            print("\nSearching:", query)

            results = search_query(
                query,
                max_results
            )

            for result in results:

                url = result.get("href")

                source_key = (field, url)

                if not url or source_key in seen_sources:
                    continue

                seen_sources.add(source_key)

                item = {
                    "company_name": company_name,
                    "location": location,
                    "field": field,
                    "query": query,
                    "title": result.get("title"),
                    "url": url,
                    "snippet": result.get("body"),
                    "search_backend": "ddgs_default",
                    "collected_at": datetime.now().isoformat()
                }

                all_results.append(item)

                print("Title:", item["title"])
                print("URL:", item["url"])

            time.sleep(QUERY_DELAY_SECONDS)

    # Save results even when some queries fail.
    output_file = Path(output_path)

    with output_file.open("w", encoding="utf-8") as file:

        json.dump(
            all_results,
            file,
            ensure_ascii=False,
            indent=4
        )

    print("\nExternal research completed.")
    print("Total unique results:", len(all_results))
    print("Saved to:", output_file.resolve())

    return all_results


# --------------------------------------------------
# STANDALONE EXECUTION
# --------------------------------------------------

if __name__ == "__main__":

    print("=== Company External Research ===")

    company_name, location = load_company_input()

    search_external_research(
        company_name=company_name,
        location=location,
        years=list(
            range(GROWTH_START_YEAR, GROWTH_END_YEAR + 1)
        )
    )
