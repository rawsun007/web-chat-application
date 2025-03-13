from django.urls import re_path
from authapp.consumers import PrivateChatConsumer, ChatListConsumer, OnlineStatusConsumer

websocket_urlpatterns = [
    re_path(r'ws/chat/(?P<other_user_id>\d+)/$', PrivateChatConsumer.as_asgi()),
    re_path(r'ws/chatlist/$', ChatListConsumer.as_asgi()),
    re_path(r'ws/status/$', OnlineStatusConsumer.as_asgi()),
]
