from django.db import models
from datetime import timedelta
import os
from django.core.exceptions import ValidationError





class Grade(models.Model):
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    rank = models.PositiveIntegerField(default=0)
    image = models.FileField(upload_to='grades/',blank=True,null=True)

    def __str__(self):
        return self.name


class Announcement(models.Model):
    PLATFORM_CHOICES = (
        ("both", "Both"),
        ("web", "Web only"),
        ("mobile", "Mobile only"),
    )

    title = models.CharField(max_length=200)
    text = models.TextField()
    image = models.FileField(upload_to="announcements/", blank=True, null=True)
    link = models.CharField(max_length=500, blank=True)
    guide_link = models.CharField(max_length=500, blank=True)
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default="both")
    is_active = models.BooleanField(default=True)
    rank = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("rank", "-created_at", "-id")

    def __str__(self):
        return self.title


class Subject(models.Model):
    grade = models.ForeignKey(Grade, on_delete=models.CASCADE, related_name='subjects')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    rank = models.PositiveIntegerField(default=0)
    image = models.FileField(upload_to='subjects/',blank=True,null=True)



    def __str__(self):
        return f"{self.name} ({self.grade.name})"



class Chapter(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='chapters')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    rank = models.PositiveIntegerField(default=0)
    chapter_number = models.IntegerField(default=0, blank=True,null=True)


    def __str__(self):
        return f"{self.chapter_number}-{self.title} - {self.subject.name} - ({self.subject.grade.name})"


class Subsection(models.Model):
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='subsections')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    rank = models.PositiveIntegerField(default=0)
    subsection_number= models.DecimalField(default=0, blank=True,null=True,decimal_places=1,max_digits=2)

    def __str__(self):
        return f"{self.title} - {self.chapter.title} - {self.chapter.subject.name} - {self.chapter.subject.grade.name}"
    
class Book(models.Model):
    Resource_Type = (
        ('class', 'Class'),
        ('additional', 'Additional'),
    )
    type = models.CharField(max_length=20, choices=Resource_Type, default='class')
    Is_Paid = (
        ('ispaid', 'Is Paid'),
        ('isfree', 'Is Free'),
    )
    ispaid=models.CharField(max_length=20, choices=Is_Paid, default='ispaid')
    grade = models.ForeignKey(Grade,on_delete=models.CASCADE, related_name='books', null=True, blank=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='books', null=True, blank=True)
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='books', null=True, blank=True)
    subsection = models.ForeignKey(Subsection, on_delete=models.CASCADE, related_name='books',null=True, blank=True)
    name = models.CharField(max_length=100)
    pdf_file = models.FileField(upload_to='books/')
    description = models.TextField(blank=True)
    meta_data = models.JSONField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    total_pages=models.PositiveIntegerField(default=0)


    def clean(self):
        # Count how many hierarchy levels are filled
        levels = [self.grade, self.subject, self.chapter, self.subsection]
        filled_levels = [level for level in levels if level is not None]

        if len(filled_levels) > 1:
            raise ValidationError("Only one of grade, subject, chapter, or subsection should be set.")

        if self.type == 'class':
            # ✅ New validation: class-type book must be on chapter or subsection level only
            if not (self.chapter or self.subsection):
                raise ValidationError("Class type content must be linked to either a chapter or a subsection.")

            if self.grade or self.subject:
                raise ValidationError("Class type content cannot be linked directly to grade or subject.")

            filters = {
                'type': 'class',
                'grade': self.grade,
                'subject': self.subject,
                'chapter': self.chapter,
                'subsection': self.subsection,
            }

            # Exclude self to allow updates
            existing = Book.objects.filter(**filters).exclude(pk=self.pk)

            if existing.exists():
                raise ValidationError("A 'class' type book already exists at this level.")


    def __str__(self):
        if self.subsection:
            return f"{self.name} - {self.subsection.title} - {self.subsection.chapter.title} - {self.subsection.chapter.subject.name} - {self.subsection.chapter.subject.grade.name}"
        elif self.chapter:
            return f"{self.name} - {self.chapter.title} - {self.chapter.subject.name} - {self.chapter.subject.grade.name}"
        elif self.subject:
            return f"{self.name} - {self.subject.name} - {self.subject.grade.name}"
        elif self.grade:
            return f"{self.name} - {self.grade.name}"
        return self.name
    
class Exercise(models.Model):
    Resource_Type = (
        ('class', 'Class'),
        ('additional', 'Additional'),
    )
    type = models.CharField(max_length=20, choices=Resource_Type, default='class')
    Is_Paid = (
        ('ispaid', 'Is Paid'),
        ('isfree', 'Is Free'),
    )
    ispaid=models.CharField(max_length=20, choices=Is_Paid, default='ispaid')
    grades = models.ManyToManyField(Grade, related_name='exercises', blank=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='exercises', null=True, blank=True)
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='exercises', null=True, blank=True)
    subsection = models.ForeignKey(Subsection, on_delete=models.CASCADE, related_name='exercises', null=True, blank=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    rank = models.PositiveIntegerField(default=0)
    total_exercise=models.PositiveIntegerField(default=0)


    def clean(self):
        has_grades = False
        if self.pk:
            has_grades = self.grades.exists()

        filled_levels = [
            self.subject is not None,
            self.chapter is not None,
            self.subsection is not None,
            has_grades
        ]

        if sum(filled_levels) > 1:
            raise ValidationError("Only one of grade, subject, chapter, or subsection should be set.")

        if self.type == 'class':
            if not (self.chapter or self.subsection):
                raise ValidationError("Class type content must be linked to either a chapter or a subsection.")
            if self.subject:
                raise ValidationError("Class type content cannot be linked directly to subject.")
            if has_grades:
                raise ValidationError("Class type content cannot be linked directly to grade.")

            if self.pk:
                filters = {
                    'type': 'class',
                    'chapter': self.chapter,
                    'subsection': self.subsection,
                }

                existing = Exercise.objects.filter(**filters).exclude(pk=self.pk)
                if existing.exists():
                    raise ValidationError("A 'class' type Exercise already exists at this level.")



    def __str__(self):
        try:
            if self.subsection:
                return f"{self.title} - {self.subsection.title} - {self.subsection.chapter.title} - {self.subsection.chapter.subject.name} - {self.subsection.chapter.subject.grade.name}"
            elif self.chapter:
                return f"{self.title} - {self.chapter.title} - {self.chapter.subject.name} - {self.chapter.subject.grade.name}"
            elif self.subject:
                return f"{self.title} - {self.subject.name} - {self.subject.grade.name}"
            elif self.pk:
                # Safe access: check if related manager is ready
                if hasattr(self, 'grades') and self.grades.exists():
                    grade_names = ", ".join(grade.name for grade in self.grades.all())
                    return f"{self.title} - {grade_names}"
        except Exception:
            return self.title  # fallback if any error happens

        return self.title



class Question(models.Model):
    exercises = models.ManyToManyField(Exercise, related_name='questions', blank=True)
    
    Question_Type = (
        ('write', 'Write'),
        ('choose', 'Choose'),
    )
    question_type = models.CharField(max_length=20, choices=Question_Type, default='write')
    
    question = models.TextField()
    answer = models.TextField(blank=True, help_text="For 'write' type, this is the correct answer.")
    rank = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.question[:50]}..."

class Option(models.Model):
    question = models.ForeignKey(Question, related_name='options', on_delete=models.CASCADE)
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.text} ({'Correct' if self.is_correct else 'Wrong'})"

from django.db import models
from django.core.files.storage import FileSystemStorage

local_storage = FileSystemStorage(location="media/videos/hls/zips")

class Video(models.Model):
    Resource_Type = (
        ('class', 'Class'),
        ('additional', 'Additional'),
    )
    type = models.CharField(max_length=20, choices=Resource_Type, default='class')
    Is_Paid = (
        ('ispaid', 'Is Paid'),
        ('isfree', 'Is Free'),
    )
    ispaid=models.CharField(max_length=20, choices=Is_Paid, default='ispaid')
    grade = models.ForeignKey(Grade, on_delete=models.CASCADE,related_name='videos', null=True, blank=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='videos', null=True, blank=True)
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='videos', null=True, blank=True)
    subsection = models.ForeignKey(Subsection, on_delete=models.CASCADE, related_name='videos',null=True, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    duration = models.DurationField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    segments_zip = models.FileField(
        upload_to="videos/hls/zips/",
        storage=local_storage,  # ✅ store locally first
        blank=True,
        null=True
    )
    hls_playlist = models.FileField(upload_to='videos/hls/playlists/', blank=True, null=True)
    encryption_key = models.FileField(upload_to='videos/hls/keys/', blank=True, null=True)

    def clean(self):
        # Count how many hierarchy levels are filled
        levels = [self.grade, self.subject, self.chapter, self.subsection]
        filled_levels = [level for level in levels if level is not None]

        if len(filled_levels) > 1:
            raise ValidationError("Only one of grade, subject, chapter, or subsection should be set.")

        if self.type == 'class':
            # ✅ New validation: class-type book must be on chapter or subsection level only
            if not (self.chapter or self.subsection):
                raise ValidationError("Class type content must be linked to either a chapter or a subsection.")

            if self.grade or self.subject:
                raise ValidationError("Class type content cannot be linked directly to grade or subject.")

            filters = {
                'type': 'class',
                'grade': self.grade,
                'subject': self.subject,
                'chapter': self.chapter,
                'subsection': self.subsection,
            }

            # Exclude self to allow updates
            existing = Video.objects.filter(**filters).exclude(pk=self.pk)

            if existing.exists():
                raise ValidationError("A 'class' type Video already exists at this level.")

    def __str__(self):
        if self.subsection:
            return f"{self.title} - {self.subsection.title} - {self.subsection.chapter.title} - {self.subsection.chapter.subject.name} - {self.subsection.chapter.subject.grade.name}"
        elif self.chapter:
            return f"{self.title} - {self.chapter.title} - {self.chapter.subject.name} - {self.chapter.subject.grade.name}"
        elif self.subject:
            return f"{self.title} - {self.subject.name} - {self.subject.grade.name}"
        elif self.grade:
            return f"{self.title} - {self.grade.name}"
        return self.title
