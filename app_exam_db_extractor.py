import argparse
import csv
import json
import re
import shutil
import sqlite3
from html import escape
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from openpyxl import Workbook


EXPORT_COLUMNS = [
    "exam_type",
    "year",
    "exam_title",
    "exam_slug",
    "exam_id",
    "exam_url",
    "stream",
    "subject",
    "chapter",
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
IMAGE_PATTERN = re.compile(r"^(?:images/|.+\.(?:png|jpg|jpeg|gif|webp|svg))", re.IGNORECASE)
PASSAGE_LABEL_PATTERN = re.compile(r"^\*{0,2}\s*(passage|table|diagram|graph)\s*\*{0,2}\s*:\s*", re.IGNORECASE)


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", value or "", flags=re.UNICODE)
    cleaned = re.sub(r"[-\s]+", "-", cleaned.strip().lower())
    return cleaned or "untitled"


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def parse_json_list(raw_value: Optional[str]) -> List[str]:
    if raw_value is None:
        return []
    raw_value = raw_value.strip()
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return [raw_value]
    if isinstance(parsed, list):
        return [str(item) for item in parsed if item not in (None, "")]
    if parsed in (None, ""):
        return []
    return [str(parsed)]


def is_image_reference(item: str) -> bool:
    return bool(IMAGE_PATTERN.match(item.strip()))


def normalize_year(value: str) -> str:
    match = re.search(r"(\d{4})", value or "")
    return match.group(1) if match else value or ""


def normalize_subject(value: str) -> str:
    value = value or ""
    for suffix in ("_NATURAL", "_SOCIAL", "_NA", "_SA"):
        if value.endswith(suffix):
            return value[: -len(suffix)]
    return value


def normalize_stream(value: str) -> str:
    mapping = {
        "NATURAL": "Natural Science",
        "SOCIAL": "Social Science",
        "NA": "Natural Science",
        "SA": "Social Science",
    }
    return mapping.get(value, value.title() if value else "")


def normalize_label_text(text: str) -> str:
    text = text.replace("**", "")
    text = re.sub(r"^#+\s*", "", text)
    text = PASSAGE_LABEL_PATTERN.sub("", text)
    text = normalize_math_delimiters(text)
    return text.strip()


def markdownish_to_html(text: str) -> str:
    text = normalize_math_delimiters(text)
    text = escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"^###\s+(.+)$", r"<h3>\1</h3>", text)
    text = re.sub(r"^##\s+(.+)$", r"<h2>\1</h2>", text)
    text = re.sub(r"^#\s+(.+)$", r"<h1>\1</h1>", text)
    return text


def normalize_math_delimiters(text: str) -> str:
    if not text:
        return ""

    # Collapse repeated runs first.
    text = re.sub(r"\${3,}", "$$", text)

    # Convert display delimiters to inline delimiters for frontend compatibility.
    text = re.sub(r"\$\$\s*(.*?)\s*\$\$", r"$\1$", text)

    # Clean up accidental empty duplicate wrappers.
    text = re.sub(r"\$\s+\$", "$", text)

    return text


def split_markdown_cells(line: str) -> List[str]:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return cells


def is_markdown_table_divider(line: str) -> bool:
    line = line.strip()
    if not line.startswith("|") or "|" not in line[1:]:
        return False
    cells = split_markdown_cells(line)
    if not cells:
        return False
    return all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)


def is_markdown_table_row(line: str) -> bool:
    line = line.strip()
    return line.startswith("|") and "|" in line[1:]


def render_markdown_table(lines: Sequence[str]) -> str:
    rows = [split_markdown_cells(line) for line in lines if is_markdown_table_row(line)]
    if not rows:
        return ""
    header = rows[0]
    body_rows = rows[2:] if len(rows) > 1 and is_markdown_table_divider(lines[1]) else rows[1:]
    parts = ["<table>"]
    parts.append("<thead><tr>" + "".join(f"<th>{markdownish_to_html(cell)}</th>" for cell in header) + "</tr></thead>")
    if body_rows:
        parts.append("<tbody>")
        for row in body_rows:
            parts.append("<tr>" + "".join(f"<td>{markdownish_to_html(cell)}</td>" for cell in row) + "</tr>")
        parts.append("</tbody>")
    parts.append("</table>")
    return "".join(parts)


def resolve_image_reference(
    image_ref: str,
    assets_dir: Optional[Path],
    output_image_dir: Path,
) -> str:
    image_ref = image_ref.strip()
    if not image_ref:
        return ""
    if not assets_dir:
        return image_ref.replace("\\", "/")

    source = assets_dir / image_ref
    if not source.exists():
        return image_ref.replace("\\", "/")

    destination = output_image_dir / image_ref
    ensure_directory(destination.parent)
    if not destination.exists():
        shutil.copy2(source, destination)
    return destination.as_posix()


def split_text_and_images(
    items: Sequence[str],
    assets_dir: Optional[Path],
    output_image_dir: Path,
) -> Tuple[List[str], List[str]]:
    texts: List[str] = []
    images: List[str] = []
    for item in items:
        if is_image_reference(item):
            images.append(resolve_image_reference(item, assets_dir, output_image_dir))
        else:
            cleaned = normalize_math_delimiters(str(item).strip())
            if cleaned:
                texts.append(cleaned)
    return texts, images


def join_text_lines(lines: Iterable[str]) -> str:
    filtered = [normalize_label_text(line) for line in lines if line and line != "---"]
    return "\n".join(filtered).strip()


def render_html_block(
    text_lines: Sequence[str],
    image_paths: Sequence[str],
) -> str:
    parts: List[str] = []
    index = 0
    while index < len(text_lines):
        line = text_lines[index]
        if line == "---":
            parts.append("<hr />")
            index += 1
            continue
        if is_markdown_table_row(line):
            table_lines = [line]
            index += 1
            while index < len(text_lines) and is_markdown_table_row(text_lines[index]):
                table_lines.append(text_lines[index])
                index += 1
            parts.append(render_markdown_table(table_lines))
            continue
        rendered = markdownish_to_html(line)
        if rendered.startswith("<h1>") or rendered.startswith("<h2>") or rendered.startswith("<h3>"):
            parts.append(rendered)
        else:
            parts.append(f"<p>{rendered}</p>")
        index += 1
    for image_path in image_paths:
        parts.append(f'<p><img src="{escape(image_path)}" alt="image" /></p>')
    return "".join(parts)


def split_question_content(
    content_items: Sequence[str],
    has_shared_context: bool,
) -> Tuple[List[str], List[str]]:
    if not content_items:
        return [], []
    if has_shared_context and "---" in content_items:
        divider = content_items.index("---")
        context_prefix = list(content_items[:divider])
        question_items = list(content_items[divider + 1 :])
        return context_prefix, question_items
    return [], list(content_items)


def clean_question_items(question_items: Sequence[str], has_shared_context: bool) -> List[str]:
    cleaned: List[str] = []
    for index, item in enumerate(question_items):
        value = item.strip()
        if not value:
            continue
        if has_shared_context and index == 0 and PASSAGE_LABEL_PATTERN.match(value):
            value = PASSAGE_LABEL_PATTERN.sub("", value).strip()
            if not value:
                continue
        cleaned.append(value)
    return cleaned


def build_exam_key(row: sqlite3.Row) -> Tuple[str, str, str]:
    year = normalize_year(row["year"])
    subject = normalize_subject(row["subject"])
    stream = normalize_stream(row["field"])
    return year, subject, stream


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


def fetch_question_rows(connection: sqlite3.Connection) -> List[sqlite3.Row]:
    connection.row_factory = sqlite3.Row
    query = """
        SELECT
            q.id,
            q.content,
            q.explanation,
            q.year,
            q.subject,
            q.chapter,
            q.field,
            q.is_grouped,
            q.group_id,
            q.group_index,
            q.shared_content_id,
            s.name AS shared_name,
            s.content AS shared_content
        FROM questions q
        LEFT JOIN shared_content s ON s.id = q.shared_content_id
        ORDER BY q.year, q.subject, q.id
    """
    return connection.execute(query).fetchall()


def fetch_choices(connection: sqlite3.Connection) -> Dict[int, List[sqlite3.Row]]:
    connection.row_factory = sqlite3.Row
    choice_map: Dict[int, List[sqlite3.Row]] = {}
    rows = connection.execute(
        "SELECT id, question_id, content, is_correct FROM choices ORDER BY question_id, id"
    ).fetchall()
    for row in rows:
        choice_map.setdefault(row["question_id"], []).append(row)
    return choice_map


def build_rows(
    database_path: Path,
    output_dir: Path,
    assets_dir: Optional[Path],
) -> List[Dict[str, str]]:
    connection = sqlite3.connect(str(database_path))
    question_rows = fetch_question_rows(connection)
    choice_map = fetch_choices(connection)

    per_exam_counter: Dict[Tuple[str, str, str], int] = {}
    rows: List[Dict[str, str]] = []

    for question_row in question_rows:
        year, subject, stream = build_exam_key(question_row)
        exam_key = (year, subject, stream)
        per_exam_counter[exam_key] = per_exam_counter.get(exam_key, 0) + 1
        question_number = per_exam_counter[exam_key]

        exam_title = f"{subject.title()} - {year} {stream}".strip()
        exam_slug = slugify(exam_title)
        exam_dir = output_dir / (year or "unknown-year") / slugify(subject or "unknown-subject")
        image_output_dir = exam_dir / "images"

        shared_items = parse_json_list(question_row["shared_content"])
        shared_text_lines, shared_images = split_text_and_images(shared_items, assets_dir, image_output_dir)
        content_items = parse_json_list(question_row["content"])
        context_prefix_items, question_items = split_question_content(content_items, bool(shared_items))
        question_items = clean_question_items(question_items, bool(shared_items))

        prefix_text_lines, prefix_images = split_text_and_images(context_prefix_items, assets_dir, image_output_dir)
        question_text_lines, question_images = split_text_and_images(question_items, assets_dir, image_output_dir)

        context_text_lines = shared_text_lines + prefix_text_lines
        context_image_paths = shared_images + prefix_images

        explanation_items = parse_json_list(question_row["explanation"])
        explanation_text_lines, explanation_images = split_text_and_images(
            explanation_items,
            assets_dir,
            image_output_dir,
        )

        option_values: Dict[str, str] = {}
        correct_letter = ""
        correct_answer = ""
        correct_answer_html = ""
        correct_answer_images = ""

        for index, choice_row in enumerate(choice_map.get(question_row["id"], [])):
            if index >= len(CHOICE_LETTERS):
                break
            letter = CHOICE_LETTERS[index]
            option_items = parse_json_list(choice_row["content"])
            option_text_lines, option_images = split_text_and_images(option_items, assets_dir, image_output_dir)
            option_text = join_text_lines(option_text_lines)
            option_html = render_html_block(option_text_lines, option_images)

            option_values[f"option_{letter.lower()}"] = option_text
            option_values[f"option_{letter.lower()}_html"] = option_html
            option_values[f"option_{letter.lower()}_image_urls"] = " | ".join(option_images)

            if choice_row["is_correct"]:
                correct_letter = letter
                correct_answer = option_text
                correct_answer_html = option_html
                correct_answer_images = " | ".join(option_images)

        row = {
            "exam_type": "App DB Exam",
            "year": year,
            "exam_title": exam_title,
            "exam_slug": exam_slug,
            "exam_id": f"{year}_{subject}_{stream}".strip("_"),
            "exam_url": str(database_path),
            "stream": stream,
            "subject": subject.title(),
            "chapter": question_row["chapter"],
            "provider": "Android App Local DB",
            "question_type": "grouped" if question_row["is_grouped"] else "standard",
            "question_number": str(question_number),
            "context_text": join_text_lines(context_text_lines),
            "context_html": render_html_block(context_text_lines, context_image_paths),
            "context_image_urls": " | ".join(context_image_paths),
            "question": join_text_lines(question_text_lines),
            "question_html": render_html_block(question_text_lines, question_images),
            "question_image_urls": " | ".join(question_images),
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
            "explanation": join_text_lines(explanation_text_lines),
            "explanation_html": render_html_block(explanation_text_lines, explanation_images),
            "explanation_image_urls": " | ".join(explanation_images),
            "source_url": str(database_path),
            "notes": (
                f"db_question_id={question_row['id']}; "
                f"field={question_row['field']}; "
                f"is_grouped={question_row['is_grouped']}; "
                f"group_id={question_row['group_id']}; "
                f"group_index={question_row['group_index']}; "
                f"shared_content_id={question_row['shared_content_id']}"
            ),
        }
        row.update(option_values)
        rows.append(row)

    connection.close()
    return rows


def write_exam_files(rows: List[Dict[str, str]], output_dir: Path) -> None:
    grouped: Dict[Tuple[str, str, str], List[Dict[str, str]]] = {}
    for row in rows:
        key = (row["year"], row["subject"], row["stream"])
        grouped.setdefault(key, []).append(row)

    for (year, subject, stream), exam_rows in grouped.items():
        exam_title = f"{subject} - {year} {stream}".strip()
        exam_slug = slugify(exam_title)
        exam_dir = output_dir / (year or "unknown-year") / slugify(subject or "unknown-subject")
        write_rows_to_csv(exam_rows, exam_dir / f"{exam_slug}.csv")
        write_rows_to_xlsx(exam_rows, exam_dir / f"{exam_slug}.xlsx")


def write_exam_index(rows: List[Dict[str, str]], output_dir: Path) -> None:
    grouped: Dict[Tuple[str, str, str], List[Dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault((row["year"], row["subject"], row["stream"]), []).append(row)

    index_rows = []
    for (year, subject, stream), exam_rows in grouped.items():
        index_rows.append(
            {
                "year": year,
                "subject": subject,
                "stream": stream,
                "question_count": len(exam_rows),
                "file_slug": slugify(f"{subject} - {year} {stream}"),
            }
        )

    destination = output_dir / "exam_index.csv"
    ensure_directory(destination.parent)
    with destination.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["year", "subject", "stream", "question_count", "file_slug"],
        )
        writer.writeheader()
        writer.writerows(index_rows)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract exam questions from the Android app SQLite database."
    )
    parser.add_argument(
        "--db",
        required=True,
        help="Path to the SQLite database file, for example C:\\Users\\nesru\\Desktop\\exam_database.db",
    )
    parser.add_argument(
        "--output-dir",
        default="app_exam_exports",
        help="Folder where CSV/XLSX files will be written.",
    )
    parser.add_argument(
        "--assets-dir",
        help="Optional folder that contains the app image files referenced by the database.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    db_path = Path(args.db).resolve()
    output_dir = Path(args.output_dir).resolve()
    assets_dir = Path(args.assets_dir).resolve() if args.assets_dir else None

    ensure_directory(output_dir)
    rows = build_rows(db_path, output_dir, assets_dir)

    if not rows:
        print("No rows were extracted.")
        return

    write_exam_files(rows, output_dir)
    write_rows_to_csv(rows, output_dir / "all_exams.csv")
    write_rows_to_xlsx(rows, output_dir / "all_exams.xlsx")
    write_exam_index(rows, output_dir)
    print(f"Done. Extracted {len(rows)} questions to {output_dir}")


if __name__ == "__main__":
    main()
