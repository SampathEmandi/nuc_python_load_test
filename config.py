"""
Configuration constants for the NUC Python load testing application.
"""

# ============================================================================
# Load Test Configuration
# ============================================================================
NUM_SESSIONS = 5
COURSES = ["MED1060", "BUMA1000"]
# ============================================================================
# API URLs
# ============================================================================
API_BASE_URL = "https://nucapi-dev.bay6.ai"
WEBSOCKET_BASE_URL = "wss://nucaiapi-dev.bay6.ai"
WEBSOCKET_ORIGIN = "https://d1gfs3xs2itqb0.cloudfront.net"

# API Endpoints
GENERATE_TOKEN_URL = f"{API_BASE_URL}/nuc/v1/generate-token"
CREATE_CHAT_URL = f"{API_BASE_URL}/nuc/v1/create-chat"
WEBSOCKET_URL_TEMPLATE = f"{WEBSOCKET_BASE_URL}/v6/chatbot_websocket/default"

# ============================================================================
# API Credentials and Configuration
# ============================================================================
API_ACCESS_KEY = "ac41226316a64b41b874c879c0f2c171"
API_SECRET_KEY = "a26fe7790cd941c5bb7a15f44a1144b1"

# API Headers
API_HEADERS = {
    'environment': 'nuc',
    'request_body_encrypted': '0',
    'need_encrypted_response': '0',
    'enc_version': 'V2',
    'Content-Type': 'application/json',
    'Cookie': 'connect.sid=s%3A_g26x0atnl7Pml4ti2Je_OoEMFvDTjo1.JDgcugahJnqrwVV%2Bdi%2Fvs2pwfx7TUOx0uBoEDNJweK0'
}

# ============================================================================
# User Context Configuration
# ============================================================================
USER_CONTEXT = {
    "user_id": 5570,
    "user_name": "Charitha Veena Talluri",
    "user_email": "ctalluri@bay6.ai",
    "course_id": 395,
    "course_name": "Anatomy and Physiology with Medical Terminology I",
    "course_catalog_code": "MED1060",
}

# ============================================================================
# Metadata Configuration
# ============================================================================
METADATA = {
    "latitude": 17.44263383572146,
    "longitude": 78.38748098260504,
    "ip_address": "183.82.102.247",
    "timezone": "Asia/Calcutta",
}

# ============================================================================
# WebSocket Message Configuration
# ============================================================================
MESSAGE_CONFIG = {
    "request_to_generate_greeting_message": 0,
    "language_code": "en",
    "user_timezone": "UTC",
}


# ============================================================================
# QUESTION POOL - Questions will be randomly assigned based on course
# ============================================================================
course_1_questions = [
    "How does understanding normal anatomy and physiology help in identifying disease or illness?",
    "Why is it helpful to learn medical terms when studying body systems?",
    "What is meant by 'organization of the human body' in this course?",
    "Which body system includes the skin, hair, and nails, and what is one key function of it?",
    "What types of bones make up the skeletal system, and how are they classified?",
    "How do muscles and bones work together to produce body movement?",
    "What is the basic function of neurons in the nervous system?",
    "What is the role of the brain and spinal cord within the nervous system?",
    "What kinds of career paths might use knowledge from this anatomy and physiology course?",
    "How are quizzes and exams used in this course to check your understanding of each module?",
]

course_2_questions = [
    "What is the required textbook for the Introduction to Business (BUMA1000) course?",
    "Which textbook chapters are assigned in Module 1: Fundamentos de los negocios?",
    "What are the three main grade categories and their percentage weights in this course?",
    "Name two ProQuest databases recommended for Module 2 assignments?",
    "Which external resources are suggested for Module 3: Negocios globales?",
    "What is the main focus of Module 4: Fundamentos de gerencia and which textbook chapter supports it?",
    "What are the four management functions mentioned in the course materials?",
    "What is the purpose of the Preprueba and does it affect the final grade?",
    "What is a business plan, and why is it important for entrepreneurs and investors?",
    "What is one key difference between entrepreneurship and management according to the transcript?",
]

general_questions = [
    "Hi, please explain the course description",
    "explain what this course is about",
    "What are the modules of this course?",
    "What topics will I learn in this course?",
    "How is this course structured?",
    "What are the learning objectives?",
    "Can you explain the course content?",
    "What should I expect from this course?",
    "Tell me about the course syllabus",
    "What will I study in this course?",
]

# Map courses to their question pools
COURSE_QUESTIONS = {
    "MED1060": course_1_questions + general_questions,  # Medical course + general questions
    "BUMA1000": course_2_questions + general_questions,  # Business course + general questions
}