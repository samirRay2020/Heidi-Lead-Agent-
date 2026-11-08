
import json
import re
from pathlib import Path
from urllib.parse import urlparse


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

COMPANY_INPUT_FILE = "company_input.json"
RESEARCH_FILE = "research_result.json"
INPUT_FILE = "external_search.json"
OUTPUT_FILE = "validated_external.json"

GROWTH_START_YEAR = 2021
GROWTH_END_YEAR = 2026


# --------------------------------------------------
# FILE HELPERS
# --------------------------------------------------

def load_json(filename):

    path = Path(filename)

    if not path.exists():
        raise FileNotFoundError(
            f"File not found: {filename}"
        )

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(data, filename):

    path = Path(filename)

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with path.open("w", encoding="utf-8") as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=4
        )

    return path


# --------------------------------------------------
# COMPANY INFORMATION
# --------------------------------------------------

def normalize_text(text):

    text = str(text).lower()

    text = re.sub(
        r"[^a-z0-9äöüß]+",
        " ",
        text
    )

    return " ".join(text.split())


def get_company_keywords(company_name):

    ignored_terms = {
        "gmbh", "mbh", "ag", "kg", "ohg",
        "ug", "gesellschaft", "company",
        "limited", "inc", "llc"
    }

    words = normalize_text(company_name).split()

    return [
        word for word in words
        if word not in ignored_terms and len(word) > 2
    ]


def is_company_related(item, company_name):

    title = item.get("title") or ""
    snippet = item.get("snippet") or ""
    url = item.get("url") or ""

    text = normalize_text(
        f"{title} {snippet} {url}"
    )

    keywords = get_company_keywords(company_name)

    if not keywords:
        return False

    matching_keywords = sum(
        1 for keyword in keywords
        if keyword in text
    )

    # Require all distinctive company-name terms.
    return matching_keywords == len(keywords)


# --------------------------------------------------
# EMPLOYEE EXTRACTION
# --------------------------------------------------

def extract_employee_information(text):

    # IMPORTANT:
    # Check ranges BEFORE exact counts.
    # Otherwise 11-50 employees could become 50 employees.

    range_patterns = [

        r"\b(\d{1,5})\s*[-–]\s*(\d{1,5})\s*"
        r"(?:mitarbeiter|mitarbeitende|beschäftigte|"
        r"angestellte|employees|staff members|staff)\b",

        r"\b(?:mitarbeiter|mitarbeitende|employees|staff)\s*"
        r"(?:zwischen|between)?\s*(\d{1,5})\s*[-–]\s*(\d{1,5})\b",

        r"\bcompany size\s*[:\-]?\s*"
        r"(\d{1,5})\s*[-–]\s*(\d{1,5})\b"
    ]

    for pattern in range_patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            lower = int(match.group(1))
            upper = int(match.group(2))

            if lower <= upper:

                return {
                    "employee_count": None,
                    "employee_range": f"{lower}–{upper}",
                    "employee_type": "Range"
                }

    # Exact employee counts.
    exact_patterns = [

        r"\b(?<![-–])(\d{1,5})\s*"
        r"(?:mitarbeiter|mitarbeitende|beschäftigte|"
        r"angestellte|employees|staff members)\b",

        r"\b(?:team von|team of)\s+(\d{1,5})\b"
    ]

    for pattern in exact_patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            return {
                "employee_count": int(match.group(1)),
                "employee_range": None,
                "employee_type": "Reported count"
            }

    return None


# --------------------------------------------------
# COMPANY GROWTH VALIDATION
# --------------------------------------------------

GROWTH_TERMS = [
    "portfolio expansion",
    "portfolio expanded",
    "portfolio growth",
    "portfolio increased",
    "bestand erweitert",
    "bestand gewachsen",
    "bestand vergrößert",
    "bestand ausgebaut",
    "portfolio erweitert",
    "portfolio ausgebaut",
    "übernahme",
    "akquisition",
    "fusion",
    "zusammenschluss",
    "acquisition",
    "merger",
    "takeover",
    "expanded portfolio",
    "new office",
    "new location",
    "additional properties",
    "additional units",
    "new properties",
    "new business area"
]


def extract_growth_year(text):

    years = re.findall(
        r"\b(?:2021|2022|2023|2024|2025|2026)\b",
        text
    )

    valid_years = [
        int(year)
        for year in years
        if GROWTH_START_YEAR <= int(year) <= GROWTH_END_YEAR
    ]

    return valid_years[0] if valid_years else None


def is_growth_evidence(text):

    text_lower = text.lower()

    return any(
        term in text_lower
        for term in GROWTH_TERMS
    )


# --------------------------------------------------
# DECISION-MAKER VALIDATION
# --------------------------------------------------

def get_known_decision_makers(research):

    people = (
        research
        .get("decision_makers", {})
        .get("people", [])
    )

    return [
        person.get("name", "").strip()
        for person in people
        if person.get("name")
    ]


def find_matching_person(text, known_people):

    normalized = normalize_text(text)

    for person in known_people:

        normalized_name = normalize_text(person)

        if normalized_name and normalized_name in normalized:
            return person

    return None


def is_direct_linkedin_profile(url):

    parsed = urlparse(url)

    if not parsed.hostname:
        return False

    domain = parsed.hostname.lower()

    return (
        domain.endswith("linkedin.com")
        and bool(
            re.match(
                r"^/in/[^/]+/?$",
                parsed.path
            )
        )
    )


# --------------------------------------------------
# VALIDATION PIPELINE
# --------------------------------------------------

def run_external_validation(
    company_data=None,
    research=None,
    external_results=None,
    company_input_file=COMPANY_INPUT_FILE,
    research_file=RESEARCH_FILE,
    input_file=INPUT_FILE,
    output_file=OUTPUT_FILE
):
    """
    Validate external research results.

    Can be called directly from main.py.

    Parameters:
        company_data: Optional company information dictionary.
        research: Optional AI research result dictionary.
        external_results: Optional external search results list.
        company_input_file: Company input JSON path.
        research_file: AI research JSON path.
        input_file: External search JSON path.
        output_file: Validation output JSON path.

    Returns:
        Validated external research dictionary.
    """

    print("\nStarting external research validation...")

    # Load data only when it has not been supplied.
    if company_data is None:
        company_data = load_json(company_input_file)

    if research is None:
        research = load_json(research_file)

    if external_results is None:
        external_results = load_json(input_file)

    company_name = company_data.get(
        "company_name",
        "Unknown company"
    )

    known_people = get_known_decision_makers(
        research
    )

    print("Company:", company_name)
    print(
        "Growth period:",
        f"{GROWTH_START_YEAR}–{GROWTH_END_YEAR}"
    )
    print("Known decision-makers:", len(known_people))
    print("External search results:", len(external_results))

    validated = {

        "company": company_name,

        "research_period": {
            "growth_start_year": GROWTH_START_YEAR,
            "growth_end_year": GROWTH_END_YEAR
        },

        "employees": [],
        "company_growth": [],
        "decision_makers": []
    }

    seen = set()

    for item in external_results:

        field = item.get("field", "")

        title = item.get("title") or ""
        snippet = item.get("snippet") or ""
        url = item.get("url") or ""

        text = f"{title} {snippet}"

        # ------------------------------------------
        # COMPANY RELEVANCE
        # ------------------------------------------

        if not is_company_related(
            item,
            company_name
        ):
            continue

        # ------------------------------------------
        # EMPLOYEES
        # ------------------------------------------

        if field == "employees":

            employee_info = extract_employee_information(
                text
            )

            if not employee_info:
                continue

            key = (
                "employees",
                employee_info["employee_count"],
                employee_info["employee_range"],
                url
            )

            if key in seen:
                continue

            seen.add(key)

            validated["employees"].append({

                **employee_info,

                "source_url": url,

                "evidence": snippet,

                "title": title
            })

        # ------------------------------------------
        # COMPANY GROWTH
        # ------------------------------------------

        elif field == "company_growth":

            year = extract_growth_year(text)

            if year is None:
                continue

            if not is_growth_evidence(text):
                continue

            key = (
                "company_growth",
                year,
                url
            )

            if key in seen:
                continue

            seen.add(key)

            validated["company_growth"].append({

                "year": year,

                "source_url": url,

                "evidence": snippet,

                "title": title
            })

        # ------------------------------------------
        # DECISION-MAKERS
        # ------------------------------------------

        elif field == "decision_makers":

            person = find_matching_person(
                text,
                known_people
            )

            if not person:
                continue

            direct_linkedin = is_direct_linkedin_profile(
                url
            )

            key = (
                "decision_makers",
                person,
                url
            )

            if key in seen:
                continue

            seen.add(key)

            validated["decision_makers"].append({

                "name": person,

                "source_url": url,

                "direct_linkedin_profile": direct_linkedin,

                "evidence": snippet,

                "title": title
            })

    # --------------------------------------------------
    # SUMMARY
    # --------------------------------------------------

    print("\nExternal validation summary:")

    print(
        "Employee findings:",
        len(validated["employees"])
    )

    print(
        "Growth findings:",
        len(validated["company_growth"])
    )

    print(
        "Decision-maker findings:",
        len(validated["decision_makers"])
    )

    output_path = save_json(
        validated,
        output_file
    )

    print("\nValidated external results:")

    print(
        json.dumps(
            validated,
            ensure_ascii=False,
            indent=2
        )
    )

    print("\nSaved to:", output_path.resolve())

    return validated


# --------------------------------------------------
# STANDALONE EXECUTION
# --------------------------------------------------

if __name__ == "__main__":

    run_external_validation()
