FROM ubuntu:24.04
# PyTorch full CUDA snapshot symbolization requires addr2line from binutils.
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3 libstdc++6 libgomp1 ca-certificates binutils && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /run
USER 65534:65534
# The runner supplies --network none, read-only mounts, a writable run directory,
# resource limits, and the project's locked .venv as /opt/venv.
ENTRYPOINT ["/opt/venv/bin/python"]
