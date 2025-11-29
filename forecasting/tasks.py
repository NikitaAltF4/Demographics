from celery import \
    shared_task  # current_task можно убрать, если self.request.id не используется для чего-то специфичного
from django.core.cache import cache
from django.template.loader import render_to_string
import copy
import logging
from typing import Dict, List, Any, Tuple, Union, Optional  # Добавлен для типизации
import json
from .forecaster import PopulationForecaster

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from .models import ForecastRun  # <--- ИМПОРТ ВАШЕЙ МОДЕЛИ
import os  # Для работы с путями
from django.conf import settings  # Для MEDIA_ROOT

# Убедитесь, что эти импорты или определения констант корректны для вашего проекта
# Если они определены в views.py, их лучше вынести в общий utils.py или импортировать
# Я добавлю их определения здесь для полноты примера.
User = get_user_model()
logger = logging.getLogger(__name__)

# === КОНСТАНТЫ (лучше вынести в forecasting/constants.py или utils.py) ===
# Предположим, что эти константы ранее были в views.py
DEFAULT_HISTORICAL_START_YEAR = 2012
DEFAULT_HISTORICAL_END_YEAR = 2022
DEFAULT_FORECAST_START_YEAR = DEFAULT_HISTORICAL_END_YEAR + 1
DEFAULT_FORECAST_END_YEAR = DEFAULT_HISTORICAL_END_YEAR + 10

MAP_CODE_FOR_ALL_RUSSIA = "RU-RF"
ID_FOR_ALL_RUSSIA = 1
ID_SETTLEMENT_TOTAL = 1
ID_SETTLEMENT_URBAN = 2
ID_SETTLEMENT_RURAL = 3
SEX_CODE_TOTAL = "A"
SEX_CODE_MALE = "M"
SEX_CODE_FEMALE = "F"

# Сценарии (из forecaster.py или coefficient_calculator.py)
# Для примера, если они там: from .coefficient_calculator import SCENARIO_LAST_YEAR, ...
# Либо определим здесь, если они не импортируются легко:
SCENARIO_LAST_YEAR = 'last_year'
SCENARIO_HISTORICAL_TREND = 'historical_trend'
SCENARIO_MANUAL_PERCENT = 'manual_percent'


# === КОНЕЦ КОНСТАНТ ===


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (лучше вынести в forecasting/utils.py) ===
def _get_region_name_by_id_for_task(region_id: int) -> str:
    from data_collector.models import Region  # Импорт внутри, чтобы избежать проблем при старте Celery
    try:
        return Region.objects.get(id=region_id).name
    except Region.DoesNotExist:
        logger.warning(f"Region with ID {region_id} not found in task helper.")
        return f"Регион ID {region_id}"


def _prepare_display_params_for_task(forecast_params_source: Dict, form_warnings_list: List) -> Dict:
    # Адаптированная версия _prepare_display_params из views.py
    # Не использует объект request
    params_for_display = copy.deepcopy(forecast_params_source)
    try:
        region_ids_list = forecast_params_source.get('region_ids', [])
        if region_ids_list:
            is_all_russia_display = False
            if len(region_ids_list) == 1 and region_ids_list[0] == ID_FOR_ALL_RUSSIA:
                from data_collector.models import Region
                russia_obj_check = Region.objects.filter(id=ID_FOR_ALL_RUSSIA,
                                                         map_code=MAP_CODE_FOR_ALL_RUSSIA).first()
                if russia_obj_check: is_all_russia_display = True

            if is_all_russia_display:
                params_for_display['region_names_display'] = [
                    russia_obj_check.name if russia_obj_check else "Российская Федерация (по ID)"]
            elif len(region_ids_list) == 1:
                params_for_display['region_names_display'] = [_get_region_name_by_id_for_task(region_ids_list[0])]
            else:
                names = [_get_region_name_by_id_for_task(rid) for rid in region_ids_list]
                params_for_display['region_names_display'] = names if names else ["Не удалось определить регионы"]
        else:
            params_for_display['region_names_display'] = ["Регионы не указаны"]
    except Exception as e_region:
        logger.error(f"Ошибка при получении названий регионов для отображения в задаче: {e_region}")
        params_for_display['region_names_display'] = [f"Ошибка получения названий: {e_region}"]
        if form_warnings_list is not None:  # form_warnings_list - это current_task_form_warnings_copy
            form_warnings_list.append(f"Ошибка отображения названий регионов в задаче: {e_region}")

    settlement_map = {ID_SETTLEMENT_TOTAL: "Все население (городское + сельское)",
                      ID_SETTLEMENT_URBAN: "Городское население", ID_SETTLEMENT_RURAL: "Сельское население"}
    params_for_display['settlement_type_name_display'] = settlement_map.get(
        forecast_params_source.get('settlement_type_id'), "Неизвестный тип")

    sex_map = {SEX_CODE_TOTAL: "Оба пола", SEX_CODE_MALE: "Мужской", SEX_CODE_FEMALE: "Женский"}
    params_for_display['sex_code_name_display'] = sex_map.get(forecast_params_source.get('sex_code_target'),
                                                              "Неизвестный пол")

    scenario_names_map_display = {
        SCENARIO_LAST_YEAR: "Фиксированные (посл. год)",
        SCENARIO_MANUAL_PERCENT: "Ручное изменение",
        SCENARIO_HISTORICAL_TREND: "Исторический тренд"
    }

    def get_scenario_display_for_prepare(scen_key, perc_key):
        scenario_code = forecast_params_source.get(scen_key)
        name = scenario_names_map_display.get(scenario_code, str(scenario_code).replace('_', ' ').capitalize())
        if scenario_code == SCENARIO_MANUAL_PERCENT:
            perc = forecast_params_source.get(perc_key)
            if perc is not None: name += f" ({perc:+.1f}%)"
        return name

    params_for_display['birth_rate_scenario_name_display'] = get_scenario_display_for_prepare('birth_rate_scenario',
                                                                                              'birth_rate_manual_change_percent')
    params_for_display['death_rate_scenario_male_name_display'] = get_scenario_display_for_prepare(
        'death_rate_scenario_male', 'death_rate_manual_change_percent_male')
    params_for_display['death_rate_scenario_female_name_display'] = get_scenario_display_for_prepare(
        'death_rate_scenario_female', 'death_rate_manual_change_percent_female')
    params_for_display['migration_scenario_name_display'] = get_scenario_display_for_prepare('migration_scenario',
                                                                                             'migration_manual_change_percent')

    target_age = forecast_params_source.get('target_age_group_input')
    params_for_display['target_age_group_input_display'] = f"{target_age[0]} - {target_age[1]} лет" if isinstance(
        target_age, tuple) else str(target_age)

    params_for_display.setdefault('output_detailed_by_age', False)
    params_for_display.setdefault('include_migration', False)
    return params_for_display


# === КОНЕЦ ВСПОМОГАТЕЛЬНЫХ ФУНКЦИЙ ===
User = get_user_model()


@shared_task(bind=True)
def calculate_forecast_task(self, task_id: str, all_run_configurations: List[Dict],
                            base_forecast_params_no_combination_specifics: Dict,
                            output_detailed_by_age_global: bool,
                            user_selected_settlement_id: int,
                            user_selected_sex_code: str,
                            initial_processed_region_db_ids: List[int],
                            form_warnings_initial: List[str],
                            params_for_group_context_map: Dict,
                            active_data_keys_list: List[str],
                            results_template_name: str,
                            current_user_id: Optional[int],
                            current_warnings_accumulator=None):  # current_warnings_accumulator теперь не используется активно
    try:
        celery_task_id_str = self.request.id if self.request.id else "NOT_AVAILABLE"
        logger.info(f"Task {task_id} (Celery ID: {celery_task_id_str}): Starting forecast calculation.")

        grouped_results_data: Dict[str, Dict[str, Any]] = {}
        completed_configurations = 0
        total_configurations = len(all_run_configurations)

        progress_data_init = {
            'total_configurations': total_configurations,
            'completed_configurations': 0,
            'status': 'starting',
            'warnings': list(form_warnings_initial),
            'html_result': None,
            'error_message': None
        }
        cache.set(f'forecast_progress_{task_id}', progress_data_init, timeout=3600)
        logger.debug(f"Task {task_id}: Initial progress set: {progress_data_init}")

        for i, run_spec in enumerate(all_run_configurations):
            logger.debug(
                f"Task {task_id}: Processing config {i + 1}/{total_configurations} for group {run_spec['region_group_key']}")

            forecaster = PopulationForecaster(run_spec['params'])
            run_result_data = forecaster.run_forecast()

            region_group_key = run_spec['region_group_key']
            current_params_of_this_run = run_spec['params']  # noqa: F841
            settlement_id_of_this_run = current_params_of_this_run['settlement_type_id']
            sex_code_of_this_run = current_params_of_this_run['sex_code_target']

            group_entry = grouped_results_data.setdefault(region_group_key, {
                'title': region_group_key,
                'params_for_display_group_context': params_for_group_context_map.get(region_group_key, {}),
                'warnings': set(),
                'data_by_year': {}
            })

            if run_result_data.get('warnings'):
                group_entry['warnings'].update(run_result_data['warnings'])

            settlement_prefix = "urban_" if settlement_id_of_this_run == ID_SETTLEMENT_URBAN else \
                ("rural_" if settlement_id_of_this_run == ID_SETTLEMENT_RURAL else \
                     ("total_" if settlement_id_of_this_run == ID_SETTLEMENT_TOTAL else "unknown_sett_"))
            sex_suffix = "male" if sex_code_of_this_run == SEX_CODE_MALE else \
                ("female" if sex_code_of_this_run == SEX_CODE_FEMALE else \
                     ("total" if sex_code_of_this_run == SEX_CODE_TOTAL else "unknown_sex_"))

            data_key_base = f"{settlement_prefix}{sex_suffix}"
            if "unknown" in data_key_base:
                logger.warning(
                    f"Task {task_id}: Unknown settlement/sex combination for data_key_base: sett_id={settlement_id_of_this_run}, sex_code={sex_code_of_this_run}")

            for year_result in run_result_data.get('results', []):
                year = year_result['year']
                year_data_entry = group_entry['data_by_year'].setdefault(year, {})
                if output_detailed_by_age_global:
                    age_data_map = year_data_entry.setdefault('age_data_map', {})
                    for age_pop_item in year_result.get('population_by_age', []):
                        age_key = str(age_pop_item['age'])
                        age_specific_entry = age_data_map.setdefault(age_key, {'age_display': age_key})
                        age_specific_entry[data_key_base] = age_pop_item['population']
                else:
                    year_data_entry[data_key_base] = year_result['total_population_in_target_group']

            completed_configurations += 1
            current_progress_data = cache.get(f'forecast_progress_{task_id}')
            if not current_progress_data:
                current_progress_data = copy.deepcopy(progress_data_init)
                current_progress_data['warnings'] = list(form_warnings_initial)
                logger.warning(f"Task {task_id}: Cache miss for progress data during loop, re-initialized.")

            current_progress_data['completed_configurations'] = completed_configurations
            current_progress_data['status'] = 'running'

            task_warnings_set = set(current_progress_data.get('warnings', []))
            if run_result_data.get('warnings'):
                task_warnings_set.update(run_result_data['warnings'])
            current_progress_data['warnings'] = list(task_warnings_set)

            cache.set(f'forecast_progress_{task_id}', current_progress_data, timeout=3600)
            logger.debug(f"Task {task_id}: Progress updated: {completed_configurations}/{total_configurations}")

        final_grouped_list_for_template: List[Dict[str, Any]] = []
        for region_title_key, group_data_item in grouped_results_data.items():
            processed_group_item = copy.deepcopy(group_data_item)
            processed_group_item['warnings'] = sorted(list(group_data_item['warnings']))
            sorted_years_data_list: List[Dict[str, Any]] = []
            for year_val, year_content_data in sorted(group_data_item['data_by_year'].items()):
                year_item_for_list: Dict[str, Any] = {'year': year_val}
                if output_detailed_by_age_global:
                    age_data_map_for_year = year_content_data.get('age_data_map', {})

                    def age_sort_key_func(age_str_key: str) -> Union[int, str]:
                        if age_str_key.isdigit(): return int(age_str_key)
                        parts = age_str_key.split('-')[0].split('+')[0]
                        return int(parts) if parts.isdigit() else age_str_key

                    sorted_age_keys_list = sorted(list(age_data_map_for_year.keys()), key=age_sort_key_func)
                    year_item_for_list['age_rows'] = [age_data_map_for_year[key] for key in sorted_age_keys_list]
                else:
                    year_item_for_list.update(year_content_data)
                sorted_years_data_list.append(year_item_for_list)
            processed_group_item['data_by_year'] = sorted_years_data_list
            final_grouped_list_for_template.append(processed_group_item)

        overall_display_params_src_task = base_forecast_params_no_combination_specifics.copy()
        overall_display_params_src_task['settlement_type_id'] = user_selected_settlement_id
        overall_display_params_src_task['sex_code_target'] = user_selected_sex_code
        overall_display_params_src_task['region_ids'] = initial_processed_region_db_ids

        current_task_form_warnings_copy = list(form_warnings_initial)
        params_display_overall = _prepare_display_params_for_task(overall_display_params_src_task,
                                                                  current_task_form_warnings_copy)

        # final_all_task_warnings_set включает current_task_form_warnings_copy (с возможными добавлениями из _prepare...)
        # и предупреждения из кеша (собранные во время цикла)
        final_all_task_warnings_set = set(current_task_form_warnings_copy)
        current_progress_final_read = cache.get(f'forecast_progress_{task_id}')
        if current_progress_final_read and current_progress_final_read.get('warnings'):
            final_all_task_warnings_set.update(current_progress_final_read['warnings'])

        user_for_template = None
        if current_user_id is not None:
            try:
                user_for_template = User.objects.get(id=current_user_id)
                logger.info(f"Task {task_id}: User '{user_for_template.username}' found for template rendering.")
            except User.DoesNotExist:
                logger.warning(
                    f"Task {task_id}: User with ID {current_user_id} not found. Template will be rendered as for anonymous user.")
        else:
            logger.info(f"Task {task_id}: No user ID provided. Template will be rendered as for anonymous user.")

        # Инициализируем final_all_warnings_list на основе всех собранных до этого момента предупреждений
        final_all_warnings_list = sorted(list(final_all_task_warnings_set))  # <--- ИЗМЕНЕНИЕ 1

        saved_file_path = None

        if user_for_template:
            logger.info(f"Task {task_id}: Preparing to save forecast history for user {user_for_template.username}.")
            data_for_file_storage = {
                'original_input_params': base_forecast_params_no_combination_specifics,
                'display_params_overall': params_display_overall,
                'all_warnings': final_all_warnings_list,  # Используем уже существующий список
                'grouped_forecasts_data': final_grouped_list_for_template,
                'output_detailed_by_age_global': output_detailed_by_age_global,
                'user_selected_settlement_id': user_selected_settlement_id,
                'user_selected_sex_code': user_selected_sex_code,
                'ID_SETTLEMENT_TOTAL': ID_SETTLEMENT_TOTAL, 'ID_SETTLEMENT_URBAN': ID_SETTLEMENT_URBAN,
                'ID_SETTLEMENT_RURAL': ID_SETTLEMENT_RURAL,
                'SEX_CODE_TOTAL': SEX_CODE_TOTAL, 'SEX_CODE_MALE': SEX_CODE_MALE, 'SEX_CODE_FEMALE': SEX_CODE_FEMALE,
                'active_data_keys': sorted(active_data_keys_list)
            }

            results_filename = f"forecast_results_{task_id}.json"
            user_folder_name_for_path = str(current_user_id)
            relative_file_path_for_db = os.path.join('forecast_history', user_folder_name_for_path, results_filename)
            full_storage_path = os.path.join(settings.MEDIA_ROOT, relative_file_path_for_db)

            try:
                os.makedirs(os.path.dirname(full_storage_path), exist_ok=True)
                with open(full_storage_path, 'w', encoding='utf-8') as f:
                    json.dump(data_for_file_storage, f, ensure_ascii=False, indent=4)
                logger.info(f"Task {task_id}: Результаты прогноза для истории сохранены в файл: {full_storage_path}")
                saved_file_path = relative_file_path_for_db
            except IOError as e:
                logger.error(f"Task {task_id}: Ошибка сохранения файла результатов истории {full_storage_path}: {e}")
                # Добавляем ошибку в ОБЩИЙ список предупреждений
                final_all_warnings_list.append(f"Внимание: Ошибка при сохранении файла результатов для истории ({e}).")
                final_all_warnings_list = sorted(list(set(final_all_warnings_list)))  # Обновить и отсортировать

            try:
                ForecastRun.objects.create(
                    id=task_id,
                    user=user_for_template,
                    input_parameters_json=params_display_overall,  # <--- ИЗМЕНЕНИЕ ЗДЕСЬ
                    results_file_path=saved_file_path,
                    warnings_json=final_all_warnings_list  # Используем обновленный список
                )
                logger.info(
                    f"Task {task_id}: Запись о прогнозе для пользователя {user_for_template.username} сохранена в ForecastRun.")
            except Exception as e_db:
                logger.error(
                    f"Task {task_id}: Ошибка сохранения записи ForecastRun в БД для пользователя {user_for_template.username}: {e_db}")
                final_all_warnings_list.append(
                    f"Внимание: Ошибка при сохранении записи о прогнозе в историю БД ({e_db}).")
                final_all_warnings_list = sorted(list(set(final_all_warnings_list)))
        else:
            logger.info(f"Task {task_id}: Пользователь не аутентифицирован. История прогноза не будет сохранена.")

        context = {
            'grouped_forecasts': final_grouped_list_for_template,
            'params_display_overall': params_display_overall,
            'form_warnings': final_all_warnings_list,  # <--- ИЗМЕНЕНИЕ 2 (используем список со всеми предупреждениями)
            'output_detailed_by_age_global': output_detailed_by_age_global,
            'active_data_keys': sorted(active_data_keys_list),
            'user_selected_settlement_id': user_selected_settlement_id,
            'user_selected_sex_code': user_selected_sex_code,
            'ID_SETTLEMENT_TOTAL': ID_SETTLEMENT_TOTAL,
            'ID_SETTLEMENT_URBAN': ID_SETTLEMENT_URBAN,
            'ID_SETTLEMENT_RURAL': ID_SETTLEMENT_RURAL,
            'SEX_CODE_TOTAL': SEX_CODE_TOTAL,
            'SEX_CODE_MALE': SEX_CODE_MALE,
            'SEX_CODE_FEMALE': SEX_CODE_FEMALE,
            'scenarios': {
                'last_year': SCENARIO_LAST_YEAR,
                'historical_trend': SCENARIO_HISTORICAL_TREND,
                'manual_percent': SCENARIO_MANUAL_PERCENT
            },
            'user': user_for_template
        }

        context['grouped_forecasts_json'] = json.dumps(final_grouped_list_for_template)
        context['active_data_keys_json'] = json.dumps(sorted(list(active_data_keys_list)))
        context['output_detailed_by_age_global_js'] = json.dumps(output_detailed_by_age_global)

        html_result_rendered = render_to_string(results_template_name, context)

        final_progress_data_to_set = cache.get(f'forecast_progress_{task_id}')
        if not final_progress_data_to_set:
            final_progress_data_to_set = copy.deepcopy(progress_data_init)
            logger.warning(
                f"Task {task_id}: Cache miss for final progress data just before setting completion, re-initialized.")

        final_progress_data_to_set['status'] = 'completed'
        final_progress_data_to_set['html_result'] = html_result_rendered
        final_progress_data_to_set['completed_configurations'] = total_configurations
        final_progress_data_to_set[
            'warnings'] = final_all_warnings_list  # <--- ИЗМЕНЕНИЕ 3 (сохраняем все собранные предупреждения)

        cache.set(f'forecast_progress_{task_id}', final_progress_data_to_set, timeout=3600)

        logger.info(f"Task {task_id} (Celery ID: {celery_task_id_str}): Forecast calculation completed.")
        return f"Task {task_id} completed successfully."

    except Exception as e_task:
        celery_task_id_str_err = self.request.id if self.request.id else "NOT_AVAILABLE"
        logger.error(
            f"Task {task_id} (Celery ID: {celery_task_id_str_err}): Error during forecast calculation: {e_task}",
            exc_info=True)

        error_progress_data_cache = cache.get(f'forecast_progress_{task_id}')
        if not error_progress_data_cache:
            completed_conf_val = completed_configurations if 'completed_configurations' in locals() else 0
            total_conf_val = total_configurations if 'total_configurations' in locals() else (
                len(all_run_configurations) if 'all_run_configurations' in locals() else 0)
            error_progress_data_cache = {
                'total_configurations': total_conf_val,
                'completed_configurations': completed_conf_val,
                'warnings': list(form_warnings_initial) if 'form_warnings_initial' in locals() else [],
                'html_result': None,
            }
        error_progress_data_cache['status'] = 'error'
        error_progress_data_cache['error_message'] = f"Ошибка в фоновой задаче: ({type(e_task).__name__}) {str(e_task)}"
        cache.set(f'forecast_progress_{task_id}', error_progress_data_cache, timeout=3600)

        return f"Task {task_id} failed: {e_task}"