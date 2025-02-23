import json
from datetime import datetime
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model
from .models import Chat, Message

User = get_user_model()

# Private Chat Consumer
class PrivateChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        query_params = {key: value for key, value in (param.split("=", 1) if "=" in param else (param, "") for param in self.scope["query_string"].decode().split("&"))}

        if "token" not in query_params:
            await self.close()
            return

        try:
            token = query_params["token"]
            token_obj = await database_sync_to_async(Token.objects.get)(key=token)
            self.scope["user"] = await database_sync_to_async(lambda: token_obj.user)()
        except Token.DoesNotExist:
            await self.close()
            return

        self.other_user_id = int(self.scope["url_route"]["kwargs"]["other_user_id"])
        self.room_name = f"chat_{min(self.scope['user'].id, self.other_user_id)}_{max(self.scope['user'].id, self.other_user_id)}"

        await self.channel_layer.group_add(self.room_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message = data.get("message", "")

            if not message:
                return

            chat_obj = await self.get_or_create_chat(self.scope["user"].id, self.other_user_id)
            saved_message = await self.save_message(chat_obj, self.scope["user"], message)

            await self.channel_layer.group_send(
                self.room_name,
                {
                    "type": "chat_message",
                    "message": saved_message.message,
                    "sender_id": str(self.scope["user"].id),
                    "timestamp": str(saved_message.timestamp),
                },
            )
        except Exception as e:
            await self.send(text_data=json.dumps({"error": "Failed to process message", "details": str(e)}))

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def get_or_create_chat(self, user1_id, user2_id):
        chat_obj, created = Chat.objects.get_or_create(user1_id=min(user1_id, user2_id), user2_id=max(user1_id, user2_id))
        return chat_obj

    @database_sync_to_async
    def save_message(self, chat_obj, sender, message):
        return Message.objects.create(chat=chat_obj, sender=sender, message=message)


# Chat List Consumer
class ChatListConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        query_params = {key: value for key, value in (param.split("=", 1) if "=" in param else (param, "") for param in self.scope["query_string"].decode().split("&"))}

        if "token" not in query_params:
            await self.close()
            return

        try:
            token = query_params["token"]
            token_obj = await database_sync_to_async(Token.objects.get)(key=token)
            self.scope["user"] = await database_sync_to_async(lambda: token_obj.user)()
        except Token.DoesNotExist:
            await self.close()
            return

        self.room_group_name = f"chatlist_{self.scope['user'].id}"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)


# Online Status Consumer
class OnlineStatusConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        self.user = self.scope["user"]

        if self.user.is_authenticated:
            await self.set_online_status(True)

    async def disconnect(self, close_code):
        if hasattr(self, "user") and self.user.is_authenticated:
            await self.set_online_status(False)

    @database_sync_to_async
    def set_online_status(self, status):
        self.user.is_online = status
        self.user.save()
