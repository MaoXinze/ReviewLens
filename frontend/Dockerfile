# ReviewLens 前端镜像：Node 构建静态资源 → nginx 托管并反代后端
FROM node:22-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

# 同源部署：/api 由 nginx 反代到 backend 容器
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
