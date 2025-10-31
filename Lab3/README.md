## Развёртывание бота с ngrok (Lab3)

Цель: запустить вашего Telegram-бота локально, но сделать доступным из интернета через ngrok с использованием webhook.

### Состав
- `bot.py` — бот с поддержкой polling и webhook (вкл. через `USE_WEBHOOK=1`).
- `requirements.txt` — зависимости (`python-telegram-bot`, `pandas`, `openpyxl`, `python-dotenv`, `pytz`).
- `data.json` — данные компании/команды/событий/дайджестов.
- `employees.csv` — сотрудники для команд `/departments`, `/staff`, `/find`.
- `.env.example` — пример конфигурации.
- `start_ngrok.ps1` / `start_ngrok.sh` — запуск ngrok на нужном порту.

### Установка зависимостей
```
pip install -r requirements.txt
```

### Конфигурация окружения
Создайте `.env` рядом с `bot.py`:
```
BOT_TOKEN=ваш_токен_бота
TIMEZONE=Europe/Moscow

# Для webhook-режима
USE_WEBHOOK=1
WEBHOOK_LISTEN=0.0.0.0
WEBHOOK_PORT=8080
WEBHOOK_PATH=/webhook
# Замените на ваш публичный URL после запуска ngrok, например https://abcd-12-34-56-78.ngrok-free.app
PUBLIC_URL=
```

### Шаги запуска с ngrok
1) Установите и авторизуйте ngrok (`ngrok config add-authtoken <TOKEN>`).
2) Запустите проброс локального порта 8080:
   - Windows PowerShell:
     ```
     ./start_ngrok.ps1
     ```
   - macOS/Linux:
     ```
     ./start_ngrok.sh
     ```
3) Скопируйте выданный публичный URL (формата `https://*.ngrok-free.app`) в `.env` → `PUBLIC_URL`.
4) Запустите бота в webhook-режиме:
   ```
   python bot.py
   ```

`bot.py` сам вызовет `run_webhook` и зарегистрирует webhook у Telegram на URL `PUBLIC_URL + WEBHOOK_PATH`.

### Проверка
- Напишите боту `/start`, затем `/help`.
- Для CSV/Excel команд убедитесь, что `employees.csv` или `employees.xlsx` лежит рядом с `bot.py`.

### Смена режима на polling
Если хочется работать без ngrok, используйте polling: в `.env` установите `USE_WEBHOOK=0` (или удалите переменную) и запустите `python bot.py`.


