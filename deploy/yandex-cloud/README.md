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
5. После выбора постоянного размещения — отдельная база PostgreSQL `boxcalc_staging`.
6. После подключения базы — Lockbox-секрет со строкой `DATABASE_URL`.
7. Позднее — Object Storage для импортов, инвентаризаций и PDF.

Первая staging-ревизия запускается без базы с `DATABASE_REQUIRED=false`, чтобы отдельно проверить публикацию и HTTP-контур. Публичный доступ к PostgreSQL на порту `5432` не допускается. Если временная база размещается на постоянно включённом Windows-компьютере, backend и PostgreSQL должны работать рядом, а наружу публикуется только HTTPS приложения. Перенос в облачный PostgreSQL выполняется стандартными `pg_dump`/`pg_restore`, без изменения API и доменной модели.

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

## Автоматическая публикация

Push в `v2-dev` после прохождения тестов публикует образ и обновляет только staging. GitHub Actions получает краткоживущий IAM-токен через OIDC Workload Identity Federation; статических ключей и GitHub secrets для Yandex Cloud нет.

- CI service account: `ke-box-calc-ci` (`ajeo882o9ucakl6drviv`);
- federation: `ke-box-calc-github` (`ajeheltm1j9ag5ccffsa`);
- разрешённый subject: `repo:ankalmykov-ui/ke-box-calc:ref:refs/heads/v2-dev`;
- registry: `ke-box-calc` (`crpdjisupq0qdshjp502`);
- container: `ke-box-calc-v2-staging` (`bbafivttvb8s8ke96goj`);
- runtime service account: `ke-box-calc-staging` (`ajed288vbcj1iab4aljt`).

CI имеет только `container-registry.images.pusher` на реестр, `serverless-containers.editor` на staging-контейнер и `iam.serviceAccounts.user` на runtime service account.

## Ручная публикация (аварийный сценарий)

После выбора отдельного каталога и создания реестра:

```bash
yc config set folder-id <FOLDER_ID>
yc container registry configure-docker
docker tag ke-box-calc-v2:staging cr.yandex/<REGISTRY_ID>/ke-box-calc-v2:<GIT_SHA>
docker push cr.yandex/<REGISTRY_ID>/ke-box-calc-v2:<GIT_SHA>
```

Ревизия разворачивается с неизменяемым тегом коммита, а не `latest`. До подключения базы используется безопасный bootstrap-режим:

```bash
yc serverless container revision deploy \
  --container-name ke-box-calc-v2-staging \
  --image cr.yandex/<REGISTRY_ID>/ke-box-calc-v2:<GIT_SHA> \
  --cores 1 \
  --memory 512MB \
  --execution-timeout 30s \
  --service-account-id <SERVICE_ACCOUNT_ID> \
  --environment APP_ENV=staging,DATABASE_REQUIRED=false,APP_LOG_LEVEL=INFO
```

После подключения PostgreSQL runtime service account получает доступ только к нужному сетевому/секретному ресурсу. `DATABASE_URL` передаётся из Lockbox и никогда не записывается в команду, историю shell или репозиторий.
