from pydantic_settings import BaseSettings,SettingsConfigDict


_base_config = SettingsConfigDict(
    env_file="app/.env",
    extra="ignore",
    env_ignore_empty=True
)
class DataBaseSettings(BaseSettings):
    DB_HOST:str
    DB_PORT:int
    DB_USERNAME:str
    DB_PASSWORD:str
    DB_NAME:str

    # REDIS_HOST:str
    # REDIS_PORT:int

    REDIS_url:str

    model_config  = _base_config

    @property
    def ASYNC_DB_URL(self):
        return f"postgresql+asyncpg://{self.DB_USERNAME}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    
    @property
    def SYNC_DB_URL(self) -> str:
        return (
            f"postgresql+psycopg2://"
            f"{self.DB_USERNAME}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    # def REDIS_URL(self,db):
    #     return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{db}"
    def REDIS_DB(self, db: int) -> str:
        return f"{self.REDIS_url}/{db}"



class TelegramBotSettings(BaseSettings):
    BOT_TOKEN:str
    @property
    def API_URL(self):
        return f"https://api.telegram.org/bot{self.BOT_TOKEN}/sendMessage"

    model_config = _base_config


class ScraperSettings(BaseSettings):
    base_url: str 
    login_index_url: str 


    model_config = _base_config


scraper_settings = ScraperSettings()
db_settings = DataBaseSettings()
bot_settings = TelegramBotSettings()