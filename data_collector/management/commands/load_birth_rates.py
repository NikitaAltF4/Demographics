import csv
import os
# import mysql.connector # Используется DBConnector'ом

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from data_collector.db_connector import DBConnector

# --- НАСТРОЙКИ СКРИПТА ---

BIRTH_RATE_FILE_PATH = os.path.join(settings.BASE_DIR, 'data_store', 'hse_cde', 'fertility',
                                    '2012_BRa2012-2023.txt')  # ЗАМЕНИТЕ НА ВАШЕ ИМЯ ФАЙЛА РОЖДАЕМОСТИ
BATCH_SIZE = 10000  # Можно сделать меньше, если данных немного
CSV_DELIMITER = ','
CSV_ENCODING = 'utf-8'

# --- Сопоставление кодов из файла с ID и значениями для БД ---
SETTLEMENT_TYPE_MAPPING = {
    'T': 1,
    'U': 2,
    'R': 3
}




class Command(BaseCommand):
    help = 'Загружает коэффициенты рождаемости из TXT/CSV файла в базу данных.'

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
                            f"Не удалось преобразовать country_id '{rosstat_code}' в число для региона с id {region_db_id}"))
        except Exception as err:
            self.stderr.write(f"Ошибка получения кодов регионов из БД: {err}")
        finally:
            if cursor: cursor.close()

        if not region_map:
            self.stdout.write(self.style.WARNING("Словарь регионов пуст."))
        return region_map

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Начало загрузки коэффициентов рождаемости..."))

        db_manager = None
        conn = None
        cursor = None

        try:
            db_manager = DBConnector()
            conn = db_manager.get_connection()

            if not conn:
                self.stderr.write(self.style.ERROR("Не удалось установить соединение с БД."))
                return
            self.stdout.write(self.style.SUCCESS(f"Успешное подключение к БД '{db_manager.db_settings.get('NAME')}'."))
        except CommandError as e:
            self.stderr.write(self.style.ERROR(str(e)))
            return
        except Exception as e_init_conn:
            self.stderr.write(self.style.ERROR(f"Непредвиденная ошибка при подключении: {e_init_conn}"))
            return

        region_id_map = self.get_region_id_map(conn)
        if not region_id_map:
            self.stderr.write(self.style.ERROR("Не удалось загрузить маппинг регионов. Прерывание."))
            if db_manager: db_manager.close()
            return
        self.stdout.write(f"Загружено {len(region_id_map)} регионов из БД.")

        insert_query = """
            INSERT INTO birth_rate (year, reg, settlement_type_id, age, birth_rate)
            VALUES (%s, %s, %s, %s, %s) 
        """  # sex здесь отсутствует
        data_batch = []
        total_rows_processed = 0
        total_db_records_prepared = 0
        total_db_records_inserted = 0
        skipped_regions = 0
        skipped_other = 0

        try:
            if not os.path.exists(BIRTH_RATE_FILE_PATH):
                self.stderr.write(self.style.ERROR(f"Файл данных рождаемости не найден: {BIRTH_RATE_FILE_PATH}"))
                return

            cursor = conn.cursor()

            with open(BIRTH_RATE_FILE_PATH, 'r', encoding=CSV_ENCODING) as csvfile:
                reader = csv.DictReader(csvfile, delimiter=CSV_DELIMITER)
                self.stdout.write(
                    f"Чтение файла: {BIRTH_RATE_FILE_PATH} (кодировка: {CSV_ENCODING}, разделитель: '{CSV_DELIMITER}')")

                if not reader.fieldnames:
                    self.stderr.write(self.style.ERROR("Не удалось прочитать заголовки из файла рождаемости."))
                    return
                self.stdout.write(
                    f"Заголовки: {', '.join(reader.fieldnames[:10])}{'...' if len(reader.fieldnames) > 10 else ''}")

                required_base = ['Year', 'Reg', 'Group']
                # Возрастные группы от Bra15 до Bra55
                # Bra15 - это возраст "15 лет и младше" (обрабатываем как возраст 15)
                # Bra55 - это "55 лет и старше" (обрабатываем как возраст 55)
                expected_br_headers = [f'Bra{i}' for i in range(15, 56)]
                all_expected_headers = required_base + expected_br_headers
                missing = [h for h in all_expected_headers if h not in reader.fieldnames]

                if missing:
                    self.stderr.write(
                        self.style.ERROR(f"ОТСУТСТВУЮТ СТОЛБЦЫ в файле рождаемости: {', '.join(missing)}"))
                    return
                self.stdout.write(self.style.SUCCESS("Все ожидаемые заголовки для рождаемости присутствуют."))

                for row_num, row_data in enumerate(reader, 1):
                    total_rows_processed += 1
                    if total_rows_processed % 200 == 0:
                        self.stdout.write(f"  Обработано строк: {total_rows_processed}...")

                    try:
                        year_str = row_data.get('Year', '').strip()
                        reg_str = row_data.get('Reg', '').strip()
                        group_str = row_data.get('Group', '').strip()

                        if not all([year_str, reg_str, group_str]):
                            skipped_other += 1;
                            continue

                        year = int(year_str)
                        reg_code_from_file = int(reg_str)

                        region_db_id = region_id_map.get(reg_code_from_file)
                        if region_db_id is None:
                            skipped_regions += 1;
                            continue

                        settlement_id = SETTLEMENT_TYPE_MAPPING.get(group_str)
                        if settlement_id is None:
                            skipped_other += 1;
                            continue

                        # Цикл по возрастам от 15 до 55
                        for age_of_mother in range(15, 56):
                            br_col_name = f'Bra{age_of_mother}'
                            birth_rate_str = row_data.get(br_col_name)

                            if birth_rate_str is None or birth_rate_str.strip() == '' or birth_rate_str.strip() == '.':
                                birth_rate_value = 0  # Если точка или пусто, считаем 0
                                # self.stdout.write(self.style.NOTICE(f"Строка {row_num}, Возраст {age_of_mother}: Обнаружена '.' или пусто. Устанавливаем коэф. рождаемости в 0."))
                            else:
                                try:

                                    birth_rate_value = int(float(birth_rate_str))  # Сначала в float, потом в int
                                except ValueError:
                                    self.stdout.write(self.style.WARNING(
                                        f"Строка {row_num}, Возраст {age_of_mother}: Ошибка преобразования '{birth_rate_str}' в число. Пропуск."))
                                    skipped_other += 1
                                    continue

                            data_batch.append((
                                year, region_db_id, settlement_id,
                                age_of_mother, birth_rate_value
                            ))
                            total_db_records_prepared += 1

                            if len(data_batch) >= BATCH_SIZE:
                                cursor.executemany(insert_query, data_batch)
                                total_db_records_inserted += len(data_batch)
                                self.stdout.write(
                                    f"  Подготовлено к коммиту {len(data_batch)} записей рождаемости (всего: {total_db_records_inserted}).")
                                data_batch = []

                    except ValueError as ve:  # Ошибки при int(year_str) или int(reg_str)
                        self.stdout.write(self.style.WARNING(
                            f"Строка {row_num}: Ошибка преобразования Year/Reg: {ve}. Пропуск. Данные: {dict(list(row_data.items())[:3])}"))
                        skipped_other += 1
                    except Exception as e_row:
                        self.stderr.write(self.style.ERROR(f"Строка {row_num}: Неожиданная ошибка: {e_row}. Пропуск."))
                        skipped_other += 1

            if data_batch:
                cursor.executemany(insert_query, data_batch)
                total_db_records_inserted += len(data_batch)
                self.stdout.write(
                    f"  Подготовлено к коммиту последних {len(data_batch)} записей рождаемости (всего: {total_db_records_inserted}).")

            conn.commit()
            self.stdout.write(self.style.SUCCESS("Все данные по рождаемости успешно закоммичены в БД."))

        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"ОШИБКА: Файл данных рождаемости не найден: {BIRTH_RATE_FILE_PATH}"))
        except csv.Error as e_csv:
            self.stderr.write(
                self.style.ERROR(f"ОШИБКА чтения CSV файла рождаемости '{BIRTH_RATE_FILE_PATH}': {e_csv}."))
        except Exception as e_glob:
            if conn:
                try:
                    conn.rollback(); self.stdout.write(self.style.WARNING("Откат транзакции из-за ошибки."))
                except:
                    pass
            self.stderr.write(self.style.ERROR(f"ГЛОБАЛЬНАЯ ОШИБКА (рождаемость): {type(e_glob).__name__} - {e_glob}"))
            import traceback
            traceback.print_exc()
        finally:
            if cursor: cursor.close()
            if db_manager: db_manager.close()

            self.stdout.write(self.style.SUCCESS("\n--- Итоги загрузки рождаемости ---"))
            self.stdout.write(f"Всего строк файла обработано: {total_rows_processed}")
            self.stdout.write(f"Записей подготовлено для БД: {total_db_records_prepared}")
            self.stdout.write(f"Записей вставлено и закоммичено в БД: {total_db_records_inserted}")
            self.stdout.write(f"Строк пропущено (регион не найден): {skipped_regions}")
            self.stdout.write(f"Строк/значений пропущено (другие проблемы): {skipped_other}")
            self.stdout.write(self.style.SUCCESS("Загрузка данных о рождаемости завершена."))