from django.contrib import admin
from django.db.models import Q
from import_export import fields, resources
from import_export.admin import ImportExportModelAdmin
from import_export.widgets import ManyToManyWidget

from .models import (
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


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "subject", "chapter_number", "rank", "is_active")
    search_fields = ("title", "description", "subject__name", "subject__grade__name")
    list_filter = (
        "is_active",
        HierarchicalGradeFilter,
        HierarchicalSubjectFilter,
    )


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


admin.site.register(Option)


