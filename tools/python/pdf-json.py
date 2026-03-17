"""Convert the undergraduate course-list PDF into frontend JSON data."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from math import inf
from pathlib import Path


XHTML_NS = {"x": "http://www.w3.org/1999/xhtml"}
CODE_RE = re.compile(r"[0-9A-Z]{7}")
LAYOUT_CODE_LINE_RE = re.compile(r"^([0-9A-Z]{7})\s+.*?\b[0-8]\s+\d+\.\d")
COURSE_HEADER = ("科目番号", "実施学期", "曜時限", "担当教員", "授業概要", "備考")
HEADER_WORDS = {
    "科目番号",
    "科目名",
    "授業",
    "方法",
    "単位数",
    "標準履",
    "修年次",
    "実施学期",
    "曜時限",
    "担当教員",
    "授業概要",
    "備考",
}
LINE_Y_TOLERANCE = 2.0
WORD_GAP_SPACE = 2.0
RECORD_LINE_GAP = 10.0
HEADER_SEARCH_ABOVE = 10.0
HEADER_SEARCH_BELOW = 15.0
NOTE_KEYWORDS = [
    "CDP",
    "G科目",
    "実務経験教員",
    "対面(",
    "対面",
    "オンライン(",
    "オンライン",
]


@dataclass(frozen=True)
class Word:
    text: str
    x0: float
    x1: float
    y0: float
    y1: float

    @property
    def x_center(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def y_center(self) -> float:
        return (self.y0 + self.y1) / 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", help="input PDF path")
    parser.add_argument("output_dir", help="output directory for kdb.json files")
    return parser.parse_args()


def run_text(pdf_path: Path) -> str:
    return subprocess.check_output(
        ["pdftotext", "-layout", str(pdf_path), "-"], text=True
    )


def run_bbox(pdf_path: Path, page_no: int) -> list[Word]:
    html = subprocess.check_output(
        [
            "pdftotext",
            "-f",
            str(page_no),
            "-l",
            str(page_no),
            "-bbox-layout",
            str(pdf_path),
            "-",
        ],
        text=True,
    )
    root = ET.fromstring(html)
    page = root.find(".//x:page", XHTML_NS)
    if page is None:
        raise ValueError(f"failed to parse page {page_no}")

    words: list[Word] = []
    for elem in page.iterfind(".//x:word", XHTML_NS):
        words.append(
            Word(
                text="".join(elem.itertext()),
                x0=float(elem.attrib["xMin"]),
                x1=float(elem.attrib["xMax"]),
                y0=float(elem.attrib["yMin"]),
                y1=float(elem.attrib["yMax"]),
            )
        )
    return words


def is_course_page(page_text: str) -> bool:
    if "開設授業科目一覧の見方" in page_text and "（例）" in page_text:
        return False

    return any(
        all(token in line for token in COURSE_HEADER) for line in page_text.splitlines()
    )


def code_count(page_text: str) -> int:
    return sum(
        1 for line in page_text.splitlines() if LAYOUT_CODE_LINE_RE.match(line)
    )


def find_start_page(pages: list[str]) -> int:
    for page_no, page_text in enumerate(pages, start=1):
        if is_course_page(page_text) and code_count(page_text) >= 5:
            return page_no
    raise ValueError("failed to locate the first course-list page")


def collect_target_pages(pages: list[str], start_page: int) -> list[int]:
    result: list[int] = []
    for page_no, page_text in enumerate(pages, start=1):
        if page_no < start_page:
            continue
        if is_course_page(page_text):
            result.append(page_no)
    return result


def count_expected_codes(pdf_path: Path, page_numbers: list[int]) -> int:
    total = 0
    for page_no in page_numbers:
        words = run_bbox(pdf_path, page_no)
        header_anchors = sorted(
            [word for word in words if word.text == "科目番号"],
            key=lambda word: word.y0,
        )
        for index, anchor in enumerate(header_anchors):
            segment_low = anchor.y0 - 8
            segment_high = (
                inf
                if index == len(header_anchors) - 1
                else header_anchors[index + 1].y0 - 8
            )
            segment_words = [
                word
                for word in words
                if segment_low <= word.y_center < segment_high
            ]
            starts = column_starts(segment_words, anchor.y0)
            positions = [position for _, position in starts]
            code_boundary = (positions[0] + positions[1]) / 2
            total += sum(
                1
                for word in segment_words
                if CODE_RE.fullmatch(word.text) and word.x_center < code_boundary
            )
    return total


def header_slice(words: list[Word], anchor_y: float) -> list[Word]:
    return [
        word
        for word in words
        if anchor_y - HEADER_SEARCH_ABOVE <= word.y_center <= anchor_y + HEADER_SEARCH_BELOW
    ]


def column_starts(words: list[Word], anchor_y: float) -> list[tuple[str, float]]:
    header_words = header_slice(words, anchor_y)
    required = {
        "code": ("科目番号",),
        "name": ("科目名",),
        "method": ("授業", "方法"),
        "credit": ("単位数", "単位"),
        "year": ("標準履", "標準", "履修", "修年次", "年次"),
        "term": ("実施学期",),
        "timeslot": ("曜時限",),
        "teacher": ("担当教員",),
        "abstract": ("授業概要",),
        "note": ("備考",),
    }

    positions: list[tuple[str, float]] = []
    for label, tokens in required.items():
        matches = [word for word in header_words if word.text in tokens]
        if not matches:
            raise ValueError(f"missing header token {tokens[0]}")
        positions.append((label, min(word.x0 for word in matches)))
    positions.sort(key=lambda item: item[1])
    return positions


def header_bottom(words: list[Word], anchor_y: float) -> float:
    return max(
        word.y1 for word in header_slice(words, anchor_y) if word.text in HEADER_WORDS
    )


def group_lines(words: list[Word]) -> list[list[Word]]:
    sorted_words = sorted(words, key=lambda word: (word.y_center, word.x0))
    lines: list[list[Word]] = []
    current: list[Word] = []
    current_y: float | None = None

    for word in sorted_words:
        if current_y is None or abs(word.y_center - current_y) <= LINE_Y_TOLERANCE:
            current.append(word)
            current_y = word.y_center if current_y is None else (current_y + word.y_center) / 2
            continue

        lines.append(current)
        current = [word]
        current_y = word.y_center

    if current:
        lines.append(current)
    return lines


def needs_space_between(prev_text: str, next_text: str) -> bool:
    if not prev_text or not next_text:
        return False

    prev_char = prev_text[-1]
    next_char = next_text[0]
    return prev_char.isascii() and prev_char.isalnum() and next_char.isascii() and next_char.isalnum()


def normalize_note(note: str) -> str:
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
    if " " in timeslot:
        base, extra = timeslot.split(" ", 1)
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


def join_line_words(words: list[Word]) -> str:
    line = sorted(words, key=lambda word: word.x0)
    result = line[0].text
    prev = line[0]
    for word in line[1:]:
        if word.x0 - prev.x1 > WORD_GAP_SPACE:
            result += " "
        result += word.text
        prev = word
    return result


def join_field(words: list[Word]) -> str:
    lines = [join_line_words(line) for line in group_lines(words)]
    if not lines:
        return ""

    result = lines[0]
    for line in lines[1:]:
        if needs_space_between(result, line):
            result += " "
        result += line
    return result.strip()


def build_record(
    words: list[Word],
    starts: list[tuple[str, float]],
    low: float,
    high: float,
    code_y: float,
) -> list[str]:
    filtered = [
        word
        for word in words
        if low <= word.y_center < high and word.text not in HEADER_WORDS
    ]
    lines = group_lines(filtered)
    code_line_index = next(
        (
            index
            for index, line in enumerate(lines)
            if any(abs(word.y_center - code_y) <= LINE_Y_TOLERANCE for word in line)
        ),
        None,
    )
    if code_line_index is None:
        return ["" for _ in starts]

    line_centers = [
        sum(word.y_center for word in line) / len(line)
        for line in lines
    ]
    begin = code_line_index
    while begin > 0 and line_centers[begin] - line_centers[begin - 1] <= RECORD_LINE_GAP:
        begin -= 1

    end = code_line_index
    while end < len(lines) - 1 and line_centers[end + 1] - line_centers[end] <= RECORD_LINE_GAP:
        end += 1

    filtered = [word for line in lines[begin : end + 1] for word in line]

    labels = [label for label, _ in starts]
    positions = [position for _, position in starts]
    boundaries = [-inf]
    boundaries.extend((positions[i] + positions[i + 1]) / 2 for i in range(len(positions) - 1))
    boundaries.append(inf)

    columns: dict[str, list[Word]] = {label: [] for label in labels}
    for word in filtered:
        for index, label in enumerate(labels):
            if boundaries[index] <= word.x_center < boundaries[index + 1]:
                columns[label].append(word)
                break

    return [join_field(columns[label]) for label in labels]


def normalize_record(record: list[str]) -> list[str]:
    code, name, method, credit, year, term, timeslot, teacher, abstract, note = record
    code_match = re.match(r"^([0-9A-Z]{7})(.*)$", code)
    if code_match is not None:
        code = code_match.group(1)
        extra_name = code_match.group(2).strip()
        if extra_name:
            name = f"{extra_name}{name}"

    combined_year_term = f"{year} {term}".strip()
    year_term_match = re.match(
        r"^([1-6](?:\s*[・-]\s*[1-6])?)\s+(.*)$", combined_year_term
    )
    if year_term_match is not None:
        year = year_term_match.group(1)
        term = year_term_match.group(2).strip()

    timeslot, teacher = normalize_teacher(timeslot, teacher)
    note = normalize_note(note)

    if not CODE_RE.fullmatch(code):
        raise ValueError(f"invalid course code: {code}")

    return [
        code,
        name,
        method,
        f" {credit}" if credit else "",
        year,
        term,
        timeslot,
        "",
        teacher,
        abstract,
        note,
    ]


def extract_records(pdf_path: Path, page_numbers: list[int]) -> list[list[str]]:
    records: list[list[str]] = []

    for page_no in page_numbers:
        words = run_bbox(pdf_path, page_no)
        header_anchors = sorted(
            [word for word in words if word.text == "科目番号"],
            key=lambda word: word.y0,
        )
        if not header_anchors:
            raise ValueError(f"no course header found on page {page_no}")

        for index, anchor in enumerate(header_anchors):
            segment_low = anchor.y0 - 8
            segment_high = (
                inf
                if index == len(header_anchors) - 1
                else header_anchors[index + 1].y0 - 8
            )
            segment_words = [
                word
                for word in words
                if segment_low <= word.y_center < segment_high
            ]

            starts = column_starts(segment_words, anchor.y0)
            header_y = header_bottom(segment_words, anchor.y0)
            labels = [label for label, _ in starts]
            positions = [position for _, position in starts]
            code_boundary = (positions[0] + positions[1]) / 2
            code_words = sorted(
                [
                    word
                    for word in segment_words
                    if CODE_RE.fullmatch(word.text) and word.x_center < code_boundary
                ],
                key=lambda word: word.y0,
            )
            if not code_words:
                continue

            for code_index, code_word in enumerate(code_words):
                low = (
                    header_y
                    if code_index == 0
                    else (code_words[code_index - 1].y0 + code_word.y0) / 2
                )
                high = (
                    segment_high
                    if code_index == len(code_words) - 1
                    else (code_word.y0 + code_words[code_index + 1].y0) / 2
                )
                record = normalize_record(
                    build_record(segment_words, starts, low, high, code_word.y_center)
                )
                records.append(record)

    return records


def validate(records: list[list[str]], expected_codes: int) -> None:
    if len(records) != expected_codes:
        raise ValueError(
            f"record count mismatch: extracted {len(records)} but found {expected_codes} codes in layout text"
        )

    invalid = [record[0] for record in records if not CODE_RE.fullmatch(record[0])]
    if invalid:
        raise ValueError(f"invalid course codes found: {invalid[:10]}")


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

    all_text = run_text(pdf_path)
    pages = all_text.split("\f")
    start_page = find_start_page(pages)
    target_pages = collect_target_pages(pages, start_page)
    expected_codes = count_expected_codes(pdf_path, target_pages)

    records = extract_records(pdf_path, target_pages)
    validate(records, expected_codes)
    unique_records, duplicate_count = dedupe_records(records)
    dump_output(unique_records, output_dir)

    undergrad_count = sum(not record[0].startswith("0") for record in unique_records)
    grad_count = len(unique_records) - undergrad_count
    print(
        json.dumps(
            {
                "start_page": start_page,
                "target_pages": len(target_pages),
                "expected_codes": expected_codes,
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
