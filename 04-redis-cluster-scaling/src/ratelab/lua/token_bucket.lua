-- Token bucket. KEYS[1]: hash {tokens, ts}. Refills at limit / window per second up to capacity.
-- ARGV: limit, window_seconds, cost, capacity.
-- Returns {allowed, capacity, remaining, reset_ms, retry_ms, delay_ms}.
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local capacity = tonumber(ARGV[4])

local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local function to_ms(seconds) return math.max(math.ceil(seconds * 1000), 0) end

local refill_rate = limit / window
local state = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = capacity
if state[1] then
  tokens = math.min(capacity, tonumber(state[1]) + (now - tonumber(state[2])) * refill_rate)
end

local allowed = 0
local retry_after = 0
if tokens + 1e-9 >= cost then
  allowed = 1
  tokens = math.max(tokens - cost, 0)
else
  retry_after = (cost - tokens) / refill_rate
end

local reset_after = (capacity - tokens) / refill_rate
if reset_after > 0 then
  redis.call('HSET', KEYS[1], 'tokens', string.format('%.6f', tokens), 'ts', string.format('%.6f', now))
  redis.call('PEXPIRE', KEYS[1], to_ms(reset_after))
else
  redis.call('DEL', KEYS[1])
end
return {allowed, capacity, math.floor(tokens + 1e-9), to_ms(reset_after), to_ms(retry_after), 0}
