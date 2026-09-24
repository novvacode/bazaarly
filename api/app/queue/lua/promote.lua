-- Move up to ARGV[2] due members of the delayed zset onto the jobs stream.
-- KEYS[1] = delayed zset, KEYS[2] = jobs stream
-- ARGV[1] = now epoch ms, ARGV[2] = batch size, ARGV[3] = stream max length (approximate)
local due = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, tonumber(ARGV[2]))
for _, member in ipairs(due) do
  redis.call('XADD', KEYS[2], 'MAXLEN', '~', ARGV[3], '*', 'envelope', member)
  redis.call('ZREM', KEYS[1], member)
end
return #due
