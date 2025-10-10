#!/bin/bash
set -e

echo "Starting CMDB Asset Management System..."

# 等待数据库准备就绪（如果使用外部数据库）
if [ -n "$DB_HOST" ]; then
    echo "Waiting for database..."
    while ! nc -z $DB_HOST ${DB_PORT:-5432}; do
        sleep 0.5
    done
    echo "Database is ready!"
fi

# 执行数据库迁移
echo "Running database migrations..."
python manage.py migrate --noinput

# 创建超级用户（如果环境变量设置了）
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "Creating superuser..."
    python manage.py shell << EOF
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists():
    User.objects.create_superuser(
        username='$DJANGO_SUPERUSER_USERNAME',
        email='${DJANGO_SUPERUSER_EMAIL:-admin@example.com}',
        password='$DJANGO_SUPERUSER_PASSWORD'
    )
    print('Superuser created successfully!')
else:
    print('Superuser already exists.')
EOF
fi

# 初始化系统配置
echo "Initializing system configuration..."
python manage.py shell << 'EOF'
from assets.models import SystemConfig
config = SystemConfig.get_config()
print(f"System config initialized: {config}")
EOF

echo "CMDB system is ready!"

# 执行传入的命令
exec "$@"
