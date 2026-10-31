# Пятёрка — первая часть профильного ЕГЭ по математике

Тренажёр ЕГЭ-2026: 12 номеров, 56 типов, теория, 923 опубликованные проверенные задачи, обучение 3+2, основной ИИ-чат, повторения и отдельная отработка ошибок. Django 5.2 / SQLite, согласованный дизайн А.

## Запуск с чистой базы

Из корня репозитория, Python 3.12–3.14:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r trainer/requirements.txt
python trainer/stage2.py migrate
python trainer/stage2.py load_catalog
python trainer/stage2.py seed_catalog_2026 --catalog-only
python trainer/stage2.py import_bank bank/approved_tasks.json
python trainer/stage2.py import_theory
python trainer/stage2.py student create student_1 --name "Ученик 1"
python trainer/stage2.py runserver 127.0.0.1:8080 --noreload --insecure
```

Открыть http://127.0.0.1:8080/ . Команда student запрашивает пароль скрыто. Повторно импортировать банк в уже заполненную базу не нужно: import_bank намеренно отклоняет дубли. load_catalog сохраняет совместимость с тестовыми примерами и тестами; интерфейс использует полный каталог ege_profile_2026.

**Точка входа — trainer/stage2.py**, она включает рабочие маршруты learning_stage2. Название сохранено исторически. Флаг --insecure здесь нужен только для локальной раздачи CSS/шрифтов при DEBUG=False.

## ИИ

Используется `gpt-6.1-sol`, API `https://api.aijuju.rest/v1/chat/completions`. Нужен системный curl. Ключ задаётся переменной AIJUJU_API_KEY или приватным файлом `.runtime/aijuju.key` (0600). Реальные ключи и пароли в репозиторий не включены. Без ключа точная проверка задач банка работает, чат сообщает о недоступности ИИ.

Основной чат получает 10 последних сообщений, актуальную задачу и методику. Фото сначала распознаётся и подтверждается учеником. Отработка использует отдельный диалог и готовые промпты; ИИ сам перепроверяет сгенерированное упражнение в одном запросе. Сервер сохраняет упражнение и начисляет +1 только один раз после оценки ответа. Оценка ИИ не является независимой математической верификацией.

## Правила

Три обучающих задачи с поддержкой, затем две самостоятельные контрольные. Ошибку можно исправить самостоятельно; математическая помощь или просмотр теории требуют новой контрольной задачи. Повторения — по две самостоятельные задачи: 7 дней от освоения; 30 дней **от фактического завершения повторения 7 дней**; 90 дней от освоения. Базовые 5/5 не сбрасываются.

Исходное [ТЗ](TZ_EGE_AI_Trainer.md) дополнено [согласованными правилами](docs/AGREED_CHANGES.md). При расхождениях действует последний документ. Исторические уточнения контроля и отработки: [SPEC v1.1](docs/SPEC-v1.1.md).

## Тестовые данные — по желанию

Новые установки не содержат аккаунтов и личных данных. Для локального тестового ученика:

```bash
python trainer/stage2.py student create student_b --name "Ученик Б"
python trainer/stage2.py demo_reviews student_b
python trainer/stage2.py demo_mistakes student_b
```

Команды добавляют тестовый прогресс, повторения и ошибки; предназначены только для тестовых логинов student_a/student_b. При повторном вызове существующая работа не обнуляется.

## Проверки

```bash
python trainer/stage2.py check
python trainer/stage2.py makemigrations --check --dry-run
python trainer/stage2.py test learning.tests.StageTwoTests learning.tests_training learning.tests_chat.ChatTests learning.tests_reviews.ReviewTests learning.tests_reviews.NotificationTests learning.tests_mistakes.MistakesTests learning.tests_deployment.ProxyAddressTests
(cd trainer/prompts && python -m unittest discover -s tests)
```

## Сервер и уведомления

Production: nginx + Gunicorn + systemd, отдельный production SECRET_KEY, HTTPS и приватное состояние вне кода. Настройки в deploy/ и config.production_settings. [Эксплуатация и резервные копии](deploy/README.md). Проверяющий уведомления запускается командой `python trainer/stage2.py send_review_notifications` по таймеру раз в минуту, либо с --watch для локального просмотра.

Для уведомлений на телефоне нужен HTTPS, установка на главный экран и разрешение ученика. В репозитории есть manifest, иконки и service worker. Физическая доставка на устройство требует проверки самим владельцем.

## Данные и состав репозитория

bank/approved_tasks.json содержит только опубликованные задачи и их источники, ответы и отметки проверки. Нужные изображения лежат в assets/tasks. Источники и сведения об использовании сохранены для каждой задачи; общий новый статус лицензии для чужих материалов не назначается. Методики EduAI атрибутированы в docs/AGREED_CHANGES.md. Теория всех 56 типов — trainer/learning/data/theory_2026.md. Дизайн-система и локальные шрифты — design-system/.

Исключены рабочая база учеников, сессии, переписка, загруженные фото, файлы ошибок, ключи, пароли, локальная .env, отчёты браузерных проверок, архивы и исследовательские выгрузки банка. Для работы создаётся приватная .runtime; не раздавайте корень репозитория простым HTTP-сервером.
