"""
Assets应用URL配置

这是assets应用的URL配置文件,定义了CMDB系统的所有路由规则。
包括Web页面路由和API接口路由,展示了Django URL配置的最佳实践。

URL设计原则：
1. RESTful风格：使用名词复数形式表示资源
2. 层次清晰：通过路径体现资源层次关系
3. 语义明确：URL路径直观反映功能
4. 版本友好：为未来API版本控制预留空间

路由分类：
1. Web页面路由：用于用户界面访问
2. API接口路由：用于Agent和系统集成
"""
from django.urls import path
from . import views, api_views

# 应用命名空间
# 用于在模板中反向解析URL时避免命名冲突
# 例如：{% url 'assets:server_list' %}
app_name = 'assets'

# URL模式列表
# Django按顺序匹配这些URL模式,找到匹配项后立即调用对应的视图函数
urlpatterns = [
    # ==================== Web页面路由 ====================
    # 这些路由用于渲染HTML页面,提供用户界面

    # 服务器列表页面（网站首页）
    # URL: /
    # 显示所有已添加的服务器列表,支持搜索和过滤功能
    # 这是CMDB系统的主入口页面
    path('', views.server_list_view, name='server_list'),

    # 归档服务器列表
    path('archive/', views.archived_server_list_view, name='archived_server_list'),

    # 批量操作
    path('server/bulk-action/', views.bulk_server_action_view, name='server_bulk_action'),
    path('archive/bulk-action/', views.bulk_archived_server_action_view, name='archived_server_bulk_action'),

    # 添加服务器页面
    # URL: /add/
    # 显示添加服务器的表单页面,支持SSH连接测试和Agent自动部署
    # GET: 显示表单页面,POST: 处理表单提交
    path('add/', views.add_server_view, name='add_server'),

    # 服务器详情页面
    # URL: /server/{id}/
    # 显示指定服务器的详细信息,包括基本信息和硬件配置
    # <int:server_id> 是路径参数,会自动转换为整数并传递给视图
    path('server/<int:server_id>/', views.server_detail_view, name='server_detail'),

    # 删除服务器操作
    # URL: /server/{id}/delete/
    # 处理服务器删除操作,只接受POST请求防止CSRF攻击
    # 删除操作完成后重定向到服务器列表页面
    path('server/<int:server_id>/delete/', views.delete_server_view, name='delete_server'),

    # 系统设置页面
    # URL: /settings/
    # 系统配置管理界面,包括IP白名单、定时任务等设置
    # 支持配置更新和批量操作功能
    path('settings/', views.system_settings_view, name='system_settings'),

    # 远程执行任务
    path('tasks/', views.task_list_view, name='task_list'),
    path('tasks/create/', views.task_create_view, name='task_create'),
    path('tasks/<int:task_id>/', views.task_detail_view, name='task_detail'),
    path('tasks/<int:task_id>/delete/', views.task_delete_view, name='task_delete'),

    # ==================== API接口路由 ====================
    # 这些路由用于提供RESTful API服务,供Agent和外部系统调用

    # Agent脚本下载接口
    # URL: /api/agent/script/
    # 供Agent下载最新的脚本文件
    # 包含IP白名单验证,确保安全性
    # 只接受GET请求
    path('api/agent/script/', api_views.agent_script, name='agent_script'),

    # Agent数据上报接口
    # URL: /api/agent/report/
    # 接收Agent上报的服务器硬件信息数据
    # 这是CMDB系统最核心的API接口
    # 只接受POST请求,数据格式为JSON
    path('api/agent/report/', api_views.agent_report, name='agent_report'),
]
