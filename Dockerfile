# Production-образ бота — для переносимости (docker run / другой PaaS / k8s).
# ВАЖНО: на Railway сборка идёт через nixpacks (см. railway.toml), этот
# Dockerfile там НЕ используется — он для локального запуска и портируемости.

FROM python:3.11-slim

# Не писать .pyc, не буферизировать stdout (логи сразу видны)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Сначала зависимости — слой кешируется, пока requirements не менялись
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Затем код
COPY . .

# Запуск от непривилегированного пользователя (безопасность)
RUN useradd --create-home --uid 1000 appuser
USER appuser

# Бот работает через long polling — HTTP-порт не нужен
CMD ["python", "bot.py"]
