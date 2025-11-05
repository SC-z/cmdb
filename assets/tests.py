import json
from django.test import TestCase
from django.urls import reverse

from .models import ArchivedHardwareInfo, ArchivedServer, HardwareInfo, Server


class AgentReportArchivingTests(TestCase):
    def _post_report(self, sn, ip, hostname='host', logical_cores=4, bmc_ip='null'):
        payload = {
            'sn': sn,
            'management_ip': ip,
            'hostname': hostname,
            'bmc_ip': bmc_ip,
            'hardware_info': {
                'cpu': {
                    'logical_cores': logical_cores,
                    'architecture': 'x86_64',
                },
                'memory': {
                    'modules': [],

                },
                'disks': [],
            }
        }
        url = reverse('assets:agent_report')
        return self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )

    def test_first_report_creates_new_server(self):
        response = self._post_report('SN-001', '10.0.0.1')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['is_new'])
        self.assertEqual(Server.objects.count(), 1)
        server = Server.objects.first()
        self.assertEqual(server.sn, 'SN-001')
        self.assertEqual(server.management_ip, '10.0.0.1')
        self.assertIsNone(server.bmc_ip)
        self.assertEqual(ArchivedServer.objects.count(), 0)

    def test_sn_same_ip_changed_archives_old_record(self):
        first = self._post_report('SN-002', '10.0.0.2', logical_cores=8, bmc_ip='192.168.0.2')
        self.assertEqual(first.status_code, 200)
        server = Server.objects.get(sn='SN-002')
        initial_hw = HardwareInfo.objects.get(server=server)
        self.assertEqual(initial_hw.cpu_info.get('logical_cores'), 8)

        # 同SN不同IP
        response = self._post_report('SN-002', '10.0.0.3', logical_cores=12, bmc_ip='192.168.0.3')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['is_new'])

        # 旧记录归档
        archived = ArchivedServer.objects.get(sn='SN-002')
        self.assertEqual(archived.management_ip, '10.0.0.2')
        self.assertEqual(archived.bmc_ip, '192.168.0.2')
        self.assertEqual(archived.archived_reason, 'sn_ip_changed')
        archived_hw = ArchivedHardwareInfo.objects.get(archived_server=archived)
        self.assertEqual(archived_hw.cpu_info.get('logical_cores'), 8)

        # 新记录生效
        new_server = Server.objects.get(sn='SN-002')
        self.assertEqual(new_server.management_ip, '10.0.0.3')
        self.assertEqual(new_server.bmc_ip, '192.168.0.3')
        self.assertEqual(new_server.hardware.cpu_info.get('logical_cores'), 12)

    def test_ip_same_sn_changed_archives_old_ip(self):
        self._post_report('SN-100', '10.0.0.10', bmc_ip='10.1.0.10')
        response = self._post_report('SN-200', '10.0.0.10', bmc_ip='10.1.0.11')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['is_new'])

        self.assertEqual(Server.objects.count(), 1)
        new_server = Server.objects.first()
        self.assertEqual(new_server.sn, 'SN-200')
        self.assertEqual(new_server.bmc_ip, '10.1.0.11')

        archived = ArchivedServer.objects.get(original_server_id__isnull=False)
        self.assertEqual(archived.archived_reason, 'ip_reused_by_new_sn')
        self.assertEqual(archived.sn, 'SN-100')
        self.assertEqual(archived.management_ip, '10.0.0.10')
        self.assertEqual(archived.bmc_ip, '10.1.0.10')

    def test_same_sn_and_ip_updates_without_archiving(self):
        self._post_report('SN-500', '10.0.0.50', logical_cores=2, bmc_ip='10.2.0.50')
        server = Server.objects.get(sn='SN-500')
        initial_report_time = server.last_report_time

        response = self._post_report('SN-500', '10.0.0.50', logical_cores=4, bmc_ip='null')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['is_new'])

        server.refresh_from_db()
        self.assertGreater(server.last_report_time, initial_report_time)
        self.assertEqual(server.hardware.cpu_info.get('logical_cores'), 4)
        self.assertIsNone(server.bmc_ip)
        self.assertEqual(ArchivedServer.objects.count(), 0)

    def test_bmc_ip_saved_and_cleared(self):
        self._post_report('SN-700', '10.0.0.70', bmc_ip='172.16.0.10')
        server = Server.objects.get(sn='SN-700')
        self.assertEqual(server.bmc_ip, '172.16.0.10')

        self._post_report('SN-700', '10.0.0.70', bmc_ip='null')
        server.refresh_from_db()
        self.assertIsNone(server.bmc_ip)

    def test_invalid_bmc_ip_is_ignored(self):
        self._post_report('SN-710', '10.0.0.71', bmc_ip='invalid-value')
        server = Server.objects.get(sn='SN-710')
        self.assertIsNone(server.bmc_ip)
