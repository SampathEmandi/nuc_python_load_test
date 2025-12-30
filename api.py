"""
FastAPI server for the NUC Python load testing application.

Provides an HTTP endpoint to trigger load tests with configurable parameters.
"""

import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

from python_service_nuc_async import run_load_test, run_progressive_load_test

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s.%(msecs)03d] [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="NUC Load Test API", version="1.0.0")


class LoadTestRequest(BaseModel):
    """Request model for load test parameters."""
    num_sessions: Optional[int] = 2
    ramp_start_sessions: Optional[int] = 10
    ramp_max_sessions: Optional[int] = 500
    ramp_increment: Optional[int] = 50
    ramp_interval_seconds: Optional[int] = 180
    use_progressive_rampup: Optional[bool] = False


class LoadTestResponse(BaseModel):
    """Response model for load test results."""
    status: str
    message: str
    statistics: dict


@app.post("/run-load-test", response_model=LoadTestResponse)
async def run_load_test_endpoint(request: LoadTestRequest):
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
        logger.info("="*80)
        logger.info("LOAD TEST REQUEST RECEIVED")
        logger.info("="*80)
        logger.info(f"Parameters:")
        logger.info(f"  num_sessions: {request.num_sessions}")
        logger.info(f"  ramp_start_sessions: {request.ramp_start_sessions}")
        logger.info(f"  ramp_max_sessions: {request.ramp_max_sessions}")
        logger.info(f"  ramp_increment: {request.ramp_increment}")
        logger.info(f"  ramp_interval_seconds: {request.ramp_interval_seconds}")
        logger.info(f"  use_progressive_rampup: {request.use_progressive_rampup}")
        logger.info("="*80)
        
        # Run the appropriate load test
        if request.use_progressive_rampup:
            stats = await run_progressive_load_test(
                start_sessions=request.ramp_start_sessions,
                max_sessions=request.ramp_max_sessions,
                increment=request.ramp_increment,
                ramp_interval=request.ramp_interval_seconds
            )
        else:
            stats = await run_load_test(num_sessions=request.num_sessions)
        
        # Return statistics as JSON
        return LoadTestResponse(
            status='success',
            message='Load test completed',
            statistics=stats
        )
        
    except Exception as e:
        logger.error(f"Error running load test: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "NUC Load Test API",
        "version": "1.0.0",
        "endpoints": {
            "POST /run-load-test": "Run load test with configurable parameters",
            "GET /health": "Health check",
            "GET /": "API information"
        }
    }

