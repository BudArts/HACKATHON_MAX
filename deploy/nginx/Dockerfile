FROM node:22-alpine AS miniapp
WORKDIR /build
ARG VITE_DEV_LOGIN=false
ENV VITE_DEV_LOGIN=$VITE_DEV_LOGIN
COPY miniapp/package*.json ./
RUN npm ci
COPY miniapp/ ./
RUN npm run build

FROM nginx:1.27-alpine
RUN apk add --no-cache curl
COPY deploy/nginx/nginx.conf /etc/nginx/nginx.conf
COPY deploy/nginx/conf.d/ /etc/nginx/templates/
COPY deploy/nginx/select-config.sh /docker-entrypoint.d/05-select-config.sh
RUN chmod +x /docker-entrypoint.d/05-select-config.sh
COPY --from=miniapp /build/dist /var/www/miniapp
EXPOSE 80 443
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fsS http://127.0.0.1/nginx-health || exit 1
