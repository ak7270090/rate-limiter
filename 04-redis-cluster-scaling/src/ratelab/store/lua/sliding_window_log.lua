-- Sliding window log. KEYS[1]: sorted set of admitted requests, scored by time.
-- ARGV: limit, window_seconds, cost, capacity.
-- Returns {allowed, limit, remaining, reset_ms, retry_ms, delay_ms}.
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])

local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local function to_ms(seconds) return math.max(math.ceil(seconds * 1000), 0) end

redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
local count = redis.call('ZCARD', KEYS[1])
local allowed = 0
local retry_after = 0
if count + cost <= limit then
  allowed = 1
  local timestamp = string.format('%.6f', now)
  for index = 1, cost do
    redis.call('ZADD', KEYS[1], now, timestamp .. ':' .. (count + index))
  end
  count = count + cost
  redis.call('PEXPIRE', KEYS[1], to_ms(window))
else
  local entries_to_expire = count + cost - limit
  local oldest_needed = redis.call('ZRANGE', KEYS[1], entries_to_expire - 1, entries_to_expire - 1, 'WITHSCORES')
  retry_after = tonumber(oldest_needed[2]) + window - now
end

local reset_after = 0
if count > 0 then
  local newest = redis.call('ZRANGE', KEYS[1], -1, -1, 'WITHSCORES')
  reset_after = tonumber(newest[2]) + window - now
end
return {allowed, limit, limit - count, to_ms(reset_after), to_ms(retry_after), 0}
