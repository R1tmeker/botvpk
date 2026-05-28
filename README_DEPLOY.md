# Деплой и настройка (инструкции)

Краткий план действий для безопасного деплоя приложения `botvpk` на сервер и настройки CI/CD.

1) Сгенерировать SSH deploy‑ключ на вашей локальной машине:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/botvpk_deploy_key -C "deploy@botvpk"
```

2) Установить публичный ключ на сервере (как root или нужный пользователь):

```bash
# на локали
ssh-copy-id -i ~/.ssh/botvpk_deploy_key.pub root@82.39.213.57
```

3) Локально: подготовить коммит и запушить в GitHub (замените `origin` и `main` при необходимости):

```bash
git add -A
git commit -m "Add deploy workflow and scripts"
git push origin main
```

4) В GitHub → Settings → Secrets → Repository secrets добавить:
- `SSH_PRIVATE_KEY` — содержимое `~/.ssh/botvpk_deploy_key` (приватный ключ)
- `SERVER_HOST` — `82.39.213.57`
- `SERVER_USER` — `root` (или другой пользователь)
- `DEPLOY_PATH` — путь на сервере, например `/opt/botvpk`

5) На сервере: создайте каталог deploy и установите права, переместите код в `DEPLOY_PATH`.

6) Настройка systemd (примерный юнит в `systemd/botvpk.service`). После размещения файла выполните:

```bash
sudo cp systemd/botvpk.service /etc/systemd/system/botvpk.service
sudo systemctl daemon-reload
sudo systemctl enable --now botvpk.service
sudo journalctl -u botvpk -f
```

7) Добавьте секреты приложения в `/opt/botvpk/.env` (или другой путь) и поставьте права доступа только для пользователя сервиса.

8) Тест Telegram уведомлений локально перед выкладкой, использовав `scripts/check_telegram.py`.

Если нужно — могу помочь выполнить шаги через VS Code Remote‑SSH или подсказать команды точнее под ваш сервер.
