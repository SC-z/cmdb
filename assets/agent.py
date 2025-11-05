#!/usr/bin/env python3
"""
CMDB Agent - 服务器硬件信息采集脚本
Version: 2.0
"""

import json
import os
import subprocess
import re
import socket
from datetime import datetime
from urllib import request, error


class CMDBAgent:
    """CMDB Agent 采集类"""

    # 默认配置
    DEFAULT_CMDB_SERVER = 'http://127.0.0.1:8000'
    DEFAULT_TIMEOUT = 30

    def __init__(self, cmdb_server=None, timeout=None):
        """
        初始化Agent

        Args:
            cmdb_server: CMDB服务器地址（如：http://10.10.170.25:8000）
            timeout: 请求超时时间（秒）
        """
        self.cmdb_server = cmdb_server or self.DEFAULT_CMDB_SERVER
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self.hardware_data = {}

    def run_command(self, cmd):
        """执行shell命令"""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10
            )
            return result.stdout.decode('utf-8').strip()
        except Exception:
            return ''

    def run(self, cmd):
        """执行命令并返回输出（兼容新采集脚本）"""
        try:
            return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
        except subprocess.CalledProcessError:
            return ""

    # ==================== 基本信息采集 ====================

    def get_sn(self):
        """
        获取服务器序列号（SN）
        使用多种方法兜底确保能获取到唯一标识
        """
        invalid_values = [
            'Not Specified',
            'To Be Filled By O.E.M.',
            'Default string',
            'System Serial Number',
            'None',
            '0',
            ''
        ]

        # 方法1: dmidecode获取物理机SN
        sn = self.run_command("dmidecode -s system-serial-number 2>/dev/null")
        if sn and sn not in invalid_values and len(sn) > 3:
            return sn

        # 方法2: sysfs获取（虚拟机）
        sn = self.run_command("cat /sys/class/dmi/id/product_serial 2>/dev/null")
        if sn and sn not in invalid_values and len(sn) > 3:
            return sn

        # 方法3: system-uuid
        sn = self.run_command("dmidecode -s system-uuid 2>/dev/null")
        if sn and sn not in invalid_values and len(sn) > 3:
            return f"UUID-{sn}"

        # 方法4: 使用MAC地址生成唯一标识（最后兜底）
        mac = self.run_command("ip link show | grep 'link/ether' | head -n1 | awk '{print $2}'")
        if mac:
            return f"MAC-{mac.replace(':', '')}"

        # 如果所有方法都失败,返回主机名作为标识
        hostname = self.get_hostname()
        return f"HOST-{hostname}"

    def get_management_ip(self):
        """获取管理IP（默认路由接口的IP）"""
        # 方法1: 获取默认路由接口的IP
        try:
            interface = self.run_command("ip route | grep default | awk '{print $5}' | head -n1")
            if interface:
                ip = self.run_command(f"ip addr show {interface} | grep 'inet ' | awk '{{print $2}}' | cut -d/ -f1")
                if ip and ip != '':
                    return ip
        except Exception:
            pass

        # 方法2: hostname -I
        ip = self.run_command("hostname -I | awk '{print $1}'")
        if ip and ip != '':
            return ip

        # 方法3: Python socket方式
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            pass

        return '127.0.0.1'

    def get_ipmitool_ip(self):
        """获取 BMC IP 地址"""

        def parse_ip(output):
            match = re.search(r"IP Address\s*:\s*([\d.]+)", output)
            if match:
                ip = match.group(1).strip()
                if ip and ip != "0.0.0.0":
                    return ip
            return None

        output = self.run_command("ipmitool lan print")
        ip = parse_ip(output)
        if ip:
            return ip

        for channel in range(0, 11):
            output = self.run_command(f"ipmitool lan print {channel}")
            ip = parse_ip(output)
            if ip:
                return ip

        return "null"

    def get_hostname(self):
        """获取主机名"""
        hostname = self.run_command("hostname")
        return hostname if hostname else 'Unknown'

    # ==================== CPU信息采集 ====================

    def get_lscpu_info(self):
        """使用 lscpu 命令解析 CPU 信息"""
        try:
            output = subprocess.check_output(["lscpu"], text=True)
        except subprocess.CalledProcessError:
            return {}

        info = {}
        for line in output.splitlines():
            if ":" not in line:
                continue
            key, value = [x.strip() for x in line.split(":", 1)]
            info[key] = value

        cpu_model = info.get("Model name", "Unknown")
        architecture = info.get("Architecture", "Unknown")
        logical_cores = int(info.get("CPU(s)", "0"))
        sockets = int(info.get("Socket(s)", "1"))
        cores_per_socket = int(info.get("Core(s) per socket", "0"))
        physical_cores = sockets * cores_per_socket

        return {
            "model": cpu_model,
            "architecture": architecture,
            "physical_cores": physical_cores,
            "logical_cores": logical_cores,
            "sockets": sockets,
        }

    def get_dmidecode_cpu(self):
        """从 dmidecode 读取 CPU 型号（备用）"""
        try:
            output = subprocess.check_output(["dmidecode", "-t", "processor"], text=True, stderr=subprocess.DEVNULL)
        except Exception:
            return None

        model_match = re.search(r"Version:\s*(.+)", output)
        return model_match.group(1).strip() if model_match else None

    def get_cpu_info(self):
        """获取CPU信息"""
        cpu_info = self.get_lscpu_info()

        # 补充CPU型号（若lscpu无结果）
        if cpu_info.get("model") == "Unknown":
            model = self.get_dmidecode_cpu()
            if model:
                cpu_info["model"] = model

        return cpu_info

    # ==================== 内存信息采集 ====================

    def get_dmidecode_memory(self):
        """运行 dmidecode 并提取内存信息"""
        try:
            output = subprocess.check_output(["dmidecode", "-t", "memory"], text=True, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            return []

        blocks = re.split(r'\n\s*\n', output)
        mem_list = []

        for block in blocks:
            if "Memory Device" not in block:
                continue

            size_match = re.search(r"Size:\s+(.+)", block)
            if not size_match or "No Module Installed" in size_match.group(1):
                continue  # 跳过空槽位

            slot = re.search(r"Locator:\s+(.+)", block)
            size = size_match.group(1).strip()
            speed = re.search(r"Speed:\s+(.+)", block)
            sn = re.search(r"Serial Number:\s+(.+)", block)
            manufacturer = re.search(r"Manufacturer:\s+(.+)", block)

            mem_list.append({
                "slot": slot.group(1).strip() if slot else "Unknown",
                "size": size,
                "speed": speed.group(1).strip() if speed else "Unknown",
                "sn": sn.group(1).strip() if sn else "Unknown",
                "vendor": manufacturer.group(1).strip() if manufacturer else "Unknown",
            })

        return mem_list

    def get_memory_info(self):
        """获取内存信息（包括内存条列表和总容量）"""
        modules = self.get_dmidecode_memory()

        # 计算系统总内存（GB）
        mem_total_kb = self.run_command("grep MemTotal /proc/meminfo | awk '{print $2}'")
        total_gb = 0
        if mem_total_kb.isdigit():
            total_gb = int(int(mem_total_kb) / 1024 / 1024)

        return {
            "modules": modules,
            "total_gb": total_gb
        }

    # ==================== 磁盘信息采集 ====================

    def get_disks(self):
        """获取所有磁盘设备名"""
        output = self.run("lsblk -ndo NAME,TYPE | grep disk | awk '{print $1}'")
        return [line for line in output.splitlines() if line]

    def get_disk_type(self, disk):
        """判断磁盘类型（NVMe/SSD/HDD）"""
        if disk.startswith("nvme"):
            return "NVMe"
        rota = self.run(f"cat /sys/block/{disk}/queue/rotational 2>/dev/null")
        if rota == "0":
            return "SSD"
        elif rota == "1":
            return "HDD"
        else:
            return "Unknown"

    def collect_disk_info(self):
        """采集所有磁盘信息（优化版：批量命令调用）"""
        disks = self.get_disks()
        if not disks:
            return []

        # 1. 批量获取所有磁盘容量
        disk_sizes = {}
        output = self.run("lsblk -ndo NAME,SIZE")
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                disk_sizes[parts[0]] = parts[1]

        # 2. 批量获取所有NVMe信息（序列号）
        nvme_serials = {}
        nvme_json = self.run("nvme list -o json 2>/dev/null")
        if nvme_json:
            try:
                data = json.loads(nvme_json)
                for dev in data.get("Devices", []):
                    dev_name = dev.get("DevicePath", "").replace("/dev/", "")
                    sn = dev.get("SerialNumber")
                    nvme_serials[dev_name] = sn if sn else "Unknown"
            except:
                pass

        # 3. 批量获取所有NVMe的PCIe/RDMA信息
        nvme_pcie = {}
        subsys_output = self.run("nvme list-subsys 2>/dev/null")
        for line in subsys_output.splitlines():
            line = line.strip()
            if line.startswith("+- nvme"):
                # 解析格式： +- nvme0 pcie 0000:b3:00.0 live
                #          或 +- nvme10 rdma traddr=172.16.128.90 trsvcid=3627 live
                parts = line.split()
                if len(parts) >= 3:
                    nvme_name = parts[1]  # nvme0, nvme10, etc.
                    connection_type = parts[2]  # pcie 或 rdma

                    if connection_type == "pcie" and len(parts) >= 4:
                        nvme_pcie[nvme_name] = parts[3]  # 0000:b3:00.0
                    elif connection_type == "rdma":
                        nvme_pcie[nvme_name] = "rdma"

        # 4. 遍历所有磁盘,组装信息
        result = []
        for d in disks:
            # 序列号
            if d.startswith("nvme"):
                serial = nvme_serials.get(d, "Unknown")
            else:
                serial = self.run(f"smartctl -i /dev/{d} 2>/dev/null | grep 'Serial Number' | awk -F: '{{print $2}}'").strip() or "Unknown"

            # PCIe槽位
            if d.startswith("nvme"):
                # 从 nvme0n1 中提取控制器名 nvme0
                controller_name = re.match(r'(nvme\d+)', d)
                if controller_name:
                    pcie_slot = nvme_pcie.get(controller_name.group(1), "Unknown")
                else:
                    pcie_slot = "Unknown"
            else:
                pcie_slot = self.run(f"udevadm info -q path -n /dev/{d} 2>/dev/null | grep -oE '0000:[0-9a-fA-F]{{2}}:[0-9a-fA-F]{{2}}.[0-9]' | head -n1") or "Unknown"

            info = {
                "device": f"/dev/{d}",
                "type": self.get_disk_type(d),
                "size": disk_sizes.get(d, "Unknown"),
                "serial": serial,
                "pcie_slot": pcie_slot,
            }
            result.append(info)

        return result

    # ==================== 主采集流程 ====================

    def collect_hardware_info(self):
        """采集所有硬件信息"""
        print("[INFO] 开始采集硬件信息...")

        # 必须采集的信息
        self.hardware_data['sn'] = self.get_sn()
        self.hardware_data['management_ip'] = self.get_management_ip()
        self.hardware_data['bmc_ip'] = self.get_ipmitool_ip()
        self.hardware_data['hostname'] = self.get_hostname()

        print(f"[INFO] SN: {self.hardware_data['sn']}")
        print(f"[INFO] IP: {self.hardware_data['management_ip']}")
        print(f"[INFO] BMC IP: {self.hardware_data['bmc_ip']}")
        print(f"[INFO] Hostname: {self.hardware_data['hostname']}")

        # 采集硬件详细信息
        hardware_info = {}

        print("[INFO] 采集CPU信息...")
        hardware_info['cpu'] = self.get_cpu_info()

        print("[INFO] 采集内存信息...")
        hardware_info['memory'] = self.get_memory_info()

        print("[INFO] 采集磁盘信息...")
        hardware_info['disks'] = self.collect_disk_info()

        self.hardware_data['hardware_info'] = hardware_info
        self.hardware_data['collected_at'] = datetime.now().isoformat()

        print("[INFO] 硬件信息采集完成")
        return self.hardware_data

    def report_to_server(self):
        """上报数据到CMDB服务器"""
        api_url = f"{self.cmdb_server}/api/agent/report/"

        print(f"[INFO] 准备上报数据到: {api_url}")

        try:
            data = json.dumps(self.hardware_data).encode('utf-8')
            req = request.Request(
                api_url,
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )

            with request.urlopen(req, timeout=self.timeout) as response:
                result = json.loads(response.read().decode('utf-8'))
                print(f"[SUCCESS] 数据上报成功: {result.get('message', 'OK')}")
                return True

        except error.HTTPError as e:
            print(f"[ERROR] HTTP错误: {e.code} - {e.reason}")
            return False
        except error.URLError as e:
            print(f"[ERROR] 连接错误: {e.reason}")
            return False
        except Exception as e:
            print(f"[ERROR] 上报失败: {e}")
            return False

    def save_to_file(self, output_file):
        """保存数据到文件（调试用）"""
        try:
            with open(output_file, 'w') as f:
                json.dump(self.hardware_data, f, indent=2, ensure_ascii=False)
            print(f"[INFO] 数据已保存到: {output_file}")
            return True
        except Exception as e:
            print(f"[ERROR] 保存文件失败: {e}")
            return False


def main():
    """主函数"""
    import argparse
    import os

    parser = argparse.ArgumentParser(description='CMDB Agent - 硬件信息采集脚本 v2.0')
    parser.add_argument('--output', '-o', help='输出到文件（调试用）')
    parser.add_argument('--server', '-s',
                        default=os.environ.get('CMDB_SERVER'),
                        help='CMDB服务器地址（如：http://10.10.170.25:8000）')
    parser.add_argument('--timeout', '-t', type=int, default=30, help='请求超时时间（秒）')
    args = parser.parse_args()

    # 创建Agent实例
    agent = CMDBAgent(cmdb_server=args.server, timeout=args.timeout)

    # 采集硬件信息
    agent.collect_hardware_info()

    # 输出到文件或上报到服务器
    if args.output:
        agent.save_to_file(args.output)
    else:
        agent.report_to_server()


if __name__ == '__main__':
    main()
