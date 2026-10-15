# ---- Stage 1: build frontend assets ----
FROM node:20-alpine AS frontend
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---- Stage 2: PHP runtime ----
FROM php:8.4-cli-alpine

RUN apk add --no-cache \
    sqlite-dev \
    libzip-dev \
    oniguruma-dev \
    icu-dev \
    bash \
    curl \
    tzdata \
    && docker-php-ext-install pdo_sqlite mbstring zip intl bcmath opcache

ENV TZ=Africa/Lagos

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer
WORKDIR /var/www/html

COPY . .

# Copy the fresh build from stage 1 — this OVERRIDES whatever is in public/build/
# in the context above, ensuring the image always has up-to-date assets.
COPY --from=frontend /app/public/build ./public/build

RUN mkdir -p storage/framework/cache/data storage/framework/sessions storage/framework/views storage/logs bootstrap/cache
RUN chmod -R 775 storage bootstrap/cache
RUN chown -R root:root storage bootstrap/cache

RUN composer install --no-dev --optimize-autoloader --no-interaction

RUN chown -R www-data:www-data storage bootstrap/cache database \
    && chmod -R 775 storage bootstrap/cache database

EXPOSE 80
CMD ["php", "artisan", "serve", "--host=0.0.0.0", "--port=80"]
