from django.urls import path, include
from . import views  # fixed import

urlpatterns = [
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),   # also check the view names!
    path('logout/', views.logout_view, name='logout'),
]
