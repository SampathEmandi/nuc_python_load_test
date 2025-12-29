import json
import uuid
import asyncio
import websockets
import time
import logging
from datetime import datetime, timezone
from typing import Optional

from node_services_async import generate_token, create_chat
from config import (
    COURSE_QUESTIONS, NUM_SESSIONS, COURSES, WEBSOCKET_URL_TEMPLATE, 
    WEBSOCKET_ORIGIN, MESSAGE_CONFIG, RAMP_START_SESSIONS, RAMP_MAX_SESSIONS,
    RAMP_INCREMENT, RAMP_INTERVAL_SECONDS
)
from encryption import encrypt, decrypt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s.%(msecs)03d] [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Global counters for concurrent invocation tracking
_concurrent_invocations = 0
_concurrent_lock = asyncio.Lock()
_peak_concurrent = 0
_total_invocations_started = 0
_total_invocations_completed = 0
_monitoring_task = None
# Error tracking
_502_errors = 0
_connection_errors = 0
_setup_failures = 0


class AsyncSessionRunner:
    def __init__(self, session_index):
        self.session_index = session_index
        self.token = None
        self.client_code = None
        self.session_id = None
        self.connection_id = None
        self.session_attributes = None
        self.chat_info = None
        self.ws = None
        self.pending_questions = []
        self.questions_sent_count = 0
        self.responses_received_count = 0
        self.current_question_index = 0
        self.all_questions_sent = False
        self.all_chunks = []
        self.question_sent_time = None
        self.response_received_time = None
        self.waiting_for_response = False
        self.connection_error_type = None
        # Create a logger for this session
        self.logger = logging.getLogger(f"Session-{self.session_index}")

    def log(self, *args):
        """Log a message for this session."""
        message = ' '.join(str(arg) for arg in args)
        self.logger.info(message)

    async def setup(self):
        """Setup session: generate token and create chat."""
        try:
            # 1. Generate token
            token_data = await generate_token()
            if not token_data or not token_data.get('token'):
                self.log("ERROR: Failed to generate token")
                return False
            self.token = token_data['token']
            self.client_code = token_data.get('client_code')
            self.connection_id = token_data.get('connection_id')
            self.session_id = token_data.get('session_id')
            
            # If session_id not in token response, try create_chat
            if not self.session_id:
                self.chat_info = await create_chat(self.token)
                if self.chat_info and self.chat_info.get('session_id'):
                    self.session_id = self.chat_info['session_id']
                else:
                    self.log("ERROR: Failed to get session_id")
                    return False
            
            return True
        except Exception as e:
            global _setup_failures, _concurrent_lock
            self.log(f"ERROR in setup: {e}")
            async with _concurrent_lock:
                _setup_failures += 1
            return False

    async def send_next_question(self, ws):
        """Send the next question and wait for response."""
        # Check if all questions have been sent
        if self.current_question_index >= len(self.pending_questions):
            self.all_questions_sent = True
            if self.questions_sent_count == self.responses_received_count:
                self.log(f"All {self.questions_sent_count} questions sent and responses received. Closing connection.")
                await ws.close()
            return
        
        # Get the next question
        course_id, question = self.pending_questions[self.current_question_index]
        self.current_question_index += 1
        
        try:
            # Create payload matching test.py format
            payload = {
                "session_id": self.session_id,
                "connection_id": self.connection_id,
                "request_id": str(uuid.uuid4()),
                "client_code": self.client_code,
                "request_to_generate_greeting_message": MESSAGE_CONFIG["request_to_generate_greeting_message"],
                "language_code": MESSAGE_CONFIG["language_code"],
                "user_message": question,
                "session_attributes": self.session_attributes if self.session_attributes is not None else {},
                "user_message_date_and_time": datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                "user_timezone": MESSAGE_CONFIG["user_timezone"],
                "conversation_id": str(uuid.uuid4()),
                "course_id": course_id
            }
            
            # Encrypt and send
            self.question_sent_time = time.time()  # Record send time
            await ws.send(encrypt(json.dumps(payload)))
            
            # Increment concurrent invocations counter
            global _concurrent_invocations, _peak_concurrent, _total_invocations_started, _concurrent_lock
            async with _concurrent_lock:
                _concurrent_invocations += 1
                _total_invocations_started += 1
                if _concurrent_invocations > _peak_concurrent:
                    _peak_concurrent = _concurrent_invocations
            
            self.questions_sent_count += 1
            self.all_chunks = []  # Clear chunks for new question
            self.response_received_time = None  # Reset response time
            self.waiting_for_response = True  # Mark that we're waiting
            send_time_str = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            
            # Enhanced session-wise question logging
            self.log("")
            self.log("=" * 80)
            self.log(f"▶ SESSION {self.session_index} - SENDING QUESTION")
            self.log(f"  Question {self.questions_sent_count}/{len(self.pending_questions)} | {send_time_str}")
            self.log(f"  Active Invocations: {_concurrent_invocations}")
            self.log(f"  Question: {question[:120]}...")
            self.log(f"  Course: {course_id}")
            self.log("=" * 80)
            self.log("")
        except websockets.exceptions.ConnectionClosed:
            self.log("Connection closed while sending question")
        except Exception as e:
            self.log(f"Send failed: {e}")
            # Continue to next question even if send failed (if connection still open)
            if not ws.closed:
                await self.send_next_question(ws)

    async def handle_message(self, message):
        """Handle incoming WebSocket message."""
        try:
            decrypted = decrypt(message)
            if not decrypted:
                self.log("[CHUNK] Received empty decrypted message")
                return
            
            # Store all chunks
            chunk_received_time = time.time()
            self.all_chunks.append(decrypted)
            
            # Calculate latency from question sent to this chunk
            chunk_latency = None
            if self.question_sent_time:
                chunk_latency = (chunk_received_time - self.question_sent_time) * 1000  # Convert to milliseconds
            
            # Log chunk info with latency (simplified)
            latency_str = f" [Latency: {chunk_latency:.2f}ms]" if chunk_latency else ""
            
            try:
                data = json.loads(decrypted)
                keys = list(data.keys())
                
                # Update session_attributes if present
                if 'session_attributes' in data:
                    self.session_attributes = data['session_attributes']
                
                # Check for complete_response - THIS IS WHAT WE WAIT FOR
                if 'complete_response' in data:
                    self.response_received_time = time.time()
                    self.responses_received_count += 1
                    
                    # Decrement concurrent invocations counter
                    global _concurrent_invocations, _total_invocations_completed
                    async with _concurrent_lock:
                        if self.waiting_for_response:
                            _concurrent_invocations -= 1
                            _total_invocations_completed += 1
                            self.waiting_for_response = False
                    
                    # Calculate total latency
                    total_latency = None
                    if self.question_sent_time and self.response_received_time:
                        total_latency = (self.response_received_time - self.question_sent_time) * 1000  # Convert to milliseconds
                    
                    latency_info = f" [Latency: {total_latency:.2f}ms]" if total_latency else ""
                    response_time_str = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                    
                    # Enhanced session-wise response logging
                    self.log("")
                    self.log("─" * 80)
                    self.log(f"✓ SESSION {self.session_index} - RESPONSE RECEIVED")
                    self.log(f"  Question {self.responses_received_count}/{self.questions_sent_count} | {response_time_str}{latency_info}")
                    self.log(f"  Active Invocations: {_concurrent_invocations} | Chunks: {len(self.all_chunks)}")
                    self.log(f"  Response Preview: {data['complete_response'][:150]}...")
                    self.log("─" * 80)
                    self.log("")
                    
                    # Send next question after receiving response
                    if not self.all_questions_sent:
                        await self.send_next_question(self.ws)
            except json.JSONDecodeError as e:
                self.log(f"[CHUNK {len(self.all_chunks)}] Not JSON: {decrypted[:200]}...")
            except Exception as e:
                self.log(f"[CHUNK {len(self.all_chunks)}] Error processing: {e}")
        except Exception as e:
            self.log(f"[CHUNK] Decryption error: {e}")

    async def start(self):
        """
        Open WebSocket and send all questions sequentially, then wait for responses.
        Returns statistics dictionary.
        """
        global _concurrent_invocations, _concurrent_lock, _502_errors, _connection_errors, _peak_concurrent, _total_invocations_started, _total_invocations_completed
        self.log("")
        self.log("=" * 80)
        self.log(f"🚀 STARTING SESSION {self.session_index}")
        self.log("=" * 80)
        ws_url = f"{WEBSOCKET_URL_TEMPLATE}?token={self.token}"

        # Build list of (course_id, question) using ALL questions from config
        for course_id in COURSES:
            question_pool = COURSE_QUESTIONS.get(course_id, [])
            # Use ALL questions from the pool for this session
            for question in question_pool:
                self.pending_questions.append((course_id, question))
        
        self.log(f"  Total Questions Prepared: {len(self.pending_questions)}")
        for course_id in COURSES:
            question_count = len(COURSE_QUESTIONS.get(course_id, []))
            self.log(f"    - {course_id}: {question_count} questions")
        self.log("=" * 80)
        self.log("")

        try:
            # Connect to WebSocket with origin header
            async with websockets.connect(
                ws_url,
                origin=WEBSOCKET_ORIGIN
            ) as ws:
                self.ws = ws
                self.log(f"✅ SESSION {self.session_index} - WebSocket connected successfully")
                self.log(f"   Starting to send questions sequentially...")
                self.log("")
                
                # Send the first question
                await self.send_next_question(ws)
                
                # Listen for messages until connection closes
                try:
                    async for message in ws:
                        await self.handle_message(message)
                        # Check if we should close after processing message
                        if self.all_questions_sent and self.questions_sent_count == self.responses_received_count:
                            break
                except websockets.exceptions.ConnectionClosed as e:
                    self.log(f"❌ SESSION {self.session_index} - Connection Closed by Server")
                    self.log(f"   Reason: {e.reason if hasattr(e, 'reason') else 'Unknown'}")
                    self.log(f"   Code: {e.code if hasattr(e, 'code') else 'N/A'}")
                    self.connection_error_type = 'Connection_Closed_By_Server'
                    # Clean up pending invocation on connection close
                    if self.waiting_for_response:
                        async with _concurrent_lock:
                            _concurrent_invocations -= 1
                            self.waiting_for_response = False
                    
        except websockets.exceptions.InvalidHandshake as e:
            # Track 502 and other HTTP errors specifically
            error_str = str(e)
            if '502' in error_str or 'Bad Gateway' in error_str:
                async with _concurrent_lock:
                    _502_errors += 1
                self.log(f"❌ SESSION {self.session_index} - 502 Bad Gateway Error (Handshake)")
                self.log(f"   Error: {e}")
                self.log(f"   Reason: Server overloaded or unavailable - cannot handle new connections")
                self.connection_error_type = '502_Bad_Gateway'
            elif '503' in error_str or 'Service Unavailable' in error_str:
                async with _concurrent_lock:
                    _connection_errors += 1
                self.log(f"❌ SESSION {self.session_index} - 503 Service Unavailable (Handshake)")
                self.log(f"   Error: {e}")
                self.log(f"   Reason: Service temporarily unavailable")
                self.connection_error_type = '503_Service_Unavailable'
            elif '504' in error_str or 'Gateway Timeout' in error_str:
                async with _concurrent_lock:
                    _connection_errors += 1
                self.log(f"❌ SESSION {self.session_index} - 504 Gateway Timeout (Handshake)")
                self.log(f"   Error: {e}")
                self.log(f"   Reason: Gateway timeout during connection handshake")
                self.connection_error_type = '504_Gateway_Timeout'
            else:
                async with _concurrent_lock:
                    _connection_errors += 1
                self.log(f"❌ SESSION {self.session_index} - WebSocket Handshake Error")
                self.log(f"   Error: {e}")
                self.log(f"   Reason: Invalid handshake response from server")
                self.connection_error_type = 'Handshake_Error'
            # Clean up pending invocation on error
            if self.waiting_for_response:
                async with _concurrent_lock:
                    _concurrent_invocations -= 1
                    self.waiting_for_response = False
        except websockets.exceptions.ConnectionClosed as e:
            self.log(f"❌ SESSION {self.session_index} - WebSocket Connection Closed")
            self.log(f"   Reason: {e.reason if hasattr(e, 'reason') else 'Unknown'}")
            self.log(f"   Code: {e.code if hasattr(e, 'code') else 'N/A'}")
            self.connection_error_type = 'Connection_Closed'
            # Clean up pending invocation on connection close
            if self.waiting_for_response:
                async with _concurrent_lock:
                    _concurrent_invocations -= 1
                    self.waiting_for_response = False
        except asyncio.TimeoutError as e:
            # Handle asyncio timeout errors
            async with _concurrent_lock:
                _connection_errors += 1
            self.log(f"❌ SESSION {self.session_index} - Connection Timeout Error")
            self.log(f"   Error: {e}")
            self.log(f"   Reason: WebSocket connection timed out during handshake")
            self.connection_error_type = 'Connection_Timeout'
            # Clean up pending invocation on error
            if self.waiting_for_response:
                async with _concurrent_lock:
                    _concurrent_invocations -= 1
                    self.waiting_for_response = False
        except Exception as e:
            error_str = str(e)
            if '502' in error_str or 'Bad Gateway' in error_str:
                async with _concurrent_lock:
                    _502_errors += 1
                self.log(f"❌ SESSION {self.session_index} - 502 Bad Gateway Error")
                self.log(f"   Error: {e}")
                self.log(f"   Reason: Server overloaded or unavailable")
                self.connection_error_type = '502_Bad_Gateway'
            elif '503' in error_str or 'Service Unavailable' in error_str:
                async with _concurrent_lock:
                    _connection_errors += 1
                self.log(f"❌ SESSION {self.session_index} - 503 Service Unavailable")
                self.log(f"   Error: {e}")
                self.connection_error_type = '503_Service_Unavailable'
            elif '504' in error_str or 'Gateway Timeout' in error_str:
                async with _concurrent_lock:
                    _connection_errors += 1
                self.log(f"❌ SESSION {self.session_index} - 504 Gateway Timeout")
                self.log(f"   Error: {e}")
                self.connection_error_type = '504_Gateway_Timeout'
            elif 'timeout' in error_str.lower() or 'timed out' in error_str.lower():
                async with _concurrent_lock:
                    _connection_errors += 1
                self.log(f"❌ SESSION {self.session_index} - Connection Timeout Error")
                self.log(f"   Error: {e}")
                self.log(f"   Reason: Operation timed out - server may be slow or overloaded")
                self.connection_error_type = 'Connection_Timeout'
            elif 'connection' in error_str.lower() and 'refused' in error_str.lower():
                async with _concurrent_lock:
                    _connection_errors += 1
                self.log(f"❌ SESSION {self.session_index} - Connection Refused Error")
                self.log(f"   Error: {e}")
                self.log(f"   Reason: Server refused the connection")
                self.connection_error_type = 'Connection_Refused'
            elif 'ssl' in error_str.lower() or 'certificate' in error_str.lower():
                async with _concurrent_lock:
                    _connection_errors += 1
                self.log(f"❌ SESSION {self.session_index} - SSL/TLS Error")
                self.log(f"   Error: {e}")
                self.connection_error_type = 'SSL_Error'
            else:
                async with _concurrent_lock:
                    _connection_errors += 1
                self.log(f"❌ SESSION {self.session_index} - WebSocket Error")
                self.log(f"   Error Type: {type(e).__name__}")
                self.log(f"   Error Message: {e}")
                self.connection_error_type = 'Unknown_Error'
            # Clean up pending invocation on error
            if self.waiting_for_response:
                async with _concurrent_lock:
                    _concurrent_invocations -= 1
                    self.waiting_for_response = False
        finally:
            # Final cleanup check - handle any remaining pending invocations
            # We need to use asyncio.create_task or await in an async context
            # But since this is finally, we'll ensure cleanup happened in exception handlers above
            self.log("")
            self.log("=" * 80)
            self.log(f"🏁 SESSION {self.session_index} - COMPLETED")
            self.log(f"  Questions Sent: {self.questions_sent_count}")
            self.log(f"  Responses Received: {self.responses_received_count}")
            
            # Determine session status
            if self.questions_sent_count == 0:
                # No questions sent - connection likely failed before sending
                self.log(f"  ❌ Status: Failed to establish connection or send questions")
                if self.connection_error_type:
                    self.log(f"  Error Type: {self.connection_error_type}")
                success_rate = 0.0
            elif self.questions_sent_count > self.responses_received_count:
                missing = self.questions_sent_count - self.responses_received_count
                self.log(f"  ⚠️  WARNING: {missing} response(s) not received")
                success_rate = (self.responses_received_count / self.questions_sent_count * 100) if self.questions_sent_count > 0 else 0
            elif self.questions_sent_count == self.responses_received_count and self.questions_sent_count > 0:
                self.log(f"  ✅ All questions received responses successfully!")
                success_rate = 100.0
            else:
                success_rate = 0.0
            
            self.log(f"  Success Rate: {success_rate:.1f}%")
            if self.connection_error_type:
                self.log(f"  Connection Error: {self.connection_error_type}")
            self.log("=" * 80)
            self.log("")
            
            # Return statistics
            return {
                'session_index': self.session_index,
                'questions_sent': self.questions_sent_count,
                'responses_received': self.responses_received_count,
                'successful': self.responses_received_count == self.questions_sent_count and self.questions_sent_count > 0,
                'setup_successful': self.session_id is not None,
                'connection_error_type': getattr(self, 'connection_error_type', None)
            }


async def run_session(index):
    """Run a single session asynchronously. Returns statistics dictionary."""
    runner = AsyncSessionRunner(index)
    if await runner.setup():
        stats = await runner.start()
        return stats
    else:
        logger.error(f"Session {index} setup failed")
        return {
            'session_index': index,
            'questions_sent': 0,
            'responses_received': 0,
            'successful': False,
            'setup_successful': False,
            'connection_error_type': 'Setup_Failed'
        }


async def monitor_concurrent_invocations(interval=5):
    """
    Background task to periodically report concurrent invocations.
    
    Args:
        interval: How often to report (in seconds)
    """
    global _concurrent_invocations, _total_invocations_started, _total_invocations_completed
    start_time = time.time()
    
    while True:
        await asyncio.sleep(interval)
        async with _concurrent_lock:
            current = _concurrent_invocations
            started = _total_invocations_started
            completed = _total_invocations_completed
            peak = _peak_concurrent
        
        elapsed = time.time() - start_time
        logger.info("")
        logger.info("─" * 80)
        logger.info(f"[REAL-TIME MONITOR] Elapsed: {elapsed:.1f}s | "
                   f"Active Invocations: {current} | "
                   f"Peak Concurrent: {peak} | "
                   f"Started: {started} | "
                   f"Completed: {completed}")
        logger.info("─" * 80)


def create_session_tasks(num_sessions: int, start_session_index: int = 1):
    """
    Create tasks for sessions without awaiting them (for progressive ramp-up).
    
    Args:
        num_sessions: Number of sessions to create
        start_session_index: Starting index for session numbering
    
    Returns:
        List of task futures
    """
    logger.info(f"Creating {num_sessions} session tasks (starting from index {start_session_index})")
    tasks = [asyncio.create_task(run_session(start_session_index + i)) for i in range(num_sessions)]
    return tasks


async def run_load_test(num_sessions: int = NUM_SESSIONS):
    """
    Run the load test with multiple concurrent sessions using async I/O.
    
    Behavior:
    - All sessions run CONCURRENTLY using asyncio tasks
    - Questions within each session are sent SEQUENTIALLY (wait for response before next)
    - Each session will ask ALL questions from the question pools
    
    Args:
        num_sessions: Number of concurrent sessions to run
    
    Returns:
        Dictionary with aggregated statistics
    """
    global _concurrent_invocations, _peak_concurrent, _total_invocations_started, _total_invocations_completed, _monitoring_task
    
    # Reset global counters
    async with _concurrent_lock:
        _concurrent_invocations = 0
        _peak_concurrent = 0
        _total_invocations_started = 0
        _total_invocations_completed = 0
    
    # Calculate total questions per session
    total_questions_per_session = sum(len(COURSE_QUESTIONS.get(course_id, [])) for course_id in COURSES)
    
    logger.info("")
    logger.info("="*80)
    logger.info("STARTING LOAD TEST (ASYNC)")
    logger.info("="*80)
    logger.info("Configuration:")
    logger.info(f"  Sessions: {num_sessions}")
    logger.info(f"  Courses: {', '.join(COURSES)}")
    logger.info(f"  Questions per course:")
    for course_id in COURSES:
        question_count = len(COURSE_QUESTIONS.get(course_id, []))
        logger.info(f"    {course_id}: {question_count} questions")
    logger.info(f"  Total questions per session: {total_questions_per_session}")
    logger.info(f"  Sending mode: Sequential (wait for response before next question)")
    logger.info(f"  Concurrency model: Async I/O (asyncio)")
    logger.info(f"  Real-time monitoring: Enabled (every 5 seconds)")
    logger.info("="*80)
    logger.info("")
    
    # Start monitoring task
    _monitoring_task = asyncio.create_task(monitor_concurrent_invocations(interval=5))
    
    # Create tasks for all sessions
    tasks = [run_session(i + 1) for i in range(num_sessions)]
    
    logger.info(f"Started {num_sessions} concurrent sessions")
    logger.info("Monitoring concurrent invocations in real-time...")
    logger.info("")
    
    try:
        # Run all sessions concurrently and collect statistics
        results = await asyncio.gather(*tasks)
    finally:
        # Cancel monitoring task
        if _monitoring_task:
            _monitoring_task.cancel()
            try:
                await _monitoring_task
            except asyncio.CancelledError:
                pass
    
    # Final concurrent count and error statistics
    async with _concurrent_lock:
        final_concurrent = _concurrent_invocations
        peak_concurrent = _peak_concurrent
        total_502_errors = _502_errors
        total_connection_errors = _connection_errors
        total_setup_failures = _setup_failures
    
    logger.info("")
    logger.info("="*80)
    logger.info("ALL SESSIONS COMPLETED")
    logger.info("="*80)
    
    # Aggregate statistics
    total_questions_sent = sum(r['questions_sent'] for r in results)
    total_responses_received = sum(r['responses_received'] for r in results)
    successful_sessions = sum(1 for r in results if r['successful'])
    setup_successful_sessions = sum(1 for r in results if r['setup_successful'])
    
    # Count error types
    error_502_sessions = sum(1 for r in results if r.get('connection_error_type') == '502_Bad_Gateway')
    error_503_sessions = sum(1 for r in results if r.get('connection_error_type') == '503_Service_Unavailable')
    error_504_sessions = sum(1 for r in results if r.get('connection_error_type') == '504_Gateway_Timeout')
    error_handshake_sessions = sum(1 for r in results if r.get('connection_error_type') == 'Handshake_Error')
    error_other_sessions = sum(1 for r in results if r.get('connection_error_type') and r.get('connection_error_type') not in ['502_Bad_Gateway', '503_Service_Unavailable', '504_Gateway_Timeout', 'Handshake_Error', 'Setup_Failed'])
    
    stats = {
        'total_sessions': num_sessions,
        'setup_successful_sessions': setup_successful_sessions,
        'successful_sessions': successful_sessions,
        'failed_sessions': num_sessions - successful_sessions,
        'total_questions_sent': total_questions_sent,
        'total_responses_received': total_responses_received,
        'success_rate': (total_responses_received / total_questions_sent * 100) if total_questions_sent > 0 else 0,
        'session_success_rate': (successful_sessions / num_sessions * 100) if num_sessions > 0 else 0,
        'peak_concurrent_invocations': peak_concurrent,
        'final_concurrent_invocations': final_concurrent,
        'total_invocations_started': _total_invocations_started,
        'total_invocations_completed': _total_invocations_completed,
        'error_statistics': {
            '502_bad_gateway_count': total_502_errors,
            '502_bad_gateway_sessions': error_502_sessions,
            '503_service_unavailable_sessions': error_503_sessions,
            '504_gateway_timeout_sessions': error_504_sessions,
            'handshake_errors': error_handshake_sessions,
            'other_connection_errors': error_other_sessions,
            'total_connection_errors': total_connection_errors,
            'setup_failures': total_setup_failures
        },
        'individual_results': results
    }
    
    return stats


async def run_progressive_load_test(
    start_sessions: int = RAMP_START_SESSIONS,
    max_sessions: int = RAMP_MAX_SESSIONS,
    increment: int = RAMP_INCREMENT,
    ramp_interval: int = RAMP_INTERVAL_SECONDS
):
    """
    Run progressive load test with gradual ramp-up.
    
    Strategy: Gradually increase load from start_sessions to max_sessions
    with ramp_interval seconds between each increment.
    
    Args:
        start_sessions: Initial number of sessions to start with
        max_sessions: Maximum number of sessions to reach
        increment: How many sessions to add at each step
        ramp_interval: Seconds to wait between increments
    
    Returns:
        Dictionary with aggregated statistics
    """
    global _concurrent_invocations, _peak_concurrent, _total_invocations_started, _total_invocations_completed, _monitoring_task
    
    # Reset global counters
    async with _concurrent_lock:
        _concurrent_invocations = 0
        _peak_concurrent = 0
        _total_invocations_started = 0
        _total_invocations_completed = 0
    
    # Calculate total questions per session
    total_questions_per_session = sum(len(COURSE_QUESTIONS.get(course_id, [])) for course_id in COURSES)
    
    logger.info("")
    logger.info("="*80)
    logger.info("STARTING PROGRESSIVE LOAD TEST (STRATEGY 2: RAMP-UP)")
    logger.info("="*80)
    logger.info("Configuration:")
    logger.info(f"  Start Sessions: {start_sessions}")
    logger.info(f"  Max Sessions: {max_sessions}")
    logger.info(f"  Increment: {increment} sessions per step")
    logger.info(f"  Ramp Interval: {ramp_interval} seconds ({ramp_interval // 60} minutes)")
    logger.info(f"  Courses: {', '.join(COURSES)}")
    logger.info(f"  Questions per course:")
    for course_id in COURSES:
        question_count = len(COURSE_QUESTIONS.get(course_id, []))
        logger.info(f"    {course_id}: {question_count} questions")
    logger.info(f"  Total questions per session: {total_questions_per_session}")
    logger.info(f"  Sending mode: Sequential (wait for response before next question)")
    logger.info(f"  Concurrency model: Async I/O (asyncio)")
    logger.info(f"  Real-time monitoring: Enabled (every 5 seconds)")
    logger.info("="*80)
    logger.info("")
    
    # Start monitoring task
    _monitoring_task = asyncio.create_task(monitor_concurrent_invocations(interval=5))
    
    all_tasks = []
    session_index = 1
    ramp_stages = []
    
    try:
        # Start with initial batch
        logger.info("")
        logger.info("="*80)
        logger.info(f"STAGE 1: Starting {start_sessions} sessions")
        logger.info("="*80)
        initial_tasks = create_session_tasks(num_sessions=start_sessions, start_session_index=session_index)
        all_tasks.extend(initial_tasks)
        session_index += start_sessions
        
        ramp_stages.append({
            'stage': 1,
            'sessions': start_sessions,
            'cumulative_sessions': start_sessions,
            'tasks': initial_tasks
        })
        
        # Progressive ramp-up: add more sessions at intervals
        current_total = start_sessions
        stage_num = 2
        
        while current_total < max_sessions:
            # Wait for the ramp interval
            logger.info("")
            logger.info(f"Waiting {ramp_interval} seconds ({ramp_interval // 60} minutes) before next ramp-up...")
            await asyncio.sleep(ramp_interval)
            
            # Calculate how many sessions to add
            next_increment = min(increment, max_sessions - current_total)
            current_total += next_increment
            
            logger.info("")
            logger.info("="*80)
            logger.info(f"STAGE {stage_num}: Adding {next_increment} more sessions (Total: {current_total})")
            logger.info("="*80)
            
            # Add new sessions
            new_tasks = create_session_tasks(num_sessions=next_increment, start_session_index=session_index)
            all_tasks.extend(new_tasks)
            session_index += next_increment
            
            ramp_stages.append({
                'stage': stage_num,
                'sessions': next_increment,
                'cumulative_sessions': current_total,
                'tasks': new_tasks
            })
            
            stage_num += 1
        
        logger.info("")
        logger.info("="*80)
        logger.info(f"Reached maximum load: {max_sessions} sessions")
        logger.info("Waiting for all sessions to complete...")
        logger.info("="*80)
        logger.info("")
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*all_tasks, return_exceptions=True)
        
    finally:
        # Cancel monitoring task
        if _monitoring_task:
            _monitoring_task.cancel()
            try:
                await _monitoring_task
            except asyncio.CancelledError:
                pass
    
    # Process results (handle exceptions)
    valid_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Session {i + 1} raised exception: {result}")
            valid_results.append({
                'session_index': i + 1,
                'questions_sent': 0,
                'responses_received': 0,
                'successful': False,
                'setup_successful': False
            })
        else:
            valid_results.append(result)
    
    # Final concurrent count and error statistics
    async with _concurrent_lock:
        final_concurrent = _concurrent_invocations
        peak_concurrent = _peak_concurrent
        total_502_errors = _502_errors
        total_connection_errors = _connection_errors
        total_setup_failures = _setup_failures
    
    logger.info("")
    logger.info("="*80)
    logger.info("ALL SESSIONS COMPLETED")
    logger.info("="*80)
    
    # Aggregate statistics
    total_questions_sent = sum(r['questions_sent'] for r in valid_results)
    total_responses_received = sum(r['responses_received'] for r in valid_results)
    successful_sessions = sum(1 for r in valid_results if r['successful'])
    setup_successful_sessions = sum(1 for r in valid_results if r['setup_successful'])
    
    # Count error types
    error_502_sessions = sum(1 for r in valid_results if r.get('connection_error_type') == '502_Bad_Gateway')
    error_503_sessions = sum(1 for r in valid_results if r.get('connection_error_type') == '503_Service_Unavailable')
    error_504_sessions = sum(1 for r in valid_results if r.get('connection_error_type') == '504_Gateway_Timeout')
    error_handshake_sessions = sum(1 for r in valid_results if r.get('connection_error_type') == 'Handshake_Error')
    error_other_sessions = sum(1 for r in valid_results if r.get('connection_error_type') and r.get('connection_error_type') not in ['502_Bad_Gateway', '503_Service_Unavailable', '504_Gateway_Timeout', 'Handshake_Error', 'Setup_Failed'])
    
    stats = {
        'total_sessions': len(all_tasks),
        'setup_successful_sessions': setup_successful_sessions,
        'successful_sessions': successful_sessions,
        'failed_sessions': len(all_tasks) - successful_sessions,
        'total_questions_sent': total_questions_sent,
        'total_responses_received': total_responses_received,
        'success_rate': (total_responses_received / total_questions_sent * 100) if total_questions_sent > 0 else 0,
        'session_success_rate': (successful_sessions / len(all_tasks) * 100) if len(all_tasks) > 0 else 0,
        'peak_concurrent_invocations': peak_concurrent,
        'final_concurrent_invocations': final_concurrent,
        'total_invocations_started': _total_invocations_started,
        'total_invocations_completed': _total_invocations_completed,
        'error_statistics': {
            '502_bad_gateway_count': total_502_errors,
            '502_bad_gateway_sessions': error_502_sessions,
            '503_service_unavailable_sessions': error_503_sessions,
            '504_gateway_timeout_sessions': error_504_sessions,
            'handshake_errors': error_handshake_sessions,
            'other_connection_errors': error_other_sessions,
            'total_connection_errors': total_connection_errors,
            'setup_failures': total_setup_failures
        },
        'ramp_stages': ramp_stages,
        'individual_results': valid_results
    }
    
    return stats


if __name__ == "__main__":
    asyncio.run(run_load_test())

