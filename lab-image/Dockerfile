FROM ubuntu:24.04
ARG HEADROOM_LOCK_SHA256
# Python belongs to the image. Neither its executable nor site-packages come from the host.
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3.12 python3.12-venv libstdc++6 libgomp1 ca-certificates binutils && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /opt/headroom-lab/requirements.txt
COPY lock.sha256 verify_runtime.py /opt/headroom-lab/
RUN test "$(cat /opt/headroom-lab/lock.sha256)" = "$HEADROOM_LOCK_SHA256" && \
    python3.12 -m venv /opt/lab-venv && \
    /opt/lab-venv/bin/python -m pip install --no-cache-dir --no-compile --require-hashes --only-binary=:all: -r /opt/headroom-lab/requirements.txt && \
    /opt/lab-venv/bin/python -m pip check && \
    /opt/lab-venv/bin/python /opt/headroom-lab/verify_runtime.py && \
    ln -s /opt/lab-venv /opt/venv
LABEL org.headroom.lab-runtime="python312-self-contained-v1" \
      org.headroom.uv-lock-sha256="$HEADROOM_LOCK_SHA256"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_CONFIG_FILE=/dev/null
WORKDIR /run
USER 65534:65534
# /opt/venv is an image-owned compatibility alias for existing recorded argv.
# Runtime source/output mounts and network/resource isolation remain the runner's responsibility.
ENTRYPOINT ["/opt/venv/bin/python"]
