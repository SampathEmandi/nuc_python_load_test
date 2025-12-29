# NUC Python Load Testing Application

A Python-based load testing tool for testing chatbot WebSocket connections with concurrent sessions and sequential question-answer flows.

## Overview

This application performs load testing on the NUC chatbot API by:
- Creating multiple concurrent WebSocket sessions
- Sending questions sequentially (waiting for `complete_response` before sending the next question)
- Tracking latency and response metrics
- Logging all chunks and responses

## How It Works

### When You Run `main.py`

```
python main.py
```

### Execution Flow

1. **Initialization**
   - Loads configuration from `config.py` (URLs, credentials, questions)
   - Sets up logging with timestamps
   - Displays configuration summary

2. **Session Creation** (Concurrent)
   - Creates `NUM_SESSIONS` (default: 3) independent sessions
   - Each session runs in its own thread
   - Sessions run **concurrently** (in parallel)

3. **Per Session Setup**
   - **Generate Token**: Calls `generate_token()` API to get authentication token
   - **Create Chat**: Calls `create_chat()` API to get `session_id`
   - Establishes WebSocket connection to chatbot endpoint

4. **Question Sending** (Sequential per Session)
   - Each session sends questions **one at a time**
   - For each question:
     - Creates encrypted payload with question, course_id, session info
     - Sends via WebSocket
     - **Waits for `complete_response`** before sending next question
   - Questions are sent for all courses configured in `COURSES` (default: MED1060, BUMA1000)

5. **Response Handling**
   - Receives encrypted messages (chunks) from server
   - Decrypts each chunk
   - Logs chunk information (keys, latency)
   - Waits until `complete_response` field is received
   - Updates `session_attributes` for subsequent questions

6. **Completion**
   - Each session completes when all questions are sent and responses received
   - Main thread waits for all sessions to finish
   - Displays summary statistics

## Configuration

All configuration is centralized in `config.py`:

### Key Settings

- **`NUM_SESSIONS`**: Number of concurrent sessions (default: 3)
- **`COURSES`**: List of courses to test (default: ["MED1060", "BUMA1000"])
- **`COURSE_QUESTIONS`**: Maps each course to its question pool
- **API URLs**: All endpoints and WebSocket URLs
- **Credentials**: API keys and authentication tokens
- **Message Config**: Language, timezone, etc.

## Example Output

```
================================================================================
NUC Python Load Testing Application
================================================================================
================================================================================
STARTING LOAD TEST
================================================================================
Configuration:
  Sessions: 3
  Courses: MED1060, BUMA1000
  Questions per course:
    MED1060: 20 questions
    BUMA1000: 20 questions
  Total questions per session: 40
  Sending mode: Sequential (wait for response before next question)
================================================================================

Started 3 concurrent sessions

[2025-12-29 15:30:00.123] [Session-1] Starting session
[2025-12-29 15:30:00.125] [Session-2] Starting session
[2025-12-29 15:30:00.127] [Session-3] Starting session
[2025-12-29 15:30:01.234] [Session-1] Question 1/40 sent: How does understanding normal anatomy...
[2025-12-29 15:30:01.456] [Session-1] [CHUNK 1] Keys: ['response_chunk', 'message_id'] [Latency: 122.34ms]
[2025-12-29 15:30:02.789] [Session-1] [CHUNK 2] Keys: ['response_chunk', 'message_id'] [Latency: 1556.78ms]
[2025-12-29 15:30:03.123] [Session-1] [CHUNK 3] Keys: ['chat_user_id', 'complete_response', 'session_attributes'] [Latency: 2890.12ms]
[2025-12-29 15:30:03.124] [Session-1] ✓ complete_response received (chunk 3)! [Total Latency: 2890.12ms]
[2025-12-29 15:30:03.125] [Session-1] Question 2/40 sent: Why is it helpful to learn medical terms...
...
[2025-12-29 15:35:00.456] [Session-1] Session complete - Sent: 40, Received: 40
[2025-12-29 15:35:00.789] [Session-2] Session complete - Sent: 40, Received: 40
[2025-12-29 15:35:01.123] [Session-3] Session complete - Sent: 40, Received: 40

================================================================================
ALL SESSIONS COMPLETED
================================================================================
```

## Architecture

### Files Structure

- **`main.py`**: Entry point - runs the load test
- **`python_service_nuc.py`**: Core load testing logic with `SessionRunner` class
- **`node_services.py`**: API functions for token generation and chat creation
- **`encryption.py`**: Encryption/decryption utilities matching JavaScript implementation
- **`config.py`**: Centralized configuration (URLs, credentials, questions)
- **`test.py`**: Single message test script for debugging

### Key Classes

**`SessionRunner`**:
- Manages a single WebSocket session
- Handles question sending and response receiving
- Tracks metrics (sent/received counts, latency)
- Logs all chunks and responses

## Behavior Details

### Sequential Question Sending
- Questions are sent **one at a time** within each session
- Each question waits for `complete_response` before the next is sent
- This ensures proper conversation flow and avoids overwhelming the server

### Concurrent Sessions
- Multiple sessions run **in parallel** (different threads)
- Each session is independent with its own WebSocket connection
- This creates realistic load testing scenario

### Response Handling
- All incoming chunks are logged with keys and latency
- Only messages with `complete_response` are counted as complete responses
- `session_attributes` are maintained across questions in a session

## Dependencies

- `websocket-client`: WebSocket communication
- `requests`: HTTP API calls
- `pycryptodome` or `cryptography`: Encryption/decryption
- Standard library: `threading`, `json`, `uuid`, `logging`, `datetime`

## Usage

### Run Load Test
```bash
python main.py
```

### Run Single Message Test
```bash
python test.py
```

### Customize Configuration
Edit `config.py` to:
- Change number of sessions (`NUM_SESSIONS`)
- Modify courses (`COURSES`)
- Update question pools (`COURSE_QUESTIONS`)
- Change API URLs and credentials
- Adjust message configuration

## Logging

- All logs include timestamps with milliseconds
- Each session has its own logger (`Session-N`)
- Chunks are logged with keys and latency
- Complete responses show total latency
- Summary statistics at the end

## Notes

- The application waits indefinitely for `complete_response` (no timeout)
- All messages are encrypted/decrypted using the same scheme as the JavaScript client
- Session attributes are maintained across questions in the same session
- The WebSocket connection stays open for the entire session duration

