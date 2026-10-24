import json
import time

from headroom.lab.deadline import clock_identity

print(json.dumps({"identity": clock_identity(), "monotonic_ns": time.monotonic_ns()}))
