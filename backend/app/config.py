import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # read all variables from .env file
    COSMOS_ENDPOINT = os.getenv("COSMOS_ENDPOINT")
    COSMOS_DATABASE_NAME = os.getenv("COSMOS_DATABASE_NAME")
    BLOB_ENDPOINT = os.getenv("BLOB_ENDPOINT")
    APPLICATIONINSIGHTS_CONNECTION_STRING = os.getenv(
        "APPLICATIONINSIGHTS_CONNECTION_STRING"
    )
    ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")
    REFRESH_TOKEN_SECRET = os.getenv("REFRESH_TOKEN_SECRET")
    ALGORITHM = os.getenv("ALGORITHM")

    # temp PETER
    OPENAI_ENDPOINT = os.getenv("OPENAI_ENDPOINT")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    PROJECT_ENDPOINT = os.getenv("PROJECT_ENDPOINT")
    REDIS_CONNECTION_URL = os.getenv("REDIS_CONNECTION_URL")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    # const variables
    ACCESS_TOKEN_EXPIRE_MINUTES = 30  # Token valid for 30 minutes
    REFRESH_TOKEN_EXPIRE_DAYS = 14  # Token valid for 14 days


settings = Settings()
