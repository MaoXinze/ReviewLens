"""应用配置（Pydantic Settings）。

读取 backend/.env 中的环境变量。JWT 密钥缺失时在引擎启动阶段报错，避免弱配置进入生产。
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "reviewlens-backend"
    debug: bool = False

    # API 前缀
    api_prefix: str = "/api"
    auth_prefix: str = "/api/auth"

    # CORS 白名单（不使用正则通配）
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # 数据库（PostgreSQL，Docker Compose 默认；宿主端口 15432 避开 Windows 保留段）
    database_url: str = (
        "postgresql+asyncpg://reviewlens:reviewlens_dev_only@localhost:15432/reviewlens"
    )

    # 队列（Redis，ARQ 异步任务）
    redis_url: str = "redis://localhost:6379/0"

    # Elasticsearch
    elasticsearch_host: str = "http://localhost:9200"
    reviews_index: str = "reviews"

    # MinIO 对象存储
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "reviewlens_admin"
    minio_secret_key: str = "reviewlens_minio_dev_only"
    minio_bucket: str = "reviewlens"
    minio_secure: bool = False

    # 数据导入
    import_batch_size: int = 1000
    max_review_text_length: int = 5000

    # NLP 服务（M4，内部 HTTP 调用）
    nlp_base_url: str = "http://localhost:8100"
    nlp_inference_timeout: float = 120.0
    nlp_training_timeout: float = 600.0
    # 触发训练所需的最低标注样本数（P2 用评分映射弱标签，>=200）
    min_training_samples: int = 200
    # 单次训练的样本采样上限（控制 LR 训练耗时）
    training_sample_cap: int = 3000
    # 训练/评测默认参数（可复现：相同 seed 得相同指标）
    default_random_seed: int = 42
    default_test_size: float = 0.2
    # 推理批次大小（与导入批次一致）
    inference_batch_size: int = 1000
    # 置信度低于该值的预测标记为待审核（供 M5）
    low_confidence_threshold: float = 0.7

    # JWT
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # 登录/注册防爆破限流（进程内滑动窗口）
    login_max_failures: int = 5  # 单 IP+邮箱 窗口内最大失败次数
    login_ip_max_failures: int = 30  # 单 IP 窗口内最大失败次数（防扫号）
    auth_rate_window_seconds: int = 300

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    def ensure_security(self) -> None:
        """启动期校验：JWT 密钥必须存在，否则拒绝启动。"""
        if not self.jwt_secret_key or len(self.jwt_secret_key) < 16:
            raise RuntimeError(
                "JWT_SECRET_KEY 未配置或长度不足(>=16)。"
                "请复制 .env.example 为 .env 并设置强随机密钥。"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
