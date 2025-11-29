import mysql.connector
from django.conf import settings
from django.core.management.base import CommandError
import logging  # Для более стандартного логгирования

logger = logging.getLogger(__name__)  # Создаем логгер для этого модуля


class DBConnector:
    def __init__(self):
        self.conn = None
        self.db_settings = None
        try:
            self._load_settings()
        except Exception as e:
            # Логгируем ошибку загрузки настроек и пробрасываем CommandError
            logger.error(f"DBConnector: Ошибка при загрузке настроек: {e}", exc_info=True)
            raise CommandError(f"DBConnector: Ошибка при загрузке настроек БД: {e}")

    def _load_settings(self):
        if not hasattr(settings, 'DATABASES') or 'default' not in settings.DATABASES:
            raise CommandError("Настройки Django (settings.DATABASES['default']) не определены или недоступны.")

        self.db_settings = settings.DATABASES['default']

        required_keys = ['NAME', 'USER', 'HOST']
        missing_keys = [key for key in required_keys if key not in self.db_settings or self.db_settings[key] is None]

        if missing_keys:
            raise CommandError(
                f"Следующие обязательные ключи БД отсутствуют или None в settings.py: {', '.join(missing_keys)}")

    def connect(self):
        if self.conn and self.conn.is_connected():
            return self.conn

        if not self.db_settings:  # Если настройки не загрузились
            raise CommandError("DBConnector: Настройки БД не были загружены, невозможно подключиться.")

        try:
            host_val = self.db_settings.get('HOST', '127.0.0.1')
            user_val = self.db_settings.get('USER')  # Проверен в _load_settings
            password_val = self.db_settings.get('PASSWORD', '')
            database_val = self.db_settings.get('NAME')  # Проверен в _load_settings
            port_val_str = self.db_settings.get('PORT', '3306') or '3306'  # or '3306' если пустая строка

            # --- Диагностика типов ---
            logger.debug(f"DBConnector: Попытка подключения с параметрами:")
            logger.debug(f"  Host: '{host_val}' (тип: {type(host_val)})")
            logger.debug(f"  User: '{user_val}' (тип: {type(user_val)})")
            logger.debug(f"  Password: '****' (тип: {type(password_val)})")  # Не логгируем пароль
            logger.debug(f"  Database: '{database_val}' (тип: {type(database_val)})")
            logger.debug(f"  Port_str: '{port_val_str}' (тип: {type(port_val_str)})")
            # --- Конец диагностики ---

            # Явное приведение к строке, если это не строка (кроме порта, который будет int)
            # Это попытка обезопаситься, но проблема скорее всего в settings.py
            db_params = {
                "host": str(host_val),
                "user": str(user_val),
                "password": str(password_val),
                "database": str(database_val),
                "port": int(port_val_str)  # mysql.connector ожидает порт как int
            }

            self.conn = mysql.connector.connect(**db_params)

            if self.conn.is_connected():
                logger.info("DBConnector: Успешное подключение к базе данных.")
                return self.conn
        except ValueError as ve:  # Ошибка преобразования порта в int
            logger.error(f"DBConnector: Ошибка значения порта БД '{port_val_str}': {ve}", exc_info=True)
            raise CommandError(f"DBConnector: Ошибка значения порта БД '{port_val_str}'. PORT должен быть числом: {ve}")
        except mysql.connector.Error as err:
            logger.error(f"DBConnector: Ошибка подключения к БД: {err}", exc_info=True)
            raise CommandError(f"Ошибка подключения к БД (DBConnector): {err}")
        except Exception as e:
            logger.error(f"DBConnector: Неожиданная ошибка при подключении: {e}", exc_info=True)
            raise CommandError(f"Неожиданная ошибка при подключении к БД (DBConnector): {e}")

        # Если дошли сюда, значит, что-то пошло не так, и соединение не установлено
        # но исключение не было перехвачено или было проигнорировано (что не должно происходить с try/except выше)
        return None

    def get_connection(self):
        if not self.conn or not self.conn.is_connected():
            # self.connect() может выбросить CommandError, который должен быть обработан вызывающим кодом
            self.connect()
        return self.conn

    def close(self):
        if self.conn and self.conn.is_connected():
            try:
                self.conn.close()
                logger.info("DBConnector: Соединение с БД закрыто.")
            except mysql.connector.Error as err:
                logger.warning(f"DBConnector: Ошибка при закрытии соединения с БД: {err}")
            finally:  # В любом случае сбрасываем self.conn
                self.conn = None