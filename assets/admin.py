from django.contrib import admin
from .models import (
    Server,
    HardwareInfo,
    SystemConfig,
    ExecutionTask,
    ExecutionTaskTarget,
    ExecutionRun,
    ExecutionStage,
    ExecutionJob,
)


@admin.register(Server)
class ServerAdmin(admin.ModelAdmin):
    list_display = ['sn', 'hostname', 'management_ip', 'status', 'agent_deployed', 'last_report_time', 'created_at']
    list_filter = ['status', 'agent_deployed', 'created_at']
    search_fields = ['sn', 'hostname', 'management_ip']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('基本信息', {
            'fields': ('sn', 'hostname', 'management_ip', 'status')
        }),
        ('SSH信息', {
            'fields': ('ssh_username', 'ssh_password', 'ssh_port')
        }),
        ('Agent信息', {
            'fields': ('agent_deployed', 'agent_version')
        }),
        ('时间信息', {
            'fields': ('last_report_time', 'created_at', 'updated_at')
        }),
    )


@admin.register(HardwareInfo)
class HardwareInfoAdmin(admin.ModelAdmin):
    list_display = ['server', 'get_cpu_model', 'memory_total_gb', 'get_disk_count', 'collected_at']
    search_fields = ['server__sn', 'server__hostname']
    readonly_fields = ['collected_at']

    fieldsets = (
        ('服务器', {
            'fields': ('server',)
        }),
        ('CPU信息', {
            'fields': ('cpu_info',)
        }),
        ('内存信息', {
            'fields': ('memory_total_gb', 'memory_modules')
        }),
        ('磁盘信息', {
            'fields': ('disks',)
        }),
        ('原始数据', {
            'fields': ('raw_data', 'collected_at'),
            'classes': ('collapse',)
        }),
    )

    def get_disk_count(self, obj):
        return len(obj.disks) if obj.disks else 0
    get_disk_count.short_description = '磁盘数量'


@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    list_display = ['id', 'cron_expression', 'cron_description', 'updated_at']
    readonly_fields = ['updated_at']

    fieldsets = (
        ('白名单配置', {
            'fields': ('allowed_networks',)
        }),
        ('定时任务配置', {
            'fields': ('cron_expression', 'cron_description')
        }),
        ('时间信息', {
            'fields': ('updated_at',)
        }),
    )

    def has_add_permission(self, request):
        # 单例模式,不允许添加新记录
        return not SystemConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # 不允许删除配置
        return False


class ExecutionTaskTargetInline(admin.TabularInline):
    model = ExecutionTaskTarget
    extra = 0
    autocomplete_fields = ['server']


@admin.register(ExecutionTask)
class ExecutionTaskAdmin(admin.ModelAdmin):
    list_display = ['name', 'task_type', 'is_enabled', 'last_run_at', 'next_run_at', 'created_by', 'created_at']
    list_filter = ['task_type', 'is_enabled', 'created_at']
    search_fields = ['name', 'description', 'command']
    autocomplete_fields = ['created_by']
    inlines = [ExecutionTaskTargetInline]
    readonly_fields = ['last_run_at', 'next_run_at', 'created_at', 'updated_at']


class ExecutionJobInline(admin.TabularInline):
    model = ExecutionJob
    extra = 0
    readonly_fields = ['server', 'status', 'exit_code', 'started_at', 'finished_at']


class ExecutionStageInline(admin.TabularInline):
    model = ExecutionStage
    extra = 0
    readonly_fields = ['name', 'status', 'started_at', 'finished_at']


@admin.register(ExecutionStage)
class ExecutionStageAdmin(admin.ModelAdmin):
    list_display = ['run', 'name', 'order', 'status', 'started_at', 'finished_at']
    list_filter = ['status']
    search_fields = ['run__task__name', 'name']
    autocomplete_fields = ['run']


@admin.register(ExecutionRun)
class ExecutionRunAdmin(admin.ModelAdmin):
    list_display = ['task', 'status', 'scheduled_for', 'started_at', 'finished_at', 'triggered_by', 'is_manual']
    list_filter = ['status', 'is_manual', 'created_at']
    search_fields = ['task__name', 'notes']
    autocomplete_fields = ['task', 'triggered_by']
    inlines = [ExecutionStageInline]
    readonly_fields = ['created_at']


@admin.register(ExecutionJob)
class ExecutionJobAdmin(admin.ModelAdmin):
    list_display = ['stage', 'server', 'status', 'exit_code', 'started_at', 'finished_at']
    list_filter = ['status', 'stage__run__task__task_type']
    search_fields = ['stage__run__task__name', 'server__management_ip']
    autocomplete_fields = ['stage', 'server']
    readonly_fields = ['stdout', 'stderr', 'error_message']
