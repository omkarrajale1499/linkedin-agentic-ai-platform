from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_database: str = "linkedin_ds"
    mysql_user: str = "appuser"
    mysql_password: str = "apppassword"

    mongo_host: str = "mongodb"
    mongo_port: int = 27017
    mongo_database: str = "linkedin_ds_logs"
    mongo_user: str = "appuser"
    mongo_password: str = "apppassword"

    redis_host: str = "redis"
    redis_port: int = 6379

    kafka_broker: str = "kafka:9092"
    kafka_analytics_group: str = "analytics-consumer-group-fastapi"

    jwt_secret: str = "changeme"

    ai_agent_url: str = "http://ai-agent-service:8000"

    cache_ttl: int = 300


settings = Settings()
