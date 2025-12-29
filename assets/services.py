import ipaddress
import logging
from django.db import transaction
from django.utils import timezone
from .models import Server, HardwareInfo, SystemConfig

logger = logging.getLogger(__name__)

class ServerService:
    """Service class for Server related operations."""

    @staticmethod
    def process_agent_report(data):
        """
        Process agent report data and update server hardware info.
        
        Args:
            data (dict): The JSON data received from the agent.
            
        Returns:
            tuple: (server_instance, is_new_boolean)
        """
        sn = data.get('sn')
        management_ip = data.get('management_ip')
        hostname = data.get('hostname', '')
        
        # Handle optional BMC IP
        bmc_ip_provided = 'bmc_ip' in data
        bmc_ip = None
        if bmc_ip_provided:
            val = data.get('bmc_ip')
            if val and isinstance(val, str) and val.strip().lower() != 'null':
                try:
                    ipaddress.ip_address(val.strip())
                    bmc_ip = val.strip()
                except ValueError:
                    pass

        hardware_info = data.get('hardware_info', {})
        now = timezone.now()
        is_new = False

        with transaction.atomic():
            # Try to find existing server by SN or IP
            server_by_ip = (
                Server.objects.select_for_update()
                .filter(management_ip=management_ip)
                .order_by('-updated_at')
                .first()
            )
            server_by_sn = (
                Server.objects.select_for_update()
                .filter(sn=sn)
                .order_by('-updated_at')
                .first()
            )

            if server_by_sn:
                server = server_by_sn
                # If IP conflict (another server has this IP but different SN), resolve it
                if server_by_ip and server_by_ip.id != server.id:
                    logger.warning(f"Duplicate IP {management_ip} detected. Deleting old server {server_by_ip.sn}.")
                    server_by_ip.delete()
            elif server_by_ip:
                server = server_by_ip
            else:
                server = Server.objects.create(
                    sn=sn,
                    hostname=hostname,
                    management_ip=management_ip,
                    bmc_ip=bmc_ip,
                    status='online',
                    last_report_time=now
                )
                is_new = True

            # Update server details
            if not is_new:
                server.sn = sn
                server.hostname = hostname
                if server.management_ip != management_ip:
                    server.management_ip = management_ip
                if bmc_ip_provided:
                    server.bmc_ip = bmc_ip
                server.status = 'online'
                server.last_report_time = now
                
                update_fields = ['sn', 'hostname', 'management_ip', 'status', 'last_report_time']
                if bmc_ip_provided:
                    update_fields.append('bmc_ip')
                server.save(update_fields=update_fields)

            # Process hardware info
            if hardware_info:
                ServerService._update_hardware_info(server, hardware_info, data)

        return server, is_new

    @staticmethod
    def _update_hardware_info(server, hardware_info, raw_data):
        """Update HardwareInfo for a server."""
        cpu_info = hardware_info.get('cpu', {})
        memory_info = hardware_info.get('memory', {})
        memory_modules = memory_info.get('modules', [])
        memory_total_gb = memory_info.get('total_gb', 0)
        disks = hardware_info.get('disks', [])

        hw_data = {
            'cpu_info': cpu_info,
            'memory_modules': memory_modules,
            'memory_total_gb': memory_total_gb,
            'disks': disks,
            'raw_data': raw_data
        }

        HardwareInfo.objects.update_or_create(
            server=server,
            defaults=hw_data
        )

