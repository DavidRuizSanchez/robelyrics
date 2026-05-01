# syntax=docker/dockerfile:1.6
FROM node:20-alpine

# pnpm vía corepack (ya viene con node 20)
RUN corepack enable && corepack prepare pnpm@9.12.3 --activate

WORKDIR /app

# Capa cacheable de dependencias
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --no-frozen-lockfile

COPY . .

EXPOSE 3000

CMD ["pnpm", "dev"]
