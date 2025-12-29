import json
import uuid
import asyncio
import websockets
import time
import logging
from datetime import datetime, timezone
from typing import Optional

from node_services_async import generate_token, create_chat
from config import COURSE_QUESTIONS, NUM_SESSIONS, COURSES, WEBSOCKET_URL_TEMPLATE, WEBSOCKET_ORIGIN, MESSAGE_CONFIG
from encryption import encrypt, decrypt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s.%(msecs)03d] [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


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
            self.log(f"ERROR in setup: {e}")
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
            
            self.questions_sent_count += 1
            self.all_chunks = []  # Clear chunks for new question
            self.response_received_time = None  # Reset response time
            send_time_str = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            self.log(f"Question {self.questions_sent_count}/{len(self.pending_questions)} sent: {question[:60]}... [Time: {send_time_str}]")
            self.log("Waiting for complete_response (will wait until received)...")
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
                    
                    # Calculate total latency
                    total_latency = None
                    if self.question_sent_time and self.response_received_time:
                        total_latency = (self.response_received_time - self.question_sent_time) * 1000  # Convert to milliseconds
                    
                    latency_info = f" [Total Latency: {total_latency:.2f}ms]" if total_latency else ""
                    self.log(f"✓ complete_response received (chunk {len(self.all_chunks)})!{latency_info}")
                    self.log(f"Response {self.responses_received_count}/{self.questions_sent_count}: {data['complete_response'][:100]}...")
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
        """
        self.log(f"Starting session")
        ws_url = f"{WEBSOCKET_URL_TEMPLATE}?token={self.token}"

        # Build list of (course_id, question) using ALL questions from config
        for course_id in COURSES:
            question_pool = COURSE_QUESTIONS.get(course_id, [])
            # Use ALL questions from the pool for this session
            for question in question_pool:
                self.pending_questions.append((course_id, question))
        
        self.log(f"Prepared {len(self.pending_questions)} questions")

        try:
            # Connect to WebSocket with origin header
            async with websockets.connect(
                ws_url,
                origin=WEBSOCKET_ORIGIN
            ) as ws:
                self.ws = ws
                self.log("WebSocket opened - sending questions sequentially (wait for response before next)")
                
                # Send the first question
                await self.send_next_question(ws)
                
                # Listen for messages until connection closes
                try:
                    async for message in ws:
                        await self.handle_message(message)
                        # Check if we should close after processing message
                        if self.all_questions_sent and self.questions_sent_count == self.responses_received_count:
                            break
                except websockets.exceptions.ConnectionClosed:
                    self.log("WebSocket connection closed by server")
                    
        except websockets.exceptions.ConnectionClosed:
            self.log("WebSocket connection closed")
        except Exception as e:
            self.log(f"WebSocket error: {e}")
        finally:
            self.log(f"Session complete - Sent: {self.questions_sent_count}, Received: {self.responses_received_count}")
            if self.questions_sent_count > self.responses_received_count:
                missing = self.questions_sent_count - self.responses_received_count
                self.log(f"WARNING: {missing} responses not received")
            self.log("Session finished")


async def run_session(index):
    """Run a single session asynchronously."""
    runner = AsyncSessionRunner(index)
    if await runner.setup():
        await runner.start()
    else:
        logger.error(f"Session {index} setup failed")


async def run_load_test(num_sessions: int = NUM_SESSIONS):
    """
    Run the load test with multiple concurrent sessions using async I/O.
    
    Behavior:
    - All sessions run CONCURRENTLY using asyncio tasks
    - Questions within each session are sent SEQUENTIALLY (wait for response before next)
    - Each session will ask ALL questions from the question pools
    
    Args:
        num_sessions: Number of concurrent sessions to run
    """
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
    logger.info("="*80)
    logger.info("")
    
    # Create tasks for all sessions
    tasks = [run_session(i + 1) for i in range(num_sessions)]
    
    logger.info(f"Started {num_sessions} concurrent sessions")
    logger.info("")
    
    # Run all sessions concurrently
    await asyncio.gather(*tasks)
    
    logger.info("")
    logger.info("="*80)
    logger.info("ALL SESSIONS COMPLETED")
    logger.info("="*80)


if __name__ == "__main__":
    asyncio.run(run_load_test())

