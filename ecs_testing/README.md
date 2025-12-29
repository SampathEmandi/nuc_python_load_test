# ECS Connection Capacity Testing

This folder contains tools to test and determine the maximum number of concurrent WebSocket connections your ECS task can handle.

## Files

- **`check_ecs_environment.py`** - Check ECS task resource limits and configuration
- **`test_connection_capacity.py`** - Test maximum concurrent connections (progressive testing)
- **`test_aws_connection_capacity.py`** - AWS-optimized connection capacity test with CloudWatch-ready logging
- **`task-definition-template.json`** - ECS task definition template with recommended settings
- **`run_test.py`** - Simple test runner (Windows/Linux compatible)
- **`run_test.sh`** - Convenience script to run the full test suite (Linux/Mac)

## Quick Start

### 1. Check Your Environment

```bash
cd ecs_testing
python check_ecs_environment.py
```

This will show:
- ECS task metadata (if running in ECS)
- CPU and memory limits
- File descriptor limits
- Network configuration
- Recommendations

### 2. Test Connection Capacity

**Option A: Progressive Testing (Recommended)**
```bash
python test_connection_capacity.py
```
- Progressively test connection counts (10, 25, 50, 100, 200, 500, 1000...)
- Report success rates for each test
- Find the maximum reliable connection count
- Stop if success rate drops below 75%

**Option B: AWS-Optimized Testing**
```bash
python test_aws_connection_capacity.py
```
- AWS-friendly test points (10, 50, 100, 200, 500, 1000, 2000, 5000)
- CloudWatch-ready logging format
- 80% success threshold
- 60 second timeout per test

### 3. Run Full Test Suite

```bash
chmod +x run_test.sh
./run_test.sh
```

Or on Windows:
```bash
python check_ecs_environment.py
python test_connection_capacity.py
```

## Understanding Results

The test will output results like:

```
✓    10 sessions:    10 successful (100.0%) in 2.34s
✓    25 sessions:    25 successful (100.0%) in 3.45s
✓    50 sessions:    48 successful ( 96.0%) in 5.67s
✓   100 sessions:    95 successful ( 95.0%) in 8.90s
✓   200 sessions:   180 successful ( 90.0%) in 15.23s
✗   500 sessions:   350 successful ( 70.0%) in 45.67s

Maximum reliable connections: ~200
Recommendation: Use 160 as safe limit
```

**Interpretation:**
- ✓ = Success rate ≥ 75% (reliable)
- ✗ = Success rate < 75% (unreliable)
- Maximum reliable = Highest count with ≥75% success
- Safe limit = 80% of maximum (adds safety margin)

## ECS Task Definition Setup

### 1. Update Task Definition

Edit `task-definition-template.json`:
- Replace `YOUR_ECR_IMAGE_URI` with your actual image
- Update IAM role ARNs
- Adjust CPU/memory as needed
- Set `NUM_SESSIONS` environment variable

### 2. Register Task Definition

```bash
aws ecs register-task-definition --cli-input-json file://task-definition-template.json
```

### 3. Update Service

```bash
aws ecs update-service \
  --cluster your-cluster \
  --service your-service \
  --task-definition nuc-load-test
```

## Key Configuration

### File Descriptors (ulimits)

Critical for connection capacity! The template sets:
```json
"ulimits": [
  {
    "name": "nofile",
    "softLimit": 65536,
    "hardLimit": 65536
  }
]
```

### CPU and Memory

| CPU | Memory | Expected Connections |
|-----|--------|---------------------|
| 0.25 vCPU | 512 MB | 200-500 |
| 0.5 vCPU | 1 GB | 500-1,000 |
| 1 vCPU | 2 GB | 1,000-2,000 |
| 2 vCPU | 4 GB | 2,000-5,000 |

### Network Mode

- **awsvpc**: Each task gets its own ENI (better isolation)
- **bridge**: Shared network (better connection density)
- **host**: Uses host network (best performance, EC2 only)

## Monitoring During Tests

### CloudWatch Metrics

Monitor these metrics during load tests:
- `CPUUtilization` - Should stay below 80%
- `MemoryUtilization` - Should stay below 80%
- Custom metrics (if implemented)

### View Logs

```bash
aws logs tail /ecs/nuc-load-test --follow
```

## Troubleshooting

### "Too many open files" Error

**Solution:** Increase ulimits in task definition (see above)

### Connection Timeouts

**Possible causes:**
- Server-side limits reached
- Network bandwidth exhausted
- Task CPU/memory limits

**Solution:** Reduce `NUM_SESSIONS` or increase task resources

### Low Success Rates

**Possible causes:**
- File descriptor limit too low
- Insufficient CPU/memory
- Network issues
- Server-side throttling

**Solution:** 
1. Check `check_ecs_environment.py` output
2. Increase task resources
3. Test with smaller increments

## Scaling Strategy

Once you know your connection capacity per task:

```python
# Example: Each task handles 2000 connections
target_connections = 10000
connections_per_task = 2000

tasks_needed = (target_connections / connections_per_task) * 1.2  # 20% buffer
# = 6 tasks
```

Update your ECS service:
```bash
aws ecs update-service \
  --cluster your-cluster \
  --service your-service \
  --desired-count 6
```

## Best Practices

1. **Start Small**: Begin with 100 sessions, increase gradually
2. **Monitor Resources**: Watch CloudWatch during tests
3. **Use Safety Margin**: Use 80% of max capacity as safe limit
4. **Test Regularly**: Re-test when changing task resources
5. **Auto-scaling**: Set up auto-scaling based on connection metrics

## Dependencies

Make sure these are installed:
- `asyncio` (Python 3.7+)
- `websockets` (pip install websockets)
- `aiohttp` (pip install aiohttp)
- `psutil` (optional, for detailed system info: pip install psutil)

## Notes

- Tests only establish connections, don't send questions
- Each test pauses 3 seconds between runs
- Timeout is 90 seconds per test (adjustable in code)
- Success threshold is 75% (adjustable in code)

