# Публикация платформы на GitHub

## 1. Создайте репозиторий на GitHub

Зайдите на https://github.com/new и создайте новый репозиторий:
- **Название**: `urack-esp32-platform` (или любое другое)
- **Описание**: Custom PlatformIO platform for ESP32 with pre-compiled libraries
- **Visibility**: Public или Private
- **НЕ создавайте**: README, .gitignore, license (они уже есть локально)

## 2. Подключите удаленный репозиторий

Замените `USERNAME` на ваш GitHub username:

```bash
cd /home/coreglitch/project/urack/urack-esp/urack-platform
git remote add origin https://github.com/USERNAME/urack-esp32-platform.git
```

Или если используете SSH:

```bash
git remote add origin git@github.com:USERNAME/urack-esp32-platform.git
```

## 3. Отправьте код на GitHub

```bash
git branch -M main
git push -u origin main
```

## 4. Использование платформы

После публикации пользователи смогут использовать платформу:

### Вариант 1: Через Git URL (рекомендуется)

В `platformio.ini`:

```ini
[env:modesp32v1]
platform = https://github.com/USERNAME/urack-esp32-platform.git
board = mod-esp32-v1
framework = arduino
```

### Вариант 2: Через локальный путь (для разработки)

```ini
[env:modesp32v1]
platform = file:///path/to/urack-platform
board = mod-esp32-v1
framework = arduino
```

## 5. Первая сборка для пользователей

Пользователям нужно будет один раз собрать предкомпилированные библиотеки:

```bash
# После клонирования платформы PlatformIO
cd ~/.platformio/platforms/urack-esp32
python3 build_precompiled_libs.py
```

Или можно добавить prebuilt/ в релизы GitHub.

## 6. Создание релиза с prebuilt библиотекой (опционально)

Если хотите распространять уже собранную библиотеку:

```bash
# Соберите библиотеку
python3 build_precompiled_libs.py

# Создайте архив
tar -czf prebuilt-v1.0.0.tar.gz prebuilt/

# Загрузите на GitHub Releases
```

В инструкции для пользователей укажите:

```bash
cd ~/.platformio/platforms/urack-esp32
wget https://github.com/USERNAME/urack-esp32-platform/releases/download/v1.0.0/prebuilt-v1.0.0.tar.gz
tar -xzf prebuilt-v1.0.0.tar.gz
```

## Структура репозитория

```
urack-platform/
├── .gitignore              # Игнорирует prebuilt/ и build_temp/
├── README.md               # Документация
├── platform.json           # Конфигурация платформы
├── platform.py             # Класс платформы
├── boards/                 # Определения плат
│   └── mod-esp32-v1.json
├── builder/                # Скрипты сборки
│   ├── main.py
│   └── frameworks/
│       ├── arduino.py
│       ├── espidf.py
│       └── pioarduino-build.py
└── build_precompiled_libs.py  # Скрипт сборки библиотек
```

## Теги версий

Рекомендуется использовать семантическое версионирование:

```bash
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

В `platform.json` обновите версию перед каждым релизом.

## Автоматическая сборка через GitHub Actions

В репозитории настроен GitHub Action (`.github/workflows/release.yml`), который автоматически:

1. **Собирает prebuilt библиотеки** при создании тега
2. **Создает ZIP архив** со всеми файлами
3. **Публикует GitHub Release** с архивом

### Как создать релиз:

```bash
# 1. Обновите версию в platform.json
# 2. Закоммитьте изменения
git add platform.json
git commit -m "Bump version to 1.0.0"
git push

# 3. Создайте и отправьте тег
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

GitHub Action автоматически:
- Установит PlatformIO
- Соберет библиотеки
- Создаст `platform-urack-esp32-v1.0.0.zip`
- Опубликует релиз

### После публикации:

Пользователи смогут использовать прямую ссылку:

```ini
[env:modesp32v1]
platform = https://github.com/USERNAME/urack-esp32-platform/releases/download/v1.0.0/platform-urack-esp32-v1.0.0.zip
board = mod-esp32-v1
framework = arduino
```

Никаких дополнительных действий не требуется - всё уже собрано!

