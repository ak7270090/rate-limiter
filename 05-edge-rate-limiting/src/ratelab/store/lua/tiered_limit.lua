-- Several limits checked together; tokens are taken from every tier only if every tier allows.
-- KEYS[i]: tier i's key. ARGV[1]: cost. Then four values per tier:
--   ARGV[2 + 4(i-1)] algorithm (gcra | fixed_window | sliding_window_counter),
--   then limit, window_seconds, capacity.
-- Returns {allowed, rejecting tier (1-based, 0 if none), retry_ms,
--          then per tier: limit, remaining, reset_ms}.
local cost = tonumber(ARGV[1])
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local function to_ms(seconds) return math.max(math.ceil(seconds * 1000), 0) end

local function evaluate_gcra(key, limit, window, capacity)
  local interval = window / limit
  local tolerance = interval * capacity
  local arrival = tonumber(redis.call('GET', key))
  if not arrival or arrival < now then arrival = now end
  local charged_arrival = arrival + interval * cost
  local allow_at = charged_arrival - tolerance
  return {
    allowed = allow_at <= now + 1e-9,
    limit = capacity,
    remaining = math.floor((tolerance - (arrival - now)) / interval + 1e-9),
    remaining_charged = math.floor((tolerance - (charged_arrival - now)) / interval + 1e-9),
    reset = arrival - now,
    reset_charged = charged_arrival - now,
    retry = allow_at - now,
    commit = function()
      redis.call('SET', key, string.format('%.6f', charged_arrival), 'PX', math.max(to_ms(charged_arrival - now), 1))
    end,
  }
end

local function evaluate_fixed_window(key, limit, window)
  local window_start = math.floor(now / window) * window
  local state = redis.call('HMGET', key, 'w', 'c')
  local count = 0
  if tonumber(state[1]) == window_start then count = tonumber(state[2]) end
  local reset = window_start + window - now
  return {
    allowed = count + cost <= limit,
    limit = limit,
    remaining = limit - count,
    remaining_charged = limit - count - cost,
    reset = reset,
    reset_charged = reset,
    retry = reset,
    commit = function()
      redis.call('HSET', key, 'w', window_start, 'c', count + cost)
      redis.call('PEXPIRE', key, math.max(to_ms(reset), 1))
    end,
  }
end

local function evaluate_sliding_window_counter(key, limit, window)
  local window_start = math.floor(now / window) * window
  local state = redis.call('HMGET', key, 'w', 'cur', 'prev')
  local stored_start = tonumber(state[1])
  local current, previous = 0, 0
  if stored_start == window_start then
    current, previous = tonumber(state[2]), tonumber(state[3])
  elseif stored_start == window_start - window then
    previous = tonumber(state[2])
  end
  local estimate = previous * (1 - (now - window_start) / window) + current
  local retry = 0
  if estimate + cost > limit + 1e-9 then
    local room_without_previous = limit - current - cost
    if room_without_previous >= 0 then
      retry = window_start + (1 - room_without_previous / previous) * window - now
    else
      retry = window_start + window + (1 - (limit - cost) / current) * window - now
    end
  end
  local reset_at = window_start
  if current > 0 then
    reset_at = window_start + 2 * window
  elseif previous > 0 then
    reset_at = window_start + window
  end
  return {
    allowed = estimate + cost <= limit + 1e-9,
    limit = limit,
    remaining = math.floor(limit - estimate + 1e-9),
    remaining_charged = math.floor(limit - estimate - cost + 1e-9),
    reset = reset_at - now,
    reset_charged = window_start + 2 * window - now,
    retry = retry,
    commit = function()
      redis.call('HSET', key, 'w', window_start, 'cur', current + cost, 'prev', previous)
      redis.call('PEXPIRE', key, to_ms(window_start + 2 * window - now))
    end,
  }
end

local evaluators = {
  gcra = evaluate_gcra,
  fixed_window = evaluate_fixed_window,
  sliding_window_counter = evaluate_sliding_window_counter,
}

local tiers = {}
local all_allowed = true
local rejecting_tier = 0
local retry = 0
for index, key in ipairs(KEYS) do
  local base = 2 + (index - 1) * 4
  local evaluate = evaluators[ARGV[base]]
  if not evaluate then return redis.error_reply('unknown algorithm ' .. ARGV[base]) end
  local result = evaluate(key, tonumber(ARGV[base + 1]), tonumber(ARGV[base + 2]), tonumber(ARGV[base + 3]))
  tiers[index] = result
  if not result.allowed then
    all_allowed = false
    if rejecting_tier == 0 then rejecting_tier = index end
    retry = math.max(retry, result.retry)
  end
end

local reply = {all_allowed and 1 or 0, rejecting_tier, to_ms(retry)}
for _, result in ipairs(tiers) do
  local remaining, reset = result.remaining, result.reset
  if all_allowed then
    result.commit()
    remaining, reset = result.remaining_charged, result.reset_charged
  end
  table.insert(reply, result.limit)
  table.insert(reply, math.max(remaining, 0))
  table.insert(reply, to_ms(math.max(reset, 0)))
end
return reply
