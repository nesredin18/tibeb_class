from rest_framework import serializers
from django.contrib.auth import get_user_model
from contents.models import Grade  # Adjust import path based on your project structure

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    grades = serializers.PrimaryKeyRelatedField(
        queryset=Grade.objects.all(), many=True, required=False
    )
    phone_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'password', 'role',
            'grades', 'phone_number', 'first_name', 'last_name','is_verified'
        ]
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def create(self, validated_data):
        grades_data = validated_data.pop('grades', [])
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email'),
            password=validated_data['password'],
            role=validated_data.get('role', 'student'),
            phone_number=validated_data.get('phone_number', ''),
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', '')
        )
        if grades_data:
            user.grades.set(grades_data)
        return user
class UserUpdateSerializer(serializers.ModelSerializer):
    grades = serializers.PrimaryKeyRelatedField(
        queryset=Grade.objects.all(), many=True, required=False
    )
    phone_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = User
        fields = [
            'grades', 'phone_number', 'first_name', 'last_name'
        ]

