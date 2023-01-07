
import os
import sys
import json
import base64
import subprocess
from typing import List
from datetime import datetime


def physical_disk_names():
    # get from 'lsblk -io KNAME,TYPE'
    # KNAME     TYPE
    # sda       disk
    # sda1      part
    # sdb       disk
    # sdb1      part
    # nvme0n1   disk
    ret = subprocess.check_output(
        'lsblk -io KNAME,TYPE', stderr=subprocess.STDOUT, shell=True).decode().strip()
    result = set()
    for line in ret.split('\n')[1:]:
        x, y = filter(None, line.split(" "))
        if y == 'disk':
            result.add(x)
    return result


def virt_domain_exec(domain: str, path: str, arg: List[str]):
    if os.geteuid() != 0:
        exit("You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting.")
    command_json = {
        'execute': 'guest-exec',
        'arguments': {
            "path": path,
            "arg": arg,
            "capture-output": True,
        }
    }
    qemu_cmd = "virsh qemu-agent-command {} '{}'".format(
        domain, json.dumps(command_json))
    ret = subprocess.check_output(
        qemu_cmd, stderr=subprocess.STDOUT, shell=True).decode().strip()
    pid = json.loads(ret)["return"]["pid"]
    command_json = {
        'execute': 'guest-exec-status',
        "arguments": {'pid': pid},
    }
    qemu_cmd = ["virsh", 'qemu-agent-command',
                domain, json.dumps(command_json)]
    qemu_cmd = "virsh qemu-agent-command {} '{}'".format(
        domain, json.dumps(command_json))
    while True:
        ret = subprocess.check_output(
            qemu_cmd, stderr=subprocess.STDOUT, shell=True).decode().strip()
        ret = json.loads(ret)
        if ret['return']['exited']:
            outdata = ret['return']['out-data']
            return base64.b64decode(outdata)


def virt_domain_up_since(domain: str):
    ret = virt_domain_exec(domain, 'uptime', ['-s'])
    ret = datetime.strptime(ret.decode().strip(), "%Y-%m-%d %H:%M:%S")
    return ret.timestamp()


if __name__ == '__main__':
    print(physical_disk_names())

    print(virt_domain_up_since("xray"))
    print(virt_domain_up_since("monitor"))

    ret = virt_domain_exec("truenas-core", 'zpool', ['list'])
    print(ret)
