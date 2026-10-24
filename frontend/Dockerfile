# Development image. A production build (next build + standalone output) is added in Phase 6.
FROM node:22-alpine

ENV NEXT_TELEMETRY_DISABLED=1
# npm 10 (bundled with Node 22) crashes resolving this dependency tree's peer sets; npm 11 does not.
RUN npm install -g npm@11.6.0
WORKDIR /app
RUN chown node:node /app
USER node

COPY --chown=node:node package.json package-lock.json ./
RUN npm ci

COPY --chown=node:node . .
# Pre-create .next so the compose volume mounted there is writable by the node user.
RUN mkdir -p .next

EXPOSE 3000
CMD ["npm", "run", "dev"]
