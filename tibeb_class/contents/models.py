from django.db import models

class Grade(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class Subject(models.Model):
    grade = models.ForeignKey(Grade, on_delete=models.CASCADE, related_name='subjects')
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name} ({self.grade.name})"


class Chapter(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='chapters')
    title = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.title} - {self.subject.name} - ({self.subject.grade.name})"


class Subsection(models.Model):
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='subsections')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.title} - {self.chapter.title} - {self.chapter.subject.name} - {self.chapter.subject.grade.name}"


class Video(models.Model):
    subsection = models.ForeignKey(Subsection, on_delete=models.CASCADE, related_name='videos')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    video_file = models.FileField(upload_to='videos/')
    duration = models.DurationField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.subsection.title} - {self.subsection.chapter.title} - {self.subsection.chapter.subject.name} - {self.subsection.chapter.subject.grade.name}"
