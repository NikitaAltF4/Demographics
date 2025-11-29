import csv
import os
# import mysql.connector # mysql.connector теперь используется внутри DBConnector

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings


from data_collector.db_connector import DBConnector



# --- НАСТРОЙКИ СКРИПТА ---
CSV_FILE_PATH = os.path.join(settings.BASE_DIR, 'data_store', 'hse_cde', 'population_structure',
                             '2012_PopDa2012-2022.txt')
BATCH_SIZE = 10000
CSV_DELIMITER = ','
CSV_ENCODING = 'utf-8'

SETTLEMENT_TYPE_MAPPING = {
    'T': 1,
    'U': 2,
    'R': 3
}
SEX_MAPPING = {
    'B': 'A',
    'M': 'M',
    'F': 'F'
}


class Command(BaseCommand):
    help = 'Загружает данные о населении из TXT/CSV файла в базу данных, используя DBConnector.'

    def get_region_id_map(self, conn):
        region_map = {}
        if not conn:
            self.stderr.write(self.style.ERROR("get_region_id_map: Соединение с БД отсутствует."))
            return region_map

        cursor = None  # Инициализируем
        try:
            cursor = conn.cursor()  # conn теперь передается от DBConnector
            cursor.execute("SELECT country_id, id FROM regions WHERE country_id IS NOT NULL")
            for rosstat_code, region_db_id in cursor:
                if rosstat_code is not None:
                    try:
                        region_map[int(rosstat_code)] = region_db_id
                    except ValueError:
                        self.stdout.write(self.style.WARNING(
                            f"Не удалось преобразовать country_id '{rosstat_code}' в число для региона с id {region_db_id} в таблице regions."))

        except Exception as err:  # Ловим общую ошибку, т.к. тип ошибки зависит от драйвера
            self.stderr.write(f"Ошибка получения кодов регионов из БД: {err}")
        finally:
            if cursor: cursor.close()

        if not region_map:
            self.stdout.write(self.style.WARNING(
                "Словарь регионов пуст. Убедитесь, что таблица 'regions' заполнена, содержит поле 'country_id' с числовыми кодами регионов из вашего файла, и что эти коды могут быть преобразованы в числа."))
        return region_map

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Начало загрузки данных о населении с использованием DBConnector..."))

        db_manager = None  # Инициализация для блока finally
        conn = None
        cursor = None

        try:
            db_manager = DBConnector()
            conn = db_manager.get_connection()  # Используем get_connection для получения активного соединения

            if not conn:

                self.stderr.write(self.style.ERROR("Не удалось установить соединение с БД через DBConnector."))
                return

            self.stdout.write(self.style.SUCCESS(
                f"Успешное подключение к базе данных '{db_manager.db_settings.get('NAME')}' через DBConnector."))

        except CommandError as e:
            self.stderr.write(self.style.ERROR(str(e)))  # Выводим сообщение из CommandError
            return
        except Exception as e_init_conn:  # Другие возможные ошибки при инициализации/подключении
            self.stderr.write(
                self.style.ERROR(f"Непредвиденная ошибка при инициализации DBConnector или подключении: {e_init_conn}"))
            import traceback
            traceback.print_exc()
            return

        region_id_map = self.get_region_id_map(conn)
        if not region_id_map:
            self.stderr.write(self.style.ERROR("Не удалось загрузить сопоставление регионов. Загрузка прервана."))
            if db_manager: db_manager.close()
            return
        self.stdout.write(f"Загружено {len(region_id_map)} регионов из БД для сопоставления.")

        insert_query = """
            INSERT INTO population (year, reg, settlement_type_id, age, sex, population)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        data_batch = []
        total_rows_processed_from_csv = 0
        total_db_records_prepared = 0
        total_db_records_inserted = 0
        skipped_due_to_region_not_found = 0
        skipped_due_to_other_data_issues = 0

        try:
            if not os.path.exists(CSV_FILE_PATH):
                self.stderr.write(self.style.ERROR(f"Файл данных не найден: {CSV_FILE_PATH}"))
                return

            cursor = conn.cursor()  # Создаем курсор из полученного соединения

            with open(CSV_FILE_PATH, 'r', encoding=CSV_ENCODING) as csvfile:
                reader = csv.DictReader(csvfile, delimiter=CSV_DELIMITER)
                self.stdout.write(
                    f"Чтение файла данных: {CSV_FILE_PATH} (кодировка: {CSV_ENCODING}, разделитель: '{CSV_DELIMITER}')")

                if not reader.fieldnames:
                    self.stderr.write(self.style.ERROR(
                        "Не удалось прочитать заголовки из файла. Файл пуст или имеет неверный формат."))
                    return

                self.stdout.write(
                    f"Найденные поля (заголовки): {', '.join(reader.fieldnames[:10])}{'...' if len(reader.fieldnames) > 10 else ''}")

                required_base_headers = ['Year', 'Reg', 'Group', 'Sex']
                expected_pop_headers = [f'PopDa{i}' for i in range(101)]
                all_expected_headers_in_file = required_base_headers + expected_pop_headers
                missing_headers = [h for h in all_expected_headers_in_file if h not in reader.fieldnames]

                if missing_headers:
                    self.stderr.write(self.style.ERROR(
                        f"ОТСУТСТВУЮТ ОБЯЗАТЕЛЬНЫЕ СТОЛБЦЫ в файле данных: {', '.join(missing_headers)}"))
                    return
                self.stdout.write(self.style.SUCCESS("Все ожидаемые заголовки столбцов присутствуют."))

                for row_num, row_data in enumerate(reader, 1):
                    total_rows_processed_from_csv += 1
                    if total_rows_processed_from_csv % 500 == 0:
                        self.stdout.write(f"  Обработано исходных строк файла: {total_rows_processed_from_csv}...")

                    try:
                        year_val_str = row_data.get('Year', '').strip()
                        reg_code_val_str = row_data.get('Reg', '').strip()
                        group_code_val = row_data.get('Group', '').strip()
                        sex_code_val = row_data.get('Sex', '').strip()

                        if not all([year_val_str, reg_code_val_str, group_code_val, sex_code_val]):
                            skipped_due_to_other_data_issues += 1
                            continue

                        year = int(year_val_str)
                        reg_code_from_file = int(reg_code_val_str)

                        region_db_id = region_id_map.get(reg_code_from_file)
                        if region_db_id is None:
                            skipped_due_to_region_not_found += 1
                            continue

                        settlement_id = SETTLEMENT_TYPE_MAPPING.get(group_code_val)
                        if settlement_id is None:
                            skipped_due_to_other_data_issues += 1
                            continue

                        sex_for_db = SEX_MAPPING.get(sex_code_val)
                        if sex_for_db is None:
                            skipped_due_to_other_data_issues += 1
                            continue

                        for age_val in range(101):
                            pop_col_name = f'PopDa{age_val}'
                            population_val_str = row_data.get(pop_col_name)

                            if population_val_str is None or population_val_str.strip() == '':
                                skipped_due_to_other_data_issues += 1
                                continue

                            try:
                                population_count = int(population_val_str)
                                data_batch.append((
                                    year, region_db_id, settlement_id,
                                    age_val, sex_for_db, population_count
                                ))
                                total_db_records_prepared += 1

                                if len(data_batch) >= BATCH_SIZE:
                                    cursor.executemany(insert_query, data_batch)
                                    total_db_records_inserted += len(data_batch)
                                    self.stdout.write(
                                        f"  Подготовлено к коммиту {len(data_batch)} записей в БД (всего подготовлено: {total_db_records_inserted}).")
                                    data_batch = []
                            except ValueError:
                                skipped_due_to_other_data_issues += 1

                    except ValueError as ve:
                        self.stdout.write(self.style.WARNING(
                            f"Строка {row_num}: Ошибка преобразования основных данных (Year/Reg): {ve}. Пропуск строки. Данные: {dict(list(row_data.items())[:4])}"))
                        skipped_due_to_other_data_issues += 1
                    except Exception as e_row_proc:
                        self.stderr.write(self.style.ERROR(
                            f"Строка {row_num}: Неожиданная ошибка при обработке: {e_row_proc}. Пропуск строки."))
                        skipped_due_to_other_data_issues += 1

            if data_batch:
                cursor.executemany(insert_query, data_batch)
                total_db_records_inserted += len(data_batch)
                self.stdout.write(
                    f"  Подготовлено к коммиту последних {len(data_batch)} записей в БД (всего подготовлено: {total_db_records_inserted}).")

            conn.commit()  # Один главный коммит после всех вставок
            self.stdout.write(self.style.SUCCESS("Все подготовленные данные успешно закоммичены в БД."))

        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"ОШИБКА: Файл данных не найден по пути: {CSV_FILE_PATH}"))
        except csv.Error as e_csv_main:
            self.stderr.write(self.style.ERROR(f"ОШИБКА чтения CSV файла '{CSV_FILE_PATH}': {e_csv_main}."))
        # Убедимся, что mysql.connector импортирован, чтобы ловить его ошибки, если он не глобальный
        except ImportError:  # Это если бы mysql.connector не был импортирован глобально
            self.stderr.write(
                self.style.ERROR("mysql.connector не импортирован, ошибка БД не может быть поймана специфично"))
        except Exception as e_global:  # Ловим все остальные ошибки, включая mysql.connector.Error если он есть
            if conn:
                try:
                    conn.rollback()
                    self.stdout.write(self.style.WARNING("Произведен откат транзакции из-за ошибки."))
                except Exception as e_rollback:
                    self.stderr.write(self.style.ERROR(f"Ошибка при попытке отката транзакции: {e_rollback}"))

            self.stderr.write(self.style.ERROR(f"ГЛОБАЛЬНАЯ ОШИБКА: {type(e_global).__name__} - {e_global}"))
            import traceback
            traceback.print_exc()
        finally:
            if cursor: cursor.close()
            if db_manager: db_manager.close()  # Используем метод close нашего DBConnector

            self.stdout.write(self.style.SUCCESS("\n--- Итоги загрузки ---"))
            self.stdout.write(f"Всего исходных строк файла обработано: {total_rows_processed_from_csv}")
            self.stdout.write(f"Записей подготовлено для БД: {total_db_records_prepared}")
            self.stdout.write(
                f"Записей фактически вставлено и закоммичено в БД: {total_db_records_inserted if conn and conn.in_transaction is False else 'НЕ ЗАКОММИЧЕНО из-за ошибки или отката'}")
            self.stdout.write(f"Строк пропущено (регион не найден): {skipped_due_to_region_not_found}")
            self.stdout.write(
                f"Строк/значений пропущено (другие проблемы с данными): {skipped_due_to_other_data_issues}")
            self.stdout.write(self.style.SUCCESS("Загрузка данных о населении завершена."))