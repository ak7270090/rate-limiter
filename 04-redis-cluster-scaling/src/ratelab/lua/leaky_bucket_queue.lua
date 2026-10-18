-- Leaky bucket, queue variant. KEYS[1]: the time the queue is empty again.
-- Requests leave one per window / limit seconds; the caller waits delay_ms.
-- ARGV: limit, window_seconds, cost, capacity.
-- Returns {allowed, capacity, remaining, reset_ms, retry_ms, delay_ms}.
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local capacity = tonumber(ARGV[4])

local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local function to_ms(seconds) return math.max(math.ceil(seconds * 1000), 0) end

local seconds_per_request = window / limit
local scheduled_at = now
local stored = tonumber(redis.call('GET', KEYS[1]))
if stored and stored > now then scheduled_at = stored end
local queued_requests = (scheduled_at - now) / seconds_per_request

local allowed = 0
local retry_after = 0
local delay = 0
local queue_empty_at = scheduled_at
if queued_requests + cost <= capacity + 1e-9 then
  allowed = 1
  delay = scheduled_at - now
  queue_empty_at = scheduled_at + cost * seconds_per_request
else
  retry_after = (queued_requests + cost - capacity) * seconds_per_request
end

local reset_after = queue_empty_at - now
if reset_after > 0 then
  redis.call('SET', KEYS[1], string.format('%.6f', queue_empty_at), 'PX', to_ms(reset_after))
end
local remaining = math.max(math.floor(capacity - reset_after / seconds_per_request + 1e-9), 0)
return {allowed, capacity, remaining, to_ms(reset_after), to_ms(retry_after), to_ms(delay)}
