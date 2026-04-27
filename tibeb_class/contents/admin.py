from django.contrib import admin
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import path, reverse
from import_export import fields, resources
from import_export.admin import ImportExportModelAdmin
from import_export.widgets import ManyToManyWidget

from .forms import (
    BulkChapterCreateForm,
    BulkSubjectCreateForm,
    BulkSubsectionCreateForm,
    parse_bulk_lines,
    parse_decimal_number,
    parse_positive_int,
)
from .models import (
    Announcement,
    Book,
    Chapter,
    Exercise,
    Grade,
    Option,
    Question,
    Subject,
    Subsection,
    Video,
)


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "platform", "rank", "is_active", "updated_at")
    list_filter = ("platform", "is_active")
    search_fields = ("title", "text", "link", "guide_link")
    ordering = ("rank", "-updated_at")


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class HierarchicalGradeFilter(admin.SimpleListFilter):
    title = "grade"
    parameter_name = "h_grade"

    def lookups(self, request, model_admin):
        grades = Grade.objects.order_by("rank", "name")
        return [(str(g.id), g.name) for g in grades]

    def queryset(self, request, queryset):
        grade_id = _safe_int(self.value())
        if not grade_id:
            return queryset

        model = queryset.model
        if model in (Book, Video):
            return queryset.filter(
                Q(grade_id=grade_id)
                | Q(subject__grade_id=grade_id)
                | Q(chapter__subject__grade_id=grade_id)
                | Q(subsection__chapter__subject__grade_id=grade_id)
            )

        if model is Subject:
            return queryset.filter(grade_id=grade_id)

        if model is Chapter:
            return queryset.filter(subject__grade_id=grade_id)

        if model is Subsection:
            return queryset.filter(chapter__subject__grade_id=grade_id)

        if model is Exercise:
            return queryset.filter(
                Q(grades__id=grade_id)
                | Q(subject__grade_id=grade_id)
                | Q(chapter__subject__grade_id=grade_id)
                | Q(subsection__chapter__subject__grade_id=grade_id)
            ).distinct()

        return queryset


class HierarchicalSubjectFilter(admin.SimpleListFilter):
    title = "subject"
    parameter_name = "h_subject"

    def lookups(self, request, model_admin):
        subjects = Subject.objects.select_related("grade").order_by("grade__rank", "name")
        grade_id = _safe_int(request.GET.get("h_grade"))
        if grade_id:
            subjects = subjects.filter(grade_id=grade_id)
        return [(str(s.id), f"{s.name} ({s.grade.name})") for s in subjects]

    def queryset(self, request, queryset):
        subject_id = _safe_int(self.value())
        if not subject_id:
            return queryset

        model = queryset.model
        if model in (Book, Video):
            return queryset.filter(
                Q(subject_id=subject_id)
                | Q(chapter__subject_id=subject_id)
                | Q(subsection__chapter__subject_id=subject_id)
            )

        if model is Chapter:
            return queryset.filter(subject_id=subject_id)

        if model is Subsection:
            return queryset.filter(chapter__subject_id=subject_id)

        if model is Exercise:
            return queryset.filter(
                Q(subject_id=subject_id)
                | Q(chapter__subject_id=subject_id)
                | Q(subsection__chapter__subject_id=subject_id)
            ).distinct()

        return queryset


class HierarchicalChapterFilter(admin.SimpleListFilter):
    title = "chapter"
    parameter_name = "h_chapter"

    def lookups(self, request, model_admin):
        chapters = Chapter.objects.select_related("subject", "subject__grade").order_by(
            "subject__grade__rank",
            "subject__name",
            "chapter_number",
            "title",
        )
        grade_id = _safe_int(request.GET.get("h_grade"))
        subject_id = _safe_int(request.GET.get("h_subject"))

        if grade_id:
            chapters = chapters.filter(subject__grade_id=grade_id)
        if subject_id:
            chapters = chapters.filter(subject_id=subject_id)

        return [
            (str(c.id), f"{c.title} ({c.subject.name} / {c.subject.grade.name})")
            for c in chapters
        ]

    def queryset(self, request, queryset):
        chapter_id = _safe_int(self.value())
        if not chapter_id:
            return queryset

        model = queryset.model
        if model in (Book, Video):
            return queryset.filter(Q(chapter_id=chapter_id) | Q(subsection__chapter_id=chapter_id))

        if model is Subsection:
            return queryset.filter(chapter_id=chapter_id)

        if model is Exercise:
            return queryset.filter(
                Q(chapter_id=chapter_id) | Q(subsection__chapter_id=chapter_id)
            ).distinct()

        return queryset


class HierarchicalSubsectionFilter(admin.SimpleListFilter):
    title = "subsection"
    parameter_name = "h_subsection"

    def lookups(self, request, model_admin):
        subsections = Subsection.objects.select_related(
            "chapter",
            "chapter__subject",
            "chapter__subject__grade",
        ).order_by(
            "chapter__subject__grade__rank",
            "chapter__subject__name",
            "chapter__chapter_number",
            "subsection_number",
            "title",
        )
        grade_id = _safe_int(request.GET.get("h_grade"))
        subject_id = _safe_int(request.GET.get("h_subject"))
        chapter_id = _safe_int(request.GET.get("h_chapter"))

        if grade_id:
            subsections = subsections.filter(chapter__subject__grade_id=grade_id)
        if subject_id:
            subsections = subsections.filter(chapter__subject_id=subject_id)
        if chapter_id:
            subsections = subsections.filter(chapter_id=chapter_id)

        return [
            (
                str(s.id),
                f"{s.title} ({s.chapter.title} / {s.chapter.subject.name} / {s.chapter.subject.grade.name})",
            )
            for s in subsections
        ]

    def queryset(self, request, queryset):
        subsection_id = _safe_int(self.value())
        if not subsection_id:
            return queryset

        return queryset.filter(subsection_id=subsection_id)


class OptionInline(admin.TabularInline):
    model = Option
    extra = 4


class QuestionResource(resources.ModelResource):
    exercises = fields.Field(
        column_name="exercises",
        attribute="exercises",
        widget=ManyToManyWidget(Exercise, field="id", separator="|"),
    )
    options = fields.Field(column_name="options")
    correct_options = fields.Field(column_name="correct_options")

    class Meta:
        model = Question
        fields = (
            "id",
            "question_type",
            "question",
            "answer",
            "rank",
            "exercises",
            "options",
            "correct_options",
        )
        import_id_fields = ("id",)
        skip_unchanged = True

    def after_import_row(self, row, row_result, **kwargs):
        question = row_result.object_id
        if not question:
            return

        try:
            question_obj = Question.objects.get(pk=question)
        except Question.DoesNotExist:
            return

        options_raw = (row.get("options") or "").strip()
        correct_raw = (row.get("correct_options") or "").strip()

        if not options_raw:
            return

        option_texts = [opt.strip() for opt in options_raw.split("|") if opt.strip()]
        correct_set = {opt.strip() for opt in correct_raw.split("|") if opt.strip()}

        question_obj.options.all().delete()
        for text in option_texts:
            Option.objects.create(
                question=question_obj,
                text=text,
                is_correct=text in correct_set,
            )

    def dehydrate_options(self, question):
        return "|".join(question.options.values_list("text", flat=True))

    def dehydrate_correct_options(self, question):
        return "|".join(
            question.options.filter(is_correct=True).values_list("text", flat=True)
        )


@admin.register(Question)
class QuestionAdmin(ImportExportModelAdmin):
    resource_class = QuestionResource
    inlines = [OptionInline]
    list_display = ("id", "question_type", "short_question", "exercise_list", "rank")
    search_fields = ("question",)
    list_filter = ("question_type",)

    def short_question(self, obj):
        return obj.question[:60]

    def exercise_list(self, obj):
        return ", ".join(ex.title for ex in obj.exercises.all())

    exercise_list.short_description = "Exercises"


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "type",
        "ispaid",
        "grade",
        "subject",
        "chapter",
        "subsection",
        "is_active",
        "total_pages",
    )
    search_fields = ("name", "description")
    list_filter = (
        "type",
        "ispaid",
        "is_active",
        HierarchicalGradeFilter,
        HierarchicalSubjectFilter,
        HierarchicalChapterFilter,
        HierarchicalSubsectionFilter,
    )


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "type",
        "ispaid",
        "grade",
        "subject",
        "chapter",
        "subsection",
        "is_active",
        "duration",
        "uploaded_at",
    )
    search_fields = ("title", "description")
    list_filter = (
        "type",
        "ispaid",
        "is_active",
        HierarchicalGradeFilter,
        HierarchicalSubjectFilter,
        HierarchicalChapterFilter,
        HierarchicalSubsectionFilter,
        "uploaded_at",
    )


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "type",
        "ispaid",
        "subject",
        "chapter",
        "subsection",
        "is_active",
        "rank",
        "total_exercise",
    )
    search_fields = ("title", "description")
    list_filter = (
        "type",
        "ispaid",
        "is_active",
        HierarchicalGradeFilter,
        HierarchicalSubjectFilter,
        HierarchicalChapterFilter,
        HierarchicalSubsectionFilter,
    )


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "rank", "is_active")
    search_fields = ("name", "description")
    list_filter = ("is_active",)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "grade", "rank", "is_active")
    search_fields = ("name", "description", "grade__name")
    list_filter = ("is_active", HierarchicalGradeFilter)
    change_list_template = "admin/contents/bulk_enabled_change_list.html"

    def get_urls(self):
        return [
            path("bulk-create/", self.admin_site.admin_view(self.bulk_create_view), name="contents_subject_bulk_create"),
            *super().get_urls(),
        ]

    def bulk_create_view(self, request):
        form = BulkSubjectCreateForm(request.POST or None)
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Bulk create subjects",
            "form": form,
            "submit_label": "Create subjects",
            "back_url": reverse("admin:contents_subject_changelist"),
        }
        if request.method == "POST" and form.is_valid():
            grade = form.cleaned_data["grade"]
            is_active = form.cleaned_data["is_active"]
            rows = parse_bulk_lines(form.cleaned_data["subjects"])
            next_rank = (Subject.objects.filter(grade=grade).order_by("-rank").values_list("rank", flat=True).first() or 0) + 1
            created = 0
            try:
                for rank_value, name in rows:
                    if not name:
                        continue
                    rank = parse_positive_int(rank_value) if rank_value is not None else next_rank
                    Subject.objects.create(
                        grade=grade,
                        name=name,
                        rank=rank,
                        is_active=is_active,
                    )
                    created += 1
                    next_rank = max(next_rank, rank + 1)
            except ValueError:
                form.add_error("subjects", "Invalid line format. Use either `Subject Name` or `rank|Subject Name`.")
                return render(request, "admin/contents/bulk_create_form.html", context)
            self.message_user(request, f"Created {created} subjects for {grade.name}.", level=messages.SUCCESS)
            return redirect("admin:contents_subject_changelist")
        return render(request, "admin/contents/bulk_create_form.html", context)


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "subject", "chapter_number", "rank", "is_active")
    search_fields = ("title", "description", "subject__name", "subject__grade__name")
    list_filter = (
        "is_active",
        HierarchicalGradeFilter,
        HierarchicalSubjectFilter,
    )
    change_list_template = "admin/contents/bulk_enabled_change_list.html"

    def get_urls(self):
        return [
            path("bulk-create/", self.admin_site.admin_view(self.bulk_create_view), name="contents_chapter_bulk_create"),
            *super().get_urls(),
        ]

    def bulk_create_view(self, request):
        form = BulkChapterCreateForm(request.POST or None)
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Bulk create chapters",
            "form": form,
            "submit_label": "Create chapters",
            "back_url": reverse("admin:contents_chapter_changelist"),
        }
        if request.method == "POST" and form.is_valid():
            subject = form.cleaned_data["subject"]
            is_active = form.cleaned_data["is_active"]
            rows = parse_bulk_lines(form.cleaned_data["chapters"])
            next_number = (Chapter.objects.filter(subject=subject).order_by("-chapter_number").values_list("chapter_number", flat=True).first() or 0) + 1
            next_rank = (Chapter.objects.filter(subject=subject).order_by("-rank").values_list("rank", flat=True).first() or 0) + 1
            created = 0
            try:
                for number_value, title in rows:
                    if not title:
                        continue
                    chapter_number = parse_positive_int(number_value) if number_value is not None else next_number
                    Chapter.objects.create(
                        subject=subject,
                        title=title,
                        chapter_number=chapter_number,
                        rank=next_rank,
                        is_active=is_active,
                    )
                    created += 1
                    next_number = max(next_number, chapter_number + 1)
                    next_rank += 1
            except ValueError:
                form.add_error("chapters", "Invalid line format. Use either `Chapter Title` or `chapter_number|Chapter Title`.")
                return render(request, "admin/contents/bulk_create_form.html", context)
            self.message_user(request, f"Created {created} chapters for {subject.name}.", level=messages.SUCCESS)
            return redirect("admin:contents_chapter_changelist")
        return render(request, "admin/contents/bulk_create_form.html", context)


@admin.register(Subsection)
class SubsectionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "chapter",
        "subsection_number",
        "rank",
        "is_active",
    )
    search_fields = (
        "title",
        "description",
        "chapter__title",
        "chapter__subject__name",
        "chapter__subject__grade__name",
    )
    list_filter = (
        "is_active",
        HierarchicalGradeFilter,
        HierarchicalSubjectFilter,
        HierarchicalChapterFilter,
    )
    change_list_template = "admin/contents/bulk_enabled_change_list.html"

    def get_urls(self):
        return [
            path("bulk-create/", self.admin_site.admin_view(self.bulk_create_view), name="contents_subsection_bulk_create"),
            *super().get_urls(),
        ]

    def bulk_create_view(self, request):
        form = BulkSubsectionCreateForm(request.POST or None)
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Bulk create subsections",
            "form": form,
            "submit_label": "Create subsections",
            "back_url": reverse("admin:contents_subsection_changelist"),
        }
        if request.method == "POST" and form.is_valid():
            chapter = form.cleaned_data["chapter"]
            is_active = form.cleaned_data["is_active"]
            rows = parse_bulk_lines(form.cleaned_data["subsections"])
            next_rank = (Subsection.objects.filter(chapter=chapter).order_by("-rank").values_list("rank", flat=True).first() or 0) + 1
            existing_numbers = list(
                Subsection.objects.filter(chapter=chapter, subsection_number__isnull=False)
                .order_by("-subsection_number")
                .values_list("subsection_number", flat=True)
            )
            next_number = existing_numbers[0] + 1 if existing_numbers else 1
            created = 0
            try:
                for number_value, title in rows:
                    if not title:
                        continue
                    subsection_number = parse_decimal_number(number_value) if number_value is not None else next_number
                    Subsection.objects.create(
                        chapter=chapter,
                        title=title,
                        subsection_number=subsection_number,
                        rank=next_rank,
                        is_active=is_active,
                    )
                    created += 1
                    next_rank += 1
                    next_number = subsection_number + 1
            except ValueError:
                form.add_error("subsections", "Invalid line format. Use either `Subsection Title` or `subsection_number|Subsection Title`.")
                return render(request, "admin/contents/bulk_create_form.html", context)
            self.message_user(request, f"Created {created} subsections for {chapter.title}.", level=messages.SUCCESS)
            return redirect("admin:contents_subsection_changelist")
        return render(request, "admin/contents/bulk_create_form.html", context)


admin.site.register(Option)


