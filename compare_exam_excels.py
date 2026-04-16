import argparse
import html
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

from bs4 import BeautifulSoup
from openpyxl import load_workbook


DEFAULT_KEY_COLUMNS = ["question_number", "question", "subject", "year"]
DEFAULT_COMPARE_COLUMNS = [
    "question",
    "context_text",
    "option_a",
    "option_b",
    "option_c",
    "option_d",
    "option_e",
    "correct_letter",
    "correct_answer",
    "explanation",
]


def read_excel(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    workbook = load_workbook(path, data_only=False)
    sheet = workbook.active
    headers = [str(cell.value).strip() if cell.value is not None else "" for cell in sheet[1]]
    rows: List[Dict[str, str]] = []
    for row in sheet.iter_rows(min_row=2, values_only=True):
        item: Dict[str, str] = {}
        for index, header in enumerate(headers):
            value = row[index] if index < len(row) else ""
            item[header] = "" if value is None else str(value)
        rows.append(item)
    return headers, rows


def html_to_text(value: str) -> str:
    if not value:
        return ""
    soup = BeautifulSoup(value, "html.parser")
    return soup.get_text(" ", strip=True)


def normalize_text(value: str) -> str:
    if not value:
        return ""
    value = html.unescape(value)
    value = html_to_text(value)
    value = value.lower()
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_subject(value: str) -> str:
    value = normalize_text(value)
    value = value.replace("_", " ")
    value = re.sub(r"\bnatural\b|\bsocial\b|\bscience\b", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_year(value: str) -> str:
    match = re.search(r"(\d{4})", value or "")
    return match.group(1) if match else ""


def build_row_key(row: Dict[str, str], key_columns: List[str]) -> str:
    parts = []
    for column in key_columns:
        parts.append(normalize_text(row.get(column, "")))
    return " | ".join(parts)


def filter_rows(rows: List[Dict[str, str]], subject_filter: str, year_filter: str) -> List[Dict[str, str]]:
    wanted_subject = normalize_subject(subject_filter) if subject_filter else ""
    wanted_year = normalize_year(year_filter) if year_filter else ""

    filtered: List[Dict[str, str]] = []
    for row in rows:
        row_subject = normalize_subject(row.get("subject", ""))
        row_year = normalize_year(row.get("year", ""))
        if wanted_subject and row_subject != wanted_subject:
            continue
        if wanted_year and row_year != wanted_year:
            continue
        filtered.append(row)
    return filtered


def index_rows(rows: List[Dict[str, str]], key_columns: List[str]) -> Dict[str, Dict[str, str]]:
    indexed: Dict[str, Dict[str, str]] = {}
    for row in rows:
        key = build_row_key(row, key_columns)
        if key and key not in indexed:
            indexed[key] = row
    return indexed


def compare_headers(left_headers: List[str], right_headers: List[str]) -> Dict[str, List[str]]:
    left_only = [header for header in left_headers if header not in right_headers]
    right_only = [header for header in right_headers if header not in left_headers]
    return {"left_only": left_only, "right_only": right_only}


def compare_rows(
    left_rows: List[Dict[str, str]],
    right_rows: List[Dict[str, str]],
    key_columns: List[str],
    compare_columns: List[str],
) -> Dict:
    left_index = index_rows(left_rows, key_columns)
    right_index = index_rows(right_rows, key_columns)

    left_keys = set(left_index)
    right_keys = set(right_index)

    only_left = sorted(left_keys - right_keys)
    only_right = sorted(right_keys - left_keys)
    common = sorted(left_keys & right_keys)

    mismatches = []
    exact_match_count = 0

    for key in common:
        left_row = left_index[key]
        right_row = right_index[key]
        row_diff = {"key": key, "columns": []}
        all_equal = True

        for column in compare_columns:
            left_value = left_row.get(column, "")
            right_value = right_row.get(column, "")
            left_norm = normalize_text(left_value)
            right_norm = normalize_text(right_value)

            if left_value == right_value:
                continue

            if left_norm == right_norm:
                row_diff["columns"].append(
                    {
                        "column": column,
                        "type": "format_only",
                        "left": left_value,
                        "right": right_value,
                    }
                )
                continue

            all_equal = False
            row_diff["columns"].append(
                {
                    "column": column,
                    "type": "content_diff",
                    "left": left_value,
                    "right": right_value,
                }
            )

        if row_diff["columns"]:
            mismatches.append(row_diff)
        if all_equal and not row_diff["columns"]:
            exact_match_count += 1

    return {
        "left_row_count": len(left_rows),
        "right_row_count": len(right_rows),
        "matched_keys": len(common),
        "exact_match_count": exact_match_count,
        "only_left": only_left,
        "only_right": only_right,
        "mismatches": mismatches,
    }


def write_report(report: Dict, destination: Path) -> None:
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_list_argument(value: str, default: List[str]) -> List[str]:
    if not value:
        return default
    return [part.strip() for part in value.split(",") if part.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare two exam Excel files and report whether they match."
    )
    parser.add_argument("--left", required=True, help="First Excel file.")
    parser.add_argument("--right", required=True, help="Second Excel file.")
    parser.add_argument(
        "--key-columns",
        help="Comma-separated columns used to align rows. Default: question_number,question,subject,year",
    )
    parser.add_argument(
        "--compare-columns",
        help="Comma-separated columns to compare after rows are aligned.",
    )
    parser.add_argument(
        "--report",
        help="Optional JSON report output path. Default: compare_report.json beside the left file.",
    )
    parser.add_argument("--subject", help="Optional subject filter, for example English.")
    parser.add_argument("--year", help="Optional year filter, for example 2016.")
    args = parser.parse_args()

    left_path = Path(args.left).resolve()
    right_path = Path(args.right).resolve()
    report_path = Path(args.report).resolve() if args.report else left_path.with_name(f"{left_path.stem}_compare_report.json")

    key_columns = parse_list_argument(args.key_columns or "", DEFAULT_KEY_COLUMNS)
    compare_columns = parse_list_argument(args.compare_columns or "", DEFAULT_COMPARE_COLUMNS)

    left_headers, left_rows = read_excel(left_path)
    right_headers, right_rows = read_excel(right_path)

    if args.subject or args.year:
        left_rows = filter_rows(left_rows, args.subject or "", args.year or "")
        right_rows = filter_rows(right_rows, args.subject or "", args.year or "")

    header_report = compare_headers(left_headers, right_headers)
    row_report = compare_rows(left_rows, right_rows, key_columns, compare_columns)

    report = {
        "left_file": str(left_path),
        "right_file": str(right_path),
        "subject_filter": args.subject or "",
        "year_filter": args.year or "",
        "same_headers": not header_report["left_only"] and not header_report["right_only"],
        "header_diff": header_report,
        "row_summary": row_report,
        "same_content": (
            not header_report["left_only"]
            and not header_report["right_only"]
            and not row_report["only_left"]
            and not row_report["only_right"]
            and not row_report["mismatches"]
        ),
    }

    write_report(report, report_path)

    print(f"Left rows: {row_report['left_row_count']}")
    print(f"Right rows: {row_report['right_row_count']}")
    print(f"Matched rows: {row_report['matched_keys']}")
    print(f"Only in left: {len(row_report['only_left'])}")
    print(f"Only in right: {len(row_report['only_right'])}")
    print(f"Rows with differences: {len(row_report['mismatches'])}")
    print(f"Same content: {report['same_content']}")
    print(f"Report saved to: {report_path}")


if __name__ == "__main__":
    main()
