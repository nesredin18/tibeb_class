from django.contrib import admin
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
        "grade",
        "subject",
        "chapter",
        "subsection",
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
        "grade",
        "subject",
        "chapter",
        "subsection",
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
        "grades",
        "subject",
        "chapter",
        "subsection",
    )


admin.site.register(Grade)
admin.site.register(Subject)
admin.site.register(Chapter)
admin.site.register(Subsection)
admin.site.register(Option)


