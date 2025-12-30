import aiohttp
import json
import uuid
import logging
from datetime import datetime
import warnings
from config import (
    GENERATE_TOKEN_URL, CREATE_CHAT_URL, API_HEADERS, API_ACCESS_KEY, API_SECRET_KEY,
    USER_CONTEXT, METADATA
)

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)


async def generate_token():
    """Async version of generate_token using aiohttp."""
    # Generate session_id and connection_id to send in request
    session_id = str(uuid.uuid4())
    connection_id = str(uuid.uuid4())
    
    payload = json.dumps({
        "session_id": session_id,
        "connection_id": connection_id,
        "access_key": API_ACCESS_KEY,
        "secret_key": API_SECRET_KEY,
        "kw_args": {
            "user_context": USER_CONTEXT,
        },
        "meta_data": {
            **METADATA,
            "browser_unique_identifier": str(uuid.uuid4()),
            "session_time": datetime.now().strftime('%d-%m-%Y %H:%M:%S')
        }
    })

    try:
        # Enable SSL verification
        connector = aiohttp.TCPConnector(ssl=True)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(
                GENERATE_TOKEN_URL,
                headers=API_HEADERS,
                data=payload
            ) as response:
                response_data = await response.json()
    except Exception as e:
        logger.error(f"Error generating token: {e}")
        return None
    
    # Return both token and client_code, and the session_id/connection_id we sent
    if response_data.get('success') == '1' and response_data.get('token'):
        return {
            'token': response_data['token'],
            'client_code': response_data.get('client_code'),
            'session_id': response_data.get('session_id') or session_id,  # Use response session_id or the one we sent
            'connection_id': response_data.get('connection_id') or connection_id  # Use response connection_id or the one we sent
        }
    return None


async def create_chat(token):
    """Async version of create_chat using aiohttp."""
    payload = json.dumps({
        "token": token
    })
    
    try:
        # Enable SSL verification
        connector = aiohttp.TCPConnector(ssl=True)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(
                CREATE_CHAT_URL,
                headers=API_HEADERS,
                data=payload
            ) as response:
                response_data = await response.json()
    except Exception as e:
        logger.error(f"Error creating chat: {e}")
        return None
    
    # Return session_id from the response
    if response_data:
        return {
            'session_id': response_data.get('session_id')
        }
    return None

