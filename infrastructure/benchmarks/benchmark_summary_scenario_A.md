# JMeter Benchmark Summary

Load profile: Scenario A (100x10), Scenario B (100x5), ramp 10s.

## Scenario A: Job Search + Job Detail

| Config | Throughput (req/s) | Avg (ms) | P95 (ms) | P99 (ms) | Error % |
|---|---:|---:|---:|---:|---:|
| B | 3.02 | 1721.5 | 10013.0 | 10016.0 | 15.16 |
| B+S | 80.98 | 148.6 | 57.0 | 10001.0 | 1.35 |
| B+S+K | 207.49 | 27.5 | 87.0 | 112.0 | 0.00 |
| B+S+K+Other | 206.33 | 17.6 | 57.0 | 78.0 | 0.00 |

## Notes

- B run was executed with Redis + Kafka stack stopped.
- B+S run had Redis enabled, Kafka stack stopped.
- B+S+K and B+S+K+Other ran with Redis + Kafka stack enabled.
- Error rates and timeout sensitivity indicate capacity limits under mixed read/write concurrency and should be discussed in the final report.
