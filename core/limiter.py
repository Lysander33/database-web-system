import time
from flask import current_app
from core.redis_client import get_redis

_LUA_SLIDING_WINDOW = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local max_req = tonumber(ARGV[3])

redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count < max_req then
    redis.call('ZADD', key, now, now .. ':' .. count)
    redis.call('EXPIRE', key, math.ceil(window * 2))
    return {1, max_req - count - 1}
end
redis.call('EXPIRE', key, math.ceil(window * 2))
return {0, 0}
"""


def check_rate_limit(user_id, max_requests=None, window=None):
    try:
        r = get_redis()
    except RuntimeError:
        return True, 0
    max_req = max_requests or current_app.config["RATE_LIMIT_MAX"]
    win = window or current_app.config["RATE_LIMIT_WINDOW"]
    key = f"rate_limit:{user_id}"
    now = time.time()
    allowed, remaining = r.eval(_LUA_SLIDING_WINDOW, 1, key, now, win, max_req)
    return bool(allowed), remaining
