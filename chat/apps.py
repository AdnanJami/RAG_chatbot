from django.apps import AppConfig

class ChatConfig(AppConfig):
    name = 'chat'

    def ready(self):
        print('ready...')
        from chat import views
        views.start()
