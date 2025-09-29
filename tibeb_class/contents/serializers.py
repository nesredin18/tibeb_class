from rest_framework import serializers
from .models import Option, Question, Video, Grade, Subject, Book, Chapter, Subsection, Exercise

class VideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Video
        fields = '__all__'
class GradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Grade
        fields = '__all__'
class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = '__all__'      

class BookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = '__all__'

class ChapterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chapter
        fields = '__all__'

class SubsectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subsection
        fields = '__all__'

class ExerciseSerializer(serializers.ModelSerializer):
    grades = serializers.StringRelatedField(many=True)  # Optional: shows grade names
    subject = serializers.StringRelatedField()
    chapter = serializers.StringRelatedField()
    subsection = serializers.StringRelatedField()

    class Meta:
        model = Exercise
        fields = [
            'id',
            'title',
            'description',
            'type',
            'ispaid',
            'grades',
            'subject',
            'chapter',
            'subsection',
            'is_active',
            'rank',
            'total_exercise',
        ]

class OptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = ['id', 'text']

class QuestionSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = ['id', 'question_type', 'question', 'options']

    def get_options(self, obj):
        if obj.question_type == 'choose':
            return OptionSerializer(obj.options.all(), many=True).data
        return None
class SubjectMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['id', 'name','description']
    
