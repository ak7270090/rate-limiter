# Algorithm comparison: 100 requests / 10 s

Measured in one Python process with a fake clock, single run, so throughput is noisy (200,000 operations per throughput run, memory over 10,000 keys).

| Algorithm | Bytes per key (full window) | Admitted from 200 at once | Admitted: 100 before + 100 after a reset | ops/s at 1 key(s) | ops/s at 10,000 key(s) | ops/s at 100,000 key(s) |
|---|---|---|---|---|---|---|
| fixed_window | 173 | 100 | 200 | 269,098 | 283,451 | 225,586 |
| sliding_window_log | 1,377 | 100 | 100 | 223,011 | 286,861 | 209,373 |
| sliding_window_counter | 169 | 100 | 102 | 225,538 | 229,234 | 212,751 |
| token_bucket | 161 | 100 | 107 | 173,753 | 164,807 | 163,839 |
| leaky_bucket | 161 | 100 | 107 | 217,580 | 247,226 | 222,248 |
| leaky_bucket_queue | 113 | 100 | 107 | 280,668 | 259,891 | 200,425 |
| gcra | 113 | 100 | 107 | 285,804 | 280,109 | 260,277 |
