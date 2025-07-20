from django.db import models
from moviepy import VideoFileClip
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
        return f"{self.title} - {self.subject.name} - ({self.subject.grade.name})"


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
    grades = models.ManyToManyField(Grade, related_name='exercises')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='exercises', null=True, blank=True)
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='exercises', null=True, blank=True)
    subsection = models.ForeignKey(Subsection, on_delete=models.CASCADE, related_name='exercises', null=True, blank=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    rank = models.PositiveIntegerField(default=0)
    total_exercise=models.PositiveIntegerField(default=0)


    def clean(self):
        # Count how many hierarchy levels are filled
        levels = [self.grades, self.subject, self.chapter, self.subsection]
        filled_levels = [level for level in levels if level is not None]

        if len(filled_levels) > 1:
            raise ValidationError("Only one of grade, subject, chapter, or subsection should be set.")

    def __str__(self):
        if self.subsection:
            return f"{self.title} - {self.subsection.title} - {self.subsection.chapter.title} - {self.subsection.chapter.subject.name} - {self.subsection.chapter.subject.grade.name}"
        elif self.chapter:
            return f"{self.title} - {self.chapter.title} - {self.chapter.subject.name} - {self.chapter.subject.grade.name}"
        elif self.subject:
            return f"{self.title} - {self.subject.name} - {self.subject.grade.name}"
        elif self.grades.exists():
            grade_names = ", ".join(grade.name for grade in self.grades.all())
            return f"{self.title} - {grade_names}"

        return self.title

class Question(models.Model):
    exercises = models.ManyToManyField(Exercise, related_name='questions', blank=True)
    Question_Type = (
        ('write', 'Write'),
        ('choose', 'Choose'),
    )
    question_type = models.CharField(max_length=20, choices=Question_Type, default='write')
    question = models.TextField(blank=True)
    answer = models.TextField(blank=True)
    rank = models.PositiveIntegerField(default=0)


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
    video_file = models.FileField(upload_to='videos/')
    duration = models.DurationField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def clean(self):
        # Count how many hierarchy levels are filled
        levels = [self.grade, self.subject, self.chapter, self.subsection]
        filled_levels = [level for level in levels if level is not None]

        if len(filled_levels) > 1:
            raise ValidationError("Only one of grade, subject, chapter, or subsection should be set.")

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
