# consumers.py

import json
from datetime import datetime
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model
from django.db.models import Q, F
from .models import Chat, Message

User = get_user_model()

class PrivateChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            query_params = self.scope["query_string"].decode().split("&")
            token = next((param.split("=")[1] for param in query_params if param.startswith("token=")), None)
            
            if not token:
                await self.close()
                return

            self.user = await self.get_user_from_token(token)
            if not self.user:
                await self.close()
                return

            self.other_user_id = int(self.scope["url_route"]["kwargs"]["other_user_id"])
            user_ids = sorted([self.user.id, self.other_user_id])
            self.room_name = f"chat_{user_ids[0]}_{user_ids[1]}"

            await self.channel_layer.group_add(self.room_name, self.channel_name)
            await self.accept()

            # Update user presence
            status_changed = await self.user_connect()
            if status_changed:
                await self.broadcast_status()
        except Exception as e:
            print(f"Connection error: {e}")
            await self.close()

    async def disconnect(self, close_code):
        if hasattr(self, 'room_name'):
            await self.channel_layer.group_discard(self.room_name, self.channel_name)
        if hasattr(self, 'user'):
            status_changed = await self.user_disconnect()
            if status_changed:
                await self.broadcast_status()

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data.get('type') == 'typing':
            await self.handle_typing_event(data)
            return

        message = data.get("message", "").strip()
        if not message:
            return

        chat_obj = await self.get_or_create_chat()
        saved_message = await self.save_message(chat_obj, message)

        await self.channel_layer.group_send(
            self.room_name,
            {
                "type": "chat_message",
                "message": saved_message.message,
                "sender_id": str(self.user.id),
                "sender_username": self.user.username,
                "timestamp": saved_message.timestamp.isoformat(),
            },
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))

    async def typing_indicator(self, event):
        # Enhanced typing indicator handling
        try:
            await self.send(text_data=json.dumps({
                "type": "typing",
                "user_id": event["user_id"],
                "is_typing": event["is_typing"],
                "timestamp": datetime.now().isoformat()  # Add timestamp for better sync
            }))
        except Exception as e:
            print(f"Error sending typing indicator: {e}")

    async def handle_typing_event(self, data):
        # Improved typing event processing
        try:
            await self.channel_layer.group_send(
                self.room_name,
                {
                    "type": "typing_indicator",
                    "user_id": str(self.user.id),
                    "is_typing": data.get("is_typing", False),
                }
            )
        except Exception as e:
            print(f"Error handling typing event: {e}")

    @database_sync_to_async
    def get_user_from_token(self, token):
        try:
            return Token.objects.get(key=token).user
        except Token.DoesNotExist:
            return None

    @database_sync_to_async
    def get_or_create_chat(self):
        return Chat.objects.get_or_create(
            user1_id=min(self.user.id, self.other_user_id),
            user2_id=max(self.user.id, self.other_user_id)
        )[0]

    @database_sync_to_async
    def save_message(self, chat, message):
        return Message.objects.create(chat=chat, sender=self.user, message=message)

    @database_sync_to_async
    def user_connect(self):
        prev_status = self.user.is_online
        self.user.active_connections = F('active_connections') + 1
        self.user.save()
        self.user.refresh_from_db()
        if self.user.active_connections == 1:
            self.user.is_online = True
            self.user.last_online = None
            self.user.save()
        return prev_status != self.user.is_online

    @database_sync_to_async
    def user_disconnect(self):
        prev_status = self.user.is_online
        self.user.active_connections = F('active_connections') - 1
        self.user.save()
        self.user.refresh_from_db()
        if self.user.active_connections == 0:
            self.user.is_online = False
            self.user.last_online = datetime.now()
            self.user.save()
        return prev_status != self.user.is_online

    async def broadcast_status(self):
        partners = await self.get_chat_partners()
        for partner_id in partners:
            await self.channel_layer.group_send(
                f"chatlist_{partner_id}",
                {
                    "type": "status",  # Changed to 'status'
                    "user_id": str(self.user.id),
                    "status": "online" if self.user.is_online else "offline"
                }
            )

    @database_sync_to_async
    def get_chat_partners(self):
        return list(User.objects.filter(
            Q(chat_user1__user2=self.user) | Q(chat_user2__user1=self.user)
        ).values_list('id', flat=True))


    

class ChatListConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            query_str = self.scope["query_string"].decode()
            query_params = dict(param.split("=", 1) if "=" in param else (param, "") for param in query_str.split("&"))
            token = query_params.get("token")
            if not token:
                await self.close()
                return

            self.user = await self.get_user_from_token(token)
            if not self.user:
                await self.close()
                return

            self.room_group_name = f"chatlist_{self.user.id}"
            await self.channel_layer.group_add(self.room_group_name, self.channel_name)
            await self.accept()
        except Exception as e:
            print(f"ChatList connection error: {e}")
            await self.close()

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def status(self, event):  # Changed from user_status
        await self.send(text_data=json.dumps(event))

    async def friend_typing(self, event):
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def get_user_from_token(self, token):
        try:
            return Token.objects.get(key=token).user
        except Token.DoesNotExist:
            return None

class OnlineStatusConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            await self.accept()
            query_params = dict(param.split("=", 1) if "=" in param else (param, "") for param in self.scope["query_string"].decode().split("&"))
            token = query_params.get("token")
            if not token:
                await self.close()
                return

            self.user = await database_sync_to_async(Token.objects.get)(key=token).user
            self.status_group = f"status_{self.user.id}"
            await self.channel_layer.group_add(self.status_group, self.channel_name)
            await self.user_connect()
        except Exception as e:
            print(f"Status connection error: {e}")
            await self.close()

    async def disconnect(self, close_code):
        if hasattr(self, 'status_group'):
            await self.channel_layer.group_discard(self.status_group, self.channel_name)
        if hasattr(self, 'user'):
            await self.user_disconnect()

    async def user_status(self, event):
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def user_connect(self):
        self.user.active_connections += 1
        if self.user.active_connections == 1:
            self.user.is_online = True
            self.user.last_online = None
        self.user.save()

    @database_sync_to_async
    def user_disconnect(self):
        self.user.active_connections = max(0, self.user.active_connections - 1)
        if self.user.active_connections == 0:
            self.user.is_online = False
            self.user.last_online = datetime.now()
        self.user.save()