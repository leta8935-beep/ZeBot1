# Используем официальный образ Playwright с Python и предустановленным Chromium
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем и устанавливаем Python-зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальной код
COPY . .

# Команда запуска
CMD ["python", "main.py"]
