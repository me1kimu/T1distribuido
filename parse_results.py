import json, glob
for f in sorted(glob.glob("results/*.json")):
    with open(f) as file:
        d = json.load(file)
        print(f"{f:35} HR={d.get('hit_rate',0):.4f} MR={d.get('miss_rate',0):.4f} QPS={d.get('throughput_qps',0):.2f} p95={d.get('latency_ms_p95',0):.2f} Evict={d.get('evictions',0)}")
