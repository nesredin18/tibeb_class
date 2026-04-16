import argparse
import base64
import csv
import hashlib
import json
import mimetypes
import re
from html import unescape
from io import BytesIO
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from openpyxl import Workbook


DEFAULT_DETAIL_URL = "https://ethioliq.com/api/exam/paid/{id}"

EXPORT_COLUMNS = [
    "exam_type",
    "year",
    "exam_title",
    "exam_slug",
    "exam_id",
    "exam_url",
    "stream",
    "subject",
    "mode",
    "provider",
    "question_type",
    "question_number",
    "context_text",
    "context_html",
    "context_image_urls",
    "question",
    "question_html",
    "question_image_urls",
    "option_a",
    "option_a_html",
    "option_a_image_urls",
    "option_b",
    "option_b_html",
    "option_b_image_urls",
    "option_c",
    "option_c_html",
    "option_c_image_urls",
    "option_d",
    "option_d_html",
    "option_d_image_urls",
    "option_e",
    "option_e_html",
    "option_e_image_urls",
    "correct_letter",
    "correct_answer",
    "correct_answer_html",
    "correct_answer_image_urls",
    "explanation",
    "explanation_html",
    "explanation_image_urls",
    "source_url",
    "notes",
]

CHOICE_LETTERS = ["A", "B", "C", "D", "E", "F"]


def make_slug(value: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", value or "", flags=re.UNICODE)
    cleaned = re.sub(r"[-\s]+", "-", cleaned.strip().lower())
    return cleaned or "untitled"


def clean_text_from_html(html: Optional[str]) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def value_to_html(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value if "<" in value else f"<p>{value}</p>"
    if isinstance(value, list):
        return "".join(value_to_html(item) for item in value if item not in (None, "", [], {}))
    if isinstance(value, dict):
        for key in ("html", "content", "text", "value", "body", "question", "passage", "description"):
            if value.get(key):
                return value_to_html(value[key])
        return "".join(
            value_to_html(item)
            for item in value.values()
            if item not in (None, "", [], {})
        )
    return f"<p>{value}</p>"


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def guess_extension_from_data_url(data_url: str) -> str:
    match = re.match(r"data:([^;]+);base64,", data_url)
    if not match:
        return ".bin"
    mime_type = match.group(1).strip().lower()
    extension = mimetypes.guess_extension(mime_type) or ".bin"
    if extension == ".jpe":
        return ".jpg"
    return extension


def guess_extension_from_url(url: str) -> str:
    path = urlparse(url).path
    extension = Path(path).suffix.lower()
    return extension or ".bin"


def save_binary_file(content: bytes, destination: Path) -> str:
    ensure_directory(destination.parent)
    destination.write_bytes(content)
    return destination.as_posix()


def save_data_url(data_url: str, destination: Path) -> str:
    _, encoded = data_url.split(",", 1)
    content = base64.b64decode(encoded)
    return save_binary_file(content, destination)


def download_remote_image(session: requests.Session, url: str, destination: Path) -> str:
    response = session.get(url, timeout=60)
    response.raise_for_status()
    return save_binary_file(response.content, destination)


def normalize_image_name(label: str, index: int, source: str) -> str:
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:10]
    return f"{label}_{index}_{digest}"


def extract_and_localize_images(
    html: Optional[str],
    image_dir: Path,
    image_label: str,
    session: requests.Session,
) -> Tuple[str, List[str]]:
    if not html:
        return "", []

    soup = BeautifulSoup(html, "html.parser")
    saved_paths: List[str] = []

    for index, img in enumerate(soup.find_all("img"), start=1):
        source = (img.get("src") or "").strip()
        if not source:
            continue

        if source.startswith("data:image/"):
            extension = guess_extension_from_data_url(source)
            file_name = normalize_image_name(image_label, index, source) + extension
            saved_path = save_data_url(source, image_dir / file_name)
        else:
            extension = guess_extension_from_url(source)
            file_name = normalize_image_name(image_label, index, source) + extension
            try:
                saved_path = download_remote_image(session, source, image_dir / file_name)
            except Exception:
                saved_path = source

        saved_paths.append(saved_path)
        img["src"] = saved_path

    return str(soup), saved_paths


def build_context_html(question_item: Dict) -> str:
    parts = []
    for field_name, title in [("direction", "Direction"), ("section", "Section"), ("passage", "Passage")]:
        value = question_item.get(field_name)
        if not value:
            continue
        rendered = value_to_html(value).strip()
        if not rendered:
            continue

        rendered_soup = BeautifulSoup(rendered, "html.parser")
        first_text = rendered_soup.get_text(" ", strip=True).lower()
        if title.lower() in first_text[: len(title) + 5]:
            parts.append(str(rendered_soup))
        else:
            parts.append(f"<div><p><strong>{title}:</strong></p>{str(rendered_soup)}</div>")
    return "".join(parts)


def parse_year(exam_data: Dict, first_question: Optional[Dict]) -> str:
    if first_question and first_question.get("year"):
        return str(first_question["year"])
    unique_name = exam_data.get("uniqueName", "")
    match = re.search(r"(20\d{2}|201[0-9])", unique_name)
    return match.group(1) if match else ""


def join_values(values: Iterable[str]) -> str:
    return " | ".join([value for value in values if value])


def exam_notes(exam_data: Dict) -> str:
    parts = []
    if exam_data.get("difficulty"):
        parts.append(f"difficulty={exam_data['difficulty']}")
    if exam_data.get("examGroup"):
        parts.append(f"exam_group={exam_data['examGroup']}")
    if exam_data.get("passingMarks") is not None:
        parts.append(f"passing_marks={exam_data['passingMarks']}")
    if exam_data.get("numberOfQuestions") is not None:
        parts.append(f"question_count={exam_data['numberOfQuestions']}")
    if exam_data.get("timeAllowedInMinute") is not None:
        parts.append(f"time_allowed_minutes={exam_data['timeAllowedInMinute']}")
    return "; ".join(parts)


def build_rows_for_exam(exam_data: Dict, base_output_dir: Path, session: requests.Session) -> List[Dict[str, str]]:
    category = exam_data.get("categoryId") or {}
    questions = exam_data.get("questions") or []
    first_question = questions[0] if questions else None

    year = parse_year(exam_data, first_question)
    subject = ", ".join(exam_data.get("subject") or [])
    stream = category.get("stream", "")
    exam_type = category.get("type", "")
    exam_title = exam_data.get("uniqueName", "")
    exam_id = exam_data.get("_id", "")
    exam_slug = make_slug(exam_title or exam_id)

    exam_folder = base_output_dir / (year or "unknown-year") / (make_slug(subject) or "unknown-subject") / exam_slug
    image_dir = exam_folder / "images"
    ensure_directory(image_dir)

    rows: List[Dict[str, str]] = []

    for question_number, question_item in enumerate(questions, start=1):
        context_html_raw = build_context_html(question_item)
        context_html, context_images = extract_and_localize_images(
            context_html_raw,
            image_dir,
            f"q{question_number}_context",
            session,
        )

        question_html, question_images = extract_and_localize_images(
            question_item.get("question", ""),
            image_dir,
            f"q{question_number}_question",
            session,
        )

        explanation_html, explanation_images = extract_and_localize_images(
            question_item.get("explanation", ""),
            image_dir,
            f"q{question_number}_explanation",
            session,
        )

        option_cells: Dict[str, str] = {}
        correct_letter = ""
        correct_answer = ""
        correct_answer_html = ""
        correct_answer_images = ""

        for choice_index, choice in enumerate(question_item.get("choices") or []):
            if choice_index >= len(CHOICE_LETTERS):
                break

            letter = CHOICE_LETTERS[choice_index]
            option_html, option_images = extract_and_localize_images(
                choice.get("choice", ""),
                image_dir,
                f"q{question_number}_option_{letter.lower()}",
                session,
            )
            option_text = clean_text_from_html(option_html)

            option_cells[f"option_{letter.lower()}"] = option_text
            option_cells[f"option_{letter.lower()}_html"] = option_html
            option_cells[f"option_{letter.lower()}_image_urls"] = join_values(option_images)

            if choice.get("isAnswer"):
                correct_letter = letter
                correct_answer = option_text
                correct_answer_html = option_html
                correct_answer_images = join_values(option_images)

        row = {
            "exam_type": exam_type,
            "year": year,
            "exam_title": exam_title,
            "exam_slug": exam_slug,
            "exam_id": exam_id,
            "exam_url": DEFAULT_DETAIL_URL.format(id=exam_id),
            "stream": stream,
            "subject": subject,
            "mode": question_item.get("mode", exam_data.get("type", "")),
            "provider": question_item.get("provider", ""),
            "question_type": question_item.get("questionType", ""),
            "question_number": str(question_number),
            "context_text": clean_text_from_html(context_html),
            "context_html": context_html,
            "context_image_urls": join_values(context_images),
            "question": clean_text_from_html(question_html),
            "question_html": question_html,
            "question_image_urls": join_values(question_images),
            "option_a": "",
            "option_a_html": "",
            "option_a_image_urls": "",
            "option_b": "",
            "option_b_html": "",
            "option_b_image_urls": "",
            "option_c": "",
            "option_c_html": "",
            "option_c_image_urls": "",
            "option_d": "",
            "option_d_html": "",
            "option_d_image_urls": "",
            "option_e": "",
            "option_e_html": "",
            "option_e_image_urls": "",
            "correct_letter": correct_letter,
            "correct_answer": correct_answer,
            "correct_answer_html": correct_answer_html,
            "correct_answer_image_urls": correct_answer_images,
            "explanation": clean_text_from_html(explanation_html),
            "explanation_html": explanation_html,
            "explanation_image_urls": join_values(explanation_images),
            "source_url": DEFAULT_DETAIL_URL.format(id=exam_id),
            "notes": exam_notes(exam_data),
        }
        row.update(option_cells)
        rows.append(row)

    raw_json_path = exam_folder / f"{exam_slug}.json"
    ensure_directory(raw_json_path.parent)
    raw_json_path.write_text(json.dumps(exam_data, ensure_ascii=False, indent=2), encoding="utf-8")

    write_rows_to_csv(rows, exam_folder / f"{exam_slug}.csv")
    write_rows_to_xlsx(rows, exam_folder / f"{exam_slug}.xlsx")
    return rows


def write_rows_to_csv(rows: List[Dict[str, str]], destination: Path) -> None:
    ensure_directory(destination.parent)
    with destination.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in EXPORT_COLUMNS})


def write_rows_to_xlsx(rows: List[Dict[str, str]], destination: Path) -> None:
    ensure_directory(destination.parent)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Questions"
    sheet.append(EXPORT_COLUMNS)
    for row in rows:
        sheet.append([row.get(column, "") for column in EXPORT_COLUMNS])
    workbook.save(destination)


def fetch_json(session: requests.Session, url: str) -> Dict:
    response = session.get(url, timeout=90)
    response.raise_for_status()
    return response.json()


def load_list_payload(args: argparse.Namespace, session: requests.Session) -> Dict:
    if args.list_json:
        return json.loads(Path(args.list_json).read_text(encoding="utf-8"))
    if args.list_url:
        return fetch_json(session, args.list_url)
    raise SystemExit("Provide either --list-url or --list-json.")


def create_session(cookie: Optional[str]) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        }
    )
    if cookie:
        session.headers["Cookie"] = cookie
    return session


def choose_exam_ids(list_payload: Dict, explicit_ids: List[str]) -> List[Dict]:
    exams = list_payload.get("data") or []
    if explicit_ids:
        id_set = {value.strip() for value in explicit_ids}
        exams = [exam for exam in exams if exam.get("_id") in id_set]
    return exams


def fetch_exam_detail(session: requests.Session, exam_id: str, detail_url_template: str) -> Dict:
    payload = fetch_json(session, detail_url_template.format(id=exam_id))
    return payload.get("data") or {}


def write_combined_exports(all_rows: List[Dict[str, str]], output_dir: Path) -> None:
    write_rows_to_csv(all_rows, output_dir / "all_exams.csv")
    write_rows_to_xlsx(all_rows, output_dir / "all_exams.xlsx")


def write_exam_index(exams: List[Dict], destination: Path) -> None:
    ensure_directory(destination.parent)
    columns = [
        "exam_id",
        "exam_title",
        "subject",
        "stream",
        "year",
        "mode",
        "question_count",
        "time_allowed_minutes",
        "passing_marks",
    ]
    rows = []
    for exam in exams:
        rows.append(
            {
                "exam_id": exam.get("_id", ""),
                "exam_title": exam.get("uniqueName", ""),
                "subject": ", ".join(exam.get("subject") or []),
                "stream": (exam.get("categoryId") or {}).get("stream", ""),
                "year": parse_year(exam, None),
                "mode": exam.get("type", ""),
                "question_count": exam.get("numberOfQuestions", ""),
                "time_allowed_minutes": exam.get("timeAllowedInMinute", ""),
                "passing_marks": exam.get("passingMarks", ""),
            }
        )

    with destination.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract Ethioliq paid exams to Excel/CSV with localized images."
    )
    parser.add_argument("--list-url", help="API URL that returns the exam list JSON.")
    parser.add_argument("--list-json", help="Path to a saved exam list JSON file.")
    parser.add_argument("--cookie", help="Cookie header value for authenticated requests.")
    parser.add_argument(
        "--detail-url-template",
        default=DEFAULT_DETAIL_URL,
        help=f"Exam detail URL template. Default: {DEFAULT_DETAIL_URL}",
    )
    parser.add_argument(
        "--exam-id",
        action="append",
        default=[],
        help="Specific exam id to fetch. Repeat this option for multiple exam ids.",
    )
    parser.add_argument(
        "--output-dir",
        default="ethioliq_exams",
        help="Folder where CSV/XLSX/images will be written.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    output_dir = Path(args.output_dir).resolve()
    ensure_directory(output_dir)

    session = create_session(args.cookie)
    list_payload = load_list_payload(args, session)
    exam_summaries = choose_exam_ids(list_payload, args.exam_id)

    if not exam_summaries:
        raise SystemExit("No exams matched the provided filters.")

    print(f"Found {len(exam_summaries)} exams to extract.")
    write_exam_index(exam_summaries, output_dir / "exam_index.csv")

    all_rows: List[Dict[str, str]] = []

    for exam_summary in exam_summaries:
        exam_id = exam_summary.get("_id", "")
        exam_name = exam_summary.get("uniqueName", exam_id)
        print(f"Fetching exam {exam_name} ({exam_id})")
        exam_detail = fetch_exam_detail(session, exam_id, args.detail_url_template)
        if not exam_detail:
            print(f"  Skipped {exam_id}: no data returned.")
            continue

        rows = build_rows_for_exam(exam_detail, output_dir, session)
        all_rows.extend(rows)
        print(f"  Saved {len(rows)} questions.")

    if all_rows:
        write_combined_exports(all_rows, output_dir)
        print(f"Done. Wrote {len(all_rows)} question rows to {output_dir}")
    else:
        print("No question rows were produced.")


if __name__ == "__main__":
    main()
