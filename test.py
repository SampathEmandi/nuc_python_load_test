
"""
Test script to send a single message, wait for only complete_response, print it, and exit.
"""

import json
import uuid
import websocket
import threading
import time
from datetime import datetime, timezone

from node_services import generate_token, create_chat
from encryption import encrypt, decrypt
from config import WEBSOCKET_URL_TEMPLATE, WEBSOCKET_ORIGIN, MESSAGE_CONFIG

import logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


class SingleMessageTest:
    def __init__(self):
        self.token = None
        self.client_code = None
        self.session_id = None
        self.connection_id = None
        self.session_attributes = None
        self.response_received = threading.Event()
        self.complete_response_text = None
        self.ws = None
        self.all_chunks = []  # Store all received chunks for debugging
        self.question_sent_time = None  # Timestamp when question was sent
        self.response_received_time = None  # Timestamp when complete_response was received

    def setup(self):
        try:
            token_data = generate_token()
            if not token_data or not token_data.get('token'):
                logger.error("Failed to generate token")
                return False
            self.token = token_data['token']
            self.client_code = token_data.get('client_code')
            self.connection_id = token_data.get('connection_id')
            self.session_id = token_data.get('session_id')
            if not self.session_id:
                chat_info = create_chat(self.token)
                if chat_info and chat_info.get('session_id'):
                    self.session_id = chat_info['session_id']
                else:
                    logger.error("session_id missing")
                    return False
            return True
        except Exception as e:
            logger.error(f"Setup error: {e}")
            return False

    def send_and_wait(self, question, course_id="MED1060", timeout=None):
        """Send a question and wait for complete_response. Reuses existing WebSocket if available.
        
        Args:
            question: The question to send
            course_id: Course ID
            timeout: Timeout in seconds (None = wait indefinitely until complete_response is received)
        """
        # Reset the event and response for this new question
        self.response_received.clear()
        self.complete_response_text = None
        self.all_chunks = []  # Clear chunks for new question
        self.question_sent_time = None
        self.response_received_time = None
        
        ws_url = f"{WEBSOCKET_URL_TEMPLATE}?token={self.token}"

        def send_message(ws):
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
            try:
                self.question_sent_time = time.time()  # Record send time
                ws.send(encrypt(json.dumps(payload)))
                logger.info(f"Question sent: {question} [Time: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}]")
            except Exception as e:
                logger.error(f"Send failed: {e}")
                self.response_received.set()

        def on_open(ws):
            send_message(ws)

        def on_message(ws, message):
            try:
                decrypted = decrypt(message)
                if not decrypted:
                    logger.warning("Received empty decrypted message")
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
                    
                    # Only log keys, not full data
                    logger.info(f"[CHUNK {len(self.all_chunks)}] Keys: {keys}{latency_str}")
                    
                    if 'session_attributes' in data:
                        self.session_attributes = data['session_attributes']
                    
                    # Check for complete_response
                    if 'complete_response' in data:
                        self.response_received_time = time.time()
                        self.complete_response_text = data['complete_response']
                        
                        # Calculate total latency
                        total_latency = None
                        if self.question_sent_time and self.response_received_time:
                            total_latency = (self.response_received_time - self.question_sent_time) * 1000  # Convert to milliseconds
                        
                        latency_info = f" [Total Latency: {total_latency:.2f}ms]" if total_latency else ""
                        logger.info(f"\n--- Complete Response (from chunk {len(self.all_chunks)}){latency_info} ---\n{self.complete_response_text}\n")
                        self.response_received.set()
                except json.JSONDecodeError as e:
                    logger.warning(f"[CHUNK] Not JSON: {decrypted[:200]}...")
                except Exception as e:
                    logger.error(f"[CHUNK] Error processing: {e}")
            except Exception as e:
                logger.error(f"[CHUNK] Decryption error: {e}")
                self.response_received.set()

        def on_error(ws, error):
            logger.error(f"WebSocket error: {error}")
            self.response_received.set()

        def on_close(ws, close_status_code, close_msg):
            self.response_received.set()

        # Create new WebSocket if we don't have one, or if it's closed
        if self.ws is None:
            self.ws = websocket.WebSocketApp(
                ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )

            threading.Thread(
                target=self.ws.run_forever,
                kwargs={"origin": WEBSOCKET_ORIGIN},
                daemon=True
            ).start()
        else:
            # Reuse existing connection - just send the message directly
            send_message(self.ws)

        if timeout:
            logger.info(f"Waiting for complete_response (timeout: {timeout}s)...")
        else:
            logger.info("Waiting for complete_response (waiting indefinitely until received)...")
        
        received = self.response_received.wait(timeout=timeout)
        
        if not received and timeout:
            logger.error(f"Timeout after {timeout} seconds. Received {len(self.all_chunks)} chunks but no complete_response.")
            logger.info(f"All chunks received: {len(self.all_chunks)}")
            for i, chunk in enumerate(self.all_chunks, 1):
                logger.info(f"Chunk {i}: {chunk[:300]}...")
        elif received:
            total_latency = None
            if self.question_sent_time and self.response_received_time:
                total_latency = (self.response_received_time - self.question_sent_time) * 1000  # Convert to milliseconds
            latency_info = f" [Total Latency: {total_latency:.2f}ms]" if total_latency else ""
            logger.info(f"✓ complete_response received after {len(self.all_chunks)} chunk(s){latency_info}")
        
        return self.complete_response_text


def main():
    """Send multiple questions sequentially, waiting for each response."""
    test = SingleMessageTest()
    
    # Setup once
    if not test.setup():
        logger.error("Setup failed")
        return
    
    # List of questions to send sequentially
    questions = [
        ("What is this course about?", "MED1060"),
        ("What are the modules of this course?", "MED1060"),
        ("What topics will I learn in this course?", "MED1060"),
    ]
    
    # Send each question and wait for response
    for i, (question, course_id) in enumerate(questions, 1):
        logger.info(f"\n{'='*60}")
        logger.info(f"Question {i}/{len(questions)}")
        logger.info(f"{'='*60}")
        
        # Wait indefinitely for complete_response (timeout=None)
        response = test.send_and_wait(question=question, course_id=course_id, timeout=None)
        if not response:
            logger.error(f"No complete_response received for question {i} after waiting")
            # Don't break - continue to next question
        else:
            logger.info(f"✓ Question {i} completed successfully")
        
        # Small delay before next question
        if i < len(questions):
            import time
            time.sleep(0.5)
    
    logger.info("\nAll questions completed!")


if __name__ == "__main__":
    main()

