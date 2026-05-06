# Performance Benchmarks

## How to Run JMeter Tests

### Step 1 — Install Apache JMeter
Download from https://jmeter.apache.org/download_jmeter.cgi  
Extract and run: `bin/jmeter` (GUI) or `bin/jmeter.sh` (CLI)

### Step 2 — Make sure Docker containers are running
```bash
docker compose up -d
```

### Step 3 — Seed benchmark CSV data
Run the project seed script first. It now generates `infrastructure/benchmarks/data/application_pairs.csv` automatically. The JMeter plan reads that CSV, so you do not need to hand-edit job_id or member_id values anymore.

### Step 4 — Run the 4 benchmark scenarios

**Scenario B (Base — no cache, no Kafka optimization):**
Temporarily disable Redis in job-service, then:
```bash
bin/jmeter -n -t jmeter_plan.jmx -l results_B.csv -e -o report_B/
```

**Scenario B+S (Base + SQL Cache — Redis enabled):**
Enable Redis caching (default), then:
```bash
bin/jmeter -n -t jmeter_plan.jmx -l results_BS.csv -e -o report_BS/
```

**Scenario B+S+K (Base + Cache + Kafka):**
Full system with Kafka async processing:
```bash
bin/jmeter -n -t jmeter_plan.jmx -l results_BSK.csv -e -o report_BSK/
```

**Scenario B+S+K+Other (+ connection pooling, indexes):**
With all optimizations enabled:
```bash
bin/jmeter -n -t jmeter_plan.jmx -l results_BSKO.csv -e -o report_BSKO/
```

### Step 5 — Generate bar charts
```bash
pip3 install matplotlib numpy
python3 generate_charts.py
```

Charts are saved to `charts/` folder as PNG files.

---

## What Each Scenario Tests

| Scenario | What changes | Expected improvement |
|---|---|---|
| B (Base) | Direct MySQL queries, no cache | Baseline |
| B+S | Redis caching on GET endpoints | ~2x throughput on reads |
| B+S+K | Kafka async for write workflows | Lower latency on writes |
| B+S+K+O | + DB indexes + connection pool | Best overall performance |

## Required Charts for Submission
1. `benchmark_job_search_+_detail_(read).png` — Read scenario throughput + latency
2. `benchmark_apply_submit_(write_+_kafka).png` — Write scenario throughput + latency
3. `benchmark_comparison.png` — Combined side-by-side comparison
