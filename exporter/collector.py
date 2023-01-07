import sys
import psutil
import platform
import socket
from metrics import ChronusMetric
from utils import physical_disk_names


def get_default_ip():
    for key, item in psutil.net_if_addrs().items():
        if key.startswith("e"):  # eth/enp5s0/enp3s0
            return item[0].address


class HostCollector():
    def __init__(self, **kwargs) -> None:
        self._host = kwargs.get('host', socket.gethostname())
        self._ip = kwargs.get('ip', get_default_ip())
        self._kwargs = kwargs
        self._metric = ChronusMetric(host=self._host)

    def pre_collect(self) -> bool:
        # return false if host is down
        self._metric.system_information.alive[1].hostname[self._host].os[platform.system(
        )].platform[platform.platform()].virt[0].ip[self._ip] = 1
        self._metric.system_up_time.value(psutil.boot_time())
        return True

    # done
    def collect_cpu(self) -> None:
        self._metric.cpu_num.value(psutil.cpu_count())
        cpu_times = psutil.cpu_times()

        # 这里是平台通用的统计
        for key in ['user', 'system', 'idle']:
            self._metric.cpu_time.mode[key] = getattr(cpu_times, key)
        # 直接返回 cpu percent 而不是手动计算
        self._metric.cpu_utilization.value(psutil.cpu_percent(interval=None))

    # done
    def collect_mem(self) -> None:
        mem = psutil.virtual_memory()
        swap_mem = psutil.swap_memory()
        self._metric.memory_total_bytes.type['physical'] = mem.total
        self._metric.memory_total_bytes.type['swap'] = swap_mem.total
        self._metric.memory_free_bytes.type['physical'] = mem.available
        self._metric.memory_free_bytes.type['swap'] = swap_mem.free

    # done
    def collect_disk(self) -> None:
        # disk usage
        partitions = psutil.disk_partitions()
        for partition in partitions:
            usage = psutil.disk_usage(partition.mountpoint)
            device = partition.device
            name = partition.mountpoint
            self._metric.disk_free_space_bytes.device[device].name[name] = usage.free
            self._metric.disk_total_space_bytes.device[device].name[name] = usage.total
        # TODO: libvirt vm passthrough disk usage?

        # disk io just in hard disk
        # https://brian-candler.medium.com/interpreting-prometheus-metrics-for-linux-disk-i-o-utilization-4db53dfedcfc
        ios = psutil.disk_io_counters(perdisk=True)
        names = physical_disk_names()
        for disk, io in ios.items():
            if disk not in names:
                continue
            # bytes
            self._metric.disk_traffic_bytes.disk[disk].type['read'] = io.read_bytes
            self._metric.disk_traffic_bytes.disk[disk].type['write'] = io.write_bytes
            # count
            self._metric.disk_traffic_count.disk[disk].type['read'] = io.read_count
            self._metric.disk_traffic_count.disk[disk].type['write'] = io.write_count
            # time
            self._metric.disk_traffic_time.disk[disk].type['read'] = io.read_time
            self._metric.disk_traffic_time.disk[disk].type['write'] = io.write_time
            # util
            self._metric.disk_traffic_busy_time.disk[disk] = io.busy_time
            

    def collect_network(self) -> None:
        stats = psutil.net_if_stats()
        for device, stat in stats.items():
            self._metric.network_stats.device[device].up[stat.isup].speed[stat.speed].mtu[stat.mtu] = 1

        traffics = psutil.net_io_counters(pernic=True)
        for device, traffic in traffics.items():
            self._metric.network_traffics.device[device].type['sent'].name['bytes'] = traffic.bytes_sent
            self._metric.network_traffics.device[device].type['recv'].name['bytes'] = traffic.bytes_recv
            self._metric.network_traffics.device[device].type['sent'].name['packets'] = traffic.packets_sent
            self._metric.network_traffics.device[device].type['recv'].name['packets'] = traffic.packets_recv
            self._metric.network_traffics.device[device].type['sent'].name['err'] = traffic.errout
            self._metric.network_traffics.device[device].type['recv'].name['err'] = traffic.errin
            self._metric.network_traffics.device[device].type['sent'].name['drop'] = traffic.dropout
            self._metric.network_traffics.device[device].type['recv'].name['drop'] = traffic.dropin

    # done
    def collect_hardware_temperature(self) -> None:
        temps = psutil.sensors_temperatures()
        # cpu(amd gpu) & nvme
        for name, entries in temps.items():
            for entry in entries:
                high = min(60 if name == 'amdgpu' else entry.high, 90)
                critical = min(80 if name == 'amdgpu' else entry.critical, 90)
                self._metric.hardware_current_temperature.device['_'.join(
                    [name, entry.label])].high[high].critical[critical] = entry.current
                # self._metric.hardware_threshold_temperature.device[name].label[entry.label] = {
                #     'high': str(high),
                #     'critical': str(critical),
                # }

        # hdd
        # make sure run service hdd_temp
        # sudo hddtemp --daemon --foreground /dev/sda1 /dev/sdb1 --listen=127.0.0.1
        data = bytearray()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect(('localhost', 7634))
            while True:
                d = s.recv(1024)
                if not d:
                    break
                data.extend(d)
        data = data.decode().split('|')[1:]
        hdd_high_temp = 50
        hdd_critical_temp = 60
        for i in range(len(data) // 5):
            device = data[i * 5]
            label = data[i * 5 + 1]
            self._metric.hardware_current_temperature.device['_'.join(
                ['hdd', device, label])].high[hdd_high_temp].critical[hdd_critical_temp] = int(data[i * 5 + 2])
            # self._metric.hardware_current_temperature.device[device].label[label].high[hdd_high_temp].critical[hdd_critical_temp] = int(
            #     data[i * 5 + 2])
            # self._metric.hardware_threshold_temperature.device[device].label[label] = {
            #     'high': str(hdd_high_temp),
            #     'critical': str(hdd_critical_temp),
            # }
        pass

    def collect_network_latency(self) -> None:
        ip_domain_list = self._kwargs.get('ping_ip_domain_list', None)
        if not ip_domain_list:
            return

    def do_collect(self):
        if not self.pre_collect():
            return
        method_list = [func for func in dir(self) if func.startswith(
            "collect_") and callable(getattr(self, func))]
        for method in method_list:
            getattr(self, method)()
        return self._metric.export()


class VirtDomainCollector(HostCollector):
    def __init__(self, dom, **kwargs) -> None:
        super().__init__(kwargs)
        self.dom = dom
        self.name = dom.name()

    def pre_collect(self) -> bool:
        alive = self.dom.isActive()
        self.registry.metric(self.name, 'alive', alive, alive=alive)
        if alive:
            self.registry.metric(self.name, 'host_up_time',
                                 self.dom.getTime()['seconds'])
        return alive

    def collect_cpu(self) -> None:
        cpu_stats = self.dom.getCPUStats(True)[0]
        self.registry.metric(self.name, 'cpu_time',
                             cpu_stats['cpu_time'], mode='total')
        self.registry.metric(self.name, 'cpu_time',
                             cpu_stats['user_time'], mode='user')
        self.registry.metric(self.name, 'cpu_time',
                             cpu_stats['system_time'], mode='sys')

        self.registry.metric(self.name, 'cpu_num', self.dom.maxVcpus())


class VirtHostCollector(HostCollector):
    def __init__(self, **kwargs) -> None:
        super().__init__(kwargs)
        import libvirt
        try:
            self.conn = libvirt.open("qemu:///system")
        except libvirt.libvirtError as e:
            print(repr(e), file=sys.stderr)
            exit(1)
        self.doms = self.conn.listAllDomains()

    def do_collect(self):
        for dom in self.doms:
            VirtDomainCollector(dom, **self._kwargs).do_collect()


if __name__ == '__main__':
    collector = HostCollector()
    print(collector.do_collect().decode())
