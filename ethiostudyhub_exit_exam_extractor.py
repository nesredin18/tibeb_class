import argparse
import csv
import html
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from openpyxl import Workbook


BASE_URL = "https://ethiostudyhub.com"
PAGE_URL = f"{BASE_URL}/exit-exams"
BUNDLE_URL = f"{BASE_URL}/assets/index-2SRA9T8Y.js"
EXPORT_COLUMNS = [
    "exam_type",
    "year",
    "exam_title",
    "exam_slug",
    "exam_id",
    "exam_url",
    "stream",
    "subject",
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

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def make_slug(value: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", value or "", flags=re.UNICODE)
    cleaned = re.sub(r"[-\s]+", "-", cleaned.strip().lower())
    return cleaned or "untitled"


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def build_session(access_token: Optional[str]) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Referer": PAGE_URL,
        }
    )
    return session


def fetch_text(session: requests.Session, url: str) -> str:
    last_error = None
    for attempt in range(4):
        try:
            response = session.get(url, timeout=120)
            response.raise_for_status()
            return response.text
        except Exception as exc:
            last_error = exc
    curl_result = subprocess.run(
        [
            "curl.exe",
            "-L",
            "-A",
            session.headers.get("User-Agent", "Mozilla/5.0"),
            "-H",
            f"Referer: {session.headers.get('Referer', PAGE_URL)}",
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if curl_result.returncode == 0 and curl_result.stdout:
        return curl_result.stdout
    raise last_error


def discover_bundle_url(page_html: str) -> str:
    match = re.search(r'<script[^>]+src="(/assets/index-[^"]+\.js)"', page_html)
    if not match:
        raise RuntimeError("Could not find the JS bundle URL on the exit-exams page.")
    return BASE_URL + match.group(1)


def extract_balanced_array(source: str, start_index: int) -> str:
    depth = 0
    in_string = False
    quote_char = ""
    escape_next = False

    for index in range(start_index, len(source)):
        char = source[index]

        if in_string:
            if escape_next:
                escape_next = False
            elif char == "\\":
                escape_next = True
            elif char == quote_char:
                in_string = False
            continue

        if char in ("'", '"', "`"):
            in_string = True
            quote_char = char
            continue

        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return source[start_index : index + 1]

    raise RuntimeError("Failed to extract a balanced JS array literal.")


def sanitize_js_array_literal(array_literal: str) -> str:
    sanitized = array_literal
    sanitized = sanitized.replace("\u2028", "\\u2028")
    sanitized = sanitized.replace("\u2029", "\\u2029")
    sanitized = sanitized.replace("\ufeff", "")
    return sanitized


def normalize_jsx_component_tags(array_literal: str) -> str:
    pattern = re.compile(r"e\.(jsx|jsxs)\(\s*([A-Za-z_$][\w$]*)\s*,")

    def repl(match: re.Match[str]) -> str:
        function_name = match.group(1)
        component_name = match.group(2)
        if component_name in {"null", "true", "false"}:
            return match.group(0)
        return f'e.{function_name}("component:{component_name}",'

    return pattern.sub(repl, array_literal)


def extract_route_component_map(bundle_text: str) -> Dict[str, str]:
    route_map: Dict[str, str] = {}
    pattern = re.compile(r'path:"([^"]+)",element:e\.jsx\(([A-Za-z_$][\w$]*)')
    for match in pattern.finditer(bundle_text):
        route_path = match.group(1)
        component_name = match.group(2)
        route_map[component_name] = route_path
    return route_map


def find_component_name_before_index(bundle_text: str, index: int) -> Optional[str]:
    window_start = max(0, index - 200000)
    window = bundle_text[window_start:index]
    matches = list(re.finditer(r'([A-Za-z_$][\w$]*)=\(\)=>\{const\{subject:[^}]+\}=Ue\(\)', window))
    if not matches:
        return None
    return matches[-1].group(1)


def derive_year_label(title_year_label: str, route_path: str) -> str:
    year_label = (title_year_label or "").strip()
    if route_path and "model" in route_path.lower() and "model" not in year_label.lower():
        year_label = f"{year_label}, Model"
    return year_label


def extract_exam_components(bundle_text: str) -> List[Dict[str, str]]:
    marker = 'sessionStorage.setItem("preSelectedDepartment","'
    components: List[Dict[str, str]] = []
    search_start = 0
    route_component_map = extract_route_component_map(bundle_text)

    while True:
        index = bundle_text.find(marker, search_start)
        if index == -1:
            break

        department_start = index + len(marker)
        department_end = bundle_text.find('"', department_start)
        department = bundle_text[department_start:department_end]

        array_anchor = bundle_text.rfind("=[{id:", 0, index)
        if array_anchor == -1:
            search_start = department_end
            continue

        array_start = array_anchor + 1
        array_literal = extract_balanced_array(bundle_text, array_start)

        window = bundle_text[index : min(len(bundle_text), index + 12000)]
        title_match = re.search(r'children:"([^"]+?) - Exit Exam ([^"]+?)"', window)
        if not title_match:
            search_start = department_end
            continue

        title_subject = title_match.group(1).strip()
        title_year_label = title_match.group(2).strip()

        component_name = find_component_name_before_index(bundle_text, index)
        route_path = route_component_map.get(component_name or "", "")
        year_label = derive_year_label(title_year_label, route_path)
        exam_url = BASE_URL + route_path if route_path else PAGE_URL

        components.append(
            {
                "department": department,
                "title_subject": title_subject,
                "year_label": year_label,
                "array_literal": array_literal,
                "exam_url": exam_url,
                "component_name": component_name or "",
            }
        )
        search_start = department_end

    deduped: List[Dict[str, str]] = []
    seen = set()
    for item in components:
        key = (item["department"], item["year_label"], item["array_literal"][:120])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def evaluate_js_array_with_node(array_literal: str, debug_name: Optional[str] = None) -> List[Dict]:
    array_literal = sanitize_js_array_literal(array_literal)
    array_literal = normalize_jsx_component_tags(array_literal)
    node_script = r"""
const fs = require('fs');
const literal = fs.readFileSync(0, 'utf8');
const e = {
  jsx: (tag, props) => ({ __jsx: true, tag, props: props || {} }),
  jsxs: (tag, props) => ({ __jsx: true, tag, props: props || {} }),
};
function walk(value) {
  if (value === null || value === undefined) return null;
  if (Array.isArray(value)) return value.map(walk);
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return value;
  if (typeof value === 'object' && value.__jsx) {
    return { __jsx: true, tag: value.tag, props: walk(value.props) };
  }
  if (typeof value === 'object') {
    const out = {};
    for (const [k, v] of Object.entries(value)) out[k] = walk(v);
    return out;
  }
  return String(value);
}
const data = eval('(' + literal + ')');
process.stdout.write(JSON.stringify(walk(data)));
"""
    result = subprocess.run(
        ["node", "-e", node_script],
        input=array_literal.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        if debug_name:
            debug_path = Path.cwd() / f"{debug_name}.debug.js"
            debug_path.write_text(array_literal, encoding="utf-8")
            raise RuntimeError(f"Node evaluation failed: {stderr.strip()} | debug file: {debug_path}")
        raise RuntimeError(f"Node evaluation failed: {stderr.strip()}")
    return json.loads(result.stdout.decode("utf-8"))


def absolute_image_url(src: str) -> str:
    if not src:
        return ""
    if src.startswith("http://") or src.startswith("https://"):
        return src
    if src.startswith("/"):
        return BASE_URL + src
    return f"{BASE_URL}/{src.lstrip('/')}"


def render_node_to_html(value) -> Tuple[str, List[str]]:
    image_urls: List[str] = []

    def _render(node) -> str:
        if node is None:
            return ""
        if isinstance(node, str):
            return html.escape(node)
        if isinstance(node, (int, float, bool)):
            return html.escape(str(node))
        if isinstance(node, list):
            return "".join(_render(item) for item in node)
        if isinstance(node, dict) and node.get("__jsx"):
            tag = node.get("tag", "div")
            props = node.get("props") or {}
            if isinstance(tag, str) and tag.startswith("component:"):
                tag = "div"
            if tag == "img":
                src = absolute_image_url(props.get("src", ""))
                alt = html.escape(str(props.get("alt", "")))
                if src:
                    image_urls.append(src)
                return f'<img src="{html.escape(src)}" alt="{alt}" />'
            children_html = _render(props.get("children"))
            return f"<{tag}>{children_html}</{tag}>"
        if isinstance(node, dict):
            return html.escape(json.dumps(node, ensure_ascii=False))
        return html.escape(str(node))

    rendered = _render(value)
    return rendered, image_urls


def normalize_html_fragment(fragment: str) -> str:
    if not fragment:
        return ""
    if fragment.startswith("<div>") or fragment.startswith("<p>") or fragment.startswith("<img"):
        return fragment
    return f"<p>{fragment}</p>"


def html_to_text(fragment: str) -> str:
    if not fragment:
        return ""
    soup = BeautifulSoup(fragment, "html.parser")
    text = soup.get_text(" ", strip=True)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_year_label(year_label: str) -> str:
    match = re.search(r"(\d{4})", year_label)
    return match.group(1) if match else year_label


def is_model_exam_year_label(year_label: str) -> bool:
    normalized = (year_label or "").strip().lower()
    return "model" in normalized


def question_value_to_html_and_text(value) -> Tuple[str, str, List[str]]:
    rendered, images = render_node_to_html(value)
    rendered = normalize_html_fragment(rendered)
    return rendered, html_to_text(rendered), images


def explanation_to_html_and_text(value: str) -> Tuple[str, str, List[str]]:
    rendered = normalize_html_fragment(html.escape(value))
    rendered = rendered.replace("\n", "<br/>")
    return rendered, html_to_text(rendered), []


def rows_for_exam(component: Dict[str, str], questions: List[Dict]) -> List[Dict[str, str]]:
    year = parse_year_label(component["year_label"])
    subject = component["department"]
    exam_title = f"{component['title_subject']} - Exit Exam {component['year_label']}"
    exam_slug = make_slug(exam_title)
    exam_id = exam_slug

    rows: List[Dict[str, str]] = []
    for index, item in enumerate(questions, start=1):
        question_html, question_text, question_images = question_value_to_html_and_text(item.get("question"))

        option_cells: Dict[str, str] = {}
        correct_letter = ""
        correct_answer = ""
        correct_answer_html = ""
        correct_answer_images = ""

        for option_index, option in enumerate(item.get("options") or []):
            if option_index >= len(CHOICE_LETTERS):
                break
            letter = CHOICE_LETTERS[option_index]
            option_html, option_text, option_images = question_value_to_html_and_text(option)
            option_cells[f"option_{letter.lower()}"] = option_text
            option_cells[f"option_{letter.lower()}_html"] = option_html
            option_cells[f"option_{letter.lower()}_image_urls"] = " | ".join(option_images)

            if item.get("correctAnswer") == option_index:
                correct_letter = letter
                correct_answer = option_text
                correct_answer_html = option_html
                correct_answer_images = " | ".join(option_images)

        explanation_html, explanation_text, explanation_images = explanation_to_html_and_text(
            item.get("explanation", "")
        )

        row = {
            "exam_type": "Exit Exam",
            "year": year,
            "exam_title": exam_title,
            "exam_slug": exam_slug,
            "exam_id": exam_id,
            "exam_url": component["exam_url"],
            "stream": "",
            "subject": subject,
            "provider": "ethiostudyhub.com bundle",
            "question_type": "multiple_choice",
            "question_number": str(index),
            "context_text": "",
            "context_html": "",
            "context_image_urls": "",
            "question": question_text,
            "question_html": question_html,
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
            "explanation": explanation_text,
            "explanation_html": explanation_html,
            "explanation_image_urls": " | ".join(explanation_images),
            "source_url": component["exam_url"],
            "notes": f"original_question_id={item.get('id', '')}; year_label={component['year_label']}",
        }
        row.update(option_cells)
        rows.append(row)
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


def write_exam_index(index_rows: List[Dict[str, str]], destination: Path) -> None:
    ensure_directory(destination.parent)
    columns = ["subject", "year", "exam_title", "exam_url", "question_count"]
    with destination.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(index_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract EthioStudyHub exit exams into Excel/CSV using the same general format as the other scrapers."
    )
    parser.add_argument("--access-token", help="Optional bearer token for requests.")
    parser.add_argument(
        "--bundle-url",
        default=BUNDLE_URL,
        help=f"Direct JS bundle URL. Default: {BUNDLE_URL}",
    )
    parser.add_argument(
        "--bundle-file",
        help="Optional path to a previously saved JS bundle file. If provided, the script will skip downloading the bundle.",
    )
    parser.add_argument(
        "--output-dir",
        default="ethiostudyhub_exit_exams",
        help="Destination folder for the exported exam files.",
    )
    parser.add_argument(
        "--subject",
        action="append",
        default=[],
        help="Optional subject filter. Repeat for multiple subjects.",
    )
    parser.add_argument(
        "--year",
        action="append",
        default=[],
        help="Optional year filter, for example 2015 or '2015, Model'. Repeat for multiple values.",
    )
    parser.add_argument(
        "--include-model",
        action="store_true",
        help="Include model exams. By default, year labels such as '2015, Model' are skipped.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    ensure_directory(output_dir)

    if args.bundle_file:
        bundle_text = Path(args.bundle_file).read_text(encoding="utf-8")
    else:
        session = build_session(args.access_token)
        bundle_text = fetch_text(session, args.bundle_url)

    components = extract_exam_components(bundle_text)
    if not args.include_model:
        components = [item for item in components if not is_model_exam_year_label(item["year_label"])]
    if args.subject:
        wanted = {item.strip().lower() for item in args.subject}
        components = [item for item in components if item["department"].strip().lower() in wanted]
    if args.year:
        wanted_years = {item.strip().lower() for item in args.year}
        components = [item for item in components if item["year_label"].strip().lower() in wanted_years]

    all_rows: List[Dict[str, str]] = []
    exam_index_rows: List[Dict[str, str]] = []

    print(f"Found {len(components)} exit exam components.")
    for component in components:
        print(f'Extracting {component["department"]} - {component["year_label"]}')
        try:
            questions = evaluate_js_array_with_node(
                component["array_literal"],
                debug_name=make_slug(f'{component["department"]}-{component["year_label"]}'),
            )
        except Exception as exc:
            print(f'  Skipped {component["department"]} - {component["year_label"]}: {exc}')
            continue
        rows = rows_for_exam(component, questions)
        all_rows.extend(rows)

        year = parse_year_label(component["year_label"])
        subject_slug = make_slug(component["department"])
        exam_slug = make_slug(f'{component["title_subject"]} - Exit Exam {component["year_label"]}')
        exam_dir = output_dir / year / subject_slug
        write_rows_to_csv(rows, exam_dir / f"{exam_slug}.csv")
        write_rows_to_xlsx(rows, exam_dir / f"{exam_slug}.xlsx")

        exam_index_rows.append(
            {
                "subject": component["department"],
                "year": component["year_label"],
                "exam_title": f'{component["title_subject"]} - Exit Exam {component["year_label"]}',
                "exam_url": component["exam_url"],
                "question_count": str(len(rows)),
            }
        )

    if all_rows:
        write_rows_to_csv(all_rows, output_dir / "all_exams.csv")
        write_rows_to_xlsx(all_rows, output_dir / "all_exams.xlsx")
        write_exam_index(exam_index_rows, output_dir / "exam_index.csv")
        print(f"Done. Wrote {len(all_rows)} questions to {output_dir}")
    else:
        print("No rows were extracted.")


if __name__ == "__main__":
    main()
