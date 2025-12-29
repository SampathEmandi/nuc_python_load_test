"""
AWS-optimized connection capacity test with CloudWatch-ready logging.
"""

import asyncio
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from python_service_nuc_async import AsyncSessionRunner
from config import WEBSOCKET_URL_TEMPLATE, WEBSOCKET_ORIGIN
import websockets

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


async def test_aws_connection_capacity():
    """Test connection capacity with AWS-optimized approach."""
    
    # AWS-friendly increments
    test_points = [10, 50, 100, 200, 500, 1000, 2000, 5000]
    
    results = {}
    
    for num_sessions in test_points:
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing {num_sessions} concurrent connections...")
        logger.info(f"{'='*60}")
        
        start_time = time.time()
        successful = 0
        failed = 0
        errors = []
        
        async def test_session(index):
            nonlocal successful, failed
            try:
                runner = AsyncSessionRunner(index)
                if await runner.setup():
                    # Test WebSocket connection
                    ws_url = f"{WEBSOCKET_URL_TEMPLATE}?token={runner.token}"
                    async with websockets.connect(
                        ws_url,
                        origin=WEBSOCKET_ORIGIN,
                        ping_interval=None,  # Disable ping for connection test
                        close_timeout=5
                    ) as ws:
                        await asyncio.sleep(0.1)  # Brief connection test
                        successful += 1
                        return True
                else:
                    failed += 1
                    return False
            except Exception as e:
                failed += 1
                errors.append(str(e)[:100])
                return False
        
        try:
            # Run with timeout
            await asyncio.wait_for(
                asyncio.gather(*[test_session(i) for i in range(num_sessions)], return_exceptions=True),
                timeout=60  # 60 second timeout
            )
            
            elapsed = time.time() - start_time
            success_rate = successful / num_sessions if num_sessions > 0 else 0
            
            results[num_sessions] = {
                'successful': successful,
                'failed': failed,
                'success_rate': success_rate,
                'elapsed': elapsed
            }
            
            logger.info(f"Results: {successful}/{num_sessions} successful ({success_rate*100:.1f}%) in {elapsed:.2f}s")
            
            if success_rate < 0.8:  # Less than 80% success
                logger.warning(f"Success rate below 80%, stopping tests")
                break
                
            # Show sample errors if any
            if errors:
                unique_errors = list(set(errors))[:3]
                logger.info(f"Sample errors: {unique_errors}")
                
        except asyncio.TimeoutError:
            logger.error(f"Timeout testing {num_sessions} sessions")
            break
        except Exception as e:
            logger.error(f"Error: {e}")
            break
        
        # Brief pause between tests
        await asyncio.sleep(2)
    
    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("CONNECTION CAPACITY TEST RESULTS")
    logger.info(f"{'='*60}")
    for sessions, result in results.items():
        logger.info(f"{sessions:5d} sessions: {result['successful']:5d} successful "
                   f"({result['success_rate']*100:5.1f}%) in {result['elapsed']:.2f}s")
    
    # Find max
    max_sessions = max([s for s, r in results.items() if r['success_rate'] >= 0.8], default=0)
    logger.info(f"\nMaximum reliable connections: ~{max_sessions}")
    
    return results


if __name__ == "__main__":
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
    except:
        pass
    
    asyncio.run(test_aws_connection_capacity())

