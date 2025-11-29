# forecasting/forecaster.py

import logging
from typing import Dict, List, Any, Optional, Tuple, Union  # Union добавлен для target_age_group_input
from collections import defaultdict
import copy  # Для глубокого копирования структур данных

from .data_providers.db_data_provider import DBDataProvider, SEX_MALE_CODE, SEX_FEMALE_CODE, SEX_TOTAL_CODE
from .coefficient_calculator import CoefficientProcessor, SCENARIO_LAST_YEAR, SCENARIO_HISTORICAL_TREND, \
    SCENARIO_MANUAL_PERCENT
from .migration_handler import MigrationProcessor

logger = logging.getLogger(__name__)

# Константы для разделения новорожденных по полу
SHARE_OF_MALE_NEWBORNS = 0.512
SHARE_OF_FEMALE_NEWBORNS = 0.488


BIRTH_RATE_AGE_15_AND_YOUNGER_DB_KEY = 15
BIRTH_RATE_AGE_55_AND_OLDER_DB_KEY = 55
FERTILE_AGE_START = 15
FERTILE_AGE_END = 49

class PopulationForecaster:
    """
    Выполняет демографический прогноз методом передвижки возрастов (компонентный метод).
    """

    def __init__(self, forecast_params: Dict[str, Any]):
        self.params = forecast_params
        self.data_provider = DBDataProvider()

        self.region_ids = self.params['region_ids']
        self.settlement_type_id = self.params['settlement_type_id']
        self.forecast_start_year = self.params['forecast_start_year']
        self.forecast_end_year = self.params['forecast_end_year']


        self.hist_data_request_start_year = self.params['historical_data_start_year']
        self.hist_data_request_end_year = self.params['historical_data_end_year']


        self.initial_population_data_year = self.params['historical_data_end_year']

        self.all_ages_list = list(range(0, 100))  # 0...99
        self.open_age_group = 100  # Возраст 100 и старше
        self.warnings = []

    def _prepare_coefficients_and_migration(self) -> Dict[str, Any]:
        logger.info("Начало подготовки коэффициентов и миграции...")

        hist_pop_for_deaths = self.data_provider.get_historical_population_for_death_rates(
            self.hist_data_request_start_year, self.hist_data_request_end_year,
            self.region_ids, self.settlement_type_id, SEX_TOTAL_CODE
        )
        hist_death_counts = self.data_provider.get_historical_death_counts_data(
            self.hist_data_request_start_year, self.hist_data_request_end_year,
            self.region_ids, self.settlement_type_id, SEX_TOTAL_CODE
        )
        hist_birth_counts = self.data_provider.get_historical_birth_rates_data(
            self.hist_data_request_start_year, self.hist_data_request_end_year,
            self.region_ids, self.settlement_type_id
        )
        hist_female_pop_for_births = self.data_provider.get_historical_female_population_for_birth_rates(
            self.hist_data_request_start_year, self.hist_data_request_end_year,
            self.region_ids, self.settlement_type_id
        )

        coeff_processor = CoefficientProcessor(
            historical_birth_counts=hist_birth_counts,
            historical_female_population=hist_female_pop_for_births,
            historical_death_counts=hist_death_counts,
            historical_population_for_deaths=hist_pop_for_deaths,
            forecast_start_year=self.forecast_start_year,
            forecast_end_year=self.forecast_end_year,
            all_ages_list=self.all_ages_list,
            open_age_group=self.open_age_group
        )

        forecasted_birth_rates = coeff_processor.get_forecasted_birth_rates(
            scenario=self.params['birth_rate_scenario'],
            manual_annual_change_percent=self.params.get('birth_rate_manual_change_percent')
        )
        if not forecasted_birth_rates:
            self.warnings.append(
                "Предупреждение: Не удалось рассчитать коэффициенты рождаемости. Рождаемость в прогнозе будет нулевой.")
            forecasted_birth_rates = defaultdict(lambda: defaultdict(float))

        fc_death_rates_male = coeff_processor.get_forecasted_death_rates(
            sex_code_to_process=SEX_MALE_CODE,
            scenario=self.params['death_rate_scenario_male'],
            manual_annual_change_percent=self.params.get('death_rate_manual_change_percent_male')
        )
        fc_death_rates_female = coeff_processor.get_forecasted_death_rates(
            sex_code_to_process=SEX_FEMALE_CODE,
            scenario=self.params['death_rate_scenario_female'],
            manual_annual_change_percent=self.params.get('death_rate_manual_change_percent_female')
        )
        if not fc_death_rates_male:
            self.warnings.append(
                "Предупреждение: Не удалось рассчитать коэффициенты смертности для мужчин. Смертность для мужчин будет нулевой.")
            fc_death_rates_male = defaultdict(lambda: defaultdict(float))
        if not fc_death_rates_female:
            self.warnings.append(
                "Предупреждение: Не удалось рассчитать коэффициенты смертности для женщин. Смертность для женщин будет нулевой.")
            fc_death_rates_female = defaultdict(lambda: defaultdict(float))

        survival_rates_male = coeff_processor.calculate_survival_rates(fc_death_rates_male)
        survival_rates_female = coeff_processor.calculate_survival_rates(fc_death_rates_female)

        forecasted_migration_male = defaultdict(lambda: defaultdict(float))
        forecasted_migration_female = defaultdict(lambda: defaultdict(float))

        if self.params.get('include_migration', False):
            logger.info("Подготовка данных по миграции...")
            pop_for_mig_dist_year = self.initial_population_data_year  # Используем год начального населения для структуры

            logger.debug(f"Загрузка населения для распределения миграции за {pop_for_mig_dist_year} год...")
            initial_pop_for_migration_raw = self.data_provider.get_initial_population(
                year=pop_for_mig_dist_year,
                region_ids=self.region_ids,
                settlement_type_id=self.settlement_type_id,
                sex_code=SEX_TOTAL_CODE
            )
            initial_pop_for_migration_dist = {SEX_MALE_CODE: {}, SEX_FEMALE_CODE: {}}
            for age, sex_data in initial_pop_for_migration_raw.items():
                if SEX_MALE_CODE in sex_data: initial_pop_for_migration_dist[SEX_MALE_CODE][age] = sex_data[
                    SEX_MALE_CODE]
                if SEX_FEMALE_CODE in sex_data: initial_pop_for_migration_dist[SEX_FEMALE_CODE][age] = sex_data[
                    SEX_FEMALE_CODE]

            hist_mig_saldo_raw = self.data_provider.get_historical_migration_saldo(
                self.hist_data_request_start_year, self.hist_data_request_end_year,
                self.region_ids, self.settlement_type_id, SEX_TOTAL_CODE
            )

            mig_processor = MigrationProcessor(
                historical_migration_saldo_raw=hist_mig_saldo_raw,
                initial_population_by_sex_age=initial_pop_for_migration_dist,
                forecast_start_year=self.forecast_start_year,
                forecast_end_year=self.forecast_end_year,
                all_ages_list=self.all_ages_list,
                open_age_group=self.open_age_group
            )
            forecasted_migration_male = mig_processor.get_forecasted_migration_saldo(
                SEX_MALE_CODE, self.params['migration_scenario'], self.params.get('migration_manual_change_percent')
            )
            forecasted_migration_female = mig_processor.get_forecasted_migration_saldo(
                SEX_FEMALE_CODE, self.params['migration_scenario'], self.params.get('migration_manual_change_percent')
            )
        else:
            logger.info("Миграция не учитывается в прогнозе.")


        logger.info("Подготовка коэффициентов и миграции завершена.")
        return {
            "birth_rates": forecasted_birth_rates,
            "survival_rates_male": survival_rates_male,
            "survival_rates_female": survival_rates_female,
            "migration_male": forecasted_migration_male,
            "migration_female": forecasted_migration_female,
        }

    def run_forecast(self) -> Dict[str, Any]:
        logger.info(f"Запуск демографического прогноза с {self.forecast_start_year} по {self.forecast_end_year}...")

        # 1. Получение исходного населения.

        if self.forecast_start_year != self.initial_population_data_year + 1:
            warning_msg = (
                f"Несоответствие годов! Год начала прогноза ({self.forecast_start_year}) должен быть на один год позже "
                f"года последних данных о населении ({self.initial_population_data_year}). "
                f"Для корректного прогноза, пожалуйста, скорректируйте входные параметры."
            )
            self.warnings.append(warning_msg)
            logger.error(warning_msg)

            return self._format_results([], self.warnings)

        logger.info(
            f"Загрузка исходного населения за {self.initial_population_data_year} год (используется как население на начало {self.forecast_start_year})...")

        initial_pop_raw = self.data_provider.get_initial_population(
            year=self.initial_population_data_year,  # Год, ЗА который есть данные о населении
            region_ids=self.region_ids,
            settlement_type_id=self.settlement_type_id,
            sex_code=SEX_TOTAL_CODE
        )

        current_population = {SEX_MALE_CODE: defaultdict(int), SEX_FEMALE_CODE: defaultdict(int)}
        if not initial_pop_raw:
            self.warnings.append(
                f"Не удалось загрузить исходное население за {self.initial_population_data_year} год. Прогноз невозможен.")
            logger.error(f"Исходное население за {self.initial_population_data_year} не найдено.")
            return self._format_results([], self.warnings)

        for age, sex_data in initial_pop_raw.items():
            try:
                age_int = int(age)
            except ValueError:
                continue
            if SEX_MALE_CODE in sex_data: current_population[SEX_MALE_CODE][age_int] = sex_data[SEX_MALE_CODE]
            if SEX_FEMALE_CODE in sex_data: current_population[SEX_FEMALE_CODE][age_int] = sex_data[SEX_FEMALE_CODE]

        prepared_data = self._prepare_coefficients_and_migration()
        forecast_results_over_time = []

        for year_t in range(self.forecast_start_year, self.forecast_end_year + 1):
            logger.debug(f"Прогнозирование для года {year_t} (результат на конец года / начало {year_t + 1})...")
            population_next_year = {SEX_MALE_CODE: defaultdict(int), SEX_FEMALE_CODE: defaultdict(int)}

            total_newborns_year_t = 0
            birth_rates_for_year_t = {
                age: rates.get(year_t, 0.0)
                for age, rates in prepared_data["birth_rates"].items()
            }

            # Рождаемость по стандартным фертильным возрастам
            for age_mother in range(FERTILE_AGE_START, FERTILE_AGE_END + 1):
                female_pop_age_mother = current_population[SEX_FEMALE_CODE].get(age_mother, 0)
                asfr = birth_rates_for_year_t.get(age_mother, 0.0)  # ВКР для конкретного возраста матери
                if female_pop_age_mother > 0 and asfr > 0:
                    total_newborns_year_t += female_pop_age_mother * asfr

            # Рождаемость "15 и младше"
            asfr_15_younger = birth_rates_for_year_t.get(BIRTH_RATE_AGE_15_AND_YOUNGER_DB_KEY, 0.0)
            if asfr_15_younger > 0:
                female_pop_15_actual = current_population[SEX_FEMALE_CODE].get(15, 0)  # Знаменатель - женщины 15 лет
                total_newborns_year_t += female_pop_15_actual * asfr_15_younger


            asfr_55_older = birth_rates_for_year_t.get(BIRTH_RATE_AGE_55_AND_OLDER_DB_KEY, 0.0)
            if asfr_55_older > 0:
                female_pop_55_plus_calc = 0
                # Суммируем женщин для знаменателя ВКР 55+
                for age_f_sum in range(BIRTH_RATE_AGE_55_AND_OLDER_DB_KEY, self.open_age_group + 1):
                    female_pop_55_plus_calc += current_population[SEX_FEMALE_CODE].get(age_f_sum, 0)
                if female_pop_55_plus_calc > 0:
                    total_newborns_year_t += female_pop_55_plus_calc * asfr_55_older

            newborn_males = total_newborns_year_t * SHARE_OF_MALE_NEWBORNS
            newborn_females = total_newborns_year_t * SHARE_OF_FEMALE_NEWBORNS

            s0_male = prepared_data["survival_rates_male"].get(0, {}).get(year_t, 0.0)  # Дожитие из возраста 0 в 1
            s0_female = prepared_data["survival_rates_female"].get(0, {}).get(year_t, 0.0)


            population_next_year[SEX_MALE_CODE][0] = newborn_males * s0_male
            population_next_year[SEX_FEMALE_CODE][0] = newborn_females * s0_female

            population_next_year[SEX_MALE_CODE][0] += prepared_data["migration_male"].get(0, {}).get(year_t, 0.0)
            population_next_year[SEX_FEMALE_CODE][0] += prepared_data["migration_female"].get(0, {}).get(year_t, 0.0)
            population_next_year[SEX_MALE_CODE][0] = max(0, population_next_year[SEX_MALE_CODE][0])
            population_next_year[SEX_FEMALE_CODE][0] = max(0, population_next_year[SEX_FEMALE_CODE][0])

            for sex_code in [SEX_MALE_CODE, SEX_FEMALE_CODE]:
                current_pop_sex = current_population[sex_code]
                survival_rates_sex_year_t = {age: rates.get(year_t, 0.0) for age, rates in (
                    prepared_data["survival_rates_male"] if sex_code == SEX_MALE_CODE else prepared_data[
                        "survival_rates_female"]).items()}
                migration_sex_year_t = {age: mig.get(year_t, 0.0) for age, mig in (
                    prepared_data["migration_male"] if sex_code == SEX_MALE_CODE else prepared_data[
                        "migration_female"]).items()}

                for age_x in self.all_ages_list:  # от 0 до 99
                    if age_x >= self.open_age_group - 1: continue  # Переход из 99 в 100+ обрабатывается ниже

                    pop_age_x = current_pop_sex.get(age_x, 0)
                    s_x = survival_rates_sex_year_t.get(age_x, 0.0)
                    mig_saldo_age_x = migration_sex_year_t.get(age_x, 0.0)

                    survived_pop_to_next_age = pop_age_x * s_x
                    population_next_year[sex_code][age_x + 1] += survived_pop_to_next_age + mig_saldo_age_x
                    population_next_year[sex_code][age_x + 1] = max(0, population_next_year[sex_code][age_x + 1])

                age_last_closed = self.open_age_group - 1
                pop_last_closed = current_pop_sex.get(age_last_closed, 0)
                s_last_closed = survival_rates_sex_year_t.get(age_last_closed, 0.0)
                mig_saldo_last_closed = migration_sex_year_t.get(age_last_closed, 0.0)
                population_next_year[sex_code][self.open_age_group] += (
                                                                                   pop_last_closed * s_last_closed) + mig_saldo_last_closed

                pop_open_group_start = current_pop_sex.get(self.open_age_group, 0)
                s_open_group = survival_rates_sex_year_t.get(self.open_age_group, 0.0)  # Дожитие внутри группы
                mig_saldo_open_group = migration_sex_year_t.get(self.open_age_group, 0.0)
                population_next_year[sex_code][self.open_age_group] += (
                                                                                   pop_open_group_start * s_open_group) + mig_saldo_open_group
                population_next_year[sex_code][self.open_age_group] = max(0, population_next_year[sex_code][
                    self.open_age_group])

            forecast_results_over_time.append({
                "year": year_t,
                "population_by_sex_age": copy.deepcopy(population_next_year)
            })
            current_population = copy.deepcopy(population_next_year)

        logger.info("Демографический прогноз завершен.")
        return self._format_results(forecast_results_over_time, self.warnings)

    def _format_results(self,
                        forecast_data_by_year: List[Dict[str, Any]],
                        warnings: List[str]  # Это список предупреждений, собранных ДО этого метода
                        ) -> Dict[str, Any]:

        # Создаем копию списка warnings, чтобы не изменять оригинал напрямую, если он передан извне
        # или если warnings может быть None
        current_warnings: List[str] = list(warnings) if warnings is not None else []

        output_results = []
        target_sex = self.params.get('sex_code_target')  # Используем .get
        # Получаем значение, которое пришло для возрастной группы
        target_age_group_input_val = self.params.get('target_age_group_input')
        output_detailed_by_age = self.params.get('output_detailed_by_age', False)

        logger.debug(
            f"FORECASTER _format_results: Получено target_age_group_input: {target_age_group_input_val} (тип: {type(target_age_group_input_val)})")
        logger.debug(f"FORECASTER _format_results: output_detailed_by_age: {output_detailed_by_age}")

        target_single_ages: List[int] = []

        # Вариант 1: Пришла строка "Все возрасты"
        if isinstance(target_age_group_input_val, str) and \
                target_age_group_input_val.lower() in ["все возрасты", "all ages", "all_ages"]:
            logger.debug("FORECASTER _format_results: Обработка 'Все возрасты' (строка).")
            target_single_ages = self.all_ages_list + [self.open_age_group]

        # Вариант 2: Пришел кортеж ИЛИ СПИСОК из двух элементов, которые можно преобразовать в int
        elif (isinstance(target_age_group_input_val, tuple) or isinstance(target_age_group_input_val, list)) and \
                len(target_age_group_input_val) == 2:

            try:
                # Пытаемся преобразовать элементы в int
                start_a = int(target_age_group_input_val[0])
                end_a = int(target_age_group_input_val[1])
            except (ValueError, TypeError) as e:
                logger.error(
                    f"FORECASTER _format_results: Ошибка преобразования элементов диапазона в int: {target_age_group_input_val}, ошибка: {e}. Используются все возрасты.")
                current_warnings.append(
                    f"Некорректные числовые значения в диапазоне возрастов: {target_age_group_input_val}. Используются все возрасты."
                )
                target_single_ages = self.all_ages_list + [self.open_age_group]
            else:
                logger.debug(
                    f"FORECASTER _format_results: Обработка диапазона (список/кортеж): старт={start_a}, конец={end_a}")

                # Валидация диапазона (start_a не может быть больше end_a, оба не отрицательные, end_a в разумных пределах)
                if not (0 <= start_a <= end_a and end_a < (self.open_age_group + 100)):  # Даем запас для end_a
                    logger.warning(
                        f"FORECASTER _format_results: Некорректный числовой диапазон ({start_a}, {end_a}) после преобразования. Используются все возрасты.")
                    current_warnings.append(
                        f"Некорректный числовой диапазон для целевой возрастной группы: ({start_a}, {end_a}). Используются все возрасты."
                    )
                    target_single_ages = self.all_ages_list + [self.open_age_group]
                else:
                    current_target_ages_temp = []
                    for age_s_check in self.all_ages_list:  # self.all_ages_list это обычно 0...99
                        if start_a <= age_s_check <= end_a:
                            current_target_ages_temp.append(age_s_check)

                    if end_a >= self.open_age_group:
                        if self.open_age_group >= start_a:
                            if self.open_age_group not in current_target_ages_temp:
                                current_target_ages_temp.append(self.open_age_group)

                    target_single_ages = sorted(list(set(current_target_ages_temp)))

                    if not target_single_ages:
                        logger.warning(
                            f"FORECASTER _format_results: Целевая возрастная группа ({start_a}, {end_a}) не содержит допустимых возрастов после фильтрации. Используются все возрасты.")
                        current_warnings.append(
                            f"Целевая возрастная группа ({start_a}, {end_a}) не содержит допустимых возрастов. Используются все возрасты."
                        )
                        target_single_ages = self.all_ages_list + [self.open_age_group]
                    else:
                        logger.debug(
                            f"FORECASTER _format_results: Сформирован список возрастов target_single_ages: {target_single_ages}")

        # Вариант 3: Входное значение для возрастной группы не соответствует ожиданиям
        else:
            logger.warning(
                f"FORECASTER _format_results: Некорректная целевая возрастная группа (не строка 'Все возрасты' и не список/кортеж из 2х чисел): {target_age_group_input_val}. Используются все возрасты.")
            current_warnings.append(  # Добавляем в КОПИЮ списка warnings
                f"Некорректная целевая возрастная группа: {target_age_group_input_val}. Используются все возрасты."
            )
            target_single_ages = self.all_ages_list + [self.open_age_group]

        # --- Дальнейшая обработка и формирование результатов ---
        # (Этот блок кода остается как в вашем оригинале, я просто скопирую его для полноты)
        for year_data in forecast_data_by_year:
            year_val = year_data['year']
            pop_by_sex_age_for_year = year_data['population_by_sex_age']

            yearly_result_item: Dict[str, Any] = {"year": year_val}  # Явная типизация
            total_pop_in_target_group_for_year = 0
            population_by_age_output: List[Dict[str, Any]] = []

            # Убедимся, что SEX_MALE_CODE, SEX_FEMALE_CODE, SEX_TOTAL_CODE импортированы или определены в классе/глобально
            sexes_to_iterate = [SEX_MALE_CODE, SEX_FEMALE_CODE] if target_sex == SEX_TOTAL_CODE else [target_sex]

            for age_val in target_single_ages:
                pop_for_age_val_target_sex = 0
                for sex_iter in sexes_to_iterate:
                    pop_for_age_val_target_sex += pop_by_sex_age_for_year.get(sex_iter, {}).get(age_val, 0)

                total_pop_in_target_group_for_year += pop_for_age_val_target_sex

                if output_detailed_by_age:
                    age_label = str(age_val) if age_val != self.open_age_group else f"{self.open_age_group}+"
                    population_by_age_output.append({
                        "age": age_label,
                        "population": round(pop_for_age_val_target_sex)
                    })

            yearly_result_item["total_population_in_target_group"] = round(total_pop_in_target_group_for_year)
            if output_detailed_by_age:
                yearly_result_item["population_by_age"] = population_by_age_output

            output_results.append(yearly_result_item)

        logger.debug(f"FORECASTER _format_results: Финальные предупреждения: {current_warnings}")
        return {
            "forecast_parameters": self.params,
            "warnings": current_warnings,  # Возвращаем обновленный список предупреждений
            "results": output_results
        }


if __name__ == '__main__':
    print("PopulationForecaster - для тестирования запустите через Django или отдельный тестовый скрипт.")