# syntax=docker/dockerfile:1

FROM node:20-slim AS frontend
WORKDIR /frontend
COPY ["interface/icodex_figma_interface/package.json", "interface/icodex_figma_interface/package-lock.json", "./"]
RUN npm ci
COPY ["interface/icodex_figma_interface/", "./"]
RUN npm run build

FROM python:3.11-slim AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY ["interface/icodex_webapp/requirements.txt", "./requirements.txt"]
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend ["/frontend/build", "./interface/icodex_figma_interface/build"]

ENV PORT=10000
EXPOSE 10000

CMD ["python", "run.py"]
