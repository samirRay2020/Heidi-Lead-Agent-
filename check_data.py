
import json
from pathlib import Path
from urllib.parse import urlparse


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

RESEARCH_FILE = "research_result.json"
EXTERNAL_FILE = "validated_external.json"
OUTPUT_FILE = "final_company_data.json"

EXPECTED_FIELDS = [
    "company_name_and_address",
    "managed_units",
    "employees",
    "digital_customer_experience",
    "company_growth",
    "decision_makers"
]


# --------------------------------------------------
# FILE HELPERS
# --------------------------------------------------

def load_json(filename):
    path = Path(filename)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {filename}")

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(data, filename):
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


# --------------------------------------------------
# GENERAL HELPERS
# --------------------------------------------------

def normalize_name(name):
    return " ".join(str(name).lower().split())


def is_valid_url(url):
    if not isinstance(url, str) or not url.strip():
        return False

    parsed = urlparse(url)

    return (
        parsed.scheme in ("http", "https")
        and bool(parsed.netloc)
    )


def add_source_url(source_urls, url):
    if is_valid_url(url) and url not in source_urls:
        source_urls.append(url)


# --------------------------------------------------
# EMPLOYEE CONSOLIDATION
# --------------------------------------------------

def consolidate_employees(research, external):

    website_result = research.get("employees") or {}
    external_results = external.get("employees", [])

    findings = []
    seen = set()

    def add_finding(value, finding_type, source_url, source_type):

        if value is None or value == "":
            return

        key = (
            str(value),
            finding_type,
            source_url
        )

        if key in seen:
            return

        seen.add(key)

        findings.append({
            "value": value,
            "type": finding_type,
            "source_url": source_url,
            "source_type": source_type
        })

    # Company website findings
    if website_result.get("value") is not None:
        add_finding(
            website_result["value"],
            "Reported employee count",
            website_result.get("source_url"),
            "Company website"
        )

    if website_result.get("employee_range"):
        add_finding(
            website_result["employee_range"],
            "Employee range",
            website_result.get("source_url"),
            "Company website"
        )

    # External findings
    for item in external_results:

        if item.get("employee_range"):
            add_finding(
                item["employee_range"],
                "Employee range",
                item.get("source_url"),
                "External source"
            )

        elif item.get("employee_count") is not None:
            add_finding(
                item["employee_count"],
                "Estimated employee count",
                item.get("source_url"),
                "External source"
            )

    return {
        "findings": findings,
        "status": "Available" if findings else "N/A",
        "note": (
            "Counts and ranges are reported separately. "
            "External estimates should not be treated as verified figures."
        )
    }


# --------------------------------------------------
# DECISION-MAKER CONSOLIDATION
# --------------------------------------------------

def consolidate_decision_makers(research, external):

    website_people = (
        research.get("decision_makers", {}).get("people", [])
    )

    external_people = external.get("decision_makers", [])

    consolidated = {}

    # First add people extracted from the company website.
    for person in website_people:

        name = person.get("name")

        if not name:
            continue

        key = normalize_name(name)

        if key not in consolidated:
            consolidated[key] = {
                "name": name,
                "role": person.get("role"),
                "management_category": person.get(
                    "management_category"
                ),
                "email": None,
                "linkedin": None,
                "source_urls": []
            }

        # Preserve the original role rather than translating it.
        if person.get("role"):
            consolidated[key]["role"] = person["role"]

        if person.get("management_category"):
            consolidated[key]["management_category"] = (
                person["management_category"]
            )

        # Only retain individually verified work emails.
        email = person.get("email")

        if email and "@" in email:
            consolidated[key]["email"] = email

        add_source_url(
            consolidated[key]["source_urls"],
            person.get("source_url")
        )

    # Add external findings and individual LinkedIn profiles.
    for person in external_people:

        name = person.get("name")

        if not name:
            continue

        key = normalize_name(name)

        if key not in consolidated:
            consolidated[key] = {
                "name": name,
                "role": None,
                "management_category": None,
                "email": None,
                "linkedin": None,
                "source_urls": []
            }

        url = person.get("source_url")

        add_source_url(
            consolidated[key]["source_urls"],
            url
        )

        # Accept only direct individual LinkedIn profile URLs.
        if (
            person.get("direct_linkedin_profile")
            and is_valid_url(url)
            and "/in/" in urlparse(url).path
        ):
            consolidated[key]["linkedin"] = url

        # Do not overwrite an existing role with an external snippet.
        if not consolidated[key]["role"] and person.get("role"):
            consolidated[key]["role"] = person["role"]

    return list(consolidated.values())


# --------------------------------------------------
# QUALITY CHECKS
# --------------------------------------------------

def check_missing_fields(data):

    missing = []

    for field in EXPECTED_FIELDS:

        if field not in data or data[field] is None:
            missing.append(field)

    return missing


def check_source_urls(data):

    missing_sources = []
    invalid_sources = []

    def inspect(value, path=""):

        if isinstance(value, dict):

            for key, item in value.items():

                current_path = (
                    f"{path}.{key}" if path else key
                )

                if key == "source_url":

                    if not item:
                        missing_sources.append(current_path)

                    elif not is_valid_url(item):
                        invalid_sources.append(current_path)

                elif key == "source_urls":

                    if not item:
                        missing_sources.append(current_path)

                    elif isinstance(item, list):

                        for index, url in enumerate(item):

                            if not is_valid_url(url):
                                invalid_sources.append(
                                    f"{current_path}[{index}]"
                                )

                else:
                    inspect(item, current_path)

        elif isinstance(value, list):

            for index, item in enumerate(value):
                inspect(item, f"{path}[{index}]")

    inspect(data)

    return {
        "missing_source_urls": missing_sources,
        "invalid_source_urls": invalid_sources
    }


# --------------------------------------------------
# MAIN CONSOLIDATION
# --------------------------------------------------

def run_consolidation(
    research=None,
    external=None,
    research_file=RESEARCH_FILE,
    external_file=EXTERNAL_FILE,
    output_file=OUTPUT_FILE
):

    print("Starting final data consolidation...\n")

    # Allow the function to be called with loaded data or file paths.
    if research is None:
        research = load_json(research_file)

    if external is None:
        external = load_json(external_file)

    final_data = {
        "company": research.get("company", {}),

        "research_period": research.get(
            "research_period", {}
        ),

        "company_name_and_address": research.get(
            "company_name_and_address"
        ),

        "managed_units": research.get(
            "managed_units"
        ),

        "employees": consolidate_employees(
            research,
            external
        ),

        "digital_customer_experience": research.get(
            "digital_customer_experience"
        ),

        "company_growth": research.get(
            "company_growth"
        ),

        "decision_makers": consolidate_decision_makers(
            research,
            external
        )
    }

    # Quality checks
    missing_fields = check_missing_fields(final_data)
    source_check = check_source_urls(final_data)

    final_data["quality_check"] = {
        "missing_fields": missing_fields,
        "missing_source_urls": source_check[
            "missing_source_urls"
        ],
        "invalid_source_urls": source_check[
            "invalid_source_urls"
        ],
        "all_expected_fields_present": (
            len(missing_fields) == 0
        )
    }

    save_json(final_data, output_file)

    company_name = (
        final_data.get("company", {}).get("company_name")
        or "Unknown company"
    )

    print("Consolidation completed.")
    print("Company:", company_name)

    print("\nQuality check:")
    print(json.dumps(
        final_data["quality_check"],
        ensure_ascii=False,
        indent=2
    ))

    print("\nFinal company data saved to:", output_file)

    return final_data


# --------------------------------------------------
# STANDALONE EXECUTION
# --------------------------------------------------

if __name__ == "__main__":
    run_consolidation()
