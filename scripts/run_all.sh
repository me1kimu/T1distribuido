#!/usr/bin/env bash
set -e

# 1. Distribution
./scripts/run_one_scenario.sh dist_zipf_lru_200mb 200mb allkeys-lru 2000 zipf 0 300

# 2. Policies
./scripts/run_one_scenario.sh policy_lfu_zipf_200mb 200mb allkeys-lfu 2000 zipf 0 300
./scripts/run_one_scenario.sh policy_random_zipf_200mb 200mb allkeys-random 2000 zipf 0 300

# 3. Size
./scripts/run_one_scenario.sh size_50mb_lru_zipf 50mb allkeys-lru 2000 zipf 0 300
./scripts/run_one_scenario.sh size_500mb_lru_zipf 500mb allkeys-lru 2000 zipf 0 300

# 4. TTL
./scripts/run_one_scenario.sh ttl_5s_zipf_200mb 200mb allkeys-lru 2000 zipf 50 5
./scripts/run_one_scenario.sh ttl_20s_zipf_200mb 200mb allkeys-lru 2000 zipf 50 20

