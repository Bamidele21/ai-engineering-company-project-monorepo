# Nexova UI development image.
# Runs both Next.js apps (website + backoffice) from a single container.
FROM node:22-alpine

# Next.js on Alpine needs the GNU libc compatibility shim.
RUN apk add --no-cache libc6-compat

WORKDIR /app/uis

# Install dependencies for each app separately.
COPY website/package.json website/package-lock.json ./website/
COPY backoffice/package.json backoffice/package-lock.json ./backoffice/
RUN cd website && npm ci && cd ../backoffice && npm ci

# Application source. Overlaid by a bind mount at runtime for hot reload.
COPY website ./website
COPY backoffice ./backoffice
COPY start.sh ./start.sh
RUN sed -i 's/\r$//' ./start.sh && chmod +x ./start.sh

EXPOSE 3000 3001
CMD ["sh", "./start.sh"]
