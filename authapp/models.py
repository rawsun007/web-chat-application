from django.contrib.auth.models import AbstractUser
from django.db import models
from channels.db import database_sync_to_async
from datetime import datetime


class CustomUser(AbstractUser):
    # Add any additional fields here if needed
    pass

    # Specify unique related_name attributes to avoid clashes
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.',
        related_name="customuser_set",  # Unique related_name
        related_query_name="user",
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name="customuser_set",  # Unique related_name
        related_query_name="user",
    )
    is_online = models.BooleanField(default=False)
    last_online = models.DateTimeField(null=True, blank=True)
    active_connections = models.IntegerField(default=0)



# OnlineStatusConsumer - Connection tracking
@database_sync_to_async 
def user_connect(self):
    self.user.active_connections += 1
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



# models.py
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class Chat(models.Model):
    """
    A simple Chat model to represent a conversation between two users.
    For group chats, you can adjust this model.
    """
    user1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_user1')
    user2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_user2')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Chat between {self.user1.username} and {self.user2.username}"

class Message(models.Model):
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sender.username}: {self.message[:20]}"


class FriendRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]

    from_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_requests')
    to_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_requests')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['from_user', 'to_user']

    def __str__(self):
        return f"{self.from_user.username} → {self.to_user.username} ({self.status})"
    

