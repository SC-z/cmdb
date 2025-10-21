from django import forms
from django.utils import timezone

from .models import ExecutionTask, Server


class ExecutionTaskForm(forms.ModelForm):
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
