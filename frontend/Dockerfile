FROM node:22-alpine AS build
ARG VITE_GIT_COMMIT=unknown
COPY .git/ /app/.git/
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN commit="$VITE_GIT_COMMIT"; \
    if [ "$commit" = "unknown" ] && [ -f /app/.git/HEAD ]; then \
      head="$(cat /app/.git/HEAD)"; \
      case "$head" in \
        "ref: "*) \
          ref="${head#ref: }"; \
          if [ -f "/app/.git/$ref" ]; then \
            commit="$(cat "/app/.git/$ref")"; \
          elif [ -f /app/.git/packed-refs ]; then \
            commit="$(awk -v ref="$ref" '$2 == ref { print $1; exit }' /app/.git/packed-refs)"; \
          fi \
          ;; \
        *) commit="$head" ;; \
      esac; \
    fi; \
    VITE_GIT_COMMIT="${commit:-unknown}" npm run build

FROM nginx:1.27-alpine
COPY frontend/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
