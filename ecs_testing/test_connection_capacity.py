"""
ECS Connection Capacity Tester - Test maximum concurrent connections.
"""

import asyncio
import logging
import os
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


class ConnectionTester:
    """Test WebSocket connection capacity."""
    
    def __init__(self):
        self.results = {}
    
    async def test_session(self, index):
        """Test a single WebSocket connection."""
        try:
            # Generate token and create chat
            token_data = await generate_token()
            if not token_data or not token_data.get('token'):
                return {'success': False, 'error': 'Failed to generate token'}
            
            token = token_data['token']
            
            # Test WebSocket connection
            ws_url = f"{WEBSOCKET_URL_TEMPLATE}?token={token}"
            async with websockets.connect(
                ws_url,
                origin=WEBSOCKET_ORIGIN,
                ping_interval=None,  # Disable ping for connection test
                close_timeout=5
            ) as ws:
                await asyncio.sleep(0.1)  # Brief connection test
                return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)[:100]}
    
    async def test_capacity(self, num_sessions, timeout=90):
        """Test connection capacity for given number of sessions."""
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing {num_sessions} concurrent connections...")
        logger.info(f"{'='*60}")
        
        start_time = time.time()
        successful = 0
        failed = 0
        connection_errors = []
        
        try:
            # Run with timeout
            results = await asyncio.wait_for(
                asyncio.gather(*[self.test_session(i) for i in range(num_sessions)], return_exceptions=True),
                timeout=timeout
            )
            
            # Count results
            for result in results:
                if isinstance(result, dict):
                    if result.get('success'):
                        successful += 1
                    else:
                        failed += 1
                        if 'error' in result:
                            connection_errors.append(result['error'])
                else:
                    failed += 1
                    connection_errors.append(str(result)[:100])
            
            elapsed = time.time() - start_time
            success_rate = successful / num_sessions if num_sessions > 0 else 0
            
            self.results[num_sessions] = {
                'successful': successful,
                'failed': failed,
                'success_rate': success_rate,
                'elapsed': elapsed,
                'errors': list(set(connection_errors))[:5]  # Top 5 unique errors
            }
            
            logger.info(f"[OK] {successful}/{num_sessions} successful ({success_rate*100:.1f}%) in {elapsed:.2f}s")
            
            # Log unique errors
            if connection_errors:
                unique_errors = list(set(connection_errors))[:3]
                for err in unique_errors:
                    logger.warning(f"  Error: {err}")
            
            return success_rate >= 0.75  # 75% success threshold
                
        except asyncio.TimeoutError:
            logger.error(f"[TIMEOUT] Testing {num_sessions} sessions (>{timeout}s)")
            self.results[num_sessions] = {
                'successful': successful,
                'failed': failed,
                'success_rate': successful / num_sessions if num_sessions > 0 else 0,
                'elapsed': timeout,
                'timeout': True
            }
            return False
        except Exception as e:
            logger.error(f"[ERROR] {e}")
            return False


async def run_capacity_test():
    """Run connection capacity test with progressive scaling."""
    
    # Get memory limit to adjust test points
    memory_mb = os.environ.get('ECS_MEMORY_LIMIT', '')
    
    # ECS-friendly test points (start conservative)
    test_points = [10, 25, 50, 100, 200, 500, 1000]
    
    if memory_mb:
        max_estimate = int((int(memory_mb) * 0.5) / 0.003)
        logger.info(f"Memory-based estimate: ~{max_estimate} connections")
        # Add test points up to estimate
        test_points = [t for t in test_points if t <= max_estimate]
        if max_estimate > 1000:
            test_points.extend([2000, 5000])
    
    tester = ConnectionTester()
    
    logger.info("="*60)
    logger.info("ECS CONNECTION CAPACITY TEST")
    logger.info("="*60)
    logger.info(f"Test points: {test_points}")
    logger.info("")
    
    for num_sessions in test_points:
        success = await tester.test_capacity(num_sessions)
        
        if not success:
            logger.warning(f"Success rate below 75%, stopping tests")
            break
        
        # Pause between tests
        if num_sessions < test_points[-1]:
            logger.info("Pausing 3 seconds before next test...")
            await asyncio.sleep(3)
    
    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("CONNECTION CAPACITY TEST RESULTS")
    logger.info(f"{'='*60}")
    
    for sessions in sorted(tester.results.keys()):
        result = tester.results[sessions]
        status = "[OK]" if result.get('success_rate', 0) >= 0.75 else "[FAIL]"
        timeout_marker = " [TIMEOUT]" if result.get('timeout') else ""
        logger.info(f"{status} {sessions:5d} sessions: {result['successful']:5d} successful "
                   f"({result['success_rate']*100:5.1f}%) in {result['elapsed']:.2f}s{timeout_marker}")
    
    # Find max reliable connections
    max_sessions = max(
        [s for s, r in tester.results.items() if r.get('success_rate', 0) >= 0.75],
        default=0
    )
    
    logger.info(f"\n{'='*60}")
    if max_sessions > 0:
        logger.info(f"[OK] Maximum reliable connections for this ECS task: ~{max_sessions}")
        logger.info(f"  Recommendation: Use {int(max_sessions * 0.8)} as safe limit")
    else:
        logger.warning("[FAIL] No reliable connection count found (all tests failed or below threshold)")
    logger.info(f"{'='*60}")
    
    return tester.results


if __name__ == "__main__":
    # Try to increase file descriptor limit if possible
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        if soft < 65536:
            try:
                resource.setrlimit(resource.RLIMIT_NOFILE, (65536, hard))
                logger.info(f"Increased file descriptor limit to 65536")
            except:
                logger.warning(f"Could not increase file descriptor limit (current: {soft})")
    except:
        pass
    
    results = asyncio.run(run_capacity_test())

