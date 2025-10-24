#!/bin/bash

echo "=========================================="
echo "  CMDB资产管理系统 - 一键启动脚本"
echo "=========================================="
echo ""

# 检查Python3
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未找到Python3,请先安装Python 3.8+"
    exit 1
fi

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "[提示] 虚拟环境不存在,正在创建..."
    python3 -m venv .venv
fi

# 激活虚拟环境
echo "[1/5] 激活虚拟环境..."
source .venv/bin/activate

# 安装依赖
echo "[2/5] 安装依赖包..."
pip install -q -r requirements.txt

# 数据库迁移
echo "[3/5] 执行数据库迁移..."
python manage.py makemigrations assets
python manage.py migrate

# 创建超级用户
echo "[4/5] 检查超级用户..."
python manage.py shell -c "
from django.contrib.auth import get_user_model;
User = get_user_model();
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin123');
    print('[成功] 超级用户已创建: admin / admin123')
else:
    print('[提示] 超级用户已存在: admin / admin123')
"

# 启动服务
echo "[5/5] 启动Django服务..."
echo ""
echo "=========================================="
echo "  服务已启动！"
echo "=========================================="
echo ""
echo "访问地址："
echo "  - Web界面: http://0.0.0.0:8000"
echo "  - Admin后台: http://0.0.0.0:8000/admin"
echo ""
echo "默认账号："
echo "  - 用户名: admin"
echo "  - 密码: admin123"
echo ""
echo "=========================================="
echo ""

python manage.py runserver 0.0.0.0:8000
