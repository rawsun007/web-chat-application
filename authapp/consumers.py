import json
from datetime import datetime
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model
from django.db.models import Q
from .models import Chat, Message

User = get_user_model()

# Private Chat Consumer 
class PrivateChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        query_params = {
            key: value
            for key, value in (
                param.split("=", 1) if "=" in param else (param, "")
                for param in self.scope["query_string"].decode().split("&")
            )
        }

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
            
            # Handle typing events
            if data.get('type') == 'typing':
                await self.handle_typing_event(data)
                return

            # Regular message handling
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
            await self.send(text_data=json.dumps({
                "error": "Failed to process message",
                "details": str(e)
            }))

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))

    async def handle_typing_event(self, data):
        """
        Broadcasts a typing indicator event to the room.
        """
        await self.channel_layer.group_send(
            self.room_name,
            {
                "type": "typing.indicator",  # This will trigger the typing_indicator method.
                "user_id": str(self.scope["user"].id),
                "is_typing": data.get("is_typing", False)
            }
        )

    async def typing_indicator(self, event):
        """
        Sends the typing indicator update to the WebSocket client.
        """
        await self.send(text_data=json.dumps({
            "type": "typing",
            "user_id": event["user_id"],
            "is_typing": event["is_typing"]
        }))

    @database_sync_to_async
    def get_or_create_chat(self, user1_id, user2_id):
        chat_obj, created = Chat.objects.get_or_create(
            user1_id=min(user1_id, user2_id),
            user2_id=max(user1_id, user2_id)
        )
        return chat_obj

    @database_sync_to_async
    def save_message(self, chat_obj, sender, message):
        return Message.objects.create(chat=chat_obj, sender=sender, message=message)


# Chat List Consumer
class ChatListConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        query_params = {
            key: value
            for key, value in (
                param.split("=", 1) if "=" in param else (param, "")
                for param in self.scope["query_string"].decode().split("&")
            )
        }

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
        # Check if room_group_name exists before discarding
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def user_status(self, event):
        await self.send(text_data=json.dumps({
            "type": "status",
            "user_id": event["user_id"],
            "status": event["status"],
            "last_online": event.get("last_online")
        }))


# Online Status Consumer
class OnlineStatusConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        query_params = {
            key: value
            for key, value in (
                param.split("=", 1) if "=" in param else (param, "")
                for param in self.scope["query_string"].decode().split("&")
            )
        }
        
        if "token" not in query_params:
            await self.close()
            return

        try:
            token = query_params["token"]
            token_obj = await database_sync_to_async(Token.objects.get)(key=token)
            self.user = await database_sync_to_async(lambda: token_obj.user)()
            await self.set_online_status(True)
            await self.send_online_status_to_chatlist(True)
        except Token.DoesNotExist:
            await self.close()

    async def disconnect(self, close_code):
        if hasattr(self, "user") and self.user.is_authenticated:
            await self.set_online_status(False)
            await self.send_online_status_to_chatlist(False)

    @database_sync_to_async
    def set_online_status(self, status):
        self.user.is_online = status
        self.user.last_online = datetime.now() if not status else None
        self.user.save()

    @database_sync_to_async
    def get_user_chat_partners(self):
        chats = Chat.objects.filter(Q(user1=self.user) | Q(user2=self.user))
        return [chat.user2 if chat.user1 == self.user else chat.user1 for chat in chats]

    async def send_online_status_to_chatlist(self, status):
        partners = await self.get_user_chat_partners()
        for partner in partners:
            await self.channel_layer.group_send(
                f"chatlist_{partner.id}",
                {
                    "type": "user.status",
                    "user_id": str(self.user.id),
                    "status": "online" if status else "offline",
                    "last_online": str(datetime.now()) if not status else None
                }
            )
