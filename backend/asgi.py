import os

# Set the settings module before anything else
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

# Force Django to set up the app registry
import django
django.setup()

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

# Now import your routing module after Django is set up.
from backend import routing

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            routing.websocket_urlpatterns
        )
    ),
})
