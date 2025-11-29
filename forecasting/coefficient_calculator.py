# forecasting/coefficient_calculator.py

import logging
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict

# Предполагается, что linear_regression.py находится в forecasting.utils
from .utils.linear_regression import calculate_linear_regression_trend, predict_value_from_trend

logger = logging.getLogger(__name__)

# --- Константы для сценариев ---
SCENARIO_LAST_YEAR = "last_year"
SCENARIO_HISTORICAL_TREND = "historical_trend"
SCENARIO_MANUAL_PERCENT = "manual_percent"  # Общий для роста/снижения/улучшения/ухудшения

# --- Границы для коэффициентов ---
MIN_COEFFICIENT_VALUE = 0.0
MAX_DEATH_RATE_PER_1000 = 1000.0  # Смертность не может быть больше, чем все население
THEORETICAL_MAX_BIRTH_RATE_PER_1000_FEMALE = 500.0  # Примерный верхний предел для СКР, для возрастных может быть иным, но для ВКР тоже нужно ограничение

MIN_HISTORICAL_YEARS_FOR_TREND = 3

# --- Параметры для крайних возрастных групп рождаемости ---
# Эти значения должны совпадать с тем, как данные хранятся/интерпретируются в birth_rate
BIRTH_RATE_AGE_15_AND_YOUNGER_DB_KEY = 15
BIRTH_RATE_AGE_55_AND_OLDER_DB_KEY = 55  # Предполагаем, что это ключ для 55+

# --- Фертильные возраста (стандартный диапазон) ---
FERTILE_AGE_START = 15
FERTILE_AGE_END = 49  # Включительно


class CoefficientProcessor:
    """
    Обрабатывает и рассчитывает демографические коэффициенты (рождаемости, смертности, дожития)
    для прогнозного периода.
    """

    def __init__(
            self,
            historical_birth_counts: Dict[int, Dict[int, float]],  # {mother_age: {year: birth_count}}
            historical_female_population: Dict[int, Dict[int, int]],  # {age: {year: female_population}}
            historical_death_counts: Dict[str, Dict[int, Dict[int, float]]],  # {sex: {age: {year: death_count}}}
            historical_population_for_deaths: Dict[str, Dict[int, Dict[int, int]]],  # {sex: {age: {year: population}}}
            forecast_start_year: int,
            forecast_end_year: int,
            all_ages_list: List[int],  # Список всех однолетних возрастов, например [0, 1, ..., 100]
            open_age_group: int = 100  # Например, 100 для 100+
    ):
        self.historical_birth_counts = historical_birth_counts
        self.historical_female_population = historical_female_population
        self.historical_death_counts = historical_death_counts
        self.historical_population_for_deaths = historical_population_for_deaths
        self.forecast_start_year = forecast_start_year
        self.forecast_end_year = forecast_end_year
        self.all_ages_list = all_ages_list
        self.open_age_group = open_age_group

        self.historical_years = self._get_common_historical_years()
        if self.historical_years:
            self.last_historical_year = max(self.historical_years)
        else:
            self.last_historical_year = None
            logger.warning("Нет общих исторических лет для расчета коэффициентов.")

        logger.debug(
            f"CoefficientProcessor инициализирован. Исторические годы: {self.historical_years}, последний: {self.last_historical_year}")

    def _get_common_historical_years(self) -> List[int]:
        """Определяет общие годы, для которых есть все необходимые исторические данные."""


        all_years = set()
        # Собираем все годы из female_population как базовые
        for age_data in self.historical_female_population.values():
            all_years.update(age_data.keys())

        # Добавляем годы из population_for_deaths
        for sex_data in self.historical_population_for_deaths.values():
            for age_data in sex_data.values():
                all_years.update(age_data.keys())

        if not all_years:
            return []

        return sorted(list(all_years))

    def _calculate_historical_age_specific_rates(
            self,
            counts_data: Dict[int, float],  # {year: count}
            population_data: Dict[int, int],  # {year: population}
            years_to_calculate: List[int]
    ) -> Dict[int, float]:  # {year: rate_per_person}
        """Рассчитывает коэффициенты (на 1 человека) для указанных лет."""
        rates = {}
        for year in years_to_calculate:
            count = counts_data.get(year)
            population = population_data.get(year)
            if count is not None and population is not None and population > 0:
                rates[year] = count / population
            else:

                pass  # Пропускаем, если нет данных, чтобы не влиять на тренд некорректно
        return rates

    def _get_coefficients_for_forecast_period(
            self,
            historical_rates_by_age_sex: Dict[Any, Dict[int, float]],  # {key (age/sex+age): {year: rate}}
            scenario: str,
            manual_annual_change_percent: Optional[float] = None,
            rate_min_val: float = MIN_COEFFICIENT_VALUE,
            rate_max_val: Optional[float] = None
    ) -> Dict[Any, Dict[int, float]]:  # {key: {forecast_year: rate}}
        """
        Рассчитывает коэффициенты для всего прогнозного периода согласно сценарию.
        'key' может быть возрастом (для рождаемости) или кортежем (пол, возраст) для смертности.
        Коэффициенты здесь - на 1 человека (не на 1000).
        """
        forecast_rates = defaultdict(dict)
        if not self.last_historical_year:
            logger.error("Невозможно рассчитать прогнозные коэффициенты: последний исторический год не определен.")
            return forecast_rates

        for key, hist_rates_for_key in historical_rates_by_age_sex.items():  # key = age или (sex, age)

            # 1. На уровне последнего доступного года
            last_year_rate = hist_rates_for_key.get(self.last_historical_year)

            if last_year_rate is None:  # Если для данного ключа нет данных за последний год
                # Пытаемся найти последний доступный коэффициент для этого ключа
                available_years_for_key = sorted(
                    [y for y in hist_rates_for_key.keys() if hist_rates_for_key.get(y) is not None])
                if available_years_for_key:
                    last_available_year_for_key = available_years_for_key[-1]
                    last_year_rate = hist_rates_for_key.get(last_available_year_for_key)
                    logger.warning(
                        f"Для ключа {key} нет данных за {self.last_historical_year}. Используется последний доступный год {last_available_year_for_key} с коэфф. {last_year_rate:.6f}")
                else:
                    logger.warning(f"Для ключа {key} нет никаких исторических данных. Коэффициент будет 0.")
                    last_year_rate = 0.0  # Или другое значение по умолчанию

            current_rate = last_year_rate

            # 2. Историческая тенденция
            trend_params = None
            actual_scenario_for_key = scenario  # Может измениться, если данных для тренда нет
            if scenario == SCENARIO_HISTORICAL_TREND:
                data_points = []
                for year in self.historical_years:  # Используем общие исторические годы
                    rate = hist_rates_for_key.get(year)
                    if rate is not None:
                        data_points.append((year, rate))

                if len(data_points) >= MIN_HISTORICAL_YEARS_FOR_TREND:
                    trend_params = calculate_linear_regression_trend(data_points)
                    if not trend_params:
                        logger.warning(
                            f"Не удалось рассчитать тренд для ключа {key} (данные: {len(data_points)} точек). Переключение на {SCENARIO_LAST_YEAR}.")
                        actual_scenario_for_key = SCENARIO_LAST_YEAR
                else:
                    logger.warning(
                        f"Недостаточно данных ({len(data_points)} точек) для расчета тренда для ключа {key}. Переключение на {SCENARIO_LAST_YEAR}.")
                    actual_scenario_for_key = SCENARIO_LAST_YEAR

            # 3. Расчет на прогнозный период
            for year_fc in range(self.forecast_start_year, self.forecast_end_year + 1):
                if year_fc == self.forecast_start_year:  # Для первого года прогноза
                    if actual_scenario_for_key == SCENARIO_HISTORICAL_TREND and trend_params:
                        # Прогнозируем значение на первый год прогноза по тренду
                        # Важно: тренд строился на исторических данных до last_historical_year.
                        # Экстраполируем от этого года.
                        predicted_val = predict_value_from_trend(trend_params, year_fc)
                        current_rate = predicted_val if predicted_val is not None else last_year_rate
                    elif actual_scenario_for_key == SCENARIO_MANUAL_PERCENT and manual_annual_change_percent is not None:
                        # Для первого года ручной процент применяется к последнему историческому
                        current_rate = last_year_rate * (1 + manual_annual_change_percent / 100.0)
                    else:  # SCENARIO_LAST_YEAR или тренд не удался
                        current_rate = last_year_rate
                else:  # Для последующих лет прогноза
                    if actual_scenario_for_key == SCENARIO_HISTORICAL_TREND and trend_params:
                        predicted_val = predict_value_from_trend(trend_params, year_fc)
                        current_rate = predicted_val if predicted_val is not None else current_rate  # Если предсказание None, оставляем предыдущее
                    elif actual_scenario_for_key == SCENARIO_MANUAL_PERCENT and manual_annual_change_percent is not None:
                        current_rate *= (1 + manual_annual_change_percent / 100.0)
                    # Для SCENARIO_LAST_YEAR коэффициент не меняется от года к году

                # Применение ограничений
                current_rate = max(rate_min_val, current_rate)
                if rate_max_val is not None:
                    current_rate = min(rate_max_val, current_rate)

                forecast_rates[key][year_fc] = current_rate

        return forecast_rates

    def get_forecasted_birth_rates(
            self,
            scenario: str,  # SCENARIO_LAST_YEAR, SCENARIO_HISTORICAL_TREND, SCENARIO_MANUAL_PERCENT
            manual_annual_change_percent: Optional[float] = None  # для SCENARIO_MANUAL_PERCENT
    ) -> Dict[int, Dict[int, float]]:  # {mother_age: {forecast_year: rate_per_female_person}}
        """
        Рассчитывает прогнозные возрастные коэффициенты рождаемости (на 1 женщину).
        """
        logger.info(
            f"Расчет прогнозных коэффициентов рождаемости. Сценарий: {scenario}, ручное изм %: {manual_annual_change_percent}")
        historical_asfr = defaultdict(dict)  # {mother_age: {year: rate}}

        # Сначала рассчитываем исторические ВКР (ASFR)
        for mother_age, births_by_year in self.historical_birth_counts.items():
            # Проверяем, что возраст матери попадает в фертильный диапазон и есть данные о женском населении
            if FERTILE_AGE_START <= mother_age <= FERTILE_AGE_END or \
                    mother_age == BIRTH_RATE_AGE_15_AND_YOUNGER_DB_KEY or \
                    mother_age == BIRTH_RATE_AGE_55_AND_OLDER_DB_KEY:

                female_pop_for_age_by_year = {}
                if mother_age == BIRTH_RATE_AGE_15_AND_YOUNGER_DB_KEY:
                    # Для "15 и младше" используем численность 15-летних женщин
                    female_pop_for_age_by_year = self.historical_female_population.get(15, {})
                elif mother_age == BIRTH_RATE_AGE_55_AND_OLDER_DB_KEY:

                    # TODO: Улучшить расчет знаменателя для "55 и старше"
                    pop_sum_for_55_plus = defaultdict(int)
                    for age_f, pop_data_f_year in self.historical_female_population.items():
                        if age_f >= BIRTH_RATE_AGE_55_AND_OLDER_DB_KEY:
                            for year_f, pop_val_f in pop_data_f_year.items():
                                pop_sum_for_55_plus[year_f] += pop_val_f
                    female_pop_for_age_by_year = pop_sum_for_55_plus

                else:  # Обычные фертильные возраста
                    female_pop_for_age_by_year = self.historical_female_population.get(mother_age, {})

                if female_pop_for_age_by_year:  # Если есть данные о женском населении для этого возраста
                    rates = self._calculate_historical_age_specific_rates(
                        births_by_year,
                        female_pop_for_age_by_year,
                        self.historical_years
                    )
                    if rates:
                        historical_asfr[mother_age] = rates
                else:
                    logger.warning(
                        f"Нет данных о женском населении для возраста матери {mother_age} для расчета исторических ВКР.")

        if not historical_asfr:
            logger.error("Не удалось рассчитать ни одного исторического ВКР. Прогноз невозможен.")
            return {}

        return self._get_coefficients_for_forecast_period(
            historical_asfr,
            scenario,
            manual_annual_change_percent,
            rate_max_val=THEORETICAL_MAX_BIRTH_RATE_PER_1000_FEMALE / 1000.0  # Переводим в долю
        )

    def get_forecasted_death_rates(
            self,
            sex_code_to_process: str,  # 'M' или 'F'
            scenario: str,
            manual_annual_change_percent: Optional[float] = None
    ) -> Dict[int, Dict[int, float]]:  # {age: {forecast_year: rate_per_person}}
        """
        Рассчитывает прогнозные возрастные коэффициенты смертности (на 1 человека) для указанного пола.
        """
        logger.info(
            f"Расчет прогнозных коэффициентов смертности для пола {sex_code_to_process}. Сценарий: {scenario}, ручное изм %: {manual_annual_change_percent}")
        historical_asdr = defaultdict(dict)  # {age: {year: rate}}

        death_counts_for_sex = self.historical_death_counts.get(sex_code_to_process, {})
        population_for_sex = self.historical_population_for_deaths.get(sex_code_to_process, {})

        if not death_counts_for_sex or not population_for_sex:
            logger.warning(f"Нет исторических данных о смертях или населении для пола {sex_code_to_process}.")
            # Возвращаем пустой результат, чтобы forecaster знал, что нет данных
            return {}

        for age in self.all_ages_list + [self.open_age_group]:  # Включая открытую группу

            # TODO: Убедиться, что open_age_group правильно обрабатывается для смертности (агрегация данных).

            deaths_by_year_for_age = death_counts_for_sex.get(age, {})
            pop_by_year_for_age = population_for_sex.get(age, {})

            if deaths_by_year_for_age and pop_by_year_for_age:
                rates = self._calculate_historical_age_specific_rates(
                    deaths_by_year_for_age,
                    pop_by_year_for_age,
                    self.historical_years
                )
                if rates:
                    historical_asdr[age] = rates
            # else:
            #     logger.debug(f"Нет данных о смертях или населении для пола {sex_code_to_process}, возраста {age}.")

        if not historical_asdr:
            logger.error(
                f"Не удалось рассчитать ни одного исторического ВКС для пола {sex_code_to_process}. Прогноз невозможен.")
            return {}

        return self._get_coefficients_for_forecast_period(
            historical_asdr,
            scenario,
            manual_annual_change_percent,
            rate_max_val=MAX_DEATH_RATE_PER_1000 / 1000.0  # Переводим в долю
        )

    def calculate_survival_rates(
            self,
            death_rates_for_sex: Dict[int, Dict[int, float]]  # {age: {year: death_rate_per_person}}
    ) -> Dict[int, Dict[int, float]]:  # {age: {year: survival_rate_Lx_to_Lx+1}}
        """
        Рассчитывает коэффициенты дожития (Lx+n / Lx, для однолетних n=1)
        Формула для однолетних групп и однолетнего шага: P_x = (1 - q_x) или Lx+1/Lx.
        Если qx - вероятность умереть, то px - вероятность дожить.
        Для передвижки возрастов нам нужен коэффициент дожития, который обычно
        представляется как L_(x+1) / L_x из таблиц смертности.
        Приближенно для однолетних групп, если m_x (ВКС) не очень высок: p_x ≈ 1 - m_x
        Или более точная формула: p_x = exp(-m_x) для непрерывного случая.
        Или Lx+1/Lx = (2 - mx) / (2 + mx) для 5-летних групп (демография), но для однолетних
        часто используют упрощение.
        Для метода компонентной передвижки, как в книге (стр. 72, Ix = Lx/Lx+y в общем виде),
        нам нужен Ix, который показывает, какая доля из группы Px доживет до следующего возраста Px+1.
        Это и есть px. Lx в таблице смертности - это число человеко-лет, прожитых поколением в интервале (x, x+n).
        Вероятность дожить от x до x+1 (px) = l_(x+1) / l_x.
        А l_x = l_0 * p_0 * p_1 * ... * p_(x-1).
        q_x (вероятность умереть в возрасте x) = 1 - p_x.
        m_x (центральный коэф. смертности, наш ВКС) = d_x / L_x.
        d_x = l_x - l_(x+1).
        Для однолетних интервалов часто принимают, что L_x ≈ (l_x + l_(x+1))/2.
        q_x = m_x / (1 + (1-a_x)*m_x), где a_x - средняя доля интервала, прожитая умершими (часто 0.5).
        q_x ≈ m_x / (1 + 0.5*m_x)  => p_x = 1 - q_x.

        Мы будем использовать приближение: Коэффициент дожития из возраста X в возраст X+1 ≈ (1 - m_x).
        Это означает, что из тех, кто был в возрасте X в начале года, доля (1-m_x) доживет до конца года (и перейдет в возраст X+1).
        Это для всех возрастов, кроме последнего открытого.
        """
        survival_rates_forecast = defaultdict(dict)
        for age, rates_by_year in death_rates_for_sex.items():
            for year, death_rate in rates_by_year.items():
                # Для всех, кроме последнего открытого возраста
                if age < self.open_age_group:
                    # s_x = 1 - m_x (вероятность дожить от начала возраста x до начала возраста x+1)
                    # Это интерпретируется как доля доживших от среднегодовой численности в возрасте х
                    # до следующего возраста.
                    # Более точный коэффициент дожития из таблиц смертности L_(x+1)/L_x
                    # Для упрощения, если m_x - это наш ВКС:
                    # P(x -> x+1) = 1 - q_x
                    # q_x = m_x / (1 + 0.5 * m_x) (приближение)
                    # p_x = 1 - (m_x / (1 + 0.5 * m_x)) = (1 + 0.5*m_x - m_x) / (1 + 0.5*m_x) = (1 - 0.5*m_x) / (1 + 0.5*m_x)
                    # Это коэффициент дожития l_(x+1) / l_x.

                    # Вариант 1: Простой (1 - m_x)
                    # survival_rate = 1.0 - death_rate

                    # Вариант 2: Более точный для однолетних групп (используется в ПО Preston, Shryock, Siegel)
                    # p_x = (1 - 0.5 * m_x) / (1 + 0.5 * m_x)
                    # где m_x это наш death_rate (ВКС)
                    if (1 + 0.5 * death_rate) == 0:  # Избегаем деления на ноль
                        survival_rate = 0.0
                    else:
                        survival_rate = (1 - 0.5 * death_rate) / (1 + 0.5 * death_rate)

                    survival_rates_forecast[age][year] = max(0.0, min(1.0, survival_rate))
                else:  # Для открытой возрастной группы (например, 100+)
                    # Коэффициент дожития ВНУТРИ этой группы S_x+ = L_x+ / (L_x+ + d_x+) ???
                    # Или P_x+ = (население_x+ в год t+1 БЕЗ учета новых входящих) / (население_x+ в год t)
                    # P_x+ = 1 - m_x+ (доля тех, кто был в группе x+ и дожил в ней же до конца года)
                    # Это коэффициент "неумирания" внутри группы за год.
                    # survival_rate = 1.0 - death_rate

                    # Используем ту же формулу, что и для других возрастов,
                    # интерпретируя это как долю тех, кто в начале года был в этой группе и дожил до конца года в ней же.
                    if (1 + 0.5 * death_rate) == 0:
                        survival_rate_open_group = 0.0
                    else:
                        survival_rate_open_group = (1 - 0.5 * death_rate) / (1 + 0.5 * death_rate)
                    survival_rates_forecast[age][year] = max(0.0, min(1.0, survival_rate_open_group))

        # Коэффициент дожития для новорожденных (от рождения до возраста 0 к концу года)
        # L0 / l0. l0 - число родившихся. L0 - число человеко-лет, прожитых в возрасте 0.
        # Часто это (1 - a0*q0), где a0 - среднее время жизни умерших в возрасте 0 (около 0.1-0.3).
        # q0 - вероятность умереть до 1 года.
        # m0 - коэффициент младенческой смертности (смерти до 1 года / родившиеся).
        # Если death_rates_for_sex[0] это m0 (ВКС для возраста 0), то
        # S_birth_to_0 = (1 - 0.5 * m_0) / (1 + 0.5 * m_0) - это дожитие от 0 до 1.
        # Нам нужен коэффициент дожития от рождения до конца нулевого года жизни (чтобы получить численность на конец года = на начало следующего).
        # Обычно это L0/l0 = 1 - (доля умерших в первый год жизни * средняя продолжительность их жизни в этом году)
        # Для простоты, S(рождение -> возраст 0 на конец года) = 1 - m_infant, где m_infant - коэф. младенческой смертности (смерти <1 / рожд)
        # В нашем случае death_rates_for_sex[0] это m0 - коэф. смертности для тех, кто *уже* в возрасте 0.
        # Будем использовать этот же коэффициент, но с пониманием, что это приближение.
        # Это S_0 -> т.е. дожитие тех, кто начал год в возрасте 0, до конца года (и перехода в возраст 1).
        # Для новорожденных, которые родились в течение года 't', их дожитие до конца года 't' (т.е. до момента, когда им исполнится в среднем 0.5 года,
        # и они войдут в группу возраста 0 на начало года t+1)
        # P_newborn_to_age0 = (1 - death_rate_age0) - грубое приближение.
        # Более правильно: L0/l0 = 1 - a0*q0.
        # Если death_rates_for_sex[0] - это m0 (ВКС для возраста 0, т.е. D0/P0_avg), то
        # survival_rates_forecast[0] уже содержит P(0->1).
        # Для новорожденных (те, кто входит в группу 0 лет) используем коэффициент дожития от младенческой смертности.
        # Если наш death_rates_for_sex[0] это коэффициент смертности для тех, кто находится в возрасте 0 (D0/P0),
        # то для новорожденных, родившихся в течение года, вероятность дожить до конца года (т.е. войти в P0 на следующий год)
        # будет немного другой. Часто берут: 1 - (коэффициент младенческой смертности * (1-a0)), где a0 - доля года, прожитая умершими.
        # В таблицах смертности это обычно L0/l0 (где l0 - число родившихся).
        # L0/l0 = (1 - k_infant_death_separation_factor * infant_mortality_rate)
        # k_infant_death_separation_factor ~ 0.8-0.9 для развитых стран.
        # Пока оставим как есть, используя рассчитанный S_0 для новорожденных как приближение.
        # Forecaster будет использовать survival_rates_forecast[0] для дожития новорожденных в группу 0.

        return survival_rates_forecast


if __name__ == '__main__':
    # Для тестирования этого модуля нужен экземпляр DBDataProvider и реальные данные.
    # Здесь можно было бы создать mock-данные для historical_*, чтобы протестировать логику.

    # Пример mock-данных (очень упрощенно):
    mock_hist_birth_counts = {15: {2020: 10, 2021: 12, 2022: 11}, 20: {2020: 100, 2021: 105, 2022: 102}}
    mock_hist_female_pop = {15: {2020: 1000, 2021: 1010, 2022: 1005}, 20: {2020: 5000, 2021: 5050, 2022: 5020}}
    mock_hist_death_counts = {
        'M': {0: {2020: 5, 2021: 4, 2022: 6}, 70: {2020: 50, 2021: 55, 2022: 52}},
        'F': {0: {2020: 4, 2021: 3, 2022: 3}, 70: {2020: 40, 2021: 42, 2022: 38}}
    }
    mock_hist_pop_for_deaths = {
        'M': {0: {2020: 1000, 2021: 1020, 2022: 1010}, 70: {2020: 2000, 2021: 2050, 2022: 2100}},
        'F': {0: {2020: 980, 2021: 990, 2022: 1000}, 70: {2020: 2500, 2021: 2550, 2022: 2600}}
    }

    processor = CoefficientProcessor(
        historical_birth_counts=mock_hist_birth_counts,
        historical_female_population=mock_hist_female_pop,
        historical_death_counts=mock_hist_death_counts,
        historical_population_for_deaths=mock_hist_pop_for_deaths,
        forecast_start_year=2023,
        forecast_end_year=2025,
        all_ages_list=list(range(0, 100)),  # до 99
        open_age_group=100
    )

    print("--- Тест коэффициентов рождаемости (последний год) ---")
    birth_rates_ly = processor.get_forecasted_birth_rates(scenario=SCENARIO_LAST_YEAR)
    for age, data in birth_rates_ly.items():
        print(f"Возраст матери {age}: {data}")

    print("\n--- Тест коэффициентов рождаемости (исторический тренд) ---")
    birth_rates_ht = processor.get_forecasted_birth_rates(scenario=SCENARIO_HISTORICAL_TREND)
    for age, data in birth_rates_ht.items():
        print(f"Возраст матери {age}: {data}")

    print("\n--- Тест коэффициентов рождаемости (ручной +1%) ---")
    birth_rates_mp = processor.get_forecasted_birth_rates(scenario=SCENARIO_MANUAL_PERCENT,
                                                          manual_annual_change_percent=1.0)
    for age, data in birth_rates_mp.items():
        print(f"Возраст матери {age}: {data}")

    print("\n--- Тест коэффициентов смертности (Мужчины, последний год) ---")
    death_rates_m_ly = processor.get_forecasted_death_rates(sex_code_to_process='M', scenario=SCENARIO_LAST_YEAR)
    for age, data in death_rates_m_ly.items():
        print(f"Пол М, Возраст {age}: {data}")

    if death_rates_m_ly:
        print("\n--- Тест коэффициентов дожития (Мужчины, из последнего года смертности) ---")
        survival_m_ly = processor.calculate_survival_rates(death_rates_m_ly)
        for age, data in survival_m_ly.items():
            print(f"Пол М, Возраст дожития из {age}: {data}")