# ===== 前端构建镜像 =====
# node 构建 → nginx 托管

FROM node:22-alpine AS builder
WORKDIR /app

# 依赖缓存层
COPY package.json pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile

# 构建产物
COPY . .
RUN pnpm build

# ===== 运行镜像：nginx 托管静态产物 =====
# 复用本地已有镜像 nginx:latest
FROM nginx:latest
COPY --from=builder /app/dist /usr/share/nginx/html
# 覆盖默认配置：支持 SPA 路由 + /api 反向代理到后端
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]