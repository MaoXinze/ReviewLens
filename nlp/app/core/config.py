"""NLP 服务配置（Pydantic Settings，M4 扩充）。

model_dir/data_dir 默认相对项目根；部署时可用环境变量覆盖为绝对路径。
训练/评测门限集中于此，保持可配置。
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "reviewlens-nlp"
    debug: bool = False

    model_dir: str = str(BASE_DIR / "app" / "models")
    data_dir: str = str(BASE_DIR / "app" / "data")
    taxonomy_file: str = str(BASE_DIR / "app" / "data" / "aspect_taxonomy.json")

    # 训练/评测默认参数
    default_test_size: float = 0.2
    default_random_seed: int = 42
    tfidf_max_features: int = 50000
    lr_c: float = 1.0
    lr_max_iter: int = 1000

    # 分层推理（P7.4/M11）：基线优先，低置信送深度模型复核
    cascade_enabled: bool = True
    cascade_theta_high: float = 0.70  # P7.4 扫描最优点：省约 40% 深度调用且精度无损
    cascade_deep_model: str = str(
        BASE_DIR / "app" / "models" / "distilbert_e2_qwen2026_llm"
    )  # 三组蒸馏中 F1 最高的生产模型

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    def ensure_dirs(self) -> None:
        """确保模型/数据目录存在（幂等）。"""
        for directory in (self.model_dir, self.data_dir):
            Path(directory).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()