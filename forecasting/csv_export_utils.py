import csv
import logging
from typing import Dict, List, Any, Optional

# Импортируем константы, если они нужны для логики формирования заголовков
# Лучше, если бы они были в общем файле constants.py
ID_SETTLEMENT_TOTAL = 1
ID_SETTLEMENT_URBAN = 2
ID_SETTLEMENT_RURAL = 3
SEX_CODE_TOTAL = "A"
SEX_CODE_MALE = "M"
SEX_CODE_FEMALE = "F"

logger = logging.getLogger(__name__)

# Карта ключей параметров на человекочитаемые метки (может быть общей с Excel utils)
PARAM_LABELS_MAP_FOR_EXPORT = {
    'region_names_display': "Изначально запрошенные регионы",
    'settlement_type_name_display': "Тип поселения (исходно)",
    'sex_code_name_display': "Целевой пол (исходно)",
    'forecast_period_display': "Период прогноза",
    'historical_period_display': "Период ист. данных",
    'target_age_group_input_display': "Возрастная группа (исходно)",
    'output_detailed_by_age_display': "Детализация по возрастам (на момент запроса)",
    'birth_rate_scenario_name_display': "Сценарий рождаемости",
    'death_rate_scenario_male_name_display': "Сценарий смертности (М)",
    'death_rate_scenario_female_name_display': "Сценарий смертности (Ж)",
    'include_migration_display': "Учет миграции",
    'migration_scenario_name_display': "Сценарий миграции",
}


def write_forecast_data_to_csv(
        writer: csv.writer,  # Объект csv.writer
        params_display_overall: Dict,
        all_warnings: List[str],
        grouped_forecasts_data: List[Dict],
        # Параметры, влияющие на структуру таблицы:
        output_detailed_by_age_global: bool,
        user_selected_settlement_id: int,
        user_selected_sex_code: str
):
    """
    Записывает данные прогноза в предоставленный csv.writer.
    """

    # --- Секция 1: Параметры и Предупреждения ---
    writer.writerow(["Общие параметры исходного запроса"])
    writer.writerow([])  # Пустая строка для разделения

    display_values_for_params = params_display_overall.copy()
    # Подготовка отображаемых значений (копипаста из excel_export_utils, лучше унифицировать)
    if 'forecast_period_display' not in display_values_for_params:  # Для случая, если эти ключи не были подготовлены заранее
        display_values_for_params[
            'forecast_period_display'] = f"{params_display_overall.get('forecast_start_year')} - {params_display_overall.get('forecast_end_year')}"
    if 'historical_period_display' not in display_values_for_params:
        display_values_for_params[
            'historical_period_display'] = f"{params_display_overall.get('historical_data_start_year')} - {params_display_overall.get('historical_data_end_year')}"
    if 'output_detailed_by_age_display' not in display_values_for_params:
        display_values_for_params['output_detailed_by_age_display'] = "Да" if output_detailed_by_age_global else "Нет"
    if 'include_migration_display' not in display_values_for_params:
        display_values_for_params['include_migration_display'] = "Да" if params_display_overall.get(
            'include_migration') else "Нет"

    for key, label in PARAM_LABELS_MAP_FOR_EXPORT.items():
        value_to_write = display_values_for_params.get(key)

        if key == 'migration_scenario_name_display' and not display_values_for_params.get('include_migration'):
            continue

        if value_to_write is not None:
            if isinstance(value_to_write, list): value_to_write = ", ".join(map(str, value_to_write))
            writer.writerow([label, str(value_to_write)])

    writer.writerow([])  # Пустая строка
    if all_warnings:
        writer.writerow(["Предупреждения и примечания"])
        for warning in all_warnings:
            writer.writerow([warning])
        writer.writerow([])

    # --- Секция 2: Данные по группам регионов ---
    for group_data in grouped_forecasts_data:
        writer.writerow([])  # Пустая строка перед новой группой
        writer.writerow([f"Результаты для: {group_data['title']}"])

        # Формирование заголовков таблицы (аналогично Excel)
        header_cols = ['Год']
        if output_detailed_by_age_global: header_cols.append('Возраст')

        # Городские
        if user_selected_settlement_id == ID_SETTLEMENT_TOTAL or user_selected_settlement_id == ID_SETTLEMENT_URBAN:
            urban_subheaders = []
            if user_selected_sex_code == SEX_CODE_TOTAL or user_selected_sex_code == SEX_CODE_MALE: urban_subheaders.append(
                'Городское (М)')
            if user_selected_sex_code == SEX_CODE_TOTAL or user_selected_sex_code == SEX_CODE_FEMALE: urban_subheaders.append(
                'Городское (Ж)')
            if user_selected_sex_code == SEX_CODE_TOTAL: urban_subheaders.append('Городское (Всего)')
            if urban_subheaders: header_cols.extend(urban_subheaders)

        # Сельские
        if user_selected_settlement_id == ID_SETTLEMENT_TOTAL or user_selected_settlement_id == ID_SETTLEMENT_RURAL:
            rural_subheaders = []
            if user_selected_sex_code == SEX_CODE_TOTAL or user_selected_sex_code == SEX_CODE_MALE: rural_subheaders.append(
                'Сельское (М)')
            if user_selected_sex_code == SEX_CODE_TOTAL or user_selected_sex_code == SEX_CODE_FEMALE: rural_subheaders.append(
                'Сельское (Ж)')
            if user_selected_sex_code == SEX_CODE_TOTAL: rural_subheaders.append('Сельское (Всего)')
            if rural_subheaders: header_cols.extend(rural_subheaders)

        writer.writerow(header_cols)

        # Данные
        for year_item in group_data['data_by_year']:
            if output_detailed_by_age_global:
                for age_row_idx, age_row in enumerate(year_item['age_rows']):
                    row_values = [year_item['year'] if age_row_idx == 0 else '',
                                  age_row['age_display']]  # Год только для первой строки возраста

                    # Городские данные
                    if user_selected_settlement_id == ID_SETTLEMENT_TOTAL or user_selected_settlement_id == ID_SETTLEMENT_URBAN:
                        if user_selected_sex_code == SEX_CODE_TOTAL or user_selected_sex_code == SEX_CODE_MALE: row_values.append(
                            age_row.get('urban_male', '-'))
                        if user_selected_sex_code == SEX_CODE_TOTAL or user_selected_sex_code == SEX_CODE_FEMALE: row_values.append(
                            age_row.get('urban_female', '-'))
                        if user_selected_sex_code == SEX_CODE_TOTAL: row_values.append(age_row.get('urban_total', '-'))
                    # Сельские данные
                    if user_selected_settlement_id == ID_SETTLEMENT_TOTAL or user_selected_settlement_id == ID_SETTLEMENT_RURAL:
                        if user_selected_sex_code == SEX_CODE_TOTAL or user_selected_sex_code == SEX_CODE_MALE: row_values.append(
                            age_row.get('rural_male', '-'))
                        if user_selected_sex_code == SEX_CODE_TOTAL or user_selected_sex_code == SEX_CODE_FEMALE: row_values.append(
                            age_row.get('rural_female', '-'))
                        if user_selected_sex_code == SEX_CODE_TOTAL: row_values.append(age_row.get('rural_total', '-'))
                    writer.writerow(row_values)
            else:  # Недетализированный по возрастам
                row_values = [year_item['year']]
                # Городские данные
                if user_selected_settlement_id == ID_SETTLEMENT_TOTAL or user_selected_settlement_id == ID_SETTLEMENT_URBAN:
                    if user_selected_sex_code == SEX_CODE_TOTAL or user_selected_sex_code == SEX_CODE_MALE: row_values.append(
                        year_item.get('urban_male', '-'))
                    if user_selected_sex_code == SEX_CODE_TOTAL or user_selected_sex_code == SEX_CODE_FEMALE: row_values.append(
                        year_item.get('urban_female', '-'))
                    if user_selected_sex_code == SEX_CODE_TOTAL: row_values.append(year_item.get('urban_total', '-'))
                # Сельские данные
                if user_selected_settlement_id == ID_SETTLEMENT_TOTAL or user_selected_settlement_id == ID_SETTLEMENT_RURAL:
                    if user_selected_sex_code == SEX_CODE_TOTAL or user_selected_sex_code == SEX_CODE_MALE: row_values.append(
                        year_item.get('rural_male', '-'))
                    if user_selected_sex_code == SEX_CODE_TOTAL or user_selected_sex_code == SEX_CODE_FEMALE: row_values.append(
                        year_item.get('rural_female', '-'))
                    if user_selected_sex_code == SEX_CODE_TOTAL: row_values.append(year_item.get('rural_total', '-'))
                writer.writerow(row_values)
