# AWS Connection Capacity Testing

This folder contains AWS-optimized connection capacity testing tools.

## Files

- **`test_aws_connection_capacity.py`** - AWS-optimized connection capacity test with CloudWatch-ready logging

## Quick Start

```bash
cd aws_testing
python test_aws_connection_capacity.py
```

## Test Configuration

### Test Points
The test uses AWS-friendly increments:
- 10, 50, 100, 200, 500, 1000, 2000, 5000 connections

### Test Behavior
- **Success Threshold**: 80% (stops if below)
- **Timeout**: 60 seconds per test
- **Pause**: 2 seconds between tests
- **Logging**: CloudWatch-ready format

## What It Does

1. Progressively tests connection counts using the specified test points
2. For each test point:
   - Creates `AsyncSessionRunner` instances
   - Generates tokens and creates chats
   - Establishes WebSocket connections
   - Measures success rate and timing
3. Reports results for each test point
4. Finds maximum reliable connection count (≥80% success)

## Output Example

```
============================================================
Testing 10 concurrent connections...
============================================================
Results: 10/10 successful (100.0%) in 2.34s

============================================================
Testing 50 concurrent connections...
============================================================
Results: 48/50 successful (96.0%) in 5.67s

============================================================
CONNECTION CAPACITY TEST RESULTS
============================================================
   10 sessions:    10 successful (100.0%) in 2.34s
   50 sessions:    48 successful ( 96.0%) in 5.67s
  100 sessions:    95 successful ( 95.0%) in 8.90s
  200 sessions:   180 successful ( 90.0%) in 15.23s
  500 sessions:   400 successful ( 80.0%) in 35.67s

Maximum reliable connections: ~500
```

## Differences from ECS Testing

| Feature | AWS Testing | ECS Testing |
|---------|-------------|-------------|
| Test Points | 10, 50, 100, 200, 500, 1000, 2000, 5000 | 10, 25, 50, 100, 200, 500, 1000... |
| Success Threshold | 80% | 75% |
| Timeout | 60 seconds | 90 seconds |
| Focus | AWS infrastructure | ECS-specific resources |
| Logging | CloudWatch-ready | Standard logging |

## Use Cases

- **AWS EC2 Instances**: Test connection capacity on EC2
- **AWS Lambda**: Not suitable (Lambda has connection limits)
- **General AWS Services**: Test against any AWS-hosted WebSocket service
- **CloudWatch Integration**: Logs are formatted for CloudWatch ingestion

## Requirements

- Python 3.7+
- `asyncio`
- `websockets` library
- `aiohttp` library
- Access to parent directory modules (`python_service_nuc_async`, `config`, etc.)

## Notes

- Tests only establish connections, don't send questions
- Each test pauses 2 seconds between runs
- Timeout is 60 seconds per test
- Success threshold is 80% (adjustable in code)
- Automatically tries to increase file descriptor limit if possible

