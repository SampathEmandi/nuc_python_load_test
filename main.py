"""
Main entry point for the NUC Python load testing application.

This module orchestrates concurrent chatbot load testing sessions
with simple logging of questions and responses.
"""

import logging
from python_service_nuc import run_load_test, NUM_SESSIONS, COURSES

import warnings
warnings.filterwarnings("ignore")
# Configure logger for main module
logger = logging.getLogger(__name__)


def main():
    """
    Main function to run the load test with logging.
    """
    logger.info("="*80)
    logger.info("NUC Python Load Testing Application")
    logger.info("="*80)
    
    # Run the load test (each session will ask ALL questions)
    run_load_test(num_sessions=NUM_SESSIONS)


if __name__ == "__main__":
    main()
