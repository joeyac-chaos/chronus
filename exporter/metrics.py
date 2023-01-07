import sys
import itertools
from prometheus_client import CollectorRegistry, Info, Gauge, Counter, generate_latest


class MetricLabel(object):
    def __init__(self, metric) -> None:
        self._metric = metric
        self._label_value = None

    def __setitem__(self, label_value, value):
        self._label_value = label_value
        self._metric.value(value)
        return self._metric

    def __getitem__(self, label_value):
        self._label_value = label_value
        return self._metric

    def set_label_value(self, label_value):
        self._label_value = label_value
        return self._metric

    def clear(self, value=None):
        self._label_value = value


class PrometheusMetric(object):
    NAME = None
    DESC = ""
    LABELS = []
    MTYPE = Gauge
    COMMON_LABELS = ['host',]

    def __init__(self, **kwargs) -> None:
        self._value_map = []
        self._kwargs = kwargs
        for label in itertools.chain(self.COMMON_LABELS, self.LABELS):
            setattr(self, label, MetricLabel(self))
        for label in self.COMMON_LABELS:
            v = self._kwargs.get(label, None)
            if not v:
                raise ValueError(
                    f'common label <{label}> for metric <{self.NAME}> missed')
            getattr(self, label).clear(v)

    def value(self, value) -> None:
        label_values = self.label_values()
        self._value_map.append({
            'labels': label_values,
            "value": value,
        })
        for label in itertools.chain(self.COMMON_LABELS, self.LABELS):
            getattr(self, label).clear(self._kwargs.get(label, None))

    def export(self, registry):
        if not self._value_map:
            print(f'W: {self.NAME} not set, skip', file=sys.stderr)
            return

        clz = self.__class__
        metric = clz.MTYPE(clz.NAME, clz.DESC, clz.LABELS +
                           clz.COMMON_LABELS, registry=registry)

        for value_map in self._value_map:
            if isinstance(metric, Gauge):
                # print(f"DEBUG {value_map['labels']}, {value_map['value']}")
                metric.labels(**value_map['labels']).set(value_map['value'])
            elif isinstance(metric, Counter):
                metric.labels(**value_map['labels']).inc(value_map['value'])
            elif isinstance(metric, Info):
                metric.labels(**value_map['labels']).info(value_map['value'])
            else:
                raise ValueError(f'invalid metric type = {type(metric)}')

    def __repr__(self) -> str:
        return f'{self.NAME} {self.MTYPE} {self.DESC} {self.LABELS + self.COMMON_LABELS}'

    def label_values(self):
        result = {}
        unset_labels = []
        for label in itertools.chain(self.COMMON_LABELS, self.LABELS):
            result[label] = getattr(getattr(self, label), '_label_value')
            if result[label] is None:
                unset_labels.append(label)
        if unset_labels:
            raise ValueError(f'{self} has unset labels: {result}')
        return result


""" ---------- metrics define start ---------- """


class SystemInfomationMetric(PrometheusMetric):
    NAME = 'system_information'
    DESC = 'The host base information, value always 1'
    LABELS = ['alive', 'hostname', 'os', 'platform', 'virt', 'ip']


class SystemUpTimeMetric(PrometheusMetric):
    NAME = 'system_up_time'
    DESC = 'represents the number of seconds since the UNIX Epoch of 1970-01-01 00:00:00 in UTC.'


class CPUNumMetric(PrometheusMetric):
    NAME = 'cpu_num'
    DESC = 'number of cpu/vcpu for calculate cpu usage percent'


class CPUTimeMetric(PrometheusMetric):
    NAME = 'cpu_time'
    DESC = 'time that processor spent in different modes (user,sys,total)'
    LABELS = ['mode']
    MTYPE = Counter


class CPUUtilizationMetric(PrometheusMetric):
    NAME = 'cpu_utilization'
    DESC = 'a float representing the current system-wide CPU utilization as a percentage'

class MemoryFreeMetric(PrometheusMetric):
    NAME = 'memory_free_bytes'
    DESC = 'Free memory of swap memory, available memory of physical memory in bytes'
    LABELS = ['type']


class MemoryTotalMetric(MemoryFreeMetric):
    NAME = 'memory_total_bytes'
    DESC = 'Total memory of {physical, swap} in bytes'


class NetWorkStatsMetric(PrometheusMetric):
    NAME = 'network_stats'
    DESC = 'information about each NIC (network interface card) installed on the system'
    LABELS = ['device', 'up', 'speed', 'mtu']


class NetWorkTrafficsMetric(PrometheusMetric):
    NAME = 'network_traffics'
    DESC = 'Network interface traffics, bytes in bytes/s | packets/err/drop in number of'
    LABELS = ['device', 'type', 'name']


class DiskFreeSpaceMetric(PrometheusMetric):
    NAME = 'disk_free_space_bytes'
    DESC = 'Filesystem free space size in bytes.'
    LABELS = ['device', 'name']


class DiskTotalSpaceMetric(DiskFreeSpaceMetric):
    NAME = 'disk_total_space_bytes'
    DESC = 'Filesystem total space size in bytes.'


class DiskTrafficBytesMetric(PrometheusMetric):
    NAME = 'disk_traffic_bytes'
    DESC = 'Filesystem traffic from psutil.disk_io_counters, type{read/write}'
    LABELS = ['disk', 'type']


class DiskTrafficCountMetric(PrometheusMetric):
    NAME = 'disk_traffic_count'
    DESC = 'number of reads/writes for disk, type{read/write}'
    LABELS = ['disk', 'type']
    MTYPE = Counter

class DiskTrafficTimeMetric(PrometheusMetric):
    NAME = 'disk_traffic_time'
    DESC = 'reads/writes for disk time in ms, type{read/write}'
    LABELS = ['disk', 'type']
    MTYPE = Counter

class DiskTrafficBusyTimeMetric(PrometheusMetric):
    NAME = 'disk_traffic_busy_time'
    DESC = 'busy time for disk in ms'
    LABELS = ['disk']
    MTYPE = Counter


class HardwareCurrentTemperatureMetric(PrometheusMetric):
    NAME = 'hardware_current_temperature'
    DESC = 'cpu/gpu/disk current temperature in °C'
    LABELS = ['device', 'high', 'critical']
    # LABELS = ['device', 'label', 'high', 'critical']

# class HardwareThresholdTemperatureMetric(PrometheusMetric):
#     NAME = 'hardware_threshold_temperature'
#     DESC = 'cpu/gpu/disk thresholds temperature in °C'
#     LABELS = ['device', 'label']
#     MTYPE = Info


class PingLatencyMetric(PrometheusMetric):
    NAME = 'ping_latency'
    DESC = 'avg latency of 3 ping from certain host in ms'
    LABELS = ['destination']


""" ---------- metrics define end ---------- """


class ChronusMetric(object):
    def __init__(self, **kwargs) -> None:
        self._registry = CollectorRegistry()
        self._names = set()
        self._metrics = []

        def register(cls):
            for impl in cls.__subclasses__():
                if impl.NAME:
                    if impl.NAME in self._names:
                        raise ValueError(f'duplicate name f{impl.NAME}')
                    self._names.add(impl.NAME)
                    setattr(self, impl.NAME, impl(**kwargs))
                register(impl)
        register(PrometheusMetric)

    def export(self):
        for name in self._names:
            metric = getattr(self, name)
            metric.export(self._registry)
        return generate_latest(self._registry)


if __name__ == '__main__':
    metric = ChronusMetric(host='localhost')
    metric.cpu_time.mode["user"] = 1
    metric.cpu_time.mode["idle"] = 2
    metric.memory_total_bytes.type['physical'] = 1024 * 1024 * 32
    metric.cpu_num.value(2)
    metric.cpu_num.value(3)
    print(metric.export().decode())
