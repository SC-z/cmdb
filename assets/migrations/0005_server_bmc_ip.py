from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assets', '0004_archivedserver_archivedhardwareinfo'),
    ]

    operations = [
        migrations.AddField(
            model_name='archivedserver',
            name='bmc_ip',
            field=models.GenericIPAddressField(blank=True, null=True, verbose_name='BMC IP'),
        ),
        migrations.AddField(
            model_name='server',
            name='bmc_ip',
            field=models.GenericIPAddressField(blank=True, help_text='服务器BMC/IPMI地址,可为空', null=True, verbose_name='BMC IP'),
        ),
    ]
