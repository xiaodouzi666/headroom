# Environment preflight

2026-10-23T00:45:17.576470+00:00

```json
{
  "DOCKER_GPU": "ok",
  "NET": "ok",
  "DISK_FREE_GB": 5694.85
}
```

## GPU

Command: `nvidia-smi`

Exit: 0

```text
Fri Oct 23 02:45:16 2026       
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 595.99.02              Driver Version: 595.99.02      CUDA Version: 13.2     |
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  NVIDIA GeForce RTX 3090 Ti     Off |   00000000:01:00.0 Off |                  Off |
|  0%   49C    P8             20W /  450W |   20684MiB /  24564MiB |      0%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+

+-----------------------------------------------------------------------------------------+
| Processes:                                                                              |
|  GPU   GI   CI              PID   Type   Process name                        GPU Memory |
|        ID   ID                                                               Usage      |
|=========================================================================================|
|    0   N/A  N/A            2397      G   /usr/lib/xorg/Xorg                       21MiB |
|    0   N/A  N/A            2722      G   /usr/bin/gnome-shell                     12MiB |
|    0   N/A  N/A          398152      C   ./bin/llama-server                    20618MiB |
+-----------------------------------------------------------------------------------------+

```

## OS

Command: `lsb_release -a`

Exit: 0

```text
Distributor ID:	Ubuntu
Description:	Ubuntu 24.04.4 LTS
Release:	24.04
Codename:	noble

```

## Disk

Command: `df -h /home/xiaodouzi/workspace/headroom`

Exit: 0

```text
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1        13T  6.5T  5.6T  54% /home

```

## Memory

Command: `free -g`

Exit: 0

```text
               total        used        free      shared  buff/cache   available
Mem:              62           6          23           0          33          55
Swap:              7           0           7

```

## Python

Command: `python3 --version`

Exit: 0

```text
Python 3.12.3

```

## Tools

Command: `bash -c command -v uv; command -v docker; command -v git; command -v gitleaks`

Exit: 1

```text
/usr/bin/docker
/usr/bin/git

```

## Docker

Command: `docker info`

Exit: 0

```text
Client: Docker Engine - Community
 Version:    29.7.2
 Context:    default
 Debug Mode: false
 Plugins:
  buildx: Docker Buildx (Docker Inc.)
    Version:  v0.36.1
    Path:     /usr/libexec/docker/cli-plugins/docker-buildx
  compose: Docker Compose (Docker Inc.)
    Version:  v5.5.0
    Path:     /usr/libexec/docker/cli-plugins/docker-compose
  model: Docker Model Runner (Docker Inc.)
    Version:  v1.2.6
    Path:     /usr/libexec/docker/cli-plugins/docker-model

Server:
 Containers: 30
  Running: 21
  Paused: 0
  Stopped: 9
 Images: 157
 Server Version: 29.7.2
 Storage Driver: overlay2
  Backing Filesystem: extfs
  Supports d_type: true
  Using metacopy: false
  Native Overlay Diff: true
  userxattr: false
 Logging Driver: json-file
 Cgroup Driver: systemd
 Cgroup Version: 2
 Plugins:
  Volume: local
  Network: bridge host ipvlan macvlan null overlay
  Log: awslogs fluentd gcplogs gelf journald json-file local splunk syslog
 CDI spec directories:
  /etc/cdi
  /run/cdi
 Discovered Devices:
  cdi: nvidia.com/gpu=0
  cdi: nvidia.com/gpu=GPU-8eab4f3f-25c8-5465-45b3-c2b5c6fe2526
  cdi: nvidia.com/gpu=all
 Swarm: inactive
 Runtimes: io.containerd.runc.v2 nvidia runc
 Default Runtime: runc
 Init Binary: docker-init
 containerd version: aad11006b869517fcd3009450b6f82da282e1a9b
 runc version: v1.4.3-0-gbb14dabe
 init version: de40ad0
 Security Options:
  apparmor
  seccomp
   Profile: builtin
  cgroupns
 Kernel Version: 7.0.0-38-generic
 Operating System: Ubuntu 24.04.4 LTS
 OSType: linux
 Architecture: x86_64
 CPUs: 12
 Total Memory: 62.72GiB
 Name: ubuntu
 ID: 473b080f-db4f-4571-959b-11d1a8252f6b
 Docker Root Dir: /var/lib/docker
 Debug Mode: false
 Experimental: false
 Insecure Registries:
  ::1/128
  127.0.0.0/8
 Live Restore Enabled: false
 Firewall Backend: iptables
  EnableUserlandProxy: true
  UserlandProxyPath: /usr/bin/docker-proxy


```

## Docker GPU

Command: `docker run --rm --gpus all --network none nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi`

Exit: 0

```text
Fri Oct 23 00:45:17 2026       
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 595.99.02              Driver Version: 595.99.02      CUDA Version: 13.2     |
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  NVIDIA GeForce RTX 3090 Ti     Off |   00000000:01:00.0 Off |                  Off |
|  0%   49C    P8             20W /  450W |   20684MiB /  24564MiB |      0%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+

+-----------------------------------------------------------------------------------------+
| Processes:                                                                              |
|  GPU   GI   CI              PID   Type   Process name                        GPU Memory |
|        ID   ID                                                               Usage      |
|=========================================================================================|
|  No running processes found                                                             |
+-----------------------------------------------------------------------------------------+

```

## Sudo

Command: `sudo -n true`

Exit: 1

```text
sudo: a password is required

```

## Network

Command: `curl -sSI --connect-timeout 15 --max-time 30 https://huggingface.co`

Exit: 0

```text
HTTP/2 200 
content-type: text/html; charset=utf-8
content-length: 182010
date: Fri, 23 Oct 2026 00:45:16 GMT
etag: W/"2c6fa-oHH7xHsQ9QNynosz5Ezuulql8ys"
x-powered-by: huggingface-moon
x-request-id: Root=1-6adaae1c-11712f1d4fa0ef264c897bf2
ratelimit: "pages";r=98;t=208
ratelimit-policy: "fixed window";"pages";q=100;w=300
cross-origin-opener-policy: same-origin
referrer-policy: strict-origin-when-cross-origin
link: </.well-known/ai-catalog.json>; rel="ai-catalog"; type="application/ai-catalog+json"
link: </.well-known/api-catalog>; rel="api-catalog"
x-frame-options: DENY
x-cache: Hit from cloudfront
via: 1.1 0f5a5feace742eb20ef71e34731fb1fa.cloudfront.net (CloudFront)
x-amz-cf-pop: AMS58-P3
alt-svc: h3=":443"; ma=86400
x-amz-cf-id: 3gxzzcw5Mi_7K6pgP-_L1NwT1YSzn4YLMVnHEqClEoxKSQik_ZbxAw==
age: 1
strict-transport-security: max-age=31536000


```
