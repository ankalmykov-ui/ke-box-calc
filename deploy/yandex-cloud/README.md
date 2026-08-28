# Yandex Cloud staging

KE | BOX CALC v2 разворачивается как обычный Docker-образ. Ресурсы создаются в отдельном каталоге `ke-box-calc`, чтобы не затронуть действующие API Gateway и Cloud Function автопубликации MAX.

## Границы окружений

- `v2-dev` разворачивается только в `ke-box-calc-v2-staging`;
- staging использует отдельную базу `boxcalc_staging`;
- production v0.7.1 и ветка `main` не изменяются;
- секреты не хранятся в Git;
- миграции запускаются отдельной командой до публикации новой ревизии;
- приложение обязано проходить `/api/v2/health/live` и `/api/v2/health/ready`.

## Ресурсы

1. Каталог `ke-box-calc` в существующем облаке.
2. Сервисный аккаунт `ke-box-calc-staging` с минимальными правами.
3. Приватный Container Registry `ke-box-calc`.
4. Serverless Container `ke-box-calc-v2-staging`.
5. Отдельная база PostgreSQL `boxcalc_staging`.
6. Lockbox-секрет со строкой `DATABASE_URL`.
7. Позднее — Object Storage для импортов, инвентаризаций и PDF.

Serverless Container и PostgreSQL подключаются к одной закрытой облачной сети. Публичный доступ к базе не включается.

## Контейнер

Приложение читает порт из переменной `PORT`, которую Serverless Containers задаёт автоматически.

```bash
docker build --tag ke-box-calc-v2:staging .
docker run --rm --publish 8080:8080 \
  --env APP_ENV=staging \
  --env DATABASE_REQUIRED=false \
  ke-box-calc-v2:staging
```

Локальная проверка:

```bash
curl --fail http://localhost:8080/api/v2/health/live
curl --fail http://localhost:8080/api/v2/health/ready
```

## Публикация образа

После выбора отдельного каталога и создания реестра:

```bash
yc config set folder-id <FOLDER_ID>
yc container registry configure-docker
docker tag ke-box-calc-v2:staging cr.yandex/<REGISTRY_ID>/ke-box-calc-v2:<GIT_SHA>
docker push cr.yandex/<REGISTRY_ID>/ke-box-calc-v2:<GIT_SHA>
```

Ревизия разворачивается с неизменяемым тегом коммита, а не `latest`:

```bash
yc serverless container revision deploy \
  --container-name ke-box-calc-v2-staging \
  --image cr.yandex/<REGISTRY_ID>/ke-box-calc-v2:<GIT_SHA> \
  --cores 1 \
  --memory 512MB \
  --execution-timeout 30s \
  --service-account-id <SERVICE_ACCOUNT_ID> \
  --network-id <NETWORK_ID> \
  --environment APP_ENV=staging,DATABASE_REQUIRED=true,APP_LOG_LEVEL=INFO \
  --secret environment-variable=DATABASE_URL,id=<LOCKBOX_SECRET_ID>,version-id=<LOCKBOX_VERSION_ID>,key=database_url
```

Сервисный аккаунт получает `container-registry.images.puller` на реестр и `lockbox.payloadViewer` только на секрет приложения. `DATABASE_URL` передаётся из Lockbox и никогда не записывается в команду, историю shell или репозиторий.
