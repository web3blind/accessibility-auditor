# Accessibility Auditor - Deployment Guide

Развёртывание на собственном сервере с доменом hexdrive.tech

## Архитектура

```
Internet → hexdrive.tech:443 (HTTPS)
    ↓
nginx (reverse proxy)
    ↓
localhost:3000 (bot_final.py)
├─ Telegram bot (async polling)
└─ FastAPI web + API (async)
```

## Предварительные требования

- Ubuntu/Debian сервер
- root или sudo доступ
- Домен hexdrive.tech (DNS указывает на IP сервера)
- Python 3.12+
- nginx установлен

## Пошаговая инструкция

### 1. Подготовка

```bash
# Обновить репозиторий
cd ~/.hermes/agents/accessibility-auditor
git pull

# Убедиться, что venv установлен
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Настройка nginx

#### 2.1. Скопировать конфиг

```bash
sudo cp ~/.hermes/agents/accessibility-auditor/nginx.conf \
    /etc/nginx/sites-available/hexdrive.tech
```

#### 2.2. Включить сайт

```bash
sudo ln -s /etc/nginx/sites-available/hexdrive.tech \
    /etc/nginx/sites-enabled/hexdrive.tech

# Отключить default если нужно
sudo rm /etc/nginx/sites-enabled/default 2>/dev/null || true
```

#### 2.3. Проверить конфиг

```bash
sudo nginx -t
```

Должно вывести:
```
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

#### 2.4. Перезагрузить nginx

```bash
sudo systemctl reload nginx
```

### 3. Let's Encrypt SSL (HTTPS)

#### 3.1. Установить certbot

```bash
sudo apt-get update
sudo apt-get install -y certbot python3-certbot-nginx
```

#### 3.2. Получить сертификат

```bash
sudo certbot certonly --nginx -d hexdrive.tech -d www.hexdrive.tech
```

Следуй инструкциям на экране:
- Введи email
- Примени Terms of Service
- Выбери опции по предпочтению

#### 3.3. Перезагрузить nginx (сертификат будет применён)

```bash
sudo systemctl reload nginx
```

#### 3.4. Auto-renewal (автоматическое обновление сертификата)

```bash
# Включить auto-renewal
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer

# Проверить статус
sudo systemctl status certbot.timer
```

### 4. DNS настройка

В панели управления доменом (регистратор):

- Тип: A
- Имя: @ (или hexdrive.tech)
- Значение: IP_ТВОЕГО_СЕРВЕРА
- TTL: 300 или меньше

Проверить:
```bash
nslookup hexdrive.tech
# или
dig hexdrive.tech
```

### 5. Запуск бота

#### 5.1. Убедиться, что переменная окружения установлена

```bash
echo $TELEGRAM_BOT_TOKEN
# Если пусто:
export TELEGRAM_BOT_TOKEN="твой_токен_здесь"
```

#### 5.2. Первый запуск (тест)

```bash
cd ~/.hermes/agents/accessibility-auditor
source venv/bin/activate
python3 -u bot_final.py
```

Должны увидеть:
```
Telegram bot initializing...
Starting FastAPI server on http://127.0.0.1:3000 (localhost only)
```

Нажать Ctrl+C для остановки

#### 5.3. Запустить в фоне

```bash
nohup python3 -u ~/.hermes/agents/accessibility-auditor/bot_final.py \
    >> ~/.hermes/agents/accessibility-auditor/bot.log 2>&1 &
```

Проверить:
```bash
ps aux | grep bot_final.py
```

### 6. Cronjob для keep-alive (перезапуск если упал)

#### 6.1. Сделать скрипт исполняемым

```bash
chmod +x ~/.hermes/agents/accessibility-auditor/keep-alive.sh
```

#### 6.2. Добавить в crontab

```bash
# Открыть редактор crontab
crontab -e

# Добавить эту строку (каждую минуту):
*/1 * * * * ~/.hermes/agents/accessibility-auditor/keep-alive.sh
```

#### 6.3. Проверить

```bash
# Список активных cronjobs
crontab -l

# Журнал keep-alive
tail -f ~/.hermes/agents/accessibility-auditor/keep-alive.log
```

## Проверка работы

### Проверить API (локально на сервере)

```bash
curl http://127.0.0.1:3000/health
# Ответ: {"status":"ok"}

curl https://hexdrive.tech/health
# Ответ: {"status":"ok"}
```

### Проверить веб-интерфейс

Открыть в браузере: **https://hexdrive.tech**

Должны увидеть:
- Форму для ввода URL
- Чекбокс "Allow public display"
- Список последних публичных аудитов

### Проверить Telegram бота

Отправить `/audit https://example.com` боту @accessibilityAuditAgentBot

Должен ответить с результатами и ссылкой на hexdrive.tech

## Мониторинг

### Логи nginx

```bash
tail -f /var/log/nginx/accessibility-auditor-access.log
tail -f /var/log/nginx/accessibility-auditor-error.log
```

### Логи бота

```bash
tail -f ~/.hermes/agents/accessibility-auditor/bot.log
```

### Логи keep-alive

```bash
tail -f ~/.hermes/agents/accessibility-auditor/keep-alive.log
```

### Проверить процесс

```bash
ps aux | grep bot_final
pgrep -f bot_final.py
```

## Обновление

```bash
cd ~/.hermes/agents/accessibility-auditor
git pull
source venv/bin/activate
pip install -r requirements.txt

# Перезагрузить процесс (keep-alive сделает автоматически)
pkill -f bot_final.py
# или подожди 1 минуту, cronjob перезапустит

# Проверить
curl https://hexdrive.tech/health
```

## Решение проблем

### nginx показывает 502 Bad Gateway

```bash
# Проверить, работает ли bot
ps aux | grep bot_final.py

# Если нет - запустить вручную
source ~/.hermes/agents/accessibility-auditor/venv/bin/activate
cd ~/.hermes/agents/accessibility-auditor
python3 -u bot_final.py

# Проверить логи
tail -f ~/.hermes/agents/accessibility-auditor/bot.log
```

### SSL сертификат не работает

```bash
# Проверить статус
sudo certbot status

# Обновить вручную
sudo certbot renew --force-renewal

# Перезагрузить nginx
sudo systemctl reload nginx
```

### Cronjob не запускается

```bash
# Проверить, запущен ли cron-демон
sudo systemctl status cron

# Проверить логи cron
grep CRON /var/log/syslog | tail -20

# Убедиться, что скрипт исполняемый
ls -la ~/.hermes/agents/accessibility-auditor/keep-alive.sh
# Должен быть: -rwxr-xr-x (755)
```

## Готово! 🚀

Теперь у тебя есть:
- ✅ Accessibility Auditor доступен на https://hexdrive.tech
- ✅ Telegram bot работает
- ✅ API скрыт за nginx (боты не увидят)
- ✅ HTTPS с Let's Encrypt (бесплатный, автоматическое обновление)
- ✅ Auto-restart если упадёт (cronjob каждую минуту)

## Командная строка для быстрого старта

Если у тебя на сервере уже nginx и Let's Encrypt:

```bash
# 1. Скопировать nginx конфиг
sudo cp ~/.hermes/agents/accessibility-auditor/nginx.conf /etc/nginx/sites-available/hexdrive.tech
sudo ln -s /etc/nginx/sites-available/hexdrive.tech /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 2. SSL сертификат
sudo certbot certonly --nginx -d hexdrive.tech -d www.hexdrive.tech

# 3. Запустить бот
source ~/.hermes/agents/accessibility-auditor/venv/bin/activate
nohup python3 -u ~/.hermes/agents/accessibility-auditor/bot_final.py >> ~/.hermes/agents/accessibility-auditor/bot.log 2>&1 &

# 4. Cronjob
chmod +x ~/.hermes/agents/accessibility-auditor/keep-alive.sh
(crontab -l 2>/dev/null; echo "*/1 * * * * ~/.hermes/agents/accessibility-auditor/keep-alive.sh") | crontab -

# 5. Проверить
curl https://hexdrive.tech/health
```
