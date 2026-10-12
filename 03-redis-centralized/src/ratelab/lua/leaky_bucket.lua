-- Leaky bucket, meter variant. KEYS[1]: hash {level, ts}. Drains at limit / window per second.
-- ARGV: limit, window_seconds, cost, capacity.
-- Returns {allowed, capacity, remaining, reset_ms, retry_ms, delay_ms}.
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local capacity = tonumber(ARGV[4])

local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local function to_ms(seconds) return math.max(math.ceil(seconds * 1000), 0) end

local leak_rate = limit / window
local state = redis.call('HMGET', KEYS[1], 'level', 'ts')
local level = 0
if state[1] then
  level = math.max(tonumber(state[1]) - (now - tonumber(state[2])) * leak_rate, 0)
end

local allowed = 0
local retry_after = 0
if level + cost <= capacity + 1e-9 then
  allowed = 1
  level = level + cost
else
  retry_after = (level + cost - capacity) / leak_rate
end

local reset_after = level / leak_rate
if reset_after > 0 then
  redis.call('HSET', KEYS[1], 'level', string.format('%.6f', level), 'ts', string.format('%.6f', now))
  redis.call('PEXPIRE', KEYS[1], to_ms(reset_after))
else
  redis.call('DEL', KEYS[1])
end
local remaining = math.max(math.floor(capacity - level + 1e-9), 0)
return {allowed, capacity, remaining, to_ms(reset_after), to_ms(retry_after), 0}
