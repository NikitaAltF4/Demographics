import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, unquote, urlparse
import datetime
import time
import re
import zipfile
import shutil  # Для shutil.rmtree и shutil.move
from django.conf import settings
from django.core.management.base import BaseCommand


HSE_CDE_CLASSIFIED_DATA_PATH = os.path.join(settings.BASE_DIR, 'data_store', 'hse_cde')

HSE_CDE_PAGE_URL = "https://www.nes.ru/demogr-fermort-data?lang=ru"  # Основная страница с данными
NES_BASE_URL = "https://www.nes.ru"  # Базовый URL для сборки абсолютных ссылок, если href относительные

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}


TXT_FILE_CLASSIFICATION_PATTERNS = {
    "population_structure": [
        # Имя файла начинается с Pop, затем B или D, затем 'a' (НЕ '5a'), затем диапазон гггг-гггг
        re.compile(r"^Pop[BD]a(?!5)\d{4}-\d{4}\.txt$", re.IGNORECASE),
    ],
    "fertility": [
        # Имя файла начинается с BRa (НЕ BRaO), затем диапазон гггг-гггг
        re.compile(r"^BRa(?!O)\d{4}-\d{4}\.txt$", re.IGNORECASE),
    ],
    "mortality": [
        # Имя файла начинается с DRa (НЕ DRac), затем диапазон гггг-гггг
        re.compile(r"^DRa(?!c)\d{4}-\d{4}\.txt$", re.IGNORECASE),
    ]
}

# --- Общие функции ---
def sanitize_filename(filename):
    filename = re.sub(r'[^\w\.\-_]', '_', filename)
    filename = re.sub(r'__+', '_', filename)
    if '.' in filename:
        name, ext = os.path.splitext(filename)
        name = name.strip('_')
        filename = name + ext if name else ext
    else:
        filename = filename.strip('_')
    return filename if filename else "unnamed_file"


class Command(BaseCommand):
    help = 'Скачивает, извлекает и классифицирует демографические TXT данные из ZIP-архивов с сайта РЭШ ЦДИ.'

    def fetch_all_zip_links_from_page(self, page_url):
        """Собирает все .zip ссылки со страницы, делая их абсолютными."""
        zip_links = []
        self.stdout.write(f"  Запрос к {page_url} для сбора ZIP ссылок...")
        try:
            response = requests.get(page_url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            for link_tag in soup.find_all('a', href=True):
                href = link_tag['href']
                if href and href.lower().endswith('.zip'):
                    absolute_url = urljoin(NES_BASE_URL,
                                           href)  # urljoin корректно обработает и абсолютные, и относительные к корню, и полные URL
                    zip_links.append(absolute_url)
            self.stdout.write(self.style.SUCCESS(f"  Найдено {len(zip_links)} ZIP ссылок на странице."))
        except requests.exceptions.RequestException as e:
            self.stderr.write(self.style.ERROR(f"Ошибка при получении ссылок с {page_url}: {e}"))
        return list(set(zip_links))  # Убираем дубликаты, если есть

    def download_and_extract_single_zip(self, zip_url, temp_download_dir, temp_extract_dir):
        """Скачивает один ZIP-архив во временную папку и извлекает его содержимое в другую временную папку."""
        try:
            # Формируем имя для временного ZIP файла
            parsed_url = urlparse(zip_url)
            zip_filename_from_url = os.path.basename(parsed_url.path)
            if not zip_filename_from_url:  # Если URL заканчивается на / или имя не извлечь
                zip_filename_from_url = f"archive_{int(time.time())}.zip"

            temp_zip_path = os.path.join(temp_download_dir, sanitize_filename(zip_filename_from_url))

            self.stdout.write(f"    Скачиваю: {zip_url} -> {temp_zip_path}")
            response = requests.get(zip_url, stream=True, headers=HEADERS, timeout=60)
            response.raise_for_status()

            with open(temp_zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            self.stdout.write(f"    Архив '{zip_filename_from_url}' скачан. Распаковка в {temp_extract_dir}...")
            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_extract_dir)

            os.remove(temp_zip_path)  # Удаляем временный ZIP после распаковки
            self.stdout.write(f"    Распаковано. Временный ZIP удален.")
            return True
        except requests.exceptions.RequestException as e:
            self.stderr.write(self.style.ERROR(f"Ошибка при скачивании {zip_url}: {e}"))
        except zipfile.BadZipFile:
            self.stderr.write(self.style.ERROR(f"Файл по {zip_url} не является корректным ZIP архивом или поврежден."))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Неожиданная ошибка при обработке ZIP {zip_url}: {e}"))
        return False

    def classify_and_move_extracted_files(self, temp_extract_dir, classified_output_dir_base,
                                          zip_url_for_year_extraction=""):
        classified_count = 0
        year_match_zip = re.search(r'(\d{4})', os.path.basename(urlparse(zip_url_for_year_extraction).path))
        year_prefix_from_zip = year_match_zip.group(1) + "_" if year_match_zip else ""
        self.stdout.write(
            f"      Извлекаем год из ZIP '{os.path.basename(urlparse(zip_url_for_year_extraction).path)}': префикс года '{year_prefix_from_zip}'")

        for root, _, files in os.walk(temp_extract_dir):
            for original_extracted_filename in files:
                self.stdout.write(f"        Обрабатываем извлеченный файл: {original_extracted_filename}")
                if original_extracted_filename.lower().endswith('.txt'):
                    source_path = os.path.join(root, original_extracted_filename)
                    filename_to_classify = original_extracted_filename.lower()  # Классифицируем по lowercase имени

                    self.stdout.write(f"          TXT для классификации: '{filename_to_classify}'")

                    determined_category = None  # Используем None, чтобы точно знать, была ли найдена категория
                    moved_to_category = False

                    for category_key, patterns in TXT_FILE_CLASSIFICATION_PATTERNS.items():
                        self.stdout.write(f"            Проверяем категорию: '{category_key}'")
                        for pattern_idx, pattern in enumerate(patterns):
                            self.stdout.write(f"              Паттерн #{pattern_idx}: {pattern.pattern}")
                            if pattern.search(filename_to_classify):
                                self.stdout.write(self.style.SUCCESS(
                                    f"                Найдено соответствие! Категория: '{category_key}' для файла '{filename_to_classify}'"))
                                determined_category = category_key

                                target_category_dir = os.path.join(classified_output_dir_base, determined_category)
                                os.makedirs(target_category_dir, exist_ok=True)

                                final_filename_in_category = sanitize_filename(
                                    f"{year_prefix_from_zip}{original_extracted_filename}")
                                final_dest_path = os.path.join(target_category_dir, final_filename_in_category)

                                if os.path.exists(final_dest_path):
                                    self.stdout.write(
                                        f"                Файл {final_filename_in_category} уже существует в {target_category_dir}. Пропускаем.")
                                else:
                                    shutil.move(source_path, final_dest_path)
                                    self.stdout.write(self.style.SUCCESS(
                                        f"                Перемещено: {original_extracted_filename} -> {determined_category}/{final_filename_in_category}"))

                                classified_count += 1
                                moved_to_category = True
                                break  # Выходим из цикла по паттернам для данной категории
                        if moved_to_category:
                            break  # Выходим из цикла по категориям, т.к. файл классифицирован

                    if not moved_to_category:
                        self.stdout.write(
                            self.style.WARNING(f"          TXT: '{original_extracted_filename}' не классифицирован."))
                else:
                    self.stdout.write(f"        Пропускаем (не TXT): {original_extracted_filename}")
        return classified_count

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE(f"--- Начинаем обработку РЭШ ЦДИ ({HSE_CDE_PAGE_URL}) ---"))
        start_time = time.time()

        # Создаем/проверяем основную директорию для классифицированных данных РЭШ ЦДИ
        if not os.path.exists(HSE_CDE_CLASSIFIED_DATA_PATH):
            try:
                os.makedirs(HSE_CDE_CLASSIFIED_DATA_PATH)
                self.stdout.write(self.style.SUCCESS(f"Создана директория: {HSE_CDE_CLASSIFIED_DATA_PATH}"))
            except OSError as e:
                self.stderr.write(
                    self.style.ERROR(f"Не удалось создать директорию {HSE_CDE_CLASSIFIED_DATA_PATH}: {e}"))
                return

        # Временные папки внутри HSE_CDE_CLASSIFIED_DATA_PATH (будут удаляться)
        temp_download_dir = os.path.join(HSE_CDE_CLASSIFIED_DATA_PATH, "_temp_downloads")
        temp_extract_dir = os.path.join(HSE_CDE_CLASSIFIED_DATA_PATH, "_temp_extracted")

        # Очищаем/создаем временные папки перед каждым запуском
        if os.path.exists(temp_download_dir): shutil.rmtree(temp_download_dir)
        if os.path.exists(temp_extract_dir): shutil.rmtree(temp_extract_dir)
        os.makedirs(temp_download_dir, exist_ok=True)
        os.makedirs(temp_extract_dir, exist_ok=True)

        all_zip_links = self.fetch_all_zip_links_from_page(HSE_CDE_PAGE_URL)

        if not all_zip_links:
            self.stdout.write(self.style.WARNING("Не найдено ZIP ссылок для обработки на странице РЭШ ЦДИ."))
            # Очищаем временные папки, так как они больше не нужны
            if os.path.exists(temp_download_dir): shutil.rmtree(temp_download_dir)
            if os.path.exists(temp_extract_dir): shutil.rmtree(temp_extract_dir)
            return

        downloaded_archives_count = 0
        successfully_classified_files_count = 0

        for zip_url in all_zip_links:
            self.stdout.write(f"  Обработка архива: {os.path.basename(urlparse(zip_url).path)}")
            # Для каждого ZIP-архива очищаем папку с извлеченными файлами (если вдруг остались от предыдущей итерации)
            if os.path.exists(temp_extract_dir):  # Убедимся, что удаляем только содержимое, а не всю папку hse_cde
                for item in os.listdir(temp_extract_dir):
                    item_path = os.path.join(temp_extract_dir, item)
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        os.unlink(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
            else:
                os.makedirs(temp_extract_dir, exist_ok=True)

            if self.download_and_extract_single_zip(zip_url, temp_download_dir, temp_extract_dir):
                downloaded_archives_count += 1
                classified_in_this_zip = self.classify_and_move_extracted_files(temp_extract_dir,
                                                                                HSE_CDE_CLASSIFIED_DATA_PATH, zip_url)
                successfully_classified_files_count += classified_in_this_zip
                time.sleep(0.5)  # Небольшая задержка между обработкой архивов
            else:
                self.stderr.write(self.style.ERROR(f"    Не удалось скачать или распаковать архив: {zip_url}"))

        # Финальная очистка временных папок
        if os.path.exists(temp_download_dir): shutil.rmtree(temp_download_dir)
        if os.path.exists(temp_extract_dir): shutil.rmtree(temp_extract_dir)
        self.stdout.write("  Временные папки очищены.")

        end_time = time.time()
        msg_style = self.style.SUCCESS if downloaded_archives_count > 0 else self.style.WARNING
        self.stdout.write(msg_style(f"Обработка РЭШ ЦДИ завершена за {end_time - start_time:.2f} сек. "
                                    f"Скачано архивов: {downloaded_archives_count}. "
                                    f"Классифицировано и перемещено TXT файлов: {successfully_classified_files_count}"))