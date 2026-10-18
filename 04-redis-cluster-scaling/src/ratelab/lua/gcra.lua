-- GCRA. KEYS[1]: theoretical arrival time (TAT) of the next request.
-- Each request moves TAT forward by window / limit; allowed while TAT stays within
-- capacity intervals of now.
-- ARGV: limit, window_seconds, cost, capacity.
-- Returns {allowed, capacity, remaining, reset_ms, retry_ms, delay_ms}.
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local capacity = tonumber(ARGV[4])

local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local function to_ms(seconds) return math.max(math.ceil(seconds * 1000), 0) end

local emission_interval = window / limit
local burst_tolerance = emission_interval * capacity
local theoretical_arrival = tonumber(redis.call('GET', KEYS[1]))
if not theoretical_arrival or theoretical_arrival < now then theoretical_arrival = now end

local new_theoretical_arrival = theoretical_arrival + emission_interval * cost
local allow_at = new_theoretical_arrival - burst_tolerance
local allowed = 0
local retry_after = 0
local stored_arrival = theoretical_arrival
if allow_at <= now + 1e-9 then
  allowed = 1
  stored_arrival = new_theoretical_arrival
  local reset_after = stored_arrival - now
  redis.call('SET', KEYS[1], string.format('%.6f', stored_arrival), 'PX', math.max(to_ms(reset_after), 1))
else
  retry_after = allow_at - now
end

local reset_after = stored_arrival - now
local remaining = math.floor((burst_tolerance - reset_after) / emission_interval + 1e-9)
return {allowed, capacity, math.max(remaining, 0), to_ms(reset_after), to_ms(retry_after), 0}
