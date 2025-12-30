"""
API server for the NUC Python load testing application.

Provides an HTTP endpoint to trigger load tests with configurable parameters.
"""

import asyncio
import logging
from aiohttp import web
from aiohttp.web import Request, Response
import json

from python_service_nuc_async import run_load_test, run_progressive_load_test

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s.%(msecs)03d] [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


async def run_load_test_endpoint(request: Request) -> Response:
    """
    HTTP endpoint to run load test with configurable parameters.
    
    Accepts POST request with JSON body containing:
    - num_sessions: Number of concurrent sessions (default: 2)
    - ramp_start_sessions: Initial number of sessions for progressive ramp-up (default: 10)
    - ramp_max_sessions: Maximum number of sessions to reach (default: 500)
    - ramp_increment: Number of sessions to add at each ramp-up step (default: 50)
    - ramp_interval_seconds: Seconds to wait between ramp-up steps (default: 180)
    - use_progressive_rampup: Whether to use progressive ramp-up strategy (default: False)
    
    Returns:
        JSON response with load test statistics
    """
    try:
        # Parse request body
        data = await request.json()
        
        # Extract parameters with defaults
        num_sessions = data.get('num_sessions', 2)
        ramp_start_sessions = data.get('ramp_start_sessions', 10)
        ramp_max_sessions = data.get('ramp_max_sessions', 500)
        ramp_increment = data.get('ramp_increment', 50)
        ramp_interval_seconds = data.get('ramp_interval_seconds', 180)
        use_progressive_rampup = data.get('use_progressive_rampup', False)
        
        logger.info("="*80)
        logger.info("LOAD TEST REQUEST RECEIVED")
        logger.info("="*80)
        logger.info(f"Parameters:")
        logger.info(f"  num_sessions: {num_sessions}")
        logger.info(f"  ramp_start_sessions: {ramp_start_sessions}")
        logger.info(f"  ramp_max_sessions: {ramp_max_sessions}")
        logger.info(f"  ramp_increment: {ramp_increment}")
        logger.info(f"  ramp_interval_seconds: {ramp_interval_seconds}")
        logger.info(f"  use_progressive_rampup: {use_progressive_rampup}")
        logger.info("="*80)
        
        # Run the appropriate load test
        if use_progressive_rampup:
            stats = await run_progressive_load_test(
                start_sessions=ramp_start_sessions,
                max_sessions=ramp_max_sessions,
                increment=ramp_increment,
                ramp_interval=ramp_interval_seconds
            )
        else:
            stats = await run_load_test(num_sessions=num_sessions)
        
        # Return statistics as JSON
        return web.json_response({
            'status': 'success',
            'message': 'Load test completed',
            'statistics': stats
        })
        
    except json.JSONDecodeError:
        logger.error("Invalid JSON in request body")
        return web.json_response(
            {'status': 'error', 'message': 'Invalid JSON in request body'},
            status=400
        )
    except Exception as e:
        logger.error(f"Error running load test: {e}", exc_info=True)
        return web.json_response(
            {'status': 'error', 'message': str(e)},
            status=500
        )


async def health_check(request: Request) -> Response:
    """Health check endpoint."""
    return web.json_response({'status': 'healthy'})


def create_app():
    """Create and configure the aiohttp application."""
    app = web.Application()
    
    # Add routes
    app.router.add_post('/run-load-test', run_load_test_endpoint)
    app.router.add_get('/health', health_check)
    
    return app


async def main():
    """Main function to run the API server."""
    app = create_app()
    
    logger.info("="*80)
    logger.info("Starting NUC Load Test API Server")
    logger.info("="*80)
    logger.info("Endpoints:")
    logger.info("  POST /run-load-test - Run load test with configurable parameters")
    logger.info("  GET  /health - Health check")
    logger.info("="*80)
    logger.info("")
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    
    logger.info("API server started on http://0.0.0.0:8080")
    logger.info("Press Ctrl+C to stop")
    
    # Keep the server running
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())

