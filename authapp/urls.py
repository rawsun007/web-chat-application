from django.urls import path

from .views import RegisterAPI, LoginAPI, UserAPI,LangflowAPI,UserListAPI,MessageHistoryAPI,SendFriendRequestAPI, AcceptFriendRequestAPI, RejectFriendRequestAPI,PendingFriendRequestsAPI, UserSearchAPI, LogoutAPI
from . import views


urlpatterns = [
    path('register/', RegisterAPI.as_view(), name='register'),
    path('login/', LoginAPI.as_view(), name='login'),
    path('user/', UserAPI.as_view(), name='user'),
    path('chat/', LangflowAPI.as_view(), name='chat-api'),
    path('users/', UserListAPI.as_view(), name='user-list'),  # New endpoint
    path('messages/<int:other_user_id>/', MessageHistoryAPI.as_view(), name='message-history'),

    path('friend-requests/send/', SendFriendRequestAPI.as_view(), name='send-request'),
    path('friend-requests/accept/<int:pk>/', AcceptFriendRequestAPI.as_view(), name='accept-request'),
    path('friend-requests/reject/<int:pk>/', RejectFriendRequestAPI.as_view(), name='reject-request'),
    path('friend-requests/pending/', PendingFriendRequestsAPI.as_view(), name='pending-requests'),
    path('users/search/', UserSearchAPI.as_view(), name='user-search'),
    path('users/<int:user_id>/status/', views.user_status, name='user-status'),
    
]
