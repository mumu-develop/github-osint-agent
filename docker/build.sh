#!/bin/bash
# 构建定制沙箱镜像

set -e

IMAGE_NAME="osint-sandbox"
IMAGE_TAG="v1.0.0"
REGISTRY="sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com"

# 沙箱目录配置（与 backend_factory.py SANDBOX_DIRS 保持一致）
SANDBOX_DIRS="/analysis /reports /memories /persisted-skills /workspace"

# 完整镜像路径
FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"

echo "=========================================="
echo "构建定制沙箱镜像"
echo "镜像: ${FULL_IMAGE}"
echo "目录: ${SANDBOX_DIRS}"
echo "=========================================="

cd "$(dirname "$0")"

# 构建镜像（传入目录参数）
docker build \
    -t "${FULL_IMAGE}" \
    -f Dockerfile.sandbox \
    --build-arg SANDBOX_DIRS="${SANDBOX_DIRS}" \
    .

echo "=========================================="
echo "构建完成！"
echo "=========================================="

# 推送镜像（需要登录到镜像仓库）
echo "如需推送镜像，请执行："
echo "  docker push ${FULL_IMAGE}"
echo ""
echo "或登录后再推送："
echo "  docker login ${REGISTRY}"
echo "  docker push ${FULL_IMAGE}"

# 显示镜像信息
echo ""
echo "镜像信息："
docker images "${FULL_IMAGE}"