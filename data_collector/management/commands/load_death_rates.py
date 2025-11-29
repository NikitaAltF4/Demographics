import csv
import os
import mysql.connector  # Используется DBConnector'ом

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

# Импортируем ваш DBConnector
from data_collector.db_connector import DBConnector

# --- НАСТРОЙКИ СКРИПТА ---

DEATH_RATE_FILE_PATH = os.path.join(settings.BASE_DIR, 'data_store', 'hse_cde', 'mortality',
                                    '2012_DRa2012-2022.txt')
BATCH_SIZE = 10000
CSV_DELIMITER = ','
CSV_ENCODING = 'utf-8'  # или 'cp1251', если будут проблемы


SETTLEMENT_TYPE_MAPPING = {
    'T': 1,
    'U': 2,
    'R': 3
}


SEX_MAPPING = {
    'B': 'A',  # Both -> All (или 'T', 'B') - Всего для обоих полов
    'M': 'M',  # Male
    'F': 'F'  # Female
}


class Command(BaseCommand):
    help = 'Загружает коэффициенты смертности из TXT/CSV файла в базу данных.'

    def get_region_id_map(self, conn):
        region_map = {}
        if not conn:
            self.stderr.write(self.style.ERROR("get_region_id_map: Соединение с БД отсутствует."))
            return region_map

        cursor = None
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT country_id, id FROM regions WHERE country_id IS NOT NULL")
            for rosstat_code, region_db_id in cursor:
                if rosstat_code is not None:
                    try:
                        region_map[int(rosstat_code)] = region_db_id
                    except ValueError:
                        self.stdout.write(self.style.WARNING(
                            f"Не удалось преобразовать country_id '{rosstat_code}' в число для региона с id {region_db_id} в таблице regions."))
        except Exception as err:
            self.stderr.write(f"Ошибка получения кодов регионов из БД: {err}")
        finally:
            if cursor: cursor.close()

        if not region_map:
            self.stdout.write(self.style.WARNING("Словарь регионов пуст..."))
        return region_map

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Начало загрузки коэффициентов смертности..."))

        db_manager = None
        conn = None
        cursor = None

        try:
            db_manager = DBConnector()
            conn = db_manager.get_connection()

            if not conn:
                self.stderr.write(self.style.ERROR("Не удалось установить соединение с БД через DBConnector."))
                return

            self.stdout.write(
                self.style.SUCCESS(f"Успешное подключение к базе данных '{db_manager.db_settings.get('NAME')}'."))

        except CommandError as e:
            self.stderr.write(self.style.ERROR(str(e)))
            return
        except Exception as e_init_conn:
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
            INSERT INTO death_rate (year, reg, settlement_type_id, sex, age, death_rate)
            VALUES (%s, %s, %s, %s, %s, %s)
        """  # Обратите внимание на порядок столбцов в таблице death_rate
        data_batch = []
        total_rows_processed_from_file = 0
        total_db_records_prepared = 0
        total_db_records_inserted = 0
        skipped_due_to_region_not_found = 0
        skipped_due_to_other_data_issues = 0

        try:
            if not os.path.exists(DEATH_RATE_FILE_PATH):
                self.stderr.write(self.style.ERROR(f"Файл данных смертности не найден: {DEATH_RATE_FILE_PATH}"))
                return

            cursor = conn.cursor()

            with open(DEATH_RATE_FILE_PATH, 'r', encoding=CSV_ENCODING) as csvfile:
                reader = csv.DictReader(csvfile, delimiter=CSV_DELIMITER)
                self.stdout.write(
                    f"Чтение файла данных смертности: {DEATH_RATE_FILE_PATH} (кодировка: {CSV_ENCODING}, разделитель: '{CSV_DELIMITER}')")

                if not reader.fieldnames:
                    self.stderr.write(self.style.ERROR("Не удалось прочитать заголовки из файла смертности."))
                    return

                self.stdout.write(
                    f"Найденные поля (заголовки): {', '.join(reader.fieldnames[:10])}{'...' if len(reader.fieldnames) > 10 else ''}")

                required_base_headers = ['Year', 'Reg', 'Group', 'Sex']
                # Для смертности столбцы называются Dra0, Dra1, ..., Dra100
                expected_dr_headers = [f'Dra{i}' for i in range(101)]
                all_expected_headers_in_file = required_base_headers + expected_dr_headers
                missing_headers = [h for h in all_expected_headers_in_file if h not in reader.fieldnames]

                if missing_headers:
                    self.stderr.write(self.style.ERROR(
                        f"ОТСУТСТВУЮТ ОБЯЗАТЕЛЬНЫЕ СТОЛБЦЫ в файле данных смертности: {', '.join(missing_headers)}"))
                    return
                self.stdout.write(self.style.SUCCESS("Все ожидаемые заголовки столбцов для смертности присутствуют."))

                for row_num, row_data in enumerate(reader, 1):
                    total_rows_processed_from_file += 1
                    if total_rows_processed_from_file % 500 == 0:
                        self.stdout.write(
                            f"  Обработано исходных строк файла смертности: {total_rows_processed_from_file}...")

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
                            # Названия столбцов для смертности - Dra0, Dra1, ...
                            dr_column_name = f'Dra{age_val}'
                            death_rate_val_str = row_data.get(dr_column_name)

                            if death_rate_val_str is None or death_rate_val_str.strip() == '':
                                skipped_due_to_other_data_issues += 1
                                continue

                            try:

                                death_rate_value = int(death_rate_val_str)

                                data_batch.append((
                                    year, region_db_id, settlement_id,
                                    sex_for_db, age_val, death_rate_value  # Порядок для death_rate таблицы
                                ))
                                total_db_records_prepared += 1

                                if len(data_batch) >= BATCH_SIZE:
                                    cursor.executemany(insert_query, data_batch)
                                    total_db_records_inserted += len(data_batch)
                                    self.stdout.write(
                                        f"  Подготовлено к коммиту {len(data_batch)} записей смертности (всего: {total_db_records_inserted}).")
                                    data_batch = []
                            except ValueError:
                                self.stdout.write(self.style.WARNING(
                                    f"Строка {row_num}, Возраст {age_val}: Ошибка преобразования коэф. смертности '{death_rate_val_str}' в число. Пропуск значения."))
                                skipped_due_to_other_data_issues += 1

                    except ValueError as ve:
                        self.stdout.write(self.style.WARNING(
                            f"Строка {row_num}: Ошибка преобразования Year/Reg: {ve}. Пропуск. Данные: {dict(list(row_data.items())[:4])}"))
                        skipped_due_to_other_data_issues += 1
                    except Exception as e_row_proc:
                        self.stderr.write(
                            self.style.ERROR(f"Строка {row_num}: Неожиданная ошибка: {e_row_proc}. Пропуск."))
                        skipped_due_to_other_data_issues += 1

            if data_batch:
                cursor.executemany(insert_query, data_batch)
                total_db_records_inserted += len(data_batch)
                self.stdout.write(
                    f"  Подготовлено к коммиту последних {len(data_batch)} записей смертности (всего: {total_db_records_inserted}).")

            conn.commit()
            self.stdout.write(self.style.SUCCESS("Все данные по смертности успешно закоммичены в БД."))

        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"ОШИБКА: Файл данных смертности не найден: {DEATH_RATE_FILE_PATH}"))
        except csv.Error as e_csv_main:
            self.stderr.write(
                self.style.ERROR(f"ОШИБКА чтения CSV файла смертности '{DEATH_RATE_FILE_PATH}': {e_csv_main}."))
        except Exception as e_global:
            if conn:
                try:
                    conn.rollback(); self.stdout.write(self.style.WARNING("Откат транзакции из-за ошибки."))
                except:
                    pass  # Ошибки при откате можно игнорировать

            self.stderr.write(
                self.style.ERROR(f"ГЛОБАЛЬНАЯ ОШИБКА (смертность): {type(e_global).__name__} - {e_global}"))
            import traceback
            traceback.print_exc()
        finally:
            if cursor: cursor.close()
            if db_manager: db_manager.close()

            self.stdout.write(self.style.SUCCESS("\n--- Итоги загрузки смертности ---"))
            self.stdout.write(f"Всего строк файла обработано: {total_rows_processed_from_file}")
            self.stdout.write(f"Записей подготовлено для БД: {total_db_records_prepared}")
            self.stdout.write(f"Записей вставлено и закоммичено в БД: {total_db_records_inserted}")
            self.stdout.write(f"Строк пропущено (регион не найден): {skipped_due_to_region_not_found}")
            self.stdout.write(f"Строк/значений пропущено (другие проблемы): {skipped_due_to_other_data_issues}")
            self.stdout.write(self.style.SUCCESS("Загрузка данных о смертности завершена."))