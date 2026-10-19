-- Sliding window counter. KEYS[1]: hash {w = window start, cur = this window, prev = last window}.
-- Estimate = prev x (1 - elapsed fraction) + cur.
-- ARGV: limit, window_seconds, cost, capacity.
-- Returns {allowed, limit, remaining, reset_ms, retry_ms, delay_ms}.
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])

local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local function to_ms(seconds) return math.max(math.ceil(seconds * 1000), 0) end

local window_start = math.floor(now / window) * window
local state = redis.call('HMGET', KEYS[1], 'w', 'cur', 'prev')
local stored_start = tonumber(state[1])
local current, previous = 0, 0
if stored_start == window_start then
  current, previous = tonumber(state[2]), tonumber(state[3])
elseif stored_start == window_start - window then
  previous = tonumber(state[2])
end

local estimate = previous * (1 - (now - window_start) / window) + current
local allowed = 0
local retry_after = 0
if estimate + cost <= limit + 1e-9 then
  allowed = 1
  current = current + cost
  estimate = estimate + cost
else
  local room_without_previous = limit - current - cost
  local retry_at
  if room_without_previous >= 0 then
    retry_at = window_start + (1 - room_without_previous / previous) * window
  else
    retry_at = window_start + window + (1 - (limit - cost) / current) * window
  end
  retry_after = retry_at - now
end

local reset_at = window_start
if current > 0 then
  reset_at = window_start + 2 * window
elseif previous > 0 then
  reset_at = window_start + window
end
local reset_after = reset_at - now
if reset_after > 0 then
  redis.call('HSET', KEYS[1], 'w', window_start, 'cur', current, 'prev', previous)
  redis.call('PEXPIRE', KEYS[1], to_ms(reset_after))
else
  redis.call('DEL', KEYS[1])
end
local remaining = math.max(math.floor(limit - estimate + 1e-9), 0)
return {allowed, limit, remaining, to_ms(reset_after), to_ms(retry_after), 0}
