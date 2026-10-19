-- Fixed window counter. KEYS[1]: hash {w = window start, c = count}.
-- ARGV: limit, window_seconds, cost, capacity.
-- Returns {allowed, limit, remaining, reset_ms, retry_ms, delay_ms}.
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])

local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local function to_ms(seconds) return math.max(math.ceil(seconds * 1000), 0) end

local window_start = math.floor(now / window) * window
local state = redis.call('HMGET', KEYS[1], 'w', 'c')
local count = 0
if tonumber(state[1]) == window_start then count = tonumber(state[2]) end

local reset_after = window_start + window - now
local allowed = 0
local retry_after = reset_after
if count + cost <= limit then
  allowed = 1
  retry_after = 0
  count = count + cost
  redis.call('HSET', KEYS[1], 'w', window_start, 'c', count)
  redis.call('PEXPIRE', KEYS[1], math.max(to_ms(reset_after), 1))
end
return {allowed, limit, limit - count, to_ms(reset_after), to_ms(retry_after), 0}
