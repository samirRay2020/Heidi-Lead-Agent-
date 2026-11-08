
import json
import re
from pathlib import Path

import ollama


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

MODEL = "qwen2.5:3b"

INPUT_FILE = "evidence.json"
COMPANY_INPUT_FILE = "company_input.json"
OUTPUT_FILE = "research_result.json"

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


def get_company_details(company_input_file=COMPANY_INPUT_FILE):

    company_data = load_json(company_input_file)

    company_name = company_data.get(
        "company_name",
        "Unknown company"
    )

    return {
        "company_name": company_name,
        "location": company_data.get("location", ""),
        "website": company_data.get("website", "")
    }


# --------------------------------------------------
# AI EXTRACTION INSTRUCTIONS
# --------------------------------------------------

FIELDS = {

    "company_name_and_address": """
Extract the legal company name and full postal address.

Use only the supplied evidence.

Return:
{
    "company_name": null,
    "address": null
}
""",

    "employees": """
Extract the company's total number of employees only if
explicitly supported by the supplied evidence.

Distinguish an exact employee count from an employee-size range.
Do not infer employee count from job advertisements.

Return:
{
    "value": null,
    "employee_range": null,
    "source_url": null,
    "notes": null
}
""",

    "digital_customer_experience": """
Identify customer-facing digital services, such as:

- Owner or tenant portals
- Online document access
- Digital invoice inspection
- Online statements
- Digital communication
- Customer-facing mobile applications

Do not include internal software unless customers use it directly.

Extract relevant features and their source URLs.

Return:
{
    "available": false,
    "features": [],
    "source_urls": []
}
""",

    "company_growth": f"""
Determine whether the company explicitly expanded its managed
portfolio or business between {GROWTH_START_YEAR} and
{GROWTH_END_YEAR}, inclusive.

Use these classifications:

- Portfolio Expansion: increase in managed units, properties,
  or client portfolios.
- Business Expansion: acquisitions, mergers, new locations,
  or expansion into new business areas.
- No: only when explicit evidence confirms no expansion.
- N/A: when evidence is insufficient.

A current portfolio figure or milestone alone does not prove
growth. Hiring alone does not prove business expansion.

Only use evidence dated between {GROWTH_START_YEAR} and
{GROWTH_END_YEAR}.

Return:
{{
    "status": "N/A",
    "type": "N/A",
    "year": null,
    "description": null,
    "source_url": null
}}
""",

    "decision_makers": """
Extract named company decision-makers and their explicitly
stated company roles.

Distinguish:

- Executive management: Geschäftsführer, Geschäftsführung,
  Managing Director, CEO.
- Other company leadership: Prokurist, Vorstand, or equivalent.
- Supervisory board: Aufsichtsrat or Supervisory Board.

Do not classify supervisory-board members as executive management.

Only include email addresses and LinkedIn profiles when explicitly
present in the evidence and clearly associated with that individual.

Never invent names, positions, emails or LinkedIn URLs.

Return:
{
    "people": [
        {
            "name": "",
            "role": "",
            "management_category": "",
            "email": null,
            "linkedin": null,
            "source_url": ""
        }
    ]
}
"""
}


# --------------------------------------------------
# AI MODEL
# --------------------------------------------------

def call_model(company, field, instruction, snippets):

    prompt = f"""
You are a business research analyst.

COMPANY:
{company['company_name']}

LOCATION:
{company['location']}

Use ONLY the evidence provided below.

Rules:
- Never invent information.
- Do not use general knowledge.
- Copy source URLs exactly.
- Use null or N/A when information is unavailable.
- Distinguish facts from estimates and ranges.
- Return only valid JSON.

TASK:
{instruction}

EVIDENCE:
{json.dumps(snippets, ensure_ascii=False, indent=2)}
"""

    response = ollama.chat(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract factual business information from German "
                    "and English sources. Be conservative and return "
                    "valid JSON only."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        format="json",
        options={
            "temperature": 0,
            "num_ctx": 4096
        }
    )

    return json.loads(
        response["message"]["content"]
    )


# --------------------------------------------------
# MANAGED UNITS: PYTHON EXTRACTION
# --------------------------------------------------

def extract_managed_units(evidence):

    candidates = []

    patterns = [
        r"Einheiten\s+verwaltet\s+([\d.]+)",

        r"([\d.]+)\s+"
        r"(?:betreute[nr]?|verwaltete[nr]?|gemanagte[nr]?)\s+"
        r"(?:Vertrags)?einheiten",

        r"(?:betreuen|verwalten|managen)\s+"
        r"(?:wir\s+)?(?:derzeit\s+)?(?:über\s+|rund\s+)?"
        r"([\d.]+)\s+(?:Vertrags)?einheiten"
    ]

    for item in evidence:

        if item.get("field") != "managed_units":
            continue

        text = item.get("text", "")

        for pattern in patterns:

            match = re.search(
                pattern,
                text,
                re.IGNORECASE
            )

            if not match:
                continue

            value = int(
                match.group(1).replace(".", "")
            )

            candidates.append({
                "value": value,
                "source_url": item.get("source_url"),
                "evidence_text": text
            })

            break

    if not candidates:

        return {
            "value": None,
            "source_url": None,
            "evidence_text": None,
            "other_reported_figures": []
        }

    # Remove duplicate figures from the same source.
    unique_candidates = []
    seen = set()

    for candidate in candidates:

        key = (
            candidate["value"],
            candidate["source_url"]
        )

        if key not in seen:

            seen.add(key)
            unique_candidates.append(candidate)

    # Select the largest reported number.
    unique_candidates.sort(
        key=lambda item: item["value"],
        reverse=True
    )

    primary = unique_candidates[0]

    return {
        "value": primary["value"],
        "source_url": primary["source_url"],
        "evidence_text": primary["evidence_text"],
        "selection_method": "Largest reported figure",
        "other_reported_figures": unique_candidates[1:]
    }


# --------------------------------------------------
# DIGITAL CUSTOMER EXPERIENCE: PYTHON FALLBACK
# --------------------------------------------------

def extract_digital_features(evidence):

    feature_patterns = {

        "Customer online portal": [
            r"Onlineportal",
            r"Onlineportale",
            r"Kundenportal",
            r"Eigentümerportal",
            r"Mieterportal"
        ],

        "Online access to property documents": [
            r"Dokumente.{0,100}(?:online|Portal|zugreifen)",
            r"(?:online|Portal).{0,100}Dokumente",
            r"Unterlagen.{0,100}(?:Onlineportal|online)"
        ],

        "Digital measures catalogue": [
            r"digitale Maßnahmenkataloge"
        ],

        "Online invoice inspection": [
            r"Onlinebelegprüfung"
        ],

        "Digital customer communication": [
            r"digitale Kommunikation"
        ],

        "Customer mobile application": [
            r"mobile app",
            r"Kunden.?App"
        ]
    }

    features = []
    source_urls = []

    for item in evidence:

        if item.get("field") != "digital_customer_experience":
            continue

        text = item.get("text", "")
        url = item.get("source_url", "")

        for feature, patterns in feature_patterns.items():

            if any(
                re.search(pattern, text, re.IGNORECASE)
                for pattern in patterns
            ):

                if feature not in features:
                    features.append(feature)

                if url and url not in source_urls:
                    source_urls.append(url)

    return {
        "available": len(features) > 0,
        "features": features,
        "source_urls": source_urls
    }


# --------------------------------------------------
# DECISION-MAKER VALIDATION
# --------------------------------------------------

def find_supervisory_board_names(evidence):

    supervisory_names = set()

    board_patterns = [

        r"(?:Vorsitzender|Vorsitzende)\s+"
        r"des\s+Aufsichtsrats\s+"
        r"(?:Dr\.?\s*)?"
        r"([A-ZÄÖÜ][a-zäöüß-]+\s+[A-ZÄÖÜ][a-zäöüß-]+)",

        r"Chairman\s+of\s+the\s+Supervisory\s+Board\s+"
        r"([A-Z][a-z-]+\s+[A-Z][a-z-]+)"
    ]

    for item in evidence:

        text = item.get("text", "")

        for pattern in board_patterns:

            matches = re.findall(
                pattern,
                text,
                re.IGNORECASE
            )

            for name in matches:
                supervisory_names.add(
                    name.strip().lower()
                )

    return supervisory_names


def validate_decision_makers(result, evidence):

    if not isinstance(result, dict):
        return {"people": []}

    people = result.get("people", [])

    if not isinstance(people, list):
        return {"people": []}

    supervisory_names = find_supervisory_board_names(
        evidence
    )

    validated_people = []

    for person in people:

        if not isinstance(person, dict):
            continue

        name = person.get("name", "")

        if not isinstance(name, str):
            continue

        name = name.strip()

        if not name:
            continue

        # Exclude explicitly identified supervisory-board members.
        if name.lower() in supervisory_names:
            continue

        validated_people.append(person)

    return {
        "people": validated_people
    }


# --------------------------------------------------
# DEFAULT RESULTS
# --------------------------------------------------

def get_default_result(field):

    defaults = {

        "company_name_and_address": {
            "company_name": None,
            "address": None
        },

        "employees": {
            "value": None,
            "employee_range": None,
            "source_url": None,
            "notes": "N/A - No supporting evidence found"
        },

        "digital_customer_experience": {
            "available": False,
            "features": [],
            "source_urls": []
        },

        "company_growth": {
            "status": "N/A",
            "type": "N/A",
            "year": None,
            "description": None,
            "source_url": None
        },

        "decision_makers": {
            "people": []
        }
    }

    return defaults.get(field)


# --------------------------------------------------
# GROWTH EVIDENCE CHECK
# --------------------------------------------------

def has_dated_growth_evidence(snippets):

    growth_pattern = re.compile(
        r"Portfolio|Bestand|erweitert|gewachsen|"
        r"vergrößert|ausgebaut|Übernahme|Akquisition|"
        r"Fusion|Expansion|new office|new location|"
        r"acquisition|merger|takeover|expanded|"
        r"portfolio growth",
        re.IGNORECASE
    )

    for item in snippets:

        text = item.get("text", "")

        has_year = any(
            re.search(rf"\b{year}\b", text)
            for year in range(
                GROWTH_START_YEAR,
                GROWTH_END_YEAR + 1
            )
        )

        if has_year and growth_pattern.search(text):
            return True

    return False


# --------------------------------------------------
# COMPANY ANALYSIS PIPELINE
# --------------------------------------------------

def run_company_analysis(
    company=None,
    company_input_file=COMPANY_INPUT_FILE,
    evidence_file=INPUT_FILE,
    output_file=OUTPUT_FILE
):
    """
    Analyse company evidence using Qwen and Python validation.

    Can be called directly from main.py.

    Parameters:
        company: Optional company dictionary.
        company_input_file: Company input JSON path.
        evidence_file: Evidence JSON path.
        output_file: Research result JSON path.

    Returns:
        Consolidated company research dictionary.
    """

    print("\nStarting company analysis...")

    if company is None:
        company = get_company_details(
            company_input_file
        )

    evidence = load_json(evidence_file)

    print("Company:", company["company_name"])
    print("Location:", company.get("location", ""))
    print(
        f"Growth period: "
        f"{GROWTH_START_YEAR}–{GROWTH_END_YEAR}"
    )
    print("Evidence snippets:", len(evidence))

    results = {
        "company": company,

        "research_period": {
            "growth_start_year": GROWTH_START_YEAR,
            "growth_end_year": GROWTH_END_YEAR
        }
    }

    # Process each AI research field.
    for field, instruction in FIELDS.items():

        snippets = [
            item for item in evidence
            if item.get("field") == field
        ]

        print(f"\nProcessing: {field}")

        if not snippets:

            results[field] = get_default_result(field)

            print("No supporting evidence found.")
            continue

        # Growth requires dated evidence before using Qwen.
        if field == "company_growth":

            if not has_dated_growth_evidence(snippets):

                results[field] = get_default_result(field)

                print("No dated growth evidence found.")
                continue

        try:

            # Limit evidence to avoid overloading the local model.
            model_snippets = snippets[:12]

            model_result = call_model(
                company,
                field,
                instruction,
                model_snippets
            )

            results[field] = model_result

        except Exception as error:

            print("AI extraction error:", error)

            results[field] = get_default_result(field)

        # Apply deterministic digital-service fallback.
        if field == "digital_customer_experience":

            digital_result = extract_digital_features(
                evidence
            )

            if (
                not isinstance(results[field], dict)
                or not results[field].get("features")
            ):

                results[field] = digital_result

        # Exclude supervisory-board members.
        elif field == "decision_makers":

            results[field] = validate_decision_makers(
                results[field],
                evidence
            )

        print(
            json.dumps(
                results[field],
                ensure_ascii=False,
                indent=2
            )
        )

    # Managed units are extracted separately using Python.
    # This avoids depending on AI interpretation of numbers.
    print("\nProcessing: managed_units")

    results["managed_units"] = extract_managed_units(
        evidence
    )

    print(
        json.dumps(
            results["managed_units"],
            ensure_ascii=False,
            indent=2
        )
    )

    # Save consolidated research result.
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
            results,
            file,
            ensure_ascii=False,
            indent=4
        )

    print("\n--------------------------------")
    print("Company analysis completed.")
    print("Saved to:", output_path.resolve())
    print("--------------------------------")

    return results


# --------------------------------------------------
# STANDALONE EXECUTION
# --------------------------------------------------

if __name__ == "__main__":

    run_company_analysis()
