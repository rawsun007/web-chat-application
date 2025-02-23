# backend/routing.py
from django.urls import re_path
from authapp import consumers  # Use absolute import


websocket_urlpatterns = [
    re_path(r'ws/chat/(?P<other_user_id>\d+)/$', consumers.PrivateChatConsumer.as_asgi()),
    re_path(r'ws/chatlist/$', consumers.ChatListConsumer.as_asgi()),

]
