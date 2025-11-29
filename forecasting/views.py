
import json
import logging
import copy  # Необходим для deepcopy, если используется
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views import View
from typing import Any, Optional, List, Dict, Union, Tuple
from django.template.loader import render_to_string  # Остается, но используется в задаче
from django.core.cache import cache
import uuid
from .csv_export_utils import write_forecast_data_to_csv
import os
import csv
from io import BytesIO
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator # Для пагинации, если прогнозов много
from .models import ForecastRun
from .excel_export_utils import generate_forecast_excel_workbook
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, Http404, JsonResponse
from .tasks import (ID_SETTLEMENT_TOTAL, ID_SETTLEMENT_URBAN, ID_SETTLEMENT_RURAL,
                    SEX_CODE_TOTAL, SEX_CODE_MALE, SEX_CODE_FEMALE,
                    SCENARIO_LAST_YEAR, SCENARIO_HISTORICAL_TREND, SCENARIO_MANUAL_PERCENT)
from .forecaster import PopulationForecaster  # Нужен только если _prepare_display_params или что-то еще его использует
from data_collector.models import Region
from .tasks import calculate_forecast_task  # Импорт вашей задачи Celery

logger = logging.getLogger(__name__)

# Для примера, оставляю константы здесь. ИДЕАЛЬНО: вынести их в отдельный файл.
MAP_CODE_FOR_ALL_RUSSIA = "RU-RF"
ID_FOR_ALL_RUSSIA = 1
ID_SETTLEMENT_TOTAL = 1
ID_SETTLEMENT_URBAN = 2
ID_SETTLEMENT_RURAL = 3
SEX_CODE_TOTAL = "A"
SEX_CODE_MALE = "M"
SEX_CODE_FEMALE = "F"
DEFAULT_HISTORICAL_START_YEAR = 2012
DEFAULT_HISTORICAL_END_YEAR = 2022
DEFAULT_FORECAST_START_YEAR = DEFAULT_HISTORICAL_END_YEAR + 1
DEFAULT_FORECAST_END_YEAR = DEFAULT_HISTORICAL_END_YEAR + 10
SCENARIO_LAST_YEAR = 'last_year'  # Предполагаемые значения
SCENARIO_HISTORICAL_TREND = 'historical_trend'
SCENARIO_MANUAL_PERCENT = 'manual_percent'






class ForecastView(View):
    template_name = 'forecasting_parameters.html'
    results_template_name = 'forecast_results.html'  # Имя шаблона будет передано в задачу

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        regions_from_db = Region.objects.filter(map_code__isnull=False, map_code__startswith="RU-")
        regions_js_map_data = {r.map_code: r.id for r in regions_from_db}
        context = {
            'default_hist_start': DEFAULT_HISTORICAL_START_YEAR,
            'default_hist_end': DEFAULT_HISTORICAL_END_YEAR,
            'default_forecast_start': DEFAULT_FORECAST_START_YEAR,
            'default_forecast_end': DEFAULT_FORECAST_END_YEAR,
            'scenarios': {
                'last_year': SCENARIO_LAST_YEAR,
                'historical_trend': SCENARIO_HISTORICAL_TREND,
                'manual_percent': SCENARIO_MANUAL_PERCENT
            },
            'regions_js_map': json.dumps(regions_js_map_data),
        }
        return render(request, self.template_name, context)

    # _get_region_name_by_id и _prepare_display_params:
    # Если они нужны только для подготовки данных для задачи Celery,
    # их можно сделать статическими методами или обычными функциями.
    # Если _prepare_display_params все еще нужен для метода GET (хотя вряд ли), он остается здесь.
    # Адаптированная версия _prepare_display_params есть в tasks.py (_prepare_display_params_for_task)

    # Эта версия остается во view, если нужна для GET или какой-то другой логики во view
    def _get_region_name_by_id_view_version(self, region_id: int) -> str:
        try:
            return Region.objects.get(id=region_id).name
        except Region.DoesNotExist:
            return f"Регион ID {region_id}"

    def _prepare_display_params_view_version(self, forecast_params_source: Dict, form_warnings_list: List) -> Dict:
        # Эта функция может остаться, если вы ее используете для чего-то в GET-запросе,
        # но для задачи Celery используется _prepare_display_params_for_task.
        # Если она здесь не нужна, ее можно удалить.
        # Я оставлю ее структуру, но логику нужно проверить.
        params_for_display = copy.deepcopy(forecast_params_source)
        # ... (скопируйте сюда логику _prepare_display_params из вашего предыдущего views.py,
        #      используя _get_region_name_by_id_view_version)
        # ВАЖНО: Убедитесь, что она не зависит от request.POST и использует только forecast_params_source.
        # Сейчас params_for_group_context_map вычисляется перед вызовом задачи Celery,
        # используя эту функцию (_prepare_display_params_view_version).
        try:
            region_ids_list = forecast_params_source.get('region_ids', [])
            if region_ids_list:
                is_all_russia_display = False
                if len(region_ids_list) == 1 and region_ids_list[0] == ID_FOR_ALL_RUSSIA:
                    russia_obj_check = Region.objects.filter(id=ID_FOR_ALL_RUSSIA,
                                                             map_code=MAP_CODE_FOR_ALL_RUSSIA).first()
                    if russia_obj_check: is_all_russia_display = True

                if is_all_russia_display:
                    params_for_display['region_names_display'] = [
                        russia_obj_check.name if russia_obj_check else "Российская Федерация (по ID)"]
                elif len(region_ids_list) == 1:
                    params_for_display['region_names_display'] = [
                        self._get_region_name_by_id_view_version(region_ids_list[0])]
                else:
                    names = [self._get_region_name_by_id_view_version(rid) for rid in region_ids_list]
                    params_for_display['region_names_display'] = names if names else ["Не удалось определить регионы"]
            else:
                params_for_display['region_names_display'] = ["Регионы не указаны (ошибка в параметрах)"]
        except Exception as e_region:
            logger.error(f"Ошибка при получении названий регионов для отображения (view): {e_region}")
            params_for_display['region_names_display'] = [f"Ошибка получения названий (view): {e_region}"]
            if form_warnings_list is not None:
                form_warnings_list.append(f"Ошибка отображения названий регионов (view): {e_region}")

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

        def get_scenario_display_for_prepare(scen_key, perc_key):  # Эта вложенная функция должна быть здесь
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

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        task_id_str = str(uuid.uuid4())  # Это task_id для нашего кеша, не путать с Celery task id
        request.session['forecast_task_id'] = task_id_str  # Если используем сессию для чего-то еще
        logger.info(f"ForecastView POST for Task Cache ID {task_id_str}: Received request, preparing Celery task.")

        form_warnings: List[str] = []

        try:
            # --- 1. ИЗВЛЕЧЕНИЕ И ПОДГОТОВКА ПАРАМЕТРОВ ДЛЯ ЗАДАЧИ CELERY ---
            # Этот блок должен содержать ВСЮ логику из вашего предыдущего ForecastView.post
            # до цикла for run_spec in all_run_configurations:
            # (Извлечение из request.POST, формирование base_forecast_params..., all_run_configurations, etc.)

            region_map_codes_str = request.POST.get('region_ids', MAP_CODE_FOR_ALL_RUSSIA).strip()
            initial_processed_region_db_ids: List[int] = []
            # ... (Ваша логика определения initial_processed_region_db_ids из region_map_codes_str)
            if not region_map_codes_str: region_map_codes_str = MAP_CODE_FOR_ALL_RUSSIA
            map_codes_to_query_initial = [MAP_CODE_FOR_ALL_RUSSIA] if region_map_codes_str == MAP_CODE_FOR_ALL_RUSSIA \
                else [code.strip() for code in region_map_codes_str.split(',') if code.strip()]
            if not map_codes_to_query_initial: map_codes_to_query_initial = [MAP_CODE_FOR_ALL_RUSSIA]

            regions_in_db_initial = Region.objects.filter(map_code__in=map_codes_to_query_initial)
            map_code_to_id_dict = {r.map_code: r.id for r in regions_in_db_initial}
            for mc_req in map_codes_to_query_initial:
                if mc_req in map_code_to_id_dict:
                    initial_processed_region_db_ids.append(map_code_to_id_dict[mc_req])
                else:
                    form_warnings.append(f"Код региона '{mc_req}' не найден в БД и будет проигнорирован.")
            if not initial_processed_region_db_ids:
                russia_fallback = Region.objects.filter(
                    map_code=MAP_CODE_FOR_ALL_RUSSIA).first() or Region.objects.filter(id=ID_FOR_ALL_RUSSIA).first()
                if russia_fallback:
                    initial_processed_region_db_ids = [russia_fallback.id]
                    form_warnings.append(f"Запрошенные регионы не найдены. Используется '{russia_fallback.name}'.")
                else:
                    raise ValueError(f"Не удалось определить регионы из '{region_map_codes_str}'. РФ не найдена.")

            user_selected_settlement_id = int(request.POST.get('settlement_type_id', ID_SETTLEMENT_TOTAL))
            user_selected_sex_code = request.POST.get('sex_code_target', SEX_CODE_TOTAL)
            historical_data_end_year = int(request.POST.get('historical_data_end_year', DEFAULT_HISTORICAL_END_YEAR))
            forecast_start_year_from_form = int(request.POST.get('forecast_start_year', historical_data_end_year + 1))
            forecast_end_year = int(request.POST.get('forecast_end_year', DEFAULT_FORECAST_END_YEAR))
            historical_data_start_year = int(
                request.POST.get('historical_data_start_year', DEFAULT_HISTORICAL_START_YEAR))
            expected_start_year = historical_data_end_year + 1
            actual_forecast_start_year = forecast_start_year_from_form
            if forecast_start_year_from_form != expected_start_year:
                msg = (
                    f"Год начала прогноза ({forecast_start_year_from_form}) скорректирован на {expected_start_year}.")
                form_warnings.append(msg);
                logger.warning(msg)
                actual_forecast_start_year = expected_start_year
            if actual_forecast_start_year > forecast_end_year: raise ValueError("Год начала прогноза > года окончания.")

            target_age_group_type = request.POST.get('target_age_group_type', 'all_ages')
            target_age_val: Union[str, Tuple[int, int]] = "Все возрасты"
            if target_age_group_type == 'specific_range':
                start_a_str, end_a_str = request.POST.get('target_age_start'), request.POST.get('target_age_end')
                if not (start_a_str and end_a_str and start_a_str.isdigit() and end_a_str.isdigit()):
                    form_warnings.append("Некорректный диапазон возраста. Используются 'Все возрасты'.")
                else:
                    start_a, end_a = int(start_a_str), int(end_a_str)
                    if start_a > end_a:
                        form_warnings.append("Начальный возраст > конечного. Используются 'Все возрасты'.")
                    else:
                        target_age_val = (start_a, end_a)

            output_detailed_by_age_global = 'output_detailed_by_age' in request.POST

            def safe_float(val_str: Optional[str]) -> Optional[float]:  # Эта функция остаётся здесь
                if val_str is None or val_str.strip() == '': return None
                try:
                    return float(val_str.replace(',', '.'))
                except (ValueError, TypeError):
                    logger.warning(f"Не удалось преобразовать '{val_str}' в float."); return None

            base_forecast_params_no_combination_specifics: Dict[str, Any] = {
                'forecast_start_year': actual_forecast_start_year, 'forecast_end_year': forecast_end_year,
                # ... (все остальные поля для base_forecast_params_no_combination_specifics)
                'historical_data_start_year': historical_data_start_year,
                'historical_data_end_year': historical_data_end_year,
                'target_age_group_input': target_age_val, 'output_detailed_by_age': output_detailed_by_age_global,
                'settlement_type_id': user_selected_settlement_id,  # Будет перезаписано в цикле конфигураций
                'sex_code_target': user_selected_sex_code,  # Будет перезаписано в цикле конфигураций
                'birth_rate_scenario': request.POST.get('birth_rate_scenario', SCENARIO_LAST_YEAR),
                'birth_rate_manual_change_percent': safe_float(request.POST.get('birth_rate_manual_change_percent')),
                'death_rate_scenario_male': request.POST.get('death_rate_scenario_male', SCENARIO_LAST_YEAR),
                'death_rate_manual_change_percent_male': safe_float(
                    request.POST.get('death_rate_manual_change_percent_male')),
                'death_rate_scenario_female': request.POST.get('death_rate_scenario_female', SCENARIO_LAST_YEAR),
                'death_rate_manual_change_percent_female': safe_float(
                    request.POST.get('death_rate_manual_change_percent_female')),
                'include_migration': 'include_migration' in request.POST,
                'migration_scenario': request.POST.get('migration_scenario', SCENARIO_LAST_YEAR),
                'migration_manual_change_percent': safe_float(request.POST.get('migration_manual_change_percent')),
            }
            for cat_key in ['birth_rate', 'death_rate_male', 'death_rate_female', 'migration']:
                scenario_val_key = f'{cat_key}_scenario';
                manual_perc_key = f'{cat_key}_manual_change_percent'
                if base_forecast_params_no_combination_specifics.get(scenario_val_key) != SCENARIO_MANUAL_PERCENT or \
                        (cat_key == 'migration' and not base_forecast_params_no_combination_specifics.get(
                            'include_migration')):
                    base_forecast_params_no_combination_specifics[manual_perc_key] = None

            region_configs: List[Tuple[List[int], str]] = []
            is_selected_all_russia_by_id = (
                        len(initial_processed_region_db_ids) == 1 and initial_processed_region_db_ids[
                    0] == ID_FOR_ALL_RUSSIA)
            if len(initial_processed_region_db_ids) > 1 and not is_selected_all_russia_by_id:
                for rid in initial_processed_region_db_ids: region_configs.append(
                    ([rid], self._get_region_name_by_id_view_version(rid)))
            sum_title_regions = self._get_region_name_by_id_view_version(initial_processed_region_db_ids[0]) if len(
                initial_processed_region_db_ids) == 1 \
                else f"Сумма по {len(initial_processed_region_db_ids)} выбранным регионам"
            region_configs.append((initial_processed_region_db_ids, sum_title_regions))

            params_for_group_context_map: Dict[str, Dict] = {}
            for region_ids_to_run_cfg, region_title_part_cfg in region_configs:
                temp_params_for_group_ctx = base_forecast_params_no_combination_specifics.copy()
                temp_params_for_group_ctx['region_ids'] = region_ids_to_run_cfg
                temp_params_for_group_ctx['settlement_type_id'] = user_selected_settlement_id
                temp_params_for_group_ctx['sex_code_target'] = user_selected_sex_code
                # Передаем form_warnings в _prepare_display_params_view_version
                params_for_group_context_map[region_title_part_cfg] = self._prepare_display_params_view_version(
                    temp_params_for_group_ctx, form_warnings
                )

            settlement_ids_to_run_forecaster: List[int] = []
            if user_selected_settlement_id == ID_SETTLEMENT_TOTAL:
                settlement_ids_to_run_forecaster.extend([ID_SETTLEMENT_URBAN, ID_SETTLEMENT_RURAL])
            else:
                settlement_ids_to_run_forecaster.append(user_selected_settlement_id)

            sex_codes_to_run_forecaster: List[str] = []
            if user_selected_sex_code == SEX_CODE_TOTAL:
                sex_codes_to_run_forecaster.extend([SEX_CODE_MALE, SEX_CODE_FEMALE, SEX_CODE_TOTAL])
            else:
                sex_codes_to_run_forecaster.append(user_selected_sex_code)

            all_run_configurations: List[Dict[str, Any]] = []
            active_data_keys: set[str] = set()
            for region_ids_to_run, region_title_part in region_configs:
                for settlement_id_for_run in settlement_ids_to_run_forecaster:
                    for sex_code_for_run in sex_codes_to_run_forecaster:
                        current_run_params = base_forecast_params_no_combination_specifics.copy()
                        current_run_params['region_ids'] = region_ids_to_run
                        current_run_params['settlement_type_id'] = settlement_id_for_run
                        current_run_params['sex_code_target'] = sex_code_for_run
                        all_run_configurations.append(
                            {'params': current_run_params, 'region_group_key': region_title_part})

                        s_prefix = "urban_" if settlement_id_for_run == ID_SETTLEMENT_URBAN else \
                            ("rural_" if settlement_id_for_run == ID_SETTLEMENT_RURAL else \
                                 ("total_" if settlement_id_for_run == ID_SETTLEMENT_TOTAL else "unknown_sett_"))
                        g_suffix = "male" if sex_code_for_run == SEX_CODE_MALE else \
                            ("female" if sex_code_for_run == SEX_CODE_FEMALE else \
                                 ("total" if sex_code_for_run == SEX_CODE_TOTAL else "unknown_sex_"))
                        active_data_keys.add(f"{s_prefix}{g_suffix}")
            # --- КОНЕЦ БЛОКА ПОДГОТОВКИ ПАРАМЕТРОВ ---

            initial_progress_data_for_cache = {
                'total_configurations': len(all_run_configurations),
                'completed_configurations': 0,
                'status': 'queued',  # Задача поставлена в очередь
                'warnings': list(form_warnings),  # Копия начальных предупреждений из парсинга формы
                'html_result': None, 'error_message': None
            }
            cache.set(f'forecast_progress_{task_id_str}', initial_progress_data_for_cache, timeout=3600)
            logger.debug(f"Task Cache ID {task_id_str}: Initial progress data (queued) set to cache.")

            ser_id_for_celery_task = None
            if request.user.is_authenticated:
                user_id_for_celery_task = request.user.id

            # Запуск задачи Celery
            calculate_forecast_task.delay(
                task_id=task_id_str,
                all_run_configurations=all_run_configurations,
                base_forecast_params_no_combination_specifics=base_forecast_params_no_combination_specifics,
                output_detailed_by_age_global=output_detailed_by_age_global,
                user_selected_settlement_id=user_selected_settlement_id,
                user_selected_sex_code=user_selected_sex_code,
                initial_processed_region_db_ids=initial_processed_region_db_ids,
                form_warnings_initial=list(form_warnings),  # Передаем копию
                params_for_group_context_map=params_for_group_context_map,
                active_data_keys_list=list(active_data_keys),  # set в list для Celery
                results_template_name=self.results_template_name,
                current_user_id = user_id_for_celery_task
            )
            logger.info(f"Task Cache ID {task_id_str}: Celery task calculate_forecast_task.delay() called.")

            return JsonResponse({'status': 'processing_initiated', 'task_id': task_id_str,
                                 'message': 'Задача генерации прогноза поставлена в очередь.'})

        except ValueError as ve:
            logger.warning(f"Task Cache ID {task_id_str}: ValueError before Celery task dispatch: {ve}", exc_info=True)
            # ... (обработка ошибок как в предыдущей версии)
            error_data = cache.get(f'forecast_progress_{task_id_str}')
            if error_data:
                error_data['status'] = 'error'
                error_data['error_message'] = f"Ошибка в параметрах (view): {ve}"
                cache.set(f'forecast_progress_{task_id_str}', error_data, timeout=3600)
            return JsonResponse({'status': 'error', 'message': f"Ошибка в параметрах: {ve}"}, status=400)
        except Exception as e:
            logger.error(f"Task Cache ID {task_id_str}: Unexpected error before Celery task dispatch: {e}",
                         exc_info=True)
            # ... (обработка ошибок как в предыдущей версии)
            error_data_e = cache.get(f'forecast_progress_{task_id_str}')
            if error_data_e:
                error_data_e['status'] = 'error'
                error_data_e['error_message'] = f"Системная ошибка (view): ({type(e).__name__}) {e}"
                cache.set(f'forecast_progress_{task_id_str}', error_data_e, timeout=3600)
            return JsonResponse({'status': 'error', 'message': f"Произошла системная ошибка: ({type(e).__name__})"},
                                status=500)


class ForecastProgressView(View):
    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        task_id = request.GET.get('task_id')
        # Fallback to session if task_id not in GET, though JS should always send it.
        if not task_id:
            task_id = request.session.get('forecast_task_id')

        if not task_id:
            return JsonResponse({'status': 'error', 'message': 'Task ID not provided.'}, status=400)

        progress_data = cache.get(f'forecast_progress_{task_id}')

        if not progress_data:
            return JsonResponse({
                'status': 'not_found',
                'message': 'Задача не найдена. Возможно, она устарела или была удалена.',
                'progress': 0  # Provide a default progress
            }, status=404)

        response_data = {
            'task_id': task_id,
            'status': progress_data.get('status', 'unknown'),
            'progress': 0,
            'total_configurations': progress_data.get('total_configurations', 0),
            'completed_configurations': progress_data.get('completed_configurations', 0),
            'message': ''
        }

        if response_data['status'] == 'error':
            response_data['message'] = progress_data.get('error_message', 'Произошла неизвестная ошибка.')
            return JsonResponse(response_data)  # Status will be 200 OK, but content indicates error

        if response_data['status'] == 'completed':
            response_data['progress'] = 100
            response_data['html_result'] = progress_data.get('html_result')
            # Optional: Clear cache after sending completed result to prevent re-sending large HTML.
            # cache.delete(f'forecast_progress_{task_id}')
            # if 'forecast_task_id' in request.session and request.session['forecast_task_id'] == task_id:
            #    del request.session['forecast_task_id']
            return JsonResponse(response_data)

        if response_data['total_configurations'] > 0:
            response_data['progress'] = round(
                (response_data['completed_configurations'] / response_data['total_configurations']) * 100
            )

        return JsonResponse(response_data)


@login_required
def forecast_history_view(request):
    user_forecasts_list = ForecastRun.objects.filter(user=request.user).order_by('-created_at')

    paginator = Paginator(user_forecasts_list, 10)  # По 10 прогнозов на страницу
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj
    }
    return render(request, 'forecast_history.html', context)


@login_required

def view_historical_forecast(request,  forecast_run_id):
    forecast_run_instance = get_object_or_404(ForecastRun, id= forecast_run_id, user=request.user)

    # Загружаем данные результатов из файла (или из JSONField, если храните там)
    results_data_from_file = None
    if forecast_run_instance.results_file_path:
        try:
            full_file_path = os.path.join(settings.MEDIA_ROOT, forecast_run_instance.results_file_path)
            with open(full_file_path, 'r', encoding='utf-8') as f:
                results_data_from_file = json.load(f)
        except Exception as e:
            logger.error(f"Ошибка чтения файла для просмотра истории {forecast_run_instance.results_file_path}: {e}")
            # Обработка ошибки - можно показать сообщение или пустые данные
            results_data_from_file = {}  # Пустые данные, чтобы шаблон не упал
    else:
        results_data_from_file = {}

    logger.info(f"ID для URL: {forecast_run_instance.id}, тип: {type(forecast_run_instance.id)}")

    context = {
        'params_display_overall': results_data_from_file.get('display_params_overall',
                                                             forecast_run_instance.input_parameters_json),
        # Фоллбэк на input_params
        'form_warnings': results_data_from_file.get('all_warnings', forecast_run_instance.warnings_json),  # Фоллбэк
        'grouped_forecasts': results_data_from_file.get('grouped_forecasts_data', []),

        # Данные для JavaScript на странице результатов (для графиков)
        'grouped_forecasts_json': json.dumps(results_data_from_file.get('grouped_forecasts_data', [])),
        'active_data_keys_json': json.dumps(results_data_from_file.get('active_data_keys', [])),
        'output_detailed_by_age_global_js': json.dumps(
            results_data_from_file.get('output_detailed_by_age_global', False)),

        # Флаги для рендеринга таблицы в шаблоне
        'output_detailed_by_age_global': results_data_from_file.get('output_detailed_by_age_global', False),
        'user_selected_settlement_id': results_data_from_file.get('user_selected_settlement_id', ID_SETTLEMENT_TOTAL),
        # Используйте константы
        'user_selected_sex_code': results_data_from_file.get('user_selected_sex_code', SEX_CODE_TOTAL),

        # --- ВАЖНО: Передаем ID текущего исторического прогноза ---
        'forecast_run_id_for_template': str(forecast_run_instance.id),  # Преобразуем UUID в строку

        # Константы, если они нужны в шаблоне (лучше их сделать доступными через кастомный context processor)
        'ID_SETTLEMENT_TOTAL': ID_SETTLEMENT_TOTAL,
        'ID_SETTLEMENT_URBAN': ID_SETTLEMENT_URBAN,
        'ID_SETTLEMENT_RURAL': ID_SETTLEMENT_RURAL,
        'SEX_CODE_TOTAL': SEX_CODE_TOTAL,
        'SEX_CODE_MALE': SEX_CODE_MALE,
        'SEX_CODE_FEMALE': SEX_CODE_FEMALE,
        'scenarios': {  # Если сценарии нужны в этом шаблоне
            'last_year': SCENARIO_LAST_YEAR,  # Убедитесь, что SCENARIO_ константы доступны
            'historical_trend': SCENARIO_HISTORICAL_TREND,
            'manual_percent': SCENARIO_MANUAL_PERCENT
        }
    }
    # Предполагаем, что страница детального просмотра использует тот же шаблон,
    # что и страница результатов после AJAX-запроса
    return render(request, 'forecast_results.html', context)



@login_required  # Только аутентифицированные пользователи могут экспортировать
def export_forecast_data_view(request, forecast_run_id, export_format):
    """
    Обрабатывает запрос на экспорт данных конкретного прогноза в формате CSV или XLSX.
    """
    try:
        # Получаем запись о прогнозе. Проверяем, что она принадлежит текущему пользователю.
        forecast_run = get_object_or_404(ForecastRun, id=forecast_run_id, user=request.user)
    except ForecastRun.DoesNotExist:  # Это избыточно, т.к. get_object_or_404 уже рейзит Http404
        logger.warning(
            f"Попытка экспорта несуществующего прогноза или прогноза другого пользователя. ID: {forecast_run_id}, User: {request.user.username}")
        raise Http404("Прогноз не найден или у вас нет к нему доступа.")

    # --- Извлекаем сохраненные данные прогноза из файла ---
    # (Предполагается, что результаты хранятся в файле, указанном в ForecastRun.results_file_path)
    input_params_from_db = forecast_run.input_parameters_json  # Исходные параметры, как они были на момент запуска

    results_data_from_file = None
    if forecast_run.results_file_path:
        try:
            full_file_path = os.path.join(settings.MEDIA_ROOT, forecast_run.results_file_path)
            logger.info(f"Попытка чтения файла для экспорта: {full_file_path}")
            with open(full_file_path, 'r', encoding='utf-8') as f:
                results_data_from_file = json.load(f)
        except FileNotFoundError:
            logger.error(f"Файл результатов для экспорта не найден: {full_file_path} (прогноз ID: {forecast_run_id})")
            raise Http404("Файл результатов прогноза не найден. Возможно, он был удален или перемещен.")
        except json.JSONDecodeError as e:
            logger.error(
                f"Ошибка декодирования JSON из файла результатов {full_file_path}: {e} (прогноз ID: {forecast_run_id})")
            raise Http404("Файл результатов прогноза поврежден или имеет неверный формат.")
        except Exception as e:
            logger.error(
                f"Непредвиденная ошибка при чтении файла результатов {full_file_path}: {e} (прогноз ID: {forecast_run_id})")
            raise Http404(f"Ошибка при доступе к файлу результатов прогноза.")
    else:
        logger.warning(
            f"Для прогноза ID {forecast_run_id} не указан путь к файлу результатов (results_file_path is null/empty).")
        raise Http404("Для этого прогноза отсутствует ссылка на файл с результатами.")

    if not results_data_from_file:  # Дополнительная проверка, хотя исключения выше должны были сработать
        raise Http404("Данные для экспорта не были загружены из файла.")

    # Извлекаем компоненты из загруженных данных
    params_display_overall_export = results_data_from_file.get('display_params_overall', {})
    all_warnings_export = results_data_from_file.get('all_warnings', [])
    grouped_forecasts_export = results_data_from_file.get('grouped_forecasts_data', [])

    # Эти параметры нужны для правильного построения заголовков таблиц.
    # Они были сохранены в data_for_file_storage в tasks.py.
    output_detailed_by_age_global_export = results_data_from_file.get('output_detailed_by_age_global', False)
    user_selected_settlement_id_export = results_data_from_file.get('user_selected_settlement_id', ID_SETTLEMENT_TOTAL)
    user_selected_sex_code_export = results_data_from_file.get('user_selected_sex_code', SEX_CODE_TOTAL)

    filename_base = f"forecast_export_{str(forecast_run_id)[:8]}"  # Короткий префикс из UUID

    # --- Генерация EXCEL ---
    if export_format.lower() == 'xlsx':
        try:
            workbook = generate_forecast_excel_workbook(
                params_display_overall=params_display_overall_export,
                all_warnings=all_warnings_export,
                grouped_forecasts_data=grouped_forecasts_export,
                output_detailed_by_age_global=output_detailed_by_age_global_export,
                user_selected_settlement_id=user_selected_settlement_id_export,
                user_selected_sex_code=user_selected_sex_code_export
            )

            output_stream = BytesIO()
            workbook.save(output_stream)
            output_stream.seek(0)  # Перемещаем указатель в начало BytesIO объекта

            response = HttpResponse(
                output_stream.getvalue(),  # getvalue() чтобы получить байты
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename_base}.xlsx"'
            logger.info(f"Успешно сформирован Excel файл для прогноза ID: {forecast_run_id}")
            return response
        except Exception as e:
            logger.error(f"Ошибка при генерации Excel для прогноза ID {forecast_run_id}: {e}", exc_info=True)
            # Можно вернуть более дружелюбное сообщение или страницу ошибки
            return HttpResponse(f"Произошла ошибка при генерации Excel файла: {e}", status=500)

    # --- Генерация CSV ---
    elif export_format.lower() == 'csv':
        try:
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            response.write(u'\ufeff'.encode('utf8'))  # BOM для Excel, чтобы кириллица отображалась корректно
            response['Content-Disposition'] = f'attachment; filename="{filename_base}.csv"'

            csv_writer = csv.writer(response, delimiter=';')  # Используем точку с запятой

            write_forecast_data_to_csv(
                writer=csv_writer,
                params_display_overall=params_display_overall_export,
                all_warnings=all_warnings_export,
                grouped_forecasts_data=grouped_forecasts_export,
                output_detailed_by_age_global=output_detailed_by_age_global_export,
                user_selected_settlement_id=user_selected_settlement_id_export,
                user_selected_sex_code=user_selected_sex_code_export
            )
            logger.info(f"Успешно сформирован CSV файл для прогноза ID: {forecast_run_id}")
            return response
        except Exception as e:
            logger.error(f"Ошибка при генерации CSV для прогноза ID {forecast_run_id}: {e}", exc_info=True)
            return HttpResponse(f"Произошла ошибка при генерации CSV файла: {e}", status=500)

    else:
        logger.warning(
            f"Запрошен неподдерживаемый формат экспорта: '{export_format}' для прогноза ID {forecast_run_id}")
        raise Http404("Неподдерживаемый формат экспорта. Доступные форматы: xlsx, csv.")
