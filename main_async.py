"""
Main entry point for the NUC Python load testing application.

This module orchestrates concurrent chatbot load testing sessions
with simple logging of questions and responses.

Now uses async I/O for better performance and scalability.

Supports two strategies:
- Strategy 1: All sessions start at once
- Strategy 2: Progressive ramp-up (10, 20, 30... 500 with 3-min gaps)
"""

import asyncio
import logging
from python_service_nuc_async import run_load_test, run_progressive_load_test, NUM_SESSIONS, COURSES
from config import RAMP_START_SESSIONS, RAMP_MAX_SESSIONS, RAMP_INCREMENT, RAMP_INTERVAL_SECONDS

import warnings
warnings.filterwarnings("ignore")
# Configure logger for main module
logger = logging.getLogger(__name__)

# Load Test Strategy Configuration
USE_PROGRESSIVE_RAMPUP = True  # Set to False for Strategy 1 (all at once)


async def main():
    """
    Main async function to run the load test with logging and success tracking.
    """
    logger.info("="*80)
    logger.info("NUC Python Load Testing Application (Async I/O)")
    logger.info("="*80)
    logger.info("")
    
    if USE_PROGRESSIVE_RAMPUP:
        # Strategy 2: Progressive ramp-up
        stats = await run_progressive_load_test(
            start_sessions=RAMP_START_SESSIONS,
            max_sessions=RAMP_MAX_SESSIONS,
            increment=RAMP_INCREMENT,
            ramp_interval=RAMP_INTERVAL_SECONDS
        )
    else:
        # Strategy 1: All sessions at once
        stats = await run_load_test(num_sessions=NUM_SESSIONS)
    
    # Display success statistics
    logger.info("")
    logger.info("="*80)
    logger.info("LOAD TEST RESULTS & SUCCESS STATISTICS")
    logger.info("="*80)
    logger.info(f"Total Sessions Started: {stats['total_sessions']}")
    logger.info(f"Sessions with Successful Setup: {stats['setup_successful_sessions']}")
    logger.info(f"Successful Sessions (all Q&A completed): {stats['successful_sessions']}")
    logger.info(f"Failed Sessions: {stats['failed_sessions']}")
    logger.info(f"Session Success Rate: {stats['session_success_rate']:.2f}%")
    logger.info("")
    logger.info(f"Total Questions Sent: {stats['total_questions_sent']}")
    logger.info(f"Total Responses Received: {stats['total_responses_received']}")
    logger.info(f"Response Success Rate: {stats['success_rate']:.2f}%")
    logger.info("")
    logger.info("CONCURRENT INVOCATION STATISTICS:")
    logger.info(f"  Peak Concurrent Invocations: {stats['peak_concurrent_invocations']}")
    logger.info(f"  Final Concurrent Invocations: {stats['final_concurrent_invocations']}")
    logger.info(f"  Total Invocations Started: {stats['total_invocations_started']}")
    logger.info(f"  Total Invocations Completed: {stats['total_invocations_completed']}")
    
    # Calculate average concurrent invocations (rough estimate)
    if stats['total_invocations_completed'] > 0:
        logger.info(f"  Avg Concurrent (rough): ~{stats['peak_concurrent_invocations'] // 2}")
    
    # Show error statistics
    if 'error_statistics' in stats:
        err_stats = stats['error_statistics']
        logger.info("")
        logger.info("ERROR STATISTICS (Capacity Issues):")
        logger.info(f"  502 Bad Gateway Errors: {err_stats['502_bad_gateway_count']} (Sessions: {err_stats['502_bad_gateway_sessions']})")
        if err_stats['503_service_unavailable_sessions'] > 0:
            logger.info(f"  503 Service Unavailable: {err_stats['503_service_unavailable_sessions']} sessions")
        if err_stats['504_gateway_timeout_sessions'] > 0:
            logger.info(f"  504 Gateway Timeout: {err_stats['504_gateway_timeout_sessions']} sessions")
        if err_stats['handshake_errors'] > 0:
            logger.info(f"  Handshake Errors: {err_stats['handshake_errors']} sessions")
        if err_stats['other_connection_errors'] > 0:
            logger.info(f"  Other Connection Errors: {err_stats['other_connection_errors']} sessions")
        logger.info(f"  Total Connection Errors: {err_stats['total_connection_errors']}")
        logger.info(f"  Setup Failures: {err_stats['setup_failures']}")
        
        # Calculate error rates
        total_errors = err_stats['502_bad_gateway_sessions'] + err_stats['total_connection_errors']
        if stats['total_sessions'] > 0:
            error_rate = (total_errors / stats['total_sessions']) * 100
            logger.info(f"  Connection Error Rate: {error_rate:.2f}%")
    
    # Show ramp-up stages if using progressive strategy
    if 'ramp_stages' in stats and stats['ramp_stages']:
        logger.info("")
        logger.info("RAMP-UP STAGES:")
        for stage_info in stats['ramp_stages']:
            logger.info(f"  Stage {stage_info['stage']}: {stage_info['sessions']} sessions "
                       f"(Cumulative: {stage_info['cumulative_sessions']})")
    
    logger.info("")
    
    # Show missing responses if any
    missing_responses = stats['total_questions_sent'] - stats['total_responses_received']
    if missing_responses > 0:
        logger.info(f"⚠️  WARNING: {missing_responses} responses were not received")
    else:
        logger.info("✓ All questions received responses successfully!")
    
    logger.info("="*80)
    
    # Optional: Show breakdown by session (for detailed analysis)
    if stats['failed_sessions'] > 0:
        logger.info("")
        logger.info("Failed Sessions Details:")
        for result in stats['individual_results']:
            if not result['successful']:
                logger.info(f"  Session {result['session_index']}: "
                          f"Sent={result['questions_sent']}, "
                          f"Received={result['responses_received']}, "
                          f"Setup={'OK' if result['setup_successful'] else 'FAILED'}")


if __name__ == "__main__":
    asyncio.run(main())
