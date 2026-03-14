from rest_framework import serializers
from django.contrib.auth import get_user_model
from contents.models import Grade  # Adjust import path based on your project structure

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    grades = serializers.PrimaryKeyRelatedField(
        queryset=Grade.objects.all(), many=True, required=False
    )

    class Meta:
        model = User
        fields = [
            'id', 'username', 'password', 'role',
            'grades', 'first_name', 'last_name','is_verified', 'last_email_change', 'username_type'
        ]
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def create(self, validated_data):
        grades_data = validated_data.pop('grades', [])
        user = User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password'],
            role=validated_data.get('role', 'student'),
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            username_type=validated_data.get('username_type', 'email')
        )
        if grades_data:
            user.grades.set(grades_data)
        return user
    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with that username already exists.")
        return value
class UserUpdateSerializer(serializers.ModelSerializer):
    grades = serializers.PrimaryKeyRelatedField(
        queryset=Grade.objects.all(), many=True, required=False
    )

    class Meta:
        model = User
        fields = [
            'grades', 'first_name', 'last_name'
        ]


class UserIdentitySerializer(serializers.ModelSerializer):
    email = serializers.SerializerMethodField()
    phone_number = serializers.SerializerMethodField()
    grades = serializers.SerializerMethodField()
    external_user_id = serializers.IntegerField(source='id', read_only=True)

    class Meta:
        model = User
        fields = [
            'id',
            'external_user_id',
            'username',
            'email',
            'phone_number',
            'role',
            'first_name',
            'last_name',
            'username_type',
            'is_verified',
            'grades',
        ]

    def get_email(self, obj):
        if obj.email:
            return obj.email
        if obj.username_type == 'email':
            return obj.username
        return None

    def get_phone_number(self, obj):
        phone_number = getattr(obj, 'phone_number', None)
        if phone_number:
            return phone_number
        if obj.username_type == 'phone':
            return obj.username
        return None

    def get_grades(self, obj):
        return list(obj.grades.values_list('id', flat=True))

