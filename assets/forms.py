from django import forms
from django.utils import timezone
import ipaddress
from .models import ExecutionTask, Server, SystemConfig

class BootstrapFormMixin:
    """Mixin to add Bootstrap classes to form fields."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, (forms.RadioSelect, forms.CheckboxSelectMultiple, forms.CheckboxInput)):
                continue
            existing = widget.attrs.get("class", "")
            base_class = "form-select" if isinstance(widget, forms.Select) else "form-control"
            classes = set(existing.split()) if existing else set()
            classes.add(base_class)
            widget.attrs["class"] = " ".join(sorted(classes))

class AddServerForm(BootstrapFormMixin, forms.ModelForm):
    """Form for adding a new server."""
    
    ssh_password = forms.CharField(label='SSH密码', widget=forms.PasswordInput)

    class Meta:
        model = Server
        fields = ['management_ip', 'ssh_username', 'ssh_password', 'ssh_port']
        widgets = {
            'ssh_password': forms.PasswordInput(),
        }

    def clean_management_ip(self):
        ip = self.cleaned_data['management_ip']
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            raise forms.ValidationError('请输入正确的IPv4或IPv6地址')
        
        if Server.objects.filter(management_ip=ip).exists():
            raise forms.ValidationError(f'IP地址 {ip} 已存在')
        return ip

    def clean_ssh_port(self):
        port = self.cleaned_data['ssh_port']
        if not (1 <= port <= 65535):
            raise forms.ValidationError('端口号必须在1-65535之间')
        return port


class SystemSettingsForm(BootstrapFormMixin, forms.ModelForm):
    """Form for system settings."""
    
    class Meta:
        model = SystemConfig
        fields = ['server_base_url', 'allowed_networks', 'cron_expression', 'cron_description']
        widgets = {
            'allowed_networks': forms.Textarea(attrs={'rows': 6, 'class': 'font-monospace'}),
            'cron_expression': forms.TextInput(attrs={'class': 'font-monospace'}),
        }


class ExecutionTaskForm(BootstrapFormMixin, forms.ModelForm):
    """远程执行任务创建表单。"""

    execution_mode = forms.ChoiceField(
        label='执行方式',
        choices=[('immediate', '立即执行'), ('schedule', '指定时间执行')],
        widget=forms.RadioSelect,
        initial='immediate',
        required=False,
    )
    scheduled_for = forms.DateTimeField(
        label='计划执行时间',
        required=False,
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
    )
    servers = forms.ModelMultipleChoiceField(
        label='目标服务器',
        queryset=Server.objects.all(),
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = ExecutionTask
        fields = ['name', 'description', 'task_type', 'command', 'cron_expression', 'is_enabled']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'command': forms.Textarea(attrs={'rows': 6, 'class': 'font-monospace'}),
            'task_type': forms.RadioSelect,
            'cron_expression': forms.TextInput(attrs={'placeholder': '如：0 * * * *'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['servers'].queryset = Server.objects.all()
        self.should_start_immediately = False
        self.scheduled_datetime = None

        if self.initial.get('task_type') is None:
            self.initial['task_type'] = 'one_off'

    def clean_servers(self):
        servers = self.cleaned_data['servers']
        if not servers:
            raise forms.ValidationError('请至少选择一台服务器。')
        return servers

    def clean(self):
        cleaned_data = super().clean()
        task_type = cleaned_data.get('task_type')
        execution_mode = cleaned_data.get('execution_mode') or 'immediate'
        scheduled_for = cleaned_data.get('scheduled_for')

        if task_type == 'one_off':
            if execution_mode == 'schedule':
                if not scheduled_for:
                    raise forms.ValidationError('请选择计划执行时间。')
                if timezone.is_naive(scheduled_for):
                    scheduled_for = timezone.make_aware(scheduled_for, timezone.get_current_timezone())
                if scheduled_for <= timezone.now():
                    raise forms.ValidationError('计划执行时间必须晚于当前时间。')
                self.scheduled_datetime = scheduled_for
                cleaned_data['scheduled_for'] = scheduled_for
            else:
                self.should_start_immediately = True
            cleaned_data['execution_mode'] = execution_mode
        else:
            # Cron任务要求填写表达式
            cron_expression = cleaned_data.get('cron_expression')
            if not cron_expression:
                raise forms.ValidationError('请填写周期任务的 Cron 表达式。')

        return cleaned_data
