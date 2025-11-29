import pandas as pd
import os
import re
# import mysql.connector # Используется DBConnector'ом

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from data_collector.db_connector import DBConnector

# --- НАСТРОЙКИ СКРИПТА ---
MIGRATION_URBAN_FILE_PATH = os.path.join(settings.BASE_DIR, 'data_store', 'migration',
                                         'Миграционный_прирост_ГОРОД.xlsx')
MIGRATION_RURAL_FILE_PATH = os.path.join(settings.BASE_DIR, 'data_store', 'migration',
                                         'Миграционный_прирост_СЕЛО.xlsx')

BATCH_SIZE = 1000

SETTLEMENT_TYPE_URBAN_ID = 2
SETTLEMENT_TYPE_RURAL_ID = 3

SEX_CODE_MALE = 'Мужчины'
SEX_CODE_FEMALE = 'Женщины'
SEX_CODE_BOTH = 'Всего'
SEX_MAPPING_TO_DB = {
    SEX_CODE_MALE.lower(): 'M',
    SEX_CODE_FEMALE.lower(): 'F',
    SEX_CODE_BOTH.lower(): 'A'
}


class Command(BaseCommand):
    help = 'Загружает данные о миграционном приросте из Excel файлов в базу данных.'

    def get_region_okato_to_id_map(self, conn):
        """ Получает словарь {строковый_okato_code: id_в_таблице_regions} """
        region_map = {}
        if not conn:
            self.stderr.write(self.style.ERROR("get_region_okato_to_id_map: Соединение с БД отсутствует."))
            return region_map
        cursor = None
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT okato_code, id FROM regions WHERE okato_code IS NOT NULL AND okato_code != ''")
            for okato_code_from_db, region_db_id in cursor:
                if okato_code_from_db:
                    region_map[str(okato_code_from_db).strip()] = region_db_id
        except Exception as err:
            self.stderr.write(f"Ошибка получения кодов регионов (ОКАТО) из БД: {err}")
        finally:
            if cursor: cursor.close()
        if not region_map:
            self.stdout.write(self.style.WARNING(
                "Словарь кодов регионов (ОКАТО) пуст. Убедитесь, что таблица 'regions' и поле 'okato_code' корректно заполнены."))
        return region_map

    def parse_age_group_label_migration(self, label_str):
        label_str_orig = str(label_str).strip()  # Сохраняем оригинальную метку для записи
        label_str_proc = label_str_orig.lower()
        start_age, end_age = None, None

        match_older = re.search(r'(\d+)\s*(лет|год|года)?\s*(и)?\s*старше', label_str_proc)
        if match_older:
            start_age = int(match_older.group(1))
            end_age = 100
            return start_age, end_age, label_str_orig

        match_single_year = re.search(r'^(\d+)\s*(год|года|лет)?$', label_str_proc)
        if match_single_year:
            start_age = int(match_single_year.group(1))
            end_age = start_age
            return start_age, end_age, label_str_orig


        return None, None, label_str_orig

    def process_excel_file(self, file_path, predetermined_settlement_type_id, conn, region_okato_to_id_map, cursor):
        self.stdout.write(
            f"  Обработка файла: {os.path.basename(file_path)} (Ожидаемый тип местности ID: {predetermined_settlement_type_id})")
        try:
            df = pd.read_excel(file_path, sheet_name=0, header=None, dtype=str)
        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"    Файл не найден: {file_path}"))
            return 0, 0
        except Exception as e_read_excel:
            self.stderr.write(self.style.ERROR(f"    Ошибка чтения Excel файла {file_path}: {e_read_excel}"))
            return 0, 0

        data_to_insert_batch = []
        # Инициализируем переменные, которые будем возвращать
        func_records_prepared = 0
        func_records_skipped = 0

        year_header_row_idx = -1
        year_columns = {}

        for r_idx_header_scan in range(df.shape[0]):
            if r_idx_header_scan > 15: break
            row_values_str = [str(v).strip() for v in df.iloc[r_idx_header_scan].values]
            temp_year_cols = {}
            year_regex = re.compile(r"^(\d{4})(?:\s*г\.?)?$")
            start_col_for_years = 2
            for c_idx in range(start_col_for_years, len(row_values_str)):
                cell_val = row_values_str[c_idx]
                match = year_regex.match(cell_val)
                if match:
                    year_num = int(match.group(1))
                    if 2000 < year_num < 2050:
                        if temp_year_cols and year_num != max(temp_year_cols.keys()) + 1 and c_idx == min(
                                temp_year_cols.values()) + len(temp_year_cols):
                            temp_year_cols.clear();
                            break
                        temp_year_cols[year_num] = c_idx
                elif temp_year_cols:
                    break
            if len(temp_year_cols) >= 2:
                first_year_col_idx = min(temp_year_cols.values())
                valid_header_row = False
                if first_year_col_idx > 0:
                    value_before_years = str(df.iloc[r_idx_header_scan, first_year_col_idx - 1]).strip()
                    if not (value_before_years.isdigit() and len(value_before_years) > 5):
                        valid_header_row = True
                elif first_year_col_idx == 0:
                    valid_header_row = True
                if valid_header_row:
                    year_header_row_idx = r_idx_header_scan
                    year_columns = dict(sorted(temp_year_cols.items()))
                    break
        if not year_columns:
            self.stderr.write(
                self.style.ERROR(f"    Не удалось определить столбцы с годами в файле {os.path.basename(file_path)}."))

            return 0, df.shape[0] - (year_header_row_idx + 1 if year_header_row_idx != -1 else 0)

        self.stdout.write(f"    Строка с заголовками годов (индекс {year_header_row_idx}): {year_columns}")

        current_sex_for_db = None
        current_age_start, current_age_end = None, None
        current_raw_age_label = None

        CODE_SETTLEMENT_URBAN = '1'
        CODE_SETTLEMENT_RURAL = '10'
        CODE_SEX_FEMALE = '2'
        CODE_SEX_MALE = '3'
        CODE_SEX_BOTH = '6'
        CODE_AGE_AGGREGATE = '1'
        skip_b_codes_as_headers = [CODE_SETTLEMENT_URBAN, CODE_SETTLEMENT_RURAL,
                                   CODE_SEX_FEMALE, CODE_SEX_MALE, CODE_SEX_BOTH,
                                   CODE_AGE_AGGREGATE]

        for r_idx in range(year_header_row_idx + 1, df.shape[0]):
            row_list = df.iloc[r_idx].tolist()
            cell_A_text = str(row_list[0]).strip() if len(row_list) > 0 else ""
            cell_B_code = str(row_list[1]).strip() if len(row_list) > 1 else ""

            if not cell_A_text and not cell_B_code: continue

            is_header_row_by_b_code = cell_B_code in skip_b_codes_as_headers
            if is_header_row_by_b_code:

                if cell_B_code == CODE_SEX_FEMALE:
                    current_sex_for_db = SEX_MAPPING_TO_DB[SEX_CODE_FEMALE.lower()]
                    current_age_start, current_age_end, current_raw_age_label = None, None, None
                    self.stdout.write(f"    Контекст: ПОЛ = Женщины ('{current_sex_for_db}'). Строка {r_idx + 1}")
                elif cell_B_code == CODE_SEX_MALE:
                    current_sex_for_db = SEX_MAPPING_TO_DB[SEX_CODE_MALE.lower()]
                    current_age_start, current_age_end, current_raw_age_label = None, None, None
                    self.stdout.write(f"    Контекст: ПОЛ = Мужчины ('{current_sex_for_db}'). Строка {r_idx + 1}")
                elif cell_B_code == CODE_SEX_BOTH:
                    current_sex_for_db = SEX_MAPPING_TO_DB[SEX_CODE_BOTH.lower()]
                    current_age_start, current_age_end, current_raw_age_label = None, None, None
                    self.stdout.write(f"    Контекст: ПОЛ = Оба пола ('{current_sex_for_db}'). Строка {r_idx + 1}")
                elif cell_B_code in [CODE_SETTLEMENT_URBAN, CODE_SETTLEMENT_RURAL]:
                    current_sex_for_db = None
                    current_age_start, current_age_end, current_raw_age_label = None, None, None
                elif cell_B_code == CODE_AGE_AGGREGATE and "всего" in cell_A_text.lower():
                    current_age_start, current_age_end, current_raw_age_label = None, None, None
                continue

            if current_sex_for_db and not (cell_B_code.isdigit() and len(cell_B_code) > 3):
                age_s, age_e, age_label = self.parse_age_group_label_migration(cell_A_text)
                if age_s is not None:
                    current_age_start = age_s
                    current_age_end = age_e
                    current_raw_age_label = age_label
                    self.stdout.write(
                        f"    Контекст: ВОЗРАСТ = '{current_raw_age_label}' ({current_age_start}-{current_age_end}), Пол = {current_sex_for_db}. Строка {r_idx + 1}.")
                    continue

            region_okato_from_excel = None
            if cell_B_code.isdigit() and len(cell_B_code) > 3:
                region_okato_from_excel = cell_B_code

            if region_okato_from_excel and current_sex_for_db and current_raw_age_label:
                region_db_id = region_okato_to_id_map.get(region_okato_from_excel)
                if not region_db_id:
                    func_records_skipped += len(year_columns)  # ИСПОЛЬЗУЕМ ИМЯ ИЗ НАЧАЛА ФУНКЦИИ
                    continue

                for year, col_idx in year_columns.items():
                    if col_idx >= len(row_list): continue
                    saldo_val_raw = row_list[col_idx]
                    if pd.isna(saldo_val_raw) or str(saldo_val_raw).strip() in ["", "-", ".", "…", "х", "X"]:
                        saldo = 0
                    else:
                        try:
                            saldo_str_cleaned = str(saldo_val_raw).replace('\xa0', '').replace(' ', '').replace(',',
                                                                                                                '.')
                            saldo = int(float(saldo_str_cleaned))
                        except ValueError:
                            func_records_skipped += 1  # ИСПОЛЬЗУЕМ ИМЯ ИЗ НАЧАЛА ФУНКЦИИ
                            continue

                    data_to_insert_batch.append((
                        year, region_db_id, predetermined_settlement_type_id,
                        current_sex_for_db, current_age_start, current_age_end,
                        current_raw_age_label, saldo
                    ))
                    func_records_prepared += 1  # ИСПОЛЬЗУЕМ ИМЯ ИЗ НАЧАЛА ФУНКЦИИ

        if data_to_insert_batch:
            insert_query = """
                INSERT INTO migration_saldo 
                (year, region_id, settlement_type_id, sex, age_group_start, age_group_end, age_group_raw_label, migration_saldo)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            for i in range(0, len(data_to_insert_batch), BATCH_SIZE):
                batch = data_to_insert_batch[i:i + BATCH_SIZE]
                try:
                    cursor.executemany(insert_query, batch)
                    self.stdout.write(
                        f"    ПОДГОТОВЛЕНО (ЗАКОММЕНТИРОВАНО): {len(batch)} (Файл: {os.path.basename(file_path)})")
                except Exception as e_insert:
                    self.stderr.write(self.style.ERROR(f"    Ошибка при подготовке батча к вставке: {e_insert}"))
                    raise
        else:
            self.stdout.write(
                self.style.WARNING(f"    Нет данных для подготовки к вставке из файла {os.path.basename(file_path)}."))

        return func_records_prepared, func_records_skipped  # ВОЗВРАЩАЕМ ПРАВИЛЬНЫЕ ПЕРЕМЕННЫЕ

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Начало загрузки данных о миграции..."))
        db_manager = None;
        conn = None;
        cursor = None
        try:
            db_manager = DBConnector()
            conn = db_manager.get_connection()
            if not conn: return
            self.stdout.write(self.style.SUCCESS(f"Успешное подключение к БД '{db_manager.db_settings.get('NAME')}'."))
        except CommandError as e:
            self.stderr.write(self.style.ERROR(str(e)));
            return
        except Exception as e_init_conn:
            self.stderr.write(self.style.ERROR(f"Непредвиденная ошибка при подключении: {e_init_conn}"));
            return

        region_okato_to_id_map = self.get_region_okato_to_id_map(conn)
        if not region_okato_to_id_map:
            self.stderr.write(self.style.ERROR("Не удалось загрузить сопоставление регионов по ОКАТО. Прерывание."))
            if db_manager: db_manager.close(); return
        self.stdout.write(f"Загружено {len(region_okato_to_id_map)} ОКАТО кодов регионов из БД.")

        total_records_prepared_overall = 0
        total_records_skipped_overall = 0

        # Создаем курсор один раз здесь
        try:
            cursor = conn.cursor()

            files_to_process = [
                (MIGRATION_URBAN_FILE_PATH, SETTLEMENT_TYPE_URBAN_ID),
                (MIGRATION_RURAL_FILE_PATH, SETTLEMENT_TYPE_RURAL_ID)
            ]

            for file_path, settlement_id in files_to_process:
                if os.path.exists(file_path):
                    prepared_count, skipped_count = self.process_excel_file(file_path, settlement_id, conn,
                                                                            region_okato_to_id_map, cursor)
                    total_records_prepared_overall += prepared_count
                    total_records_skipped_overall += skipped_count
                else:
                    self.stderr.write(self.style.ERROR(f"Файл не найден: {file_path}"))

            if total_records_prepared_overall > 0:

                conn.commit()
                self.stdout.write(self.style.WARNING(
                    f"Всего {total_records_prepared_overall} записей по миграции ПОДГОТОВЛЕНО. КОММИТ В БД ЗАКОММЕНТИРОВАН ДЛЯ ОТЛАДКИ."))
                self.stdout.write(self.style.SUCCESS(f"Всего {total_records_prepared_overall} записей по миграции успешно закоммичены в БД."))
            else:
                self.stdout.write(self.style.WARNING("Не было подготовлено записей по миграции для коммита."))

        except Exception as e_global:
            if conn:
                try:
                    conn.rollback(); self.stdout.write(self.style.WARNING("Откат транзакции миграции из-за ошибки."))
                except:
                    pass
            self.stderr.write(self.style.ERROR(f"ГЛОБАЛЬНАЯ ОШИБКА (миграция): {type(e_global).__name__} - {e_global}"))
            import traceback
            traceback.print_exc()
        finally:
            if cursor: cursor.close()
            if db_manager: db_manager.close()

            self.stdout.write(self.style.SUCCESS("\n--- Итоги загрузки миграции ---"))
            self.stdout.write(f"Всего записей подготовлено к вставке в БД: {total_records_prepared_overall}")
            self.stdout.write(f"Всего записей пропущено при обработке файлов: {total_records_skipped_overall}")
            self.stdout.write(self.style.SUCCESS("Загрузка данных о миграции завершена."))