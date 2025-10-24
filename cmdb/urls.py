"""
URL configuration for cmdb project.

这是Django CMDB项目的主URL配置文件,负责将传入的HTTP请求路由到相应的视图函数或类。
Django的URL路由系统支持：
1. 函数视图 (Function views)
2. 类视图 (Class-based views)
3. 包含其他URL配置 (Including another URLconf)

URL配置的工作原理：
- Django按顺序匹配urlpatterns列表中的每个模式
- 找到匹配项后立即调用对应的视图
- 如果没有匹配项,返回404错误

参考文档：https://docs.djangoproject.com/en/4.2/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include

# URL模式列表
# Django按照定义顺序依次匹配这些URL模式
urlpatterns = [
    # Django管理后台路由
    # 访问 http://domain/admin/ 进入Django自带的管理界面
    # 可以用于管理数据库模型、用户、权限等
    path('admin/', admin.site.urls),

    # 包含assets应用的URL配置
    # 将所有其他请求都转发到assets应用处理
    # include()函数允许我们将URL配置分散到不同的应用中
    # 这样可以保持项目结构的清晰和模块化
    path('', include('assets.urls')),
]
