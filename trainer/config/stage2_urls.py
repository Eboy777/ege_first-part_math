from django.urls import path
from learning import stage2_views as views
from learning import training_views,chat_views,notification_views,mistakes_views
urlpatterns = [
    path('api/mistakes',mistakes_views.history),
    path('api/mistakes/send',mistakes_views.message),
    path('sw.js',notification_views.worker),
    path('manifest.webmanifest',notification_views.manifest),
    path('api/notifications/config',notification_views.config),
    path('api/notifications/subscription',notification_views.subscription),
    path('api/chat',chat_views.history),
    path('api/chat/send',chat_views.message),
    path('api/chat/upload',chat_views.upload),
    path('api/chat/confirm',chat_views.confirm),
    path('api/chat/photo-dismiss',chat_views.dismiss_photo),
    path('api/chat/photos/<uuid:photo_id>',chat_views.photo_file),
    path('assets/tasks/<slug:task_id>/<path:name>',training_views.task_asset),
    path('login', views.login_page, name='login'),
    path('logout', views.logout_page, name='logout'),
    path('', views.home, name='home'),
    path('exam/<slug:version>/tasks/<int:number>', views.number_page, name='number'),
    path('exam/<slug:version>/types/<slug:slug>', training_views.type_page, name='type'),
    path('mistakes', mistakes_views.page, name='mistakes'),
    path('api/me', views.api_me),
    path('api/progress', views.api_progress),
    path('api/progress/<uuid:progress_id>', views.api_progress),
]
