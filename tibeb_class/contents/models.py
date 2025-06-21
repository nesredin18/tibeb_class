from django.db import models

class Grade(models.Model):
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    rank = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.name


class Subject(models.Model):
    grade = models.ForeignKey(Grade, on_delete=models.CASCADE, related_name='subjects')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    rank = models.PositiveIntegerField(default=0)


    def __str__(self):
        return f"{self.name} ({self.grade.name})"
class Book(models.Model):
    name = models.CharField(max_length=100)
    pdf_file = models.FileField(upload_to='books/')
    description = models.TextField(blank=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='books', null=True, blank=True)
    meta_data = models.JSONField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} - {self.subject.name}) - ({self.subject.grade.name})"


class Chapter(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='chapters')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    rank = models.PositiveIntegerField(default=0)


    def __str__(self):
        return f"{self.title} - {self.subject.name} - ({self.subject.grade.name})"


class Subsection(models.Model):
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='subsections')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    rank = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.title} - {self.chapter.title} - {self.chapter.subject.name} - {self.chapter.subject.grade.name}"
    
class Exercise(models.Model):
    grades = models.ManyToManyField(Grade, related_name='exercises', blank=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='exercises', null=True, blank=True)
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='exercises', null=True, blank=True)
    subsection = models.ForeignKey(Subsection, on_delete=models.CASCADE, related_name='exercises', null=True, blank=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    rank = models.PositiveIntegerField(default=0)

    def __str__(self):
        parts = [self.title]

        if self.chapter:
            parts.append(self.chapter.title)

            if self.chapter.subject:
                parts.append(self.chapter.subject.name)

                # For grades (ManyToMany)
                grade_names = [grade.name for grade in self.grades.all()]
                if grade_names:
                    parts.append(', '.join(grade_names))

        return " - ".join(parts)



class Video(models.Model):
    subsection = models.ForeignKey(Subsection, on_delete=models.CASCADE, related_name='videos')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    video_file = models.FileField(upload_to='videos/')
    duration = models.DurationField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    rank = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.title} - {self.subsection.title} - {self.subsection.chapter.title} - {self.subsection.chapter.subject.name} - {self.subsection.chapter.subject.grade.name}"
