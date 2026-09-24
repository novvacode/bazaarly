-- Dead-letter a job and acknowledge the delivery atomically.
-- KEYS[1] = dead stream, KEYS[2] = jobs stream
-- ARGV[1] = envelope JSON, ARGV[2] = error type, ARGV[3] = error message,
-- ARGV[4] = traceback (truncated), ARGV[5] = failed_at ISO, ARGV[6] = group, ARGV[7] = entry id
redis.call('XADD', KEYS[1], '*',
  'envelope', ARGV[1], 'error_type', ARGV[2], 'error', ARGV[3],
  'traceback', ARGV[4], 'failed_at', ARGV[5])
return redis.call('XACK', KEYS[2], ARGV[6], ARGV[7])
