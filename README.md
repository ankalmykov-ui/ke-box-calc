# KE | BOX CALC — v0.9-dev

Стартовая реализация v0.9 по ТЗ v2.2. Ветка `v0.9-dev` отделена от `v0.8-dev`; `main` и production v0.7.1 не изменяются.

## Первый срез v0.9

- PostgreSQL как единая база продукта, без номера версии в именах таблиц.
- Последовательные SQL-миграции с контрольными суммами.
- Организации, площадки, склады и базовая ролевая модель.
- Отдельное хранилище карточек сырья, внешних идентификаторов и ширин рулонов.
- Партии и конкретные рулоны.
- Неизменяемые складские движения; баланс вычисляется как их сумма.
- Ручное поступление сырья.
- Отдельное идемпотентное подтверждение списания сырья.
- Транзакционная защита от конкурентного отрицательного остатка.
- Сторно отдельным обратным документом без удаления истории.
- Версионируемый API `/api/v1` при сохранении расчётных endpoint v0.8.
- Выгрузка из 1С допускается только как preview для инвентаризационной сверки; она не является оперативной базой.

Композиции, полный импорт/инвентаризация, связь выбранного раскроя с потребностью, аутентификация и складской интерфейс добавляются следующими срезами v0.9.

## API v1

- `GET /api/v1/meta` — версия приложения, API и состояние схемы.
- `POST /api/v1/organizations` — организация.
- `POST /api/v1/sites` — производственная площадка.
- `POST /api/v1/warehouses` — склад.
- `POST /api/v1/materials` — карточка сырья.
- `GET /api/v1/materials` — справочник сырья организации.
- `POST /api/v1/stock/receipts` — поступление.
- `GET /api/v1/stock/warehouses/{warehouse_id}/balances` — производный остаток.
- `POST /api/v1/stock/writeoffs/confirm` — отдельное подтверждение списания.
- `POST /api/v1/stock/writeoffs/{document_id}/reverse` — сторно.
- `POST /api/v1/inventory/imports/1c/preview` — безопасный preview внешнего файла 1С.

Формирование PDF не вызывает ни один складской endpoint и не изменяет остатки.

## Локальный запуск с Docker

```bash
cp .env.docker.example .env
# заменить локальный пароль одновременно в POSTGRES_PASSWORD и DATABASE_URL
docker compose up --build
```

Миграции выполняются отдельным контейнером `migrate` до запуска приложения.

## Запуск без Docker

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
export DATABASE_URL='postgresql://...'
PYTHONPATH=backend python -m app.db_migrations
PYTHONPATH=backend uvicorn app.main:app --reload
```

Без `DATABASE_URL` расчётные API и интерфейс запускаются, а складские endpoint возвращают `503`. Значение подключения никогда не зашито в код.

## Тесты

```bash
PYTHONPATH=backend pytest -q backend/tests
```

## Vercel

Предпочтительный ресурс — Neon Postgres через Vercel Marketplace. Preview/staging и production должны использовать разные базы с общей цепочкой миграций. Сначала миграции применяются к staging; production v0.7.1 остаётся нетронутым до отдельного решения.
