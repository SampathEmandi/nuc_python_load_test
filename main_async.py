"""
Main entry point for the NUC Python load testing application.

This module orchestrates concurrent chatbot load testing sessions
with simple logging of questions and responses.

Now uses async I/O for better performance and scalability.
"""

import asyncio
import logging
from python_service_nuc_async import run_load_test, NUM_SESSIONS, COURSES

import warnings
warnings.filterwarnings("ignore")
# Configure logger for main module
logger = logging.getLogger(__name__)


async def main():
    """
    Main async function to run the load test with logging.
    """
    logger.info("="*80)
    logger.info("NUC Python Load Testing Application (Async I/O)")
    logger.info("="*80)
    
    # Run the load test (each session will ask ALL questions)
    await run_load_test(num_sessions=NUM_SESSIONS)


if __name__ == "__main__":
    asyncio.run(main())
