"""
ALB Connection Capacity Test - Tests sustained concurrent connections with keep-alive.
This script keeps connections open to properly test ALB ActiveConnectionCount metric.
"""

import asyncio
import logging
import sys
import time
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from node_services_async import generate_token, create_chat
from config import WEBSOCKET_URL_TEMPLATE, WEBSOCKET_ORIGIN
import websockets

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# ALB idle timeout is typically 60 seconds, so we ping every 30 seconds
ALB_IDLE_TIMEOUT = 60
HEARTBEAT_INTERVAL = 30  # Send heartbeat every 30 seconds
TEST_DURATION = 120  # Keep connections open for 2 minutes to test sustained load


async def connect_and_stay_alive(uri, client_id, test_duration=TEST_DURATION):
    """
    Connect to WebSocket and keep connection alive with periodic heartbeats.
    
    Args:
        uri: WebSocket URI
        client_id: Unique identifier for this client
        test_duration: How long to keep the connection open (seconds)
    
    Returns:
        dict with connection status and stats
    """
    start_time = time.time()
    heartbeat_count = 0
    last_error = None
    
    try:
        async with websockets.connect(
            uri,
            origin=WEBSOCKET_ORIGIN,
            ping_interval=HEARTBEAT_INTERVAL,  # Enable automatic ping every 30s
            ping_timeout=10,
            close_timeout=10
        ) as websocket:
            logger.debug(f"Client {client_id} connected")
            
            # Keep connection alive for test duration
            end_time = start_time + test_duration
            while time.time() < end_time:
                try:
                    # Wait for messages or timeout
                    try:
                        message = await asyncio.wait_for(
                            websocket.recv(),
                            timeout=HEARTBEAT_INTERVAL
                        )
                        # Process message if needed (optional)
                        logger.debug(f"Client {client_id} received message")
                    except asyncio.TimeoutError:
                        # No message received, connection still alive
                        heartbeat_count += 1
                        logger.debug(f"Client {client_id} heartbeat {heartbeat_count}")
                    except websockets.exceptions.ConnectionClosed:
                        logger.warning(f"Client {client_id} connection closed by server")
                        break
                        
                except Exception as e:
                    last_error = str(e)
                    logger.error(f"Client {client_id} error: {e}")
                    break
            
            connection_duration = time.time() - start_time
            return {
                'success': True,
                'client_id': client_id,
                'duration': connection_duration,
                'heartbeats': heartbeat_count,
                'error': None
            }
            
    except Exception as e:
        last_error = str(e)
        logger.error(f"Client {client_id} connection failed: {e}")
        return {
            'success': False,
            'client_id': client_id,
            'duration': time.time() - start_time,
            'heartbeats': heartbeat_count,
            'error': last_error
        }


async def test_alb_connection_capacity(test_duration=TEST_DURATION):
    """
    Test ALB connection capacity with sustained connections.
    
    Args:
        test_duration: How long to keep connections open (seconds)
    
    Returns:
        dict with test results
    """
    # AWS-friendly test points
    test_points = [50, 100, 200, 500, 1000, 2000, 5000]
    
    results = {}
    
    for num_connections in test_points:
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing {num_connections} sustained concurrent connections...")
        logger.info(f"  Duration: {test_duration} seconds")
        logger.info(f"  Heartbeat interval: {HEARTBEAT_INTERVAL} seconds")
        logger.info(f"{'='*60}")
        
        # Setup: Generate tokens for all connections
        logger.info("Generating tokens for all connections...")
        tokens = []
        setup_start = time.time()
        
        for i in range(num_connections):
            try:
                token_data = await generate_token()
                if token_data and token_data.get('token'):
                    tokens.append(token_data['token'])
                else:
                    logger.warning(f"Failed to generate token for connection {i}")
            except Exception as e:
                logger.warning(f"Error generating token {i}: {e}")
        
        setup_time = time.time() - setup_start
        logger.info(f"Generated {len(tokens)}/{num_connections} tokens in {setup_time:.2f}s")
        
        if len(tokens) < num_connections * 0.8:  # Less than 80% success
            logger.warning(f"Token generation success rate too low ({len(tokens)}/{num_connections}), skipping this test")
            continue
        
        # Create WebSocket URIs
        ws_uris = [f"{WEBSOCKET_URL_TEMPLATE}?token={token}" for token in tokens]
        
        # Start all connections concurrently
        logger.info(f"Establishing {len(ws_uris)} concurrent connections...")
        test_start = time.time()
        
        tasks = [
            connect_and_stay_alive(uri, i, test_duration)
            for i, uri in enumerate(ws_uris)
        ]
        
        try:
            # Wait for all connections to complete (or timeout)
            connection_results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=test_duration + 30  # Add buffer for setup/teardown
            )
        except asyncio.TimeoutError:
            logger.error(f"Test timeout after {test_duration + 30} seconds")
            connection_results = []
        
        test_elapsed = time.time() - test_start
        
        # Analyze results
        successful = 0
        failed = 0
        total_heartbeats = 0
        errors = []
        
        for result in connection_results:
            if isinstance(result, dict):
                if result.get('success'):
                    successful += 1
                    total_heartbeats += result.get('heartbeats', 0)
                else:
                    failed += 1
                    if result.get('error'):
                        errors.append(result['error'])
            else:
                failed += 1
                errors.append(str(result)[:100])
        
        success_rate = successful / len(ws_uris) if ws_uris else 0
        avg_heartbeats = total_heartbeats / successful if successful > 0 else 0
        
        results[num_connections] = {
            'total': len(ws_uris),
            'successful': successful,
            'failed': failed,
            'success_rate': success_rate,
            'test_duration': test_elapsed,
            'avg_heartbeats': avg_heartbeats,
            'errors': list(set(errors))[:5]  # Top 5 unique errors
        }
        
        logger.info(f"Results: {successful}/{len(ws_uris)} successful ({success_rate*100:.1f}%)")
        logger.info(f"  Average heartbeats per connection: {avg_heartbeats:.1f}")
        logger.info(f"  Test duration: {test_elapsed:.2f}s")
        
        if errors:
            unique_errors = list(set(errors))[:3]
            logger.info(f"  Sample errors: {unique_errors}")
        
        if success_rate < 0.8:  # Less than 80% success
            logger.warning(f"Success rate below 80%, stopping tests")
            break
        
        # Brief pause between test points
        logger.info("Pausing 5 seconds before next test...")
        await asyncio.sleep(5)
    
    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("ALB CONNECTION CAPACITY TEST RESULTS")
    logger.info(f"{'='*60}")
    logger.info(f"Test configuration:")
    logger.info(f"  Connection duration: {test_duration} seconds")
    logger.info(f"  Heartbeat interval: {HEARTBEAT_INTERVAL} seconds")
    logger.info(f"  ALB idle timeout: {ALB_IDLE_TIMEOUT} seconds (typical)")
    logger.info("")
    
    for connections, result in results.items():
        status = "[OK]" if result['success_rate'] >= 0.8 else "[FAIL]"
        logger.info(f"{status} {connections:5d} connections: {result['successful']:5d}/{result['total']:5d} successful "
                   f"({result['success_rate']*100:5.1f}%) | "
                   f"Avg heartbeats: {result['avg_heartbeats']:.1f} | "
                   f"Duration: {result['test_duration']:.2f}s")
    
    # Find max reliable connections
    max_connections = max(
        [c for c, r in results.items() if r['success_rate'] >= 0.8],
        default=0
    )
    
    logger.info(f"\n{'='*60}")
    if max_connections > 0:
        logger.info(f"[OK] Maximum reliable concurrent connections: ~{max_connections}")
        logger.info(f"  Recommendation: Use {int(max_connections * 0.8)} as safe limit for ALB")
        logger.info(f"  This should match ALB ActiveConnectionCount metric")
    else:
        logger.warning("[FAIL] No reliable connection count found")
    logger.info(f"{'='*60}")
    
    return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Test ALB connection capacity with sustained connections')
    parser.add_argument(
        '--duration',
        type=int,
        default=TEST_DURATION,
        help=f'How long to keep connections open (seconds, default: {TEST_DURATION})'
    )
    parser.add_argument(
        '--heartbeat',
        type=int,
        default=HEARTBEAT_INTERVAL,
        help=f'Heartbeat interval in seconds (default: {HEARTBEAT_INTERVAL}, should be < ALB idle timeout)'
    )
    
    args = parser.parse_args()
    
    # Increase file descriptor limit if possible
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        if soft < 65536:
            try:
                resource.setrlimit(resource.RLIMIT_NOFILE, (65536, hard))
                logger.info(f"Increased file descriptor limit to 65536")
            except:
                logger.warning(f"Could not increase file descriptor limit (current: {soft})")
                logger.warning("  Run: ulimit -n 65536 (Linux/Mac) or increase system limits (Windows)")
    except:
        logger.warning("Could not check/increase file descriptor limit (Windows or no resource module)")
    
    logger.info("="*60)
    logger.info("ALB Connection Capacity Test")
    logger.info("="*60)
    logger.info(f"Test duration: {args.duration} seconds")
    logger.info(f"Heartbeat interval: {args.heartbeat} seconds")
    logger.info("")
    
    asyncio.run(test_alb_connection_capacity(test_duration=args.duration))

