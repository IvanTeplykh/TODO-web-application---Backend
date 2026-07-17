# TODO Web Application - Backend

Цей проект є серверною частиною (Backend) веб-додатку для керування завданнями (TODO). Він реалізує RESTful API з автентифікацією користувачів та збереженням завдань.

---

## 🛠️ Стек технологій (Tech Stack)

*   **Мова програмування**: Python 3.10+
*   **Веб-фреймворк**: **FastAPI** — для розробки високопродуктивного API.
*   **Асинхронний драйвер бази даних**: **Motor** — асинхронний MongoDB драйвер для Python.
*   **Валідація даних**: **Pydantic v2** — забезпечення безпеки типів та валідації запитів/відповідей.
*   **База даних**: **MongoDB** (використовується хмарне рішення MongoDB Atlas).
*   **Безпека та автентифікація**:
    *   **JWT (JSON Web Tokens)** — авторизація за допомогою токенів доступу (access tokens).
    *   **CryptContext (passlib & bcrypt)** — для надійного хешування та перевірки паролів користувачів.
*   **Сервер виконання**: **Uvicorn** — асинхронний ASGI-сервер.

---

## 🚀 Основні можливості (Features)

1.  **Автентифікація та авторизація**:
    *   Реєстрація користувачів (`/api/v1/auth/register`).
    *   Вхід користувача з видачею JWT токена (`/api/v1/auth/login`).
    *   Отримання профілю поточного користувача (`/api/v1/auth/me`).
2.  **Керування завданнями (CRUD)**:
    *   Створення завдання (`POST /api/v1/tasks`) з назвою (до 100 символів), описом, дедлайном (`due_date`) та пріоритетом (1-10).
    *   Отримання пагінованого списку завдань поточного користувача (`GET /api/v1/tasks`) з можливістю пошуку, сортування та фільтрації за статусом.
    *   Оновлення завдання (`PUT /api/v1/tasks/{id}`) та його статусу (`PATCH /api/v1/tasks/{id}/status`).
    *   Видалення завдання (`DELETE /api/v1/tasks/{id}`).
3.  **CORS**: Налаштоване Middleware для дозволу запитів з будь-яких джерел (`allow_origins=["*"]`).
4.  **Автоматична документація**: Інтерактивний Swagger UI доступний за адресою `/docs`.

---

## ⚙️ Налаштування оточення (Environment Variables)

Для запуску сервера необхідно створити файл `.env` у кореневій директорії бекенду з наступними змінними:

```env
SECRET_KEY=your_jwt_secret_key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
MONGODB_URL=mongodb+srv://<username>:<password>@cluster.mongodb.net/dbname
DATABASE_NAME=todo_app_database
```

---

## 🏁 Швидкий старт (Quick Start)

### 1. Встановлення залежностей
Рекомендується використовувати віртуальне оточення:

```bash
# Створення віртуального оточення
python -m venv .venv

# Активація (Windows)
.venv\Scripts\activate

# Активація (macOS/Linux)
source .venv/bin/activate

# Встановлення залежностей
pip install -r requirements.txt
```

### 2. Запуск сервера розробки
```bash
uvicorn app.main:app --reload
```
Після цього сервер запуститься за адресою `http://localhost:8000`.

*   **Swagger API Docs**: `http://localhost:8000/docs`
*   **Redoc API Docs**: `http://localhost:8000/redoc`
