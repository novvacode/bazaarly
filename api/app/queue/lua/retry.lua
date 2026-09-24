-- Schedule a retry and acknowledge the failed delivery atomically.
-- KEYS[1] = delayed zset, KEYS[2] = jobs stream
-- ARGV[1] = run-at epoch ms, ARGV[2] = envelope JSON (attempt already incremented),
-- ARGV[3] = consumer group, ARGV[4] = stream entry id
redis.call('ZADD', KEYS[1], ARGV[1], ARGV[2])
return redis.call('XACK', KEYS[2], ARGV[3], ARGV[4])
