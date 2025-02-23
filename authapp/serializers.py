from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import CustomUser

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ('id', 'username', 'email')

class RegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ('id', 'username', 'email', 'password')
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        user = CustomUser.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password']
        )
        return user

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()

    def validate(self, data):
        user = authenticate(**data)
        if user and user.is_active:
            return user
        raise serializers.ValidationError("Incorrect Credentials")


# serializers.py
from rest_framework import serializers
from .models import Message

class MessageSerializer(serializers.ModelSerializer):
    sender_username = serializers.CharField(source='sender.username')
    
    class Meta:
        model = Message
        fields = ['message', 'sender_username', 'timestamp', 'sender']


from rest_framework import serializers
from .models import Chat

class ChatListSerializer(serializers.ModelSerializer):
    other_user_id = serializers.IntegerField()
    other_user_username = serializers.CharField()
    latest_message_content = serializers.CharField()
    latest_message_time = serializers.DateTimeField()

    class Meta:
        model = Chat
        fields = ['other_user_id', 'other_user_username', 'latest_message_content', 'latest_message_time']



from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import FriendRequest

User = get_user_model()

class FriendRequestUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username']

class FriendRequestSerializer(serializers.ModelSerializer):
    from_user = FriendRequestUserSerializer(read_only=True)
    to_user = FriendRequestUserSerializer(read_only=True)

    class Meta:
        model = FriendRequest
        fields = ['id', 'from_user', 'to_user', 'status', 'timestamp']
        read_only_fields = ['from_user', 'timestamp']
