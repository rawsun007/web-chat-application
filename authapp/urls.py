from django.urls import path
from .views import RegisterAPI, LoginAPI, UserAPI,LangflowAPI


urlpatterns = [
    path('register/', RegisterAPI.as_view(), name='register'),
    path('login/', LoginAPI.as_view(), name='login'),
    path('user/', UserAPI.as_view(), name='user'),
    path('chat/', LangflowAPI.as_view(), name='chat-api'),

]