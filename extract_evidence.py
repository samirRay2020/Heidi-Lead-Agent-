
import json
import re
from pathlib import Path


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

INPUT_FILE = "website_data.json"
OUTPUT_FILE = "evidence.json"

GROWTH_START_YEAR = 2021
GROWTH_END_YEAR = 2026

GROWTH_YEARS = re.compile(
    rf"\b(?:{'|'.join(str(year) for year in range(GROWTH_START_YEAR, GROWTH_END_YEAR + 1))})\b"
)


# --------------------------------------------------
# EVIDENCE PATTERNS
# --------------------------------------------------

PATTERNS = {

    "managed_units": [
        r"\b\d[\d.,]*\s+(?:betreute[nr]?|verwaltete[nr]?|gemanagte[nr]?)\s+(?:Vertrags)?einheiten\b",
        r"\b(?:betreuen|verwalten|managen)\s+(?:wir\s+)?(?:derzeit\s+)?(?:über\s+|rund\s+|ca\.\s*)?\d[\d.,]*\s+(?:Vertrags)?einheiten\b",
        r"\b(?:Einheiten|Vertragseinheiten|Wohneinheiten)\s+(?:verwaltet|betreut)\s+\d[\d.,]*\b",
        r"\b\d[\d.,]*\s+(?:managed|administered)\s+units\b",
        r"\b(?:manage|manages|managing)\s+(?:over\s+|around\s+)?\d[\d.,]*\s+units\b"
    ],

    "employees": [
        r"\b\d+\s*(?:Mitarbeiter|Mitarbeitende|Beschäftigte|Angestellte)\b",
        r"\b\d+\s*(?:employees|staff members)\b",
        r"\b(?:Team von|team of)\s+\d+\b",
        r"\b(?:company size|Mitarbeiterzahl)\b.{0,60}\b\d+\b"
    ],

    "digital_customer_experience": [
        r"Onlineportal",
        r"Onlineportale",
        r"Kundenportal",
        r"Eigentümerportal",
        r"Mieterportal",
        r"Onlinebelegprüfung",
        r"digitale Maßnahmenkataloge",
        r"digitale Kommunikation",
        r"Dokumente.{0,100}(?:online|Portal|zugreifen)",
        r"(?:online|Portal).{0,100}(?:Dokumente|Rechnungen|Abrechnungen)",
        r"customer portal",
        r"tenant portal",
        r"owner portal",
        r"online document access",
        r"digital customer service",
        r"mobile app"
    ],

    "company_growth": [
        r"(?:Portfolio|Bestand).{0,100}(?:erweitert|gewachsen|vergrößert|ausgebaut)",
        r"(?:Übernahme|Akquisition|Fusion|Zusammenschluss)",
        r"(?:acquisition|merger|takeover)",
        r"(?:Expansion|expandiert|neuer Standort)",
        r"(?:new office|new location|portfolio growth)",
        r"(?:neue|zusätzliche) (?:Objekte|Einheiten|Immobilien|Mandate)",
        r"(?:new|additional) (?:properties|units|portfolios|contracts)"
    ],

    "decision_makers": [
        r"Geschäftsführer(?:in)?",
        r"Geschäftsführung",
        r"Geschäftsführender Gesellschafter",
        r"Vorstand",
        r"Prokurist(?:in)?",
        r"Mitglied der Geschäftsleitung",
        r"Managing Director",
        r"Chief Executive Officer",
        r"\bCEO\b",
        r"\bCFO\b",
        r"\bCOO\b",
        r"Executive Management"
    ]
}


# --------------------------------------------------
# VALIDATION PATTERNS
# --------------------------------------------------

GROWTH_TERMS = re.compile(
    r"Portfolio|Bestand|erweitert|gewachsen|vergrößert|ausgebaut|"
    r"Übernahme|Akquisition|Fusion|Expansion|neuer Standort|"
    r"acquisition|merger|takeover|expanded|expansion|"
    r"new office|new location|portfolio growth",
    re.IGNORECASE
)

AREA_PATTERN = re.compile(
    r"m[²2]|qm|Quadratmeter|square metres?|square meters?",
    re.IGNORECASE
)

SUPERVISORY_BOARD_TERMS = re.compile(
    r"Aufsichtsrat|Vorsitzender des Aufsichtsrats|"
    r"Chairman of the Supervisory Board|"
    r"Supervisory Board",
    re.IGNORECASE
)


# --------------------------------------------------
# INPUT
# --------------------------------------------------

def load_pages(input_file=INPUT_FILE):

    path = Path(input_file)

    if not path.exists():
        raise FileNotFoundError(
            f"File not found: {input_file}"
        )

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


# --------------------------------------------------
# TEXT PROCESSING
# --------------------------------------------------

def split_sentences(content):

    return [
        sentence.strip()
        for sentence in re.split(
            r"(?<=[.!?])\s+|\n+",
            content
        )
        if len(sentence.strip()) >= 20
    ]


def contains_person_name(sentence):

    return bool(
        re.search(
            r"\b[A-ZÄÖÜ][a-zäöüß-]+\s+"
            r"[A-ZÄÖÜ][a-zäöüß-]+\b",
            sentence
        )
    )


# --------------------------------------------------
# EVIDENCE EXTRACTION
# --------------------------------------------------

def extract_evidence(pages):

    evidence = []

    for page in pages:

        url = page.get("url", "")
        content = page.get("content", "")

        if not content:
            continue

        is_impressum = "impressum" in url.lower()

        # Preserve legal information for company name/address.
        if is_impressum:

            evidence.append({
                "field": "company_name_and_address",
                "source_url": url,
                "text": content[:5000]
            })

        sentences = split_sentences(content)

        for field, patterns in PATTERNS.items():

            for sentence in sentences:

                matches = any(
                    re.search(
                        pattern,
                        sentence,
                        re.IGNORECASE
                    )
                    for pattern in patterns
                )

                if not matches:
                    continue

                # Avoid confusing floor area with managed units.
                if field == "managed_units":

                    if AREA_PATTERN.search(sentence):
                        continue

                # Growth must be supported by a year
                # between 2021 and 2026.
                if field == "company_growth":

                    if not GROWTH_YEARS.search(sentence):
                        continue

                    if not GROWTH_TERMS.search(sentence):
                        continue

                # Exclude supervisory-board references.
                if field == "decision_makers":

                    if SUPERVISORY_BOARD_TERMS.search(sentence):
                        continue

                    if not contains_person_name(sentence):
                        continue

                evidence.append({
                    "field": field,
                    "source_url": url,
                    "text": sentence
                })

    return evidence


# --------------------------------------------------
# DEDUPLICATION
# --------------------------------------------------

def remove_duplicates(evidence):

    unique = []
    seen = set()

    for item in evidence:

        key = (
            item["field"],
            item["source_url"],
            item["text"].lower()
        )

        if key not in seen:

            seen.add(key)
            unique.append(item)

    return unique


# --------------------------------------------------
# SAVE OUTPUT
# --------------------------------------------------

def save_evidence(evidence, output_file=OUTPUT_FILE):

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
            evidence,
            file,
            ensure_ascii=False,
            indent=4
        )

    return output_path


# --------------------------------------------------
# COMPLETE EVIDENCE PIPELINE
# --------------------------------------------------

def run_evidence_extraction(
    input_file=INPUT_FILE,
    output_file=OUTPUT_FILE
):

    pages = load_pages(input_file)

    evidence = extract_evidence(pages)

    evidence = remove_duplicates(evidence)

    output_path = save_evidence(
        evidence,
        output_file
    )

    print("\nEvidence extraction completed.")
    print("Website pages loaded:", len(pages))
    print("Evidence snippets:", len(evidence))
    print("Saved to:", output_path.resolve())

    return evidence


# --------------------------------------------------
# STANDALONE EXECUTION
# --------------------------------------------------

if __name__ == "__main__":

    print("Starting generic evidence extraction...")
    print(
        f"Growth evidence period: "
        f"{GROWTH_START_YEAR}–{GROWTH_END_YEAR}\n"
    )

    evidence = run_evidence_extraction()

    for item in evidence:

        print(f"\nFIELD: {item['field']}")
        print(f"SOURCE: {item['source_url']}")
        print(f"EVIDENCE: {item['text'][:400]}")
