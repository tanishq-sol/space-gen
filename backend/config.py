from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    gemini_api_key: str = ""
    gemini_fast_model: str = "gemini-2.5-flash"
    gemini_image_model: str = "gemini-2.5-flash"
    gemini_reasoning_model: str = "gemini-2.5-pro"
    cors_origins: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

settings = Settings()
