# miniapp/ — Legacy Telegram Mini App

> **УСТАРЕЛО.** Эта директория содержит оригинальную vanilla-JS версию Telegram Mini App.
> Она полностью заменена React-приложением в [`frontend/`](../frontend/).

## Что это

Первая версия Mini App — один HTML-файл с vanilla JS, который отправлял коды действий
через `tg.sendData()` обратно боту. Бот получал JSON `{ key, title, role }` и
открывал нужный раздел.

## Статус: НЕ ДЕПЛОИТЬ

Переменная окружения `MINI_APP_URL` должна указывать на сборку из **`frontend/`**,
а не на эту директорию. Если случайно задеплоить `miniapp/`, пользователи
потеряют весь функционал React-приложения.

## Почему сохранена

Оставлена для справки. Перечень ключей (`schedule`, `attendance`, `norms`, `admin`...)
является документацией оригинального протокола `sendData` между Mini App и ботом.

## Полное удаление

```bash
git rm -r miniapp/
```

Весь функционал перенесён во фронтенд: [`frontend/src/screens/App.tsx`](../frontend/src/screens/App.tsx)
