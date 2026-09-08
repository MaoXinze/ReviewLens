# ReviewLens Elasticsearch 镜像：基础镜像 + IK 分词器插件
#
# 构建参数 IK_VERSION 需与基础镜像版本一致（默认 8.15.0）。
# IK 插件由 infinilabs 官方托管在 release.infinilabs.com，非 GitHub Release。
ARG ES_VERSION=8.15.0
FROM elasticsearch:${ES_VERSION}
ARG IK_VERSION=${ES_VERSION}
ARG IK_BASE=https://release.infinilabs.com/analysis-ik/stable
RUN bin/elasticsearch-plugin install --batch "${IK_BASE}/elasticsearch-analysis-ik-${IK_VERSION}.zip" \
    || echo "[warn] IK 插件下载失败，ES 仍将启动但中文分词不可用"