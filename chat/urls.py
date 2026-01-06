from django.urls import path
from .views import ChatHistoryView, ChatView

urlpatterns = [
    path('chat-history/', ChatHistoryView.as_view(), name='chat-history'),
    path('chat/', ChatView.as_view(), name='chat'),
]