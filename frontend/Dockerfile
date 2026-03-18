FROM node:20-slim

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

# Accept build-time API URL
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
