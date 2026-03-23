"""Convert the undergraduate course-list PDF into frontend JSON data using pdfplumber."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path

import pdfplumber

CODE_RE = re.compile(r"^[0-9A-Z]{7}$")
NOTE_KEYWORDS = [
    "CDP",
    "G科目",
    "実務経験教員",
    "対面(",
    "対面",
    "オンライン(",
    "オンライン",
]

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", help="input PDF path")
    parser.add_argument("output_dir", help="output directory for kdb.json files")
    return parser.parse_args()

def normalize_note(note: str) -> str:
    if not note:
        return ""
    
    # Process newlines in note: 
    # If a line has less than 9 characters, prepend a space.
    # Otherwise, replace '\n' with an empty string.
    lines = note.split('\n')
    note_cleaned = ""
    for i, line in enumerate(lines):
        if i > 0:
            if len(lines[i-1]) < 9:
                note_cleaned += " "
        note_cleaned += line
        
    note = note_cleaned

    for keyword in NOTE_KEYWORDS:
        note = note.replace(keyword, f" {keyword}")
    note = re.sub(r"(対象)(?=\S)", r"\1 ", note)
    note = re.sub(r"\s+", " ", note).strip()
    return note

def looks_like_name(text: str) -> bool:
    return bool(
        re.fullmatch(r"[A-Za-zァ-ヶ一-龯々・ー]+(?: [A-Za-zァ-ヶ一-龯々・ー]+)?", text)
    )

def normalize_teacher(timeslot: str, teacher: str) -> tuple[str, str]:
    if not teacher:
        teacher = ""
    if not timeslot:
        timeslot = ""
        
    if " " in timeslot:
        parts = timeslot.split(" ", 1)
        if len(parts) == 2:
            base, extra = parts
            if extra and not any(char.isdigit() for char in extra):
                timeslot = base
                teacher = f"{extra} {teacher}".strip()

    if "。" in teacher and not teacher.startswith("注:"):
        suffix = teacher.rsplit("。", 1)[-1].strip()
        if looks_like_name(suffix):
            teacher = suffix

    teacher = re.sub(r"^[ぁ-んァ-ヶー一-龯々]+。", "", teacher).strip()
    teacher = re.sub(r"\s+", " ", teacher)
    return timeslot, teacher

def normalize_record(record: list[str | None]) -> list[str]:
    # 10 columns: [科目番号, 科目名, 授業方法, 単位数, 標準履修年次, 実施学期, 曜時限, 担当教員, 授業概要, 備考]
    raw_record = [str(cell) if cell is not None else "" for cell in record]
    
    # 1. Clean up newlines
    # For note (index 9), we let normalize_note handle the raw string with \n
    cleaned = []
    for i, field in enumerate(raw_record):
        if i == 9:
            cleaned.append(field.strip())
        elif i in (1, 8):
            field = re.sub(r'([a-zA-Z])\n', r'\1 ', field)
            cleaned.append(field.replace("\n", "").strip())
        else:
            cleaned.append(field.replace("\n", "").strip())
    
    code = cleaned[0]
    name = cleaned[1]
    method = cleaned[2]
    credit = cleaned[3].replace(" ", "") # Remove spaces inside credit like "1 . 0" if any
    year = cleaned[4]
    term = cleaned[5]
    timeslot = cleaned[6]
    teacher = cleaned[7]
    abstract = cleaned[8]
    note = cleaned[9]

    # Handle combined code + name (e.g., if columns got merged or split weirdly in `code`)
    code_match = re.match(r"^([0-9A-Z]{7})(.*)$", code)
    if code_match is not None:
        code = code_match.group(1)
        extra_name = code_match.group(2).strip()
        if extra_name:
            name = f"{extra_name} {name}".strip()

    # Handle combined year and term
    combined_year_term = f"{year} {term}".strip()
    year_term_match = re.match(
        r"^([1-6](?:\s*[・-]\s*[1-6])?)\s+(.*)$", combined_year_term
    )
    if year_term_match is not None:
        year = year_term_match.group(1).replace(" ", "")
        term = year_term_match.group(2).strip()

    timeslot, teacher = normalize_teacher(timeslot, teacher)
    note = normalize_note(note)

    if not CODE_RE.fullmatch(code):
        raise ValueError(f"invalid course code: {code}")

    # Output expects 11 columns, index 7 is an empty string for compatibility
    return [
        code,
        name,
        method.replace(" ", ""),
        f" {credit}" if credit else "",
        year,
        term,
        timeslot,
        "",
        teacher,
        abstract,
        note,
    ]

def dedupe_records(records: list[list[str]]) -> tuple[list[list[str]], int]:
    unique: list[list[str]] = []
    seen: set[str] = set()
    duplicate_count = 0
    for record in records:
        if record[0] in seen:
            duplicate_count += 1
            continue
        seen.add(record[0])
        unique.append(record)
    return unique, duplicate_count

def extract_records_from_pdf(pdf_path: Path) -> list[list[str]]:
    records: list[list[str]] = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            table = page.extract_table({
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "snap_tolerance": 3,
            })
            if not table:
                continue
            
            # Check if this table is the course catalog
            header = table[0]
            if not header or not header[0] or "科目番号" not in header[0].replace("\n", ""):
                continue
                
            for row in table[1:]:
                if not row or not row[0]:
                    continue
                
                # Simple check if the first column looks like a course code
                code_cand = str(row[0]).replace("\n", "").strip()[:7]
                if CODE_RE.match(code_cand) and len(row) >= 10:
                    try:
                        normalized = normalize_record(row[:10])
                        records.append(normalized)
                    except ValueError:
                        # Skip rows that couldn't be normalized (invalid code etc.)
                        pass
                        
    return records

def dump_output(records: list[list[str]], output_dir: Path) -> None:
    updated = dt.datetime.now().strftime("%Y/%m/%d")
    undergrad = [record for record in records if not record[0].startswith("0")]
    grad = [record for record in records if record[0].startswith("0")]

    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "kdb.json").open("w", encoding="utf-8") as fp:
        json.dump({"updated": updated, "subject": undergrad}, fp, indent="  ", ensure_ascii=False)
    with (output_dir / "kdb-grad.json").open("w", encoding="utf-8") as fp:
        json.dump({"updated": updated, "subject": grad}, fp, indent="  ", ensure_ascii=False)

def main() -> None:
    args = parse_args()
    pdf_path = Path(args.pdf)
    output_dir = Path(args.output_dir)

    records = extract_records_from_pdf(pdf_path)
    
    if not records:
        print("Error: No syllabus records found.")
        return

    unique_records, duplicate_count = dedupe_records(records)
    dump_output(unique_records, output_dir)

    undergrad_count = sum(not record[0].startswith("0") for record in unique_records)
    grad_count = len(unique_records) - undergrad_count

    print(
        json.dumps(
            {
                "raw_records": len(records),
                "duplicate_codes": duplicate_count,
                "unique_records": len(unique_records),
                "undergrad": undergrad_count,
                "grad": grad_count,
            },
            ensure_ascii=False,
        )
    )

if __name__ == "__main__":
    main()