"""
Web URL Configuration
"""
from django.urls import path
from . import views, api_views

app_name = 'assets'

urlpatterns = [
    # 服务器列表（首页）
    path('', views.server_list_view, name='server_list'),

    # 添加服务器
    path('add/', views.add_server_view, name='add_server'),

    # 服务器详情
    path('server/<int:server_id>/', views.server_detail_view, name='server_detail'),

    # 删除服务器
    path('server/<int:server_id>/delete/', views.delete_server_view, name='delete_server'),

    # 系统设置
    path('settings/', views.system_settings_view, name='system_settings'),

    # API - Agent脚本下载
    path('api/agent/script/', api_views.agent_script, name='agent_script'),

    # API - Agent数据上报
    path('api/agent/report/', api_views.agent_report, name='agent_report'),
]
