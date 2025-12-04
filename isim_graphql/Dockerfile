FROM node:23.1.0-bullseye-slim

RUN mkdir -p /app
WORKDIR /app

COPY package.json .
RUN npm cache clean --force
RUN npm install --force --default-timeout=300 --verbose
COPY . .
RUN npm run build

EXPOSE 4001

CMD ["npm", "start"]
