from decimal import Decimal, InvalidOperation

from django import forms

from .models import Chapter, Grade, Subject


class BulkSubjectCreateForm(forms.Form):
    grade = forms.ModelChoiceField(queryset=Grade.objects.order_by("rank", "name"))
    subjects = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 12, "placeholder": "Mathematics\nPhysics\nChemistry"}),
        help_text="One subject per line. Optional format: rank|subject name",
    )
    is_active = forms.BooleanField(required=False, initial=True)


class BulkChapterCreateForm(forms.Form):
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.select_related("grade").order_by("grade__rank", "name"),
        help_text="Select the subject that will receive all chapters below.",
    )
    chapters = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 12, "placeholder": "1|Introduction\n2|Linear Equations"}),
        help_text="One chapter per line. Format: chapter_number|title. If chapter_number is omitted, it will auto-increment.",
    )
    is_active = forms.BooleanField(required=False, initial=True)


class BulkSubsectionCreateForm(forms.Form):
    chapter = forms.ModelChoiceField(
        queryset=Chapter.objects.select_related("subject", "subject__grade").order_by(
            "subject__grade__rank",
            "subject__name",
            "chapter_number",
            "title",
        ),
        help_text="Select the chapter that will receive all subsections below.",
    )
    subsections = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 12, "placeholder": "1.1|Definition\n1.2|Worked Example"}),
        help_text="One subsection per line. Format: subsection_number|title. If subsection_number is omitted, it will auto-increment.",
    )
    is_active = forms.BooleanField(required=False, initial=True)


def parse_bulk_lines(raw_value):
    lines = []
    for raw_line in (raw_value or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "|" in line:
            left, right = line.split("|", 1)
            lines.append((left.strip(), right.strip()))
        else:
            lines.append((None, line))
    return lines


def parse_positive_int(value):
    if value in (None, ""):
        return None
    return int(str(value).strip())


def parse_decimal_number(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError("Invalid decimal number.") from exc
