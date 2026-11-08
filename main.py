
import json
from pathlib import Path

from crawler import crawl_company_website
from extract_evidence import run_evidence_extraction
from analyze_company import run_company_analysis
from external_research import search_external_research
from validate_external import run_external_validation
from check_data import run_consolidation


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

COMPANY_INPUT_FILE = "company_input.json"

WEBSITE_DATA_FILE = "website_data.json"
EVIDENCE_FILE = "evidence.json"
RESEARCH_FILE = "research_result.json"

EXTERNAL_SEARCH_FILE = "external_search.json"
VALIDATED_EXTERNAL_FILE = "validated_external.json"

FINAL_OUTPUT_FILE = "final_company_data.json"


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def load_company_input():

    path = Path(COMPANY_INPUT_FILE)

    if not path.exists():
        raise FileNotFoundError(
            f"Company input file not found: {COMPANY_INPUT_FILE}"
        )

    with path.open("r", encoding="utf-8") as file:
        company = json.load(file)

    required_fields = [
        "company_name",
        "location",
        "website"
    ]

    for field in required_fields:

        if not company.get(field):
            raise ValueError(
                f"Missing required company input: {field}"
            )

    return company


def print_step(step, message):

    print("\n" + "=" * 60)
    print(f"STEP {step}: {message}")
    print("=" * 60)


def check_output_file(filename):

    path = Path(filename)

    if not path.exists():
        raise FileNotFoundError(
            f"Expected output file was not created: {filename}"
        )

    return path


# --------------------------------------------------
# MAIN PIPELINE
# --------------------------------------------------

def main():

    print("\nHEIDI SYSTEMS - COMPANY RESEARCH AGENT")
    print("=" * 60)

    # Load company information
    company = load_company_input()

    company_name = company["company_name"]
    location = company["location"]
    website = company["website"]

    print(f"\nCompany: {company_name}")
    print(f"Location: {location}")
    print(f"Website: {website}")

    # --------------------------------------------------
    # STEP 1: CRAWL COMPANY WEBSITE
    # --------------------------------------------------

    print_step(1, "CRAWLING COMPANY WEBSITE")

    pages = crawl_company_website(
        base_url=website,
        max_pages=20,
        output_file=WEBSITE_DATA_FILE
    )

    if not pages:
        raise RuntimeError(
            "Website crawling returned no pages. "
            "Stopping the research pipeline."
        )

    print(f"Pages collected: {len(pages)}")

    check_output_file(WEBSITE_DATA_FILE)

    # --------------------------------------------------
    # STEP 2: EXTRACT WEBSITE EVIDENCE
    # --------------------------------------------------

    print_step(2, "EXTRACTING WEBSITE EVIDENCE")

    evidence = run_evidence_extraction(
        input_file=WEBSITE_DATA_FILE,
        output_file=EVIDENCE_FILE
    )

    check_output_file(EVIDENCE_FILE)

    print("Website evidence extraction completed.")

    # --------------------------------------------------
    # STEP 3: AI COMPANY ANALYSIS
    # --------------------------------------------------

    print_step(3, "ANALYSING COMPANY WITH QWEN")

    research = run_company_analysis(
        company=company,
        evidence_file=EVIDENCE_FILE,
        output_file=RESEARCH_FILE
    )

    check_output_file(RESEARCH_FILE)

    print("AI company analysis completed.")

    # --------------------------------------------------
    # STEP 4: EXTERNAL RESEARCH
    # --------------------------------------------------

    print_step(4, "SEARCHING EXTERNAL SOURCES")

    external_results = search_external_research(
        company_name=company_name,
        location=location,
        output_path=EXTERNAL_SEARCH_FILE
    )

    check_output_file(EXTERNAL_SEARCH_FILE)

    print(
        f"External research completed. "
        f"Results collected: {len(external_results)}"
    )

    # --------------------------------------------------
    # STEP 5: VALIDATE EXTERNAL FINDINGS
    # --------------------------------------------------

    print_step(5, "VALIDATING EXTERNAL FINDINGS")

    validated_external = run_external_validation(
        company_data=company,
        research=research,
        external_results=external_results,
        output_file=VALIDATED_EXTERNAL_FILE
    )

    check_output_file(VALIDATED_EXTERNAL_FILE)

    print("External validation completed.")

    # --------------------------------------------------
    # STEP 6: CONSOLIDATE FINAL RESULTS
    # --------------------------------------------------

    print_step(6, "CONSOLIDATING FINAL COMPANY DATA")

    final_data = run_consolidation(
        research=research,
        external=validated_external,
        output_file=FINAL_OUTPUT_FILE
    )

    check_output_file(FINAL_OUTPUT_FILE)

    # --------------------------------------------------
    # FINAL SUMMARY
    # --------------------------------------------------

    print("\n" + "=" * 60)
    print("RESEARCH PIPELINE COMPLETED")
    print("=" * 60)

    print(f"Company: {company_name}")
    print(f"Location: {location}")

    print("\nGenerated files:")

    output_files = [
        WEBSITE_DATA_FILE,
        EVIDENCE_FILE,
        RESEARCH_FILE,
        EXTERNAL_SEARCH_FILE,
        VALIDATED_EXTERNAL_FILE,
        FINAL_OUTPUT_FILE
    ]

    for filename in output_files:
        print(f"  - {filename}")

    print("\nQuality check:")

    print(json.dumps(
        final_data.get("quality_check", {}),
        ensure_ascii=False,
        indent=2
    ))

    print("\nAll pipeline steps completed successfully.")


# --------------------------------------------------
# EXECUTION
# --------------------------------------------------

if __name__ == "__main__":

    try:
        main()

    except Exception as error:

        print("\n" + "=" * 60)
        print("PIPELINE STOPPED")
        print("=" * 60)

        print(f"Error: {error}")

        raise
