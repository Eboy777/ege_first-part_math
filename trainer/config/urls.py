from django.urls import path
from learning import views
urlpatterns = [
    path('login', views.login_page, name='login'),
    path('logout', views.logout_page, name='logout'),
    path('', views.home, name='home'),
    path('exam/<slug:version>/tasks/<int:number>', views.number_page, name='number'),
    path('exam/<slug:version>/types/<slug:slug>', views.type_page, name='type'),
    path('bank/tasks/<slug:task_id>', views.bank_task_page, name='bank-task'),
    path('assets/tasks/<slug:task_id>/<str:filename>', views.bank_asset, name='bank-asset'),
    path('bank', views.bank_status, name='bank-status'),
    path('mistakes', views.mistakes_page, name='mistakes'),
    path('api/me', views.api_me),
    path('api/progress', views.api_progress),
    path('api/progress/<uuid:progress_id>', views.api_progress),
]
