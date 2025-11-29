# forecasting/migration_handler.py

import logging
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict

# Предполагается, что linear_regression.py находится в forecasting.utils
from .utils.linear_regression import calculate_linear_regression_trend, predict_value_from_trend

logger = logging.getLogger(__name__)

# --- Константы для сценариев (должны совпадать с coefficient_calculator) ---
SCENARIO_LAST_YEAR = "last_year"
SCENARIO_HISTORICAL_TREND = "historical_trend"
SCENARIO_MANUAL_PERCENT = "manual_percent"

MIN_HISTORICAL_YEARS_FOR_TREND = 3


class MigrationProcessor:
    """
    Обрабатывает данные по миграционному сальдо и подготавливает их для прогноза.
    """

    def __init__(
            self,
            historical_migration_saldo_raw: Dict[str, Dict[Tuple[int, int], Dict[int, int]]],
            # {sex: {(age_start, age_end): {year: saldo}}}
            initial_population_by_sex_age: Dict[str, Dict[int, int]],
            # {sex: {age: population}} - на последний исторический год или начало прогноза
            forecast_start_year: int,
            forecast_end_year: int,
            all_ages_list: List[int],  # Список всех однолетних возрастов, например [0, 1, ..., 99]
            open_age_group: int = 100  # Например, 100 для 100+
    ):
        self.historical_migration_saldo_raw = historical_migration_saldo_raw
        self.initial_population_by_sex_age = initial_population_by_sex_age  # Используется для распределения
        self.forecast_start_year = forecast_start_year
        self.forecast_end_year = forecast_end_year
        self.all_ages_list = all_ages_list  # Включая 0, но не включая open_age_group как отдельный элемент
        self.open_age_group = open_age_group  # Сам возраст начала открытой группы

        self.historical_years = self._get_common_historical_years_for_migration()
        if self.historical_years:
            self.last_historical_year = max(self.historical_years)
        else:
            self.last_historical_year = None
            logger.warning("Нет общих исторических лет для данных по миграции.")

        # Предварительно обрабатываем миграцию до однолетних групп
        self.historical_migration_saldo_single_age = self._distribute_migration_to_single_ages()
        logger.debug(
            f"MigrationProcessor инициализирован. Последний исторический год миграции: {self.last_historical_year}")

    def _get_common_historical_years_for_migration(self) -> List[int]:
        all_years = set()
        for sex_data in self.historical_migration_saldo_raw.values():
            for age_group_data in sex_data.values():
                all_years.update(age_group_data.keys())
        if not all_years:
            return []
        return sorted(list(all_years))

    def _distribute_migration_to_single_ages(self) -> Dict[str, Dict[int, Dict[int, float]]]:
        """
        Распределяет сальдо миграции из агрегированных групп по однолетним возрастам
        пропорционально численности населения в этих однолетних группах.
        Возвращает: {sex: {age: {year: distributed_saldo_float}}}
        """
        distributed_saldo = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))

        for sex, age_groups_data in self.historical_migration_saldo_raw.items():
            # Нужна численность населения соответствующего пола для распределения
            population_for_sex = self.initial_population_by_sex_age.get(sex, {})
            if not population_for_sex:
                logger.warning(
                    f"Нет данных о населении для распределения миграции для пола {sex}. Миграция для этого пола будет 0.")
                continue

            for (age_start, age_end), saldo_by_year in age_groups_data.items():
                # Определяем однолетние возраста, входящие в эту группу
                current_group_ages = []
                if age_start == self.open_age_group:  # Если это уже открытая группа (например, 100+)
                    current_group_ages = [self.open_age_group]  # Обрабатываем как одну группу
                else:
                    current_group_ages = [a for a in self.all_ages_list if age_start <= a <= age_end]
                    if age_end >= self.open_age_group:  # если группа включает открытый возраст (например 75-100+)
                        # Убедимся, что сама open_age_group входит, если она конечная
                        current_group_ages = [a for a in self.all_ages_list if age_start <= a < self.open_age_group]
                        current_group_ages.append(self.open_age_group)

                if not current_group_ages:
                    logger.warning(
                        f"Не удалось определить однолетние возраста для группы миграции {sex}: ({age_start}-{age_end})")
                    continue

                for year, total_saldo_for_group in saldo_by_year.items():
                    # Считаем суммарное население в current_group_ages для данного пола
                    total_population_in_group = 0
                    for age in current_group_ages:
                        total_population_in_group += population_for_sex.get(age, 0)

                    if total_population_in_group == 0:

                        if total_saldo_for_group != 0:
                            logger.warning(
                                f"Нулевое население для распределения миграции {total_saldo_for_group} "
                                f"для пола {sex}, группы ({age_start}-{age_end}), год {year}. Сальдо не будет распределено."
                            )
                        continue  # Пропускаем распределение для этой группы/года

                    for age in current_group_ages:
                        pop_in_single_age = population_for_sex.get(age, 0)
                        proportion = (
                                    pop_in_single_age / total_population_in_group) if total_population_in_group > 0 else 0
                        distributed_saldo[sex][age][year] += total_saldo_for_group * proportion

        return distributed_saldo

    def get_forecasted_migration_saldo(
            self,
            sex_code_to_process: str,  # 'M' или 'F'
            scenario: str,
            manual_annual_change_percent: Optional[float] = None
    ) -> Dict[int, Dict[int, float]]:  # {age: {forecast_year: saldo_float}}
        """
        Рассчитывает прогнозное сальдо миграции для указанного пола по однолетним возрастам.
        """
        logger.info(
            f"Расчет прогнозного сальдо миграции для пола {sex_code_to_process}. Сценарий: {scenario}, ручное изм %: {manual_annual_change_percent}")

        # Используем уже распределенные по однолетним возрастам исторические данные
        historical_saldo_for_sex = self.historical_migration_saldo_single_age.get(sex_code_to_process, {})

        if not historical_saldo_for_sex:
            logger.warning(
                f"Нет предварительно обработанных исторических данных по миграции для пола {sex_code_to_process}. Прогноз миграции будет 0.")
            # Возвращаем пустой результат, чтобы forecaster знал, что нет данных
            # Но для forecaster'а нужно, чтобы были все года и возрасты, пусть и с 0
            forecast_saldo_empty = defaultdict(lambda: defaultdict(float))
            for age in self.all_ages_list + [self.open_age_group]:
                for year_fc in range(self.forecast_start_year, self.forecast_end_year + 1):
                    forecast_saldo_empty[age][year_fc] = 0.0
            return forecast_saldo_empty

        forecast_saldo = defaultdict(lambda: defaultdict(float))

        if not self.last_historical_year:
            logger.error("Невозможно рассчитать прогнозное сальдо миграции: последний исторический год не определен.")
            # Заполняем нулями, если нет исторических данных
            for age in historical_saldo_for_sex.keys():  # Используем возрасты, для которых есть хоть какие-то данные
                for year_fc in range(self.forecast_start_year, self.forecast_end_year + 1):
                    forecast_saldo[age][year_fc] = 0.0
            return forecast_saldo

        for age, hist_saldo_for_age in historical_saldo_for_sex.items():  # age - однолетний возраст
            last_year_saldo = hist_saldo_for_age.get(self.last_historical_year)

            if last_year_saldo is None:
                available_years_for_age = sorted(
                    [y for y in hist_saldo_for_age.keys() if hist_saldo_for_age.get(y) is not None])
                if available_years_for_age:
                    last_available_year_for_age = available_years_for_age[-1]
                    last_year_saldo = hist_saldo_for_age.get(last_available_year_for_age)
                    logger.warning(
                        f"Для миграции (пол {sex_code_to_process}, возраст {age}) нет данных за {self.last_historical_year}. Используется год {last_available_year_for_age} с сальдо {last_year_saldo:.2f}")
                else:
                    logger.warning(
                        f"Для миграции (пол {sex_code_to_process}, возраст {age}) нет исторических данных. Сальдо будет 0.")
                    last_year_saldo = 0.0

            current_saldo = last_year_saldo
            trend_params = None
            actual_scenario_for_age = scenario

            if scenario == SCENARIO_HISTORICAL_TREND:
                data_points = []
                for year in self.historical_years:
                    saldo_val = hist_saldo_for_age.get(year)
                    if saldo_val is not None:
                        data_points.append((year, saldo_val))

                if len(data_points) >= MIN_HISTORICAL_YEARS_FOR_TREND:
                    trend_params = calculate_linear_regression_trend(data_points)
                    if not trend_params:
                        logger.warning(
                            f"Не удалось рассчитать тренд миграции для {sex_code_to_process}, {age}. Переключение на {SCENARIO_LAST_YEAR}.")
                        actual_scenario_for_age = SCENARIO_LAST_YEAR
                else:
                    logger.warning(
                        f"Недостаточно данных ({len(data_points)}) для тренда миграции для {sex_code_to_process}, {age}. Переключение на {SCENARIO_LAST_YEAR}.")
                    actual_scenario_for_age = SCENARIO_LAST_YEAR

            for year_fc in range(self.forecast_start_year, self.forecast_end_year + 1):
                if year_fc == self.forecast_start_year:
                    if actual_scenario_for_age == SCENARIO_HISTORICAL_TREND and trend_params:
                        predicted_val = predict_value_from_trend(trend_params, year_fc)
                        current_saldo = predicted_val if predicted_val is not None else last_year_saldo
                    elif actual_scenario_for_age == SCENARIO_MANUAL_PERCENT and manual_annual_change_percent is not None:
                        current_saldo = last_year_saldo * (1 + manual_annual_change_percent / 100.0)
                    else:  # SCENARIO_LAST_YEAR
                        current_saldo = last_year_saldo
                else:  # Последующие годы прогноза
                    if actual_scenario_for_age == SCENARIO_HISTORICAL_TREND and trend_params:
                        predicted_val = predict_value_from_trend(trend_params, year_fc)
                        current_saldo = predicted_val if predicted_val is not None else current_saldo
                    elif actual_scenario_for_age == SCENARIO_MANUAL_PERCENT and manual_annual_change_percent is not None:
                        current_saldo *= (1 + manual_annual_change_percent / 100.0)

                # Ограничения на сальдо миграции (менее строгие, т.к. может быть большим)
                # Например, можно ограничить максимальное изменение от года к году, если нужно.
                # Пока не добавляем жестких ограничений на абсолютное значение.
                forecast_saldo[age][year_fc] = current_saldo

        # Убедимся, что для всех возрастов из all_ages_list + open_age_group есть значения (хотя бы 0)
        all_possible_ages = self.all_ages_list + [self.open_age_group]
        for age in all_possible_ages:
            if age not in forecast_saldo:  # Если для какого-то возраста вообще не было исторических данных
                for year_fc in range(self.forecast_start_year, self.forecast_end_year + 1):
                    forecast_saldo[age][year_fc] = 0.0
            else:  # Если возраст был, но для каких-то прогнозных лет нет значения (не должно быть по логике выше)
                for year_fc in range(self.forecast_start_year, self.forecast_end_year + 1):
                    if year_fc not in forecast_saldo[age]:
                        forecast_saldo[age][year_fc] = 0.0  # Или значение последнего года, если логика пропусков иная

        return forecast_saldo


if __name__ == '__main__':
    # Пример использования с mock-данными
    mock_hist_migration_raw = {
        'M': {
            (0, 4): {2020: 100, 2021: 110, 2022: 105},  # Группа 0-4
            (70, 70): {2020: -20, 2021: -25, 2022: -22},  # Группа 70 лет (однолетняя)
            (75, 150): {2020: 50, 2021: 55, 2022: 45}  # Группа 75+ (age_end > open_age_group)
        },
        'F': {
            (0, 4): {2020: 90, 2021: 100, 2022: 95},
        }
    }
    # Население на последний исторический год (2022) для распределения
    mock_initial_pop = {
        'M': {0: 1000, 1: 1000, 2: 1000, 3: 1000, 4: 1000,  # Для группы 0-4
              70: 500,  # Для группы 70
              75: 200, 76: 190,  # ... и так далее до 99
              99: 50, 100: 150},  # Для группы 75+ (включая 100+)
        'F': {0: 900, 1: 900, 2: 900, 3: 900, 4: 900}
    }
    # Заполним mock_initial_pop['M'] для возрастов 77-98 для полноты
    for age_m in range(77, 99):
        mock_initial_pop['M'][age_m] = 180 - (age_m - 76) * 5 if 180 - (age_m - 76) * 5 > 0 else 10

    all_ages = list(range(0, 100))  # 0...99
    open_age = 100

    processor = MigrationProcessor(
        historical_migration_saldo_raw=mock_hist_migration_raw,
        initial_population_by_sex_age=mock_initial_pop,
        forecast_start_year=2023,
        forecast_end_year=2025,
        all_ages_list=all_ages,
        open_age_group=open_age
    )

    print("--- Распределенное историческое сальдо миграции (Мужчины) ---")
    if 'M' in processor.historical_migration_saldo_single_age:
        for age, data_by_year in processor.historical_migration_saldo_single_age['M'].items():
            if age in [0, 1, 2, 3, 4, 70, 75, 99, 100]:  # Выведем только некоторые для примера
                print(f"Пол М, Возраст {age}: {data_by_year}")

    print("\n--- Прогнозное сальдо миграции (Мужчины, последний год) ---")
    mig_saldo_m_ly = processor.get_forecasted_migration_saldo(sex_code_to_process='M', scenario=SCENARIO_LAST_YEAR)
    if mig_saldo_m_ly:
        for age, data_by_year in mig_saldo_m_ly.items():
            if age in [0, 4, 70, 75, 99, 100]:  # Выведем только некоторые
                print(f"Пол М, Возраст {age}: Прогноз={data_by_year}")

    print("\n--- Прогнозное сальдо миграции (Мужчины, исторический тренд) ---")
    mig_saldo_m_ht = processor.get_forecasted_migration_saldo(sex_code_to_process='M',
                                                              scenario=SCENARIO_HISTORICAL_TREND)
    if mig_saldo_m_ht:
        for age, data_by_year in mig_saldo_m_ht.items():
            if age in [0, 4, 70, 75, 99, 100]:
                print(f"Пол М, Возраст {age}: Прогноз={data_by_year}")

    print("\n--- Прогнозное сальдо миграции (Мужчины, ручное -5%) ---")
    mig_saldo_m_mp = processor.get_forecasted_migration_saldo(
        sex_code_to_process='M',
        scenario=SCENARIO_MANUAL_PERCENT,
        manual_annual_change_percent=-5.0
    )
    if mig_saldo_m_mp:
        for age, data_by_year in mig_saldo_m_mp.items():
            if age in [0, 4, 70, 75, 99, 100]:
                print(f"Пол М, Возраст {age}: Прогноз={data_by_year}")