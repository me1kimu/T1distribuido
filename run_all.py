import subprocess
import os

scenarios = [
    # distribution
    ("dist_uniform_lru_200mb", "200mb", "allkeys-lru", 4000, "uniform", 0, 300),
    ("dist_zipf_lru_200mb", "200mb", "allkeys-lru", 4000, "zipf", 0, 300),
    # policies
    ("policy_lru_zipf_200mb", "200mb", "allkeys-lru", 5000, "zipf", 0, 300),
    ("policy_lfu_zipf_200mb", "200mb", "allkeys-lfu", 5000, "zipf", 0, 300),
    ("policy_random_zipf_200mb", "200mb", "allkeys-random", 5000, "zipf", 0, 300),
    # size
    ("size_50mb_lru_zipf", "50mb", "allkeys-lru", 3000, "zipf", 0, 300),
    ("size_200mb_lru_zipf", "200mb", "allkeys-lru", 5000, "zipf", 0, 300),
    ("size_500mb_lru_zipf", "500mb", "allkeys-lru", 8000, "zipf", 0, 300),
    # TTL
    ("ttl_5s_zipf_200mb", "200mb", "allkeys-lru", 4000, "zipf", 0, 5),
    ("ttl_20s_zipf_200mb", "200mb", "allkeys-lru", 4000, "zipf", 0, 20),
    ("ttl_120s_zipf_200mb", "200mb", "allkeys-lru", 4000, "zipf", 0, 120),
]

def main():
    script = "./scripts/run_one_scenario.sh"
    for s in scenarios:
        name, max_mem, policy, reqs, dist, sleep, ttl = s
        print(f"Running scenario {name} with {reqs} requests...")
        subprocess.run([script, name, max_mem, policy, str(reqs), dist, str(sleep), str(ttl)])

if __name__ == "__main__":
    main()
