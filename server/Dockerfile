FROM node:24-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY tsconfig.json echo.ts protocol.ts probe-resample.ts server.ts ./
RUN npm run build && npm prune --omit=dev --ignore-scripts --no-audit --no-fund

FROM node:24-bookworm-slim
ENV NODE_ENV=production PORT=8080
WORKDIR /app
COPY --from=build --chown=node:node /app/package.json ./
COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/dist ./dist
USER node
EXPOSE 8080
CMD ["node", "dist/server.js"]
