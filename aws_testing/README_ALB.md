# ALB Connection Capacity Testing

This document explains how to properly test ALB (Application Load Balancer) connection capacity.

## The Problem with Quick Connection Tests

A standard connection test that:
- Opens a connection
- Immediately closes it (or closes after 0.1 seconds)

**Will NOT properly test ALB `ActiveConnectionCount`** because:
1. Connections close too quickly to register
2. ALB closes idle connections after 60 seconds (default)
3. No keep-alive means connections timeout

## Solution: Sustained Connection Test

The `test_alb_connection_capacity.py` script:
- ✅ Keeps connections open for a sustained period (default: 2 minutes)
- ✅ Sends periodic heartbeats (every 30 seconds) to prevent ALB idle timeout
- ✅ Uses async/await for true concurrency
- ✅ Properly tests ALB `ActiveConnectionCount` metric

## Usage

### Basic Usage

```bash
cd aws_testing
python test_alb_connection_capacity.py
```

### Custom Duration

```bash
# Keep connections open for 5 minutes
python test_alb_connection_capacity.py --duration 300

# Custom heartbeat interval (must be < ALB idle timeout)
python test_alb_connection_capacity.py --heartbeat 20
```

## How It Works

1. **Token Generation**: Generates tokens for all connections upfront
2. **Concurrent Connection**: Establishes all WebSocket connections simultaneously
3. **Keep-Alive**: Maintains connections with periodic heartbeats (every 30s)
4. **Sustained Test**: Keeps connections open for test duration (default: 2 minutes)
5. **Metrics**: Reports success rate, heartbeats, and connection duration

## Test Points

The script tests these connection counts:
- 50, 100, 200, 500, 1000, 2000, 5000

## ALB Configuration

### Check Your ALB Idle Timeout

```bash
aws elbv2 describe-load-balancer-attributes \
  --load-balancer-arn <your-alb-arn> \
  --query 'Attributes[?Key==`idle_timeout.timeout_seconds`]'
```

Default is **60 seconds**. Your heartbeat interval should be less than this.

### Monitor ALB Metrics

While the test runs, monitor in CloudWatch:
- `ActiveConnectionCount` - Should match your test connections
- `NewConnectionCount` - Should spike at test start
- `ProcessedBytes` - Should increase with heartbeats

## File Descriptor Limits

### Linux/Mac

```bash
# Check current limit
ulimit -n

# Increase limit (current session)
ulimit -n 65536

# Make permanent (add to ~/.bashrc)
echo "ulimit -n 65536" >> ~/.bashrc
```

### Windows

Windows doesn't have `ulimit`. Instead:
1. Check Task Manager → Performance → Open Handles
2. Increase via system settings if needed
3. The script will attempt to increase programmatically

### ECS Task Definition

Add to your task definition:
```json
"ulimits": [
  {
    "name": "nofile",
    "softLimit": 65536,
    "hardLimit": 65536
  }
]
```

## Expected Output

```
============================================================
Testing 500 sustained concurrent connections...
  Duration: 120 seconds
  Heartbeat interval: 30 seconds
============================================================
Generating tokens for all connections...
Generated 500/500 tokens in 15.23s
Establishing 500 concurrent connections...
Results: 495/500 successful (99.0%)
  Average heartbeats per connection: 4.0
  Test duration: 125.45s

============================================================
ALB CONNECTION CAPACITY TEST RESULTS
============================================================
[OK]    50 connections:    50/   50 successful (100.0%) | Avg heartbeats: 4.0 | Duration: 125.23s
[OK]   100 connections:    98/  100 successful ( 98.0%) | Avg heartbeats: 4.0 | Duration: 125.45s
[OK]   500 connections:   495/  500 successful ( 99.0%) | Avg heartbeats: 4.0 | Duration: 125.67s

[OK] Maximum reliable concurrent connections: ~500
  Recommendation: Use 400 as safe limit for ALB
  This should match ALB ActiveConnectionCount metric
```

## Comparison: Quick Test vs Sustained Test

| Aspect | Quick Test (0.1s) | Sustained Test (2min) |
|--------|------------------|----------------------|
| Tests ALB ActiveConnectionCount | ❌ No | ✅ Yes |
| Tests ALB idle timeout | ❌ No | ✅ Yes |
| Tests connection stability | ❌ No | ✅ Yes |
| Tests memory usage | ❌ No | ✅ Yes |
| Realistic load | ❌ No | ✅ Yes |

## Troubleshooting

### Connections Closing Prematurely

**Symptom**: Connections close before test duration ends

**Solutions**:
1. Check ALB idle timeout: `--heartbeat` should be < ALB timeout
2. Increase heartbeat frequency: `--heartbeat 20`
3. Check server-side connection limits

### Low Success Rate

**Possible causes**:
- File descriptor limit too low
- ALB connection limits reached
- Server-side throttling
- Network issues

**Solutions**:
1. Increase ulimit: `ulimit -n 65536`
2. Check ALB connection limits
3. Reduce test points (start smaller)
4. Check CloudWatch for ALB errors

### Timeout Errors

**Symptom**: `asyncio.TimeoutError` during test

**Solutions**:
1. Increase test duration: `--duration 300`
2. Check network latency
3. Verify ALB health checks are passing

## Best Practices

1. **Start Small**: Begin with 50-100 connections
2. **Monitor CloudWatch**: Watch ALB metrics during test
3. **Check ECS Resources**: Ensure CPU/memory not exhausted
4. **Verify Heartbeat**: Ensure connections stay alive
5. **Test Incrementally**: Increase gradually (50 → 100 → 200...)

## Integration with CloudWatch

The script outputs logs in a format suitable for CloudWatch ingestion. You can:

1. **Stream logs to CloudWatch**:
```bash
aws logs create-log-stream --log-group-name /aws/load-test --log-stream-name alb-test-$(date +%s)
```

2. **Create custom metrics** from the results

3. **Set up alarms** based on connection capacity

## Next Steps

After finding your maximum connection capacity:

1. **Update ECS Service**: Scale based on connection capacity
2. **Set Auto-Scaling**: Use connection count as metric
3. **Configure ALB**: Adjust idle timeout if needed
4. **Monitor**: Set up CloudWatch alarms

