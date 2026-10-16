FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json ./
# npm ci installs exactly what the lockfile pins, so the image matches local dev.
RUN npm ci
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
