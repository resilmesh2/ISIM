FROM node:23.1.0-bullseye-slim

RUN mkdir -p /app
WORKDIR /app

COPY package.json .
RUN npm install
COPY . .
RUN npm run build

EXPOSE 4001

CMD ["npm", "start"]
