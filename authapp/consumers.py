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
            # Extract token from query parameters
            query_params = self.scope["query_string"].decode().split("&")
            token = None
            for param in query_params:
                if param.startswith("token="):
                    token = param.split("=")[1]
                    break

            if not token:
                print("No token provided")
                await self.close()
                return

            # Authenticate user using token
            self.user = await self.get_user_from_token(token)
            if not self.user:
                print("Invalid token or user not found")
                await self.close()
                return

            print(f"User authenticated: {self.user.username}")

            # Set up chat room
            self.other_user_id = int(self.scope["url_route"]["kwargs"]["other_user_id"])
            user_ids = sorted([self.user.id, self.other_user_id])
            self.room_name = f"chat_{user_ids[0]}_{user_ids[1]}"

            # Join room group
            await self.channel_layer.group_add(self.room_name, self.channel_name)
            await self.accept()

            # Update user presence
            status_changed = await self.update_presence(True)
            if status_changed:
                await self.broadcast_status()

        except Exception as e:
            print(f"Connection error: {str(e)}")
            await self.close()

    async def disconnect(self, close_code):
        try:
            if hasattr(self, 'room_name') and self.room_name:
                await self.channel_layer.group_discard(self.room_name, self.channel_name)
            if hasattr(self, 'user'):
                status_changed = await self.update_presence(False)
                if status_changed:
                    await self.broadcast_status()
        except Exception as e:
            print(f"Disconnect error: {str(e)}")

    async def receive(self, text_data):
        try:
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
                    "type": "chat_message",  # Changed from "chat.message"
                    "message": saved_message.message,
                    "sender_id": str(self.user.id),
                    "sender_username": self.user.username,
                    "timestamp": saved_message.timestamp.isoformat(),
                },
            )

        except Exception as e:
            await self.send_error(str(e))

    async def chat_message(self, event):  # Method name matches the "type" field above
        await self.send(text_data=json.dumps(event))

    async def typing_indicator(self, event):
        await self.send(text_data=json.dumps({
            "type": "typing",
            "user_id": event["user_id"],
            "is_typing": event["is_typing"]
        }))

    async def handle_typing_event(self, data):
        await self.channel_layer.group_send(
            self.room_name,
            {
                "type": "typing.indicator",
                "user_id": str(self.user.id),
                "is_typing": data.get("is_typing", False)
            }
        )

        await self.channel_layer.group_send(
            f"chatlist_{self.other_user_id}",
            {
                "type": "friend.typing",
                "user_id": self.user.id,
                "is_typing": data.get("is_typing", False)
            }
        )

    @database_sync_to_async
    def get_user_from_token(self, token):
        try:
            token_obj = Token.objects.get(key=token)
            return token_obj.user
        except Token.DoesNotExist:
            return None

    @database_sync_to_async
    def get_or_create_chat(self):
        user1_id, user2_id = sorted([self.user.id, self.other_user_id])
        chat, _ = Chat.objects.get_or_create(user1_id=user1_id, user2_id=user2_id)
        return chat

    @database_sync_to_async
    def save_message(self, chat, message):
        return Message.objects.create(chat=chat, sender=self.user, message=message)

    @database_sync_to_async
    def update_presence(self, connecting):
        try:
            if connecting:
                User.objects.filter(id=self.user.id).update(active_connections=F('active_connections') + 1)
            else:
                User.objects.filter(id=self.user.id).update(active_connections=F('active_connections') - 1)

            self.user.refresh_from_db()

            was_online = self.user.is_online
            new_is_online = self.user.active_connections > 0

            update_fields = []
            if new_is_online != self.user.is_online:
                self.user.is_online = new_is_online
                update_fields.append('is_online')
            if not new_is_online:
                self.user.last_online = datetime.now()
                update_fields.append('last_online')

            if update_fields:
                self.user.save(update_fields=update_fields)

            return new_is_online != was_online
        except Exception as e:
            print(f"Presence update error: {str(e)}")
            return False

    async def broadcast_status(self):
        partners = await self.get_chat_partners()
        current_time = datetime.now().isoformat()
        for partner_id in partners:
            await self.channel_layer.group_send(
                f"chatlist_{partner_id}",
                {
                    "type": "user.status",
                    "user_id": str(self.user.id),
                    "status": "online" if self.user.is_online else "offline",
                    "last_online": current_time if not self.user.is_online else None
                }
            )

    @database_sync_to_async
    def get_chat_partners(self):
        return list(User.objects.filter(
            Q(chat_user1__user2=self.user) | Q(chat_user2__user1=self.user)
        ).distinct().values_list('id', flat=True))

    async def send_error(self, error_msg):
        await self.send(text_data=json.dumps({
            "type": "error",
            "message": error_msg
        }))

class ChatListConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            query_params = {
                key: value for key, value in (
                    param.split("=", 1) if "=" in param else (param, "")
                    for param in self.scope["query_string"].decode().split("&")
                )
            }
            token = query_params.get("token")
            if not token:
                await self.close()
                return

            token_obj = await database_sync_to_async(Token.objects.get)(key=token)
            self.user = token_obj.user
            self.room_group_name = f"chatlist_{self.user.id}"

            await self.channel_layer.group_add(self.room_group_name, self.channel_name)
            await self.accept()

        except Exception as e:
            await self.close(code=4001)

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def user_status(self, event):
        await self.send(text_data=json.dumps({
            "type": "status",
            "user_id": event["user_id"],
            "status": event["status"],
            "last_online": event.get("last_online")
        }))

    async def friend_typing(self, event):
        await self.send(text_data=json.dumps({
            "type": "friend_typing",
            "user_id": event["user_id"],
            "is_typing": event["is_typing"]
        }))

class OnlineStatusConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            await self.accept()
            query_params = {
                key: value for key, value in (
                    param.split("=", 1) if "=" in param else (param, "")
                    for param in self.scope["query_string"].decode().split("&")
                )
            }
            token = query_params.get("token")
            if not token:
                await self.close()
                return

            token_obj = await database_sync_to_async(Token.objects.get)(key=token)
            self.user = token_obj.user
            self.status_group = f"status_{self.user.id}"
            await self.channel_layer.group_add(self.status_group, self.channel_name)

        except Exception as e:
            await self.close(code=4001)

    async def disconnect(self, close_code):
        if hasattr(self, 'status_group'):
            await self.channel_layer.group_discard(self.status_group, self.channel_name)

    async def user_status(self, event):
        await self.send(text_data=json.dumps({
            "type": "status",
            "user_id": event["user_id"],
            "status": event["status"],
            "last_online": event.get("last_online")
        }))




