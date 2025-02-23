from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import login
from .serializers import UserSerializer, RegisterSerializer, LoginSerializer

class RegisterAPI(generics.GenericAPIView):
    serializer_class = RegisterSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, created = Token.objects.get_or_create(user=user)
        return Response({
            "user": UserSerializer(user, context=self.get_serializer_context()).data,
            "token": token.key
        })

class LoginAPI(generics.GenericAPIView):
    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data
        login(request, user)
        token, created = Token.objects.get_or_create(user=user)
        return Response({
            "user": UserSerializer(user, context=self.get_serializer_context()).data,
            "token": token.key
        })

class UserAPI(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user
    
    
from django.db.models import Q, OuterRef, Subquery, Case, When, F
from rest_framework import generics, permissions
from .serializers import ChatListSerializer
from .models import Chat, Message, User
from django.db import models


# views.py
class UserListAPI(generics.ListAPIView):
    serializer_class = ChatListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        current_user = self.request.user
        search_query = self.request.query_params.get('search', '').strip()

        # Get all friends (accepted requests)
        accepted_users = User.objects.filter(
            Q(received_requests__from_user=current_user, received_requests__status='accepted') |
            Q(sent_requests__to_user=current_user, sent_requests__status='accepted')
        ).distinct()

        # Get or create chats for accepted friends
        for user in accepted_users:
            if current_user.id < user.id:
                Chat.objects.get_or_create(user1=current_user, user2=user)
            else:
                Chat.objects.get_or_create(user1=user, user2=current_user)

        # Subquery to get the latest message in each chat
        latest_message = Message.objects.filter(
            chat=OuterRef('pk')
        ).order_by('-timestamp')

        # Get all chats involving the current user
        chats = Chat.objects.filter(
            Q(user1=current_user) | Q(user2=current_user)
        ).annotate(
            other_user_id=Case(
                When(user1=current_user, then=F('user2')),
                When(user2=current_user, then=F('user1')),
                output_field=models.IntegerField()
            ),
            other_user_username=Case(
                When(user1=current_user, then=F('user2__username')),
                When(user2=current_user, then=F('user1__username')),
                output_field=models.CharField()
            ),
            latest_message_content=Subquery(latest_message.values('message')[:1]),
            latest_message_time=Subquery(latest_message.values('timestamp')[:1])
        ).order_by('-latest_message_time')

        # Filter by search query
        if search_query:
            chats = chats.filter(
                other_user_username__icontains=search_query
            )

        return chats
    

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Chat, Message
from .serializers import MessageSerializer

from rest_framework import generics
from .models import Message
from .serializers import MessageSerializer
from django.db.models import Q,Max
from rest_framework.views import APIView


# views.py
class MessageHistoryAPI(generics.ListAPIView):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        other_user_id = self.kwargs['other_user_id']
        current_user = self.request.user
        
        # Get messages in chronological order (oldest first)
        return Message.objects.filter(
            Q(chat__user1=current_user, chat__user2=other_user_id) |
            Q(chat__user2=current_user, chat__user1=other_user_id)
        ).order_by('timestamp')  # Oldest first


from django.db.models import Q
from rest_framework.views import APIView
from rest_framework import permissions, status
from rest_framework.response import Response
from .models import FriendRequest, User, Chat
from .serializers import FriendRequestSerializer

class SendFriendRequestAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        to_user_id = request.data.get('to_user')
        if not to_user_id:
            return Response(
                {"error": "Field 'to_user' is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            to_user = User.objects.get(id=to_user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "User not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # 1) Check if they're already friends (accepted both ways).
        already_friends = FriendRequest.objects.filter(
            Q(from_user=request.user, to_user=to_user, status='accepted') |
            Q(from_user=to_user, to_user=request.user, status='accepted')
        ).exists()
        if already_friends:
            return Response(
                {"error": "You are already friends."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2) Check if there's a pending request from this user to the target user.
        already_pending = FriendRequest.objects.filter(
            from_user=request.user, 
            to_user=to_user, 
            status='pending'
        ).exists()
        if already_pending:
            return Response(
                {"error": "Friend request already sent."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # (Optional) Remove old rejected requests to allow a fresh one
        FriendRequest.objects.filter(
            from_user=request.user, 
            to_user=to_user, 
            status='rejected'
        ).delete()

        # 3) Create the new friend request
        friend_request = FriendRequest.objects.create(
            from_user=request.user, 
            to_user=to_user
        )
        serializer = FriendRequestSerializer(friend_request)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    

# views.py
class AcceptFriendRequestAPI(generics.UpdateAPIView):
    queryset = FriendRequest.objects.all()
    serializer_class = FriendRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def update(self, request, *args, **kwargs):
        friend_request = self.get_object()
        if friend_request.to_user != request.user:
            return Response({"error": "Unauthorized."}, status=status.HTTP_403_FORBIDDEN)

        # Accept the friend request
        friend_request.status = 'accepted'
        friend_request.save()

        # Create a chat between the two users if it doesn't exist
        user1 = friend_request.from_user
        user2 = friend_request.to_user

        # Ensure user1.id is always smaller to avoid duplicate chats
        if user1.id > user2.id:
            user1, user2 = user2, user1

        Chat.objects.get_or_create(user1=user1, user2=user2)

        # Send WebSocket updates
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        channel_layer = get_channel_layer()

        # Notify both users
        for user_id in [user1.id, user2.id]:
            async_to_sync(channel_layer.group_send)(
                f"chatlist_{user_id}",
                {
                    "type": "friend_update",
                    "user_id": user2.id if user_id == user1.id else user1.id,
                    "status": "connected"
                }
            )

        return Response({"status": "accepted"})

class RejectFriendRequestAPI(generics.UpdateAPIView):
    queryset = FriendRequest.objects.all()
    serializer_class = FriendRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def update(self, request, *args, **kwargs):
        friend_request = self.get_object()
        if friend_request.to_user != request.user:
            return Response({"error": "Unauthorized."}, status=status.HTTP_403_FORBIDDEN)

        friend_request.status = 'rejected'
        friend_request.save()
        return Response({"status": "rejected"})

class PendingFriendRequestsAPI(generics.ListAPIView):
    serializer_class = FriendRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return FriendRequest.objects.filter(to_user=self.request.user, status='pending')
    


from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from django.db.models import Exists, OuterRef, Q
from rest_framework import status

User = get_user_model()

class UserSearchAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        search_query = request.query_params.get('search', '')
        current_user = request.user
        
        # Get users with friendship status
        users = User.objects.filter(username__icontains=search_query).exclude(id=current_user.id).annotate(
            is_friend=Exists(
                FriendRequest.objects.filter(
                    Q(from_user=current_user, to_user=OuterRef('pk'), status='accepted') |
                    Q(from_user=OuterRef('pk'), to_user=current_user, status='accepted')
                )
            ),
            has_pending_request_sent=Exists(
                FriendRequest.objects.filter(from_user=current_user, to_user=OuterRef('pk'), status='pending')
            ),
            has_pending_request_received=Exists(
                FriendRequest.objects.filter(from_user=OuterRef('pk'), to_user=current_user, status='pending')
            )
        )

        user_data = []
        for user in users:
            user_data.append({
                'id': user.id,
                'username': user.username,
                'is_friend': user.is_friend,
                'has_pending_request_sent': user.has_pending_request_sent,
                'has_pending_request_received': user.has_pending_request_received
            })

        # Add no users found message
        if not user_data:
            return Response({"detail": "No users found with that name"}, status=status.HTTP_200_OK)
            
        return Response(user_data)



# views.py
class FriendListAPI(generics.ListAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        current_user = self.request.user
        # Get users who have accepted friend requests
        accepted_users = User.objects.filter(
            Q(received_requests__from_user=current_user, received_requests__status='accepted') |
            Q(sent_requests__to_user=current_user, sent_requests__status='accepted')
        ).distinct()
        return accepted_users


#view.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAuthenticated

class LogoutAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        try:
            # Delete the user's token to log them out
            request.user.auth_token.delete()
            return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




















































from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import requests
import json
from typing import Optional

import os
from dotenv import load_dotenv
import dj_database_url

# Load environment variables from .env file
load_dotenv()


# Access environment variables
BASE_API_URL = os.getenv("BASE_API_URL")
LANGFLOW_ID = os.getenv("LANGFLOW_ID")
FLOW_ID = os.getenv("FLOW_ID")
APPLICATION_TOKEN = os.getenv("APPLICATION_TOKEN")
ENDPOINT = os.getenv("ENDPOINT", "")  # You can set a specific endpoint name in the flow settings

TWEAKS = {
    "ChatInput-H8D4c": {},
    "ChatOutput-lbpA5": {},
    "File-PPYW6": {},
    "CustomComponent-c79R6": {},
    "HuggingFaceModel-wsmU0": {}
}

class LangflowAPI(APIView):
    """
    A view to handle the LangFlow chat functionality.
    Accepts a POST request with the message and customizations (optional).
    """

    def post(self, request, *args, **kwargs):
        message = request.data.get("message", "").strip()
        tweaks = request.data.get("tweaks", TWEAKS)
        application_token = request.data.get("application_token", APPLICATION_TOKEN)

        # Debug: Print message and tweaks received in the request
        print("Received message:", message)
        print("Received tweaks:", tweaks)

        if not message:
            return Response({"error": "Message cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)

        # Ensure this method is not called multiple times
        if hasattr(request, '_post_called'):
            return Response({"error": "Duplicate request."}, status=status.HTTP_400_BAD_REQUEST)
        request._post_called = True

        # Run LangFlow API with the given message and optional tweaks
        response = self.run_langflow(message, tweaks, application_token)

        # Debug: Print response from LangFlow API
        print("Response from LangFlow API:", response)

        return Response(response, status=status.HTTP_200_OK)

    def run_langflow(self, message: str, tweaks: Optional[dict] = None, application_token: Optional[str] = None) -> dict:
        """
        Run the LangFlow API with the provided message and optional tweaks.

        :param message: The message to send to the LangFlow API.
        :param tweaks: Optional dictionary of tweaks to customize the flow.
        :param application_token: The application token for authentication.
        :return: The response JSON from LangFlow API.
        """
        api_url = f"{BASE_API_URL}/lf/{LANGFLOW_ID}/api/v1/run/{ENDPOINT or FLOW_ID}"

        payload = {
            "input_value": message,
            "output_type": "chat",
            "input_type": "chat",
            "tweaks": tweaks if tweaks else TWEAKS
        }

        headers = {"Authorization": f"Bearer {application_token}", "Content-Type": "application/json"}

        # Debug: Print the API request URL and payload
        print("Request URL:", api_url)
        print("Request Payload:", json.dumps(payload, indent=2))
        
        try:
            response = requests.post(api_url, json=payload, headers=headers)

            # Debug: Print raw response status and content before processing
            print("Raw Response Status:", response.status_code)
            print("Raw Response Content:", response.text)

            response.raise_for_status()  # Raises HTTPError for bad responses
            return response.json()

        except requests.exceptions.HTTPError as errh:
            print("HTTP Error:", errh)  # Debug: Print error message
            return {"error": f"HTTP Error: {errh}"}
        except requests.exceptions.RequestException as err:
            print("Request Error:", err)  # Debug: Print error message
            return {"error": f"Request Error: {err}"}





