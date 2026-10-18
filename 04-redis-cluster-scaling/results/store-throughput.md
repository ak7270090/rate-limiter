# Lua script throughput: one Redis vs Redis Cluster

`sliding_window_counter.lua` called with `EVALSHA` by memtier_benchmark 2.1.1 inside the Compose
network (4 threads x 25 connections, pipeline 32, 10 s per run, unless noted). Calls and failed
calls come from `INFO commandstats` on each node after the run. Laptop: 8 logical cores
(4 physical) shared by every Redis process and the load generator.

| Setup | Script calls per second | Calls | Failed | Calls per primary |
|---|---|---|---|---|
| one node, 100,000 keys | 62,807 | 630,656 | 0 | redis=630,656 |
| one node, one hot key | 62,745 | 629,312 | 0 | redis=629,312 |
| cluster, 100,000 keys | 49,334 | 499,424 | 0 | node-1=168,928, node-2=166,368, node-3=164,128 |
| cluster, 100,000 keys, 8 client threads | 60,934 | | 0 | |
| cluster, one hot key (slot 13307 on node-3) | 39,297 | 393,824 | 0 | node-3=393,824 |
| cluster, hot key split into 10 sub-keys | 63,109 | 629,687 | 0 | node-1=206,912, node-2=209,664, node-3=213,111 |

CPU during the runs (`docker stats`): the single node at 96%; with the cluster, each primary at
97–99% and each replica at 21–28% (replication of the scripts' writes).

Sub-key slots for the split run: `bench:hot:1`=7924, `:2`=11927, `:3`=16054, `:4`=3665,
`:5`=7792, `:6`=11795, `:7`=15922, `:8`=4061, `:9`=8188, `:10`=10464.

## Cross-slot scripts

| Keys | Slots | Result |
|---|---|---|
| `rl:items:key:k42:current`, `rl:items:key:k42:previous` | 6551, 14097 | redis-py: `EVAL - all keys must map to the same key slot`; Redis: `CROSSSLOT Keys in request don't hash to the same slot` |
| `rl:{items:key:k42}:current`, `rl:{items:key:k42}:previous` | 9241, 9241 | runs |
