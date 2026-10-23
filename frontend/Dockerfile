FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_DEMO_ADMIN_EMAIL=admin@invoice.local
ARG VITE_DEMO_ADMIN_PASSWORD=change-me
ARG VITE_DEMO_USER_EMAIL=ivan@invoice.local
ARG VITE_DEMO_USER_PASSWORD=change-me-user
ARG VITE_DEMO_USER_TWO_EMAIL=maria@invoice.local
ENV VITE_DEMO_ADMIN_EMAIL=$VITE_DEMO_ADMIN_EMAIL \
    VITE_DEMO_ADMIN_PASSWORD=$VITE_DEMO_ADMIN_PASSWORD \
    VITE_DEMO_USER_EMAIL=$VITE_DEMO_USER_EMAIL \
    VITE_DEMO_USER_PASSWORD=$VITE_DEMO_USER_PASSWORD \
    VITE_DEMO_USER_TWO_EMAIL=$VITE_DEMO_USER_TWO_EMAIL
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
