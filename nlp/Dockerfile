# ReviewLens NLP 服务镜像（推理精简版：基线 TF-IDF+LR + 规则属性抽取）
# 不含 torch/transformers：深度模型缺失时级联自动回退基线路径，接口契约不变。
# 需要 DistilBERT 训练/级联复核时，请基于完整 requirements.txt 自行构建。
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv/app

COPY requirements-slim.txt ./
RUN pip install --no-cache-dir -r requirements-slim.txt

COPY app ./app

# 训练产物（基线 joblib / 状态文件）持久化到卷，重启不丢
VOLUME ["/srv/app/app/models"]

EXPOSE 8100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
