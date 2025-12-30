import json
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from .models import HardwareInfo, Server


class AgentReportTests(TestCase):
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

    def test_sn_change_updates_existing_record(self):
        first = self._post_report('SN-002', '10.0.0.2', logical_cores=8, bmc_ip='192.168.0.2')
        self.assertEqual(first.status_code, 200)
        server = Server.objects.get(sn='SN-002')
        initial_hw = HardwareInfo.objects.get(server=server)
        self.assertEqual(initial_hw.cpu_info.get('logical_cores'), 8)

        # 同SN不同IP
        response = self._post_report('SN-002', '10.0.0.3', logical_cores=12, bmc_ip='192.168.0.3')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['is_new'])

        updated_server = Server.objects.get(sn='SN-002')
        self.assertEqual(updated_server.management_ip, '10.0.0.3')
        self.assertEqual(updated_server.bmc_ip, '192.168.0.3')
        self.assertEqual(updated_server.hardware.cpu_info.get('logical_cores'), 12)

    def test_ip_reuse_updates_existing_record(self):
        self._post_report('SN-100', '10.0.0.10', bmc_ip='10.1.0.10')
        response = self._post_report('SN-200', '10.0.0.10', bmc_ip='10.1.0.11')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['is_new'])

        self.assertEqual(Server.objects.count(), 1)
        new_server = Server.objects.first()
        self.assertEqual(new_server.sn, 'SN-200')
        self.assertEqual(new_server.management_ip, '10.0.0.10')
        self.assertEqual(new_server.bmc_ip, '10.1.0.11')

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

    def test_placeholder_server_is_reused_without_archiving(self):
        temp_server = Server.objects.create(
            sn='TEMP-10.0.0.80',
            hostname='',
            management_ip='10.0.0.80',
            status='unknown'
        )

        response = self._post_report('SN-800', '10.0.0.80', bmc_ip='192.168.20.10')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['is_new'])

        temp_server.refresh_from_db()
        self.assertEqual(temp_server.sn, 'SN-800')
        self.assertEqual(temp_server.bmc_ip, '192.168.20.10')
        self.assertEqual(Server.objects.count(), 1)


from .models import Credential

class CredentialViewTests(TestCase):
    def setUp(self):
        self.cred = Credential.objects.create(
            title='Test Credential',
            username='root'
        )
        self.cred.set_password('testpass')
        self.cred.save()

    def test_credential_list_view(self):
        url = reverse('assets:credential_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Credential')

    def test_credential_add_view(self):
        url = reverse('assets:credential_add')
        data = {
            'title': 'New Cred',
            'username': 'admin',
            'input_password': 'newpassword'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302) # Redirects on success
        self.assertEqual(Credential.objects.count(), 2)
        new_cred = Credential.objects.get(title='New Cred')
        self.assertEqual(new_cred.get_password(), 'newpassword')

    def test_credential_edit_view(self):
        url = reverse('assets:credential_edit', args=[self.cred.id])
        # Update username but keep password (empty password field means keep existing)
        data = {
            'title': 'Updated Cred',
            'username': 'root_updated',
            'input_password': ''
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.cred.refresh_from_db()
        self.assertEqual(self.cred.title, 'Updated Cred')
        self.assertEqual(self.cred.username, 'root_updated')
        self.assertEqual(self.cred.get_password(), 'testpass') # Password unchanged

        # Update password
        data['input_password'] = 'changedpass'
        self.client.post(url, data)
        self.cred.refresh_from_db()
        self.assertEqual(self.cred.get_password(), 'changedpass')

    def test_credential_delete_view(self):
        url = reverse('assets:credential_delete', args=[self.cred.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Credential.objects.filter(id=self.cred.id).exists())


class ServerOOBTests(TestCase):
    def setUp(self):
        self.server = Server.objects.create(
            sn='OOB-TEST',
            management_ip='192.168.1.100',
            bmc_ip='192.168.1.200',
            oob_username='admin'
        )
        self.server.set_oob_password('admin123')
        self.server.save()
        
        self.cred = Credential.objects.create(title='OOB Cred', username='bmc_admin')
        self.cred.set_password('bmc_pass')
        self.cred.save()

    def test_oob_update_view_manual(self):
        url = reverse('assets:server_edit_oob', args=[self.server.id])
        data = {
            'bmc_ip': '192.168.1.201',
            'oob_username': 'new_admin',
            'oob_password_input': 'new_pass'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        self.server.refresh_from_db()
        self.assertEqual(self.server.bmc_ip, '192.168.1.201')
        self.assertEqual(self.server.oob_username, 'new_admin')
        self.assertEqual(self.server.get_oob_password(), 'new_pass')

    def test_oob_update_view_credential(self):
        url = reverse('assets:server_edit_oob', args=[self.server.id])
        data = {
            'bmc_ip': '192.168.1.200',
            'credential': self.cred.id
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        self.server.refresh_from_db()
        self.assertEqual(self.server.oob_username, 'bmc_admin')
        self.assertEqual(self.server.get_oob_password(), 'bmc_pass')

    @patch('subprocess.run')
    def test_power_on_view(self, mock_run):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = 'Chassis Power Control: Up/On'
        
        url = reverse('assets:server_power_on', args=[self.server.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        
        # Verify ipmitool arguments
        args = mock_run.call_args[0][0]
        self.assertIn('ipmitool', args)
        self.assertIn('power', args)
        self.assertIn('on', args)
        self.assertIn(self.server.bmc_ip, args)

    @patch('subprocess.run')
    def test_power_failure(self, mock_run):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = 'Error: Connection failed'
        
        url = reverse('assets:server_power_off', args=[self.server.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)