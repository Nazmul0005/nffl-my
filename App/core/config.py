import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
env_path = Path(__file__).resolve().parent.parent.parent / '.env'
print(f"Loading .env file from: {env_path}")
load_dotenv(dotenv_path=env_path)

# Print environment variables for debugging
api_key = os.getenv("FANTASY_NERDS_API_KEY")
if not api_key:
    raise ValueError("FANTASY_NERDS_API_KEY not found in environment variables. Please add it to your .env file.")

base_url = "https://api.fantasynerds.com/v1/nfl"
gpt_api_key = os.getenv("GPT_API_KEY")  # Added GPT API Key
print(f"Fantasy Nerds API Key loaded: {'*' * 4}{api_key[-4:] if api_key else 'Not found'}")
print(f"Base URL loaded: {base_url}")
print(f"GPT API Key loaded: {'*' * 4}{gpt_api_key[-4:] if gpt_api_key else 'Not found'}")

class Settings:
    API_KEY: str = api_key
    BASE_URL: str = base_url
    GPT_API_KEY: str = gpt_api_key  # Added GPT API Key
    
    # API Info for Swagger UI
    API_TITLE: str = "NFL Fantasy Data API"
    API_DESCRIPTION: str = "API for fetching NFL data from Fantasy Nerds"
    API_VERSION: str = "0.2.0"

settings = Settings()
