FROM node:24-alpine
WORKDIR /app
ARG API_ORIGIN=http://api:8000
ENV API_ORIGIN=$API_ORIGIN
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
EXPOSE 3000
CMD ["npm", "start", "--", "--hostname", "0.0.0.0"]
