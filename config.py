import os
from dotenv import load_dotenv

load_dotenv()

KAFKA_BROKER = os.getenv('KAFKA_BROKER', 'localhost:9092')
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))

PROFILE_SERVICE_URL = os.getenv('PROFILE_SERVICE_URL', 'http://platform-api:3000')
JOB_SERVICE_URL = os.getenv('JOB_SERVICE_URL', 'http://platform-api:3000')
APPLICATION_SERVICE_URL = os.getenv('APPLICATION_SERVICE_URL', 'http://platform-api:3000')

# Groq OpenAI-compatible API (https://console.groq.com/docs/openai-compat)
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')
GROQ_BASE_URL = (os.getenv('GROQ_BASE_URL', '') or 'https://api.groq.com/openai/v1').rstrip('/')
GROQ_CHAT_COMPLETIONS_URL = f'{GROQ_BASE_URL}/chat/completions'

# Default model — override with LLM_MODEL in environment if needed
LLM_MODEL = os.getenv('LLM_MODEL', '') or os.getenv('GROQ_MODEL', '') or 'llama-3.3-70b-versatile'

AI_INLINE_FALLBACK = os.getenv('AI_INLINE_FALLBACK', 'true').lower() == 'true'
RESUME_PARSER_USE_LLM = os.getenv('RESUME_PARSER_USE_LLM', 'false').lower() == 'true'
CAREER_COACH_USE_LLM = os.getenv('CAREER_COACH_USE_LLM', 'true').lower() == 'true'

MONGO_DATABASE = os.getenv('MONGO_DATABASE', 'linkedin_ds_logs')
MONGO_URI = (
    f"mongodb://{os.getenv('MONGO_USER', 'appuser')}:{os.getenv('MONGO_PASSWORD', 'apppassword')}"
    f"@{os.getenv('MONGO_HOST', 'localhost')}:{os.getenv('MONGO_PORT', 27017)}"
    f"/{MONGO_DATABASE}?authSource=admin"
)
