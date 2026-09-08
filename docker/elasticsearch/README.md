# Elasticsearch + IK 初始化

## 说明
- ES 基础镜像：`elasticsearch:8.15.0`
- IK 分词语插件在 `Dockerfile` 构建阶段自动安装
- IK 插件的官方分发地址是 `https://release.infinilabs.com/analysis-ik/stable/`
- 构建产物镜像 tag：`reviewlens/elasticsearch:8.15.0`

## 启动
```bash
docker compose -f docker/docker-compose.yml up -d elasticsearch
```

## 验证 IK 分词
```bash
curl -X POST "http://localhost:9200/_analyze" -H 'Content-Type: application/json' \
  -d '{"analyzer":"ik_max_word","text":"商品评论分析平台"}'
```

## 如果 IK 下载失败
1. 确认 `IK_VERSION` 与基础镜像版本一致（ES 与 IK 主版本必须完全相同）
2. 检查能否访问 `release.infinilabs.com`（必要时开启代理）
3. IK 为可选增强：缺失时 ES 可用，仅中文细粒度分词不可用