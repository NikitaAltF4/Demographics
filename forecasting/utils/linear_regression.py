# forecasting/utils/linear_regression.py

import logging
from typing import List, Tuple, Optional, Dict

logger = logging.getLogger(__name__)


def calculate_linear_regression_trend(
        data_points: List[Tuple[int, float]]
) -> Optional[Dict[str, float]]:
    """
    Рассчитывает параметры линейной регрессии (y = slope * x + intercept).

    Args:
        data_points: Список кортежей (год, значение_коэффициента).
                     Годы должны быть в хронологическом порядке.

    Returns:
        Словарь с ключами 'slope' и 'intercept' или None, если данных недостаточно
        или все значения y одинаковы (что приведет к проблемам с делением).
    """
    n = len(data_points)
    if n < 2:  # Для тренда нужно хотя бы 2 точки
        logger.debug(f"Недостаточно данных для расчета тренда: {n} точек.")
        return None

    sum_x = 0
    sum_y = 0
    sum_xy = 0
    sum_x_squared = 0

    # Используем относительные годы для большей стабильности вычислений,
    # хотя для небольшого количества лет это может быть не критично.
    # Здесь x - это год, y - это значение коэффициента.
    # Для простоты можно использовать годы как есть, если их диапазон не слишком велик.
    # Мы будем использовать годы напрямую.

    for year, value in data_points:
        sum_x += year
        sum_y += value
        sum_xy += year * value
        sum_x_squared += year * year

    # Формула для наклона (slope)
    # slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x_squared - sum_x * sum_x)
    denominator = (n * sum_x_squared - sum_x * sum_x)
    if denominator == 0:
        # Это происходит, если все значения x (годы) одинаковы (не должно быть, если данные корректны)
        # или если всего одна точка (уже отсеяно).
        # Также может быть, если все значения y одинаковы, что приведет к горизонтальной линии (slope=0).
        # Если все y одинаковы, наклон будет 0, но intercept будет средним y.
        all_y_same = all(point[1] == data_points[0][1] for point in data_points)
        if all_y_same:
            slope = 0.0
            intercept = sum_y / n
            logger.debug(f"Все значения y одинаковы. Slope: {slope}, Intercept: {intercept}")
            return {'slope': slope, 'intercept': intercept}
        else:
            logger.warning("Знаменатель равен нулю при расчете линейной регрессии. Невозможно рассчитать тренд.")
            return None

    slope = (n * sum_xy - sum_x * sum_y) / denominator

    # Формула для пересечения (intercept)
    # intercept = (sum_y - slope * sum_x) / n
    intercept = (sum_y - slope * sum_x) / n

    logger.debug(f"Рассчитанный тренд: slope={slope}, intercept={intercept} для данных: {data_points}")
    return {'slope': slope, 'intercept': intercept}


def predict_value_from_trend(
        trend_params: Dict[str, float],
        year: int
) -> Optional[float]:
    """
    Прогнозирует значение для заданного года на основе параметров тренда.

    Args:
        trend_params: Словарь с 'slope' и 'intercept'.
        year: Год, для которого делается прогноз.

    Returns:
        Прогнозное значение или None, если параметры тренда отсутствуют.
    """
    if not trend_params or 'slope' not in trend_params or 'intercept' not in trend_params:
        return None

    return trend_params['slope'] * year + trend_params['intercept']


if __name__ == '__main__':
    # Пример использования:
    print("Пример 1: Растущий тренд")
    example_data_1 = [(2010, 10.0), (2011, 11.0), (2012, 12.0), (2013, 13.0)]
    trend1 = calculate_linear_regression_trend(example_data_1)
    if trend1:
        print(f"Параметры тренда: {trend1}")
        print(f"Прогноз на 2014: {predict_value_from_trend(trend1, 2014)}")  # Ожидается ~14.0
        print(f"Прогноз на 2015: {predict_value_from_trend(trend1, 2015)}")  # Ожидается ~15.0

    print("\nПример 2: Убывающий тренд")
    example_data_2 = [(2010, 15.0), (2011, 14.0), (2012, 13.0), (2013, 12.0)]
    trend2 = calculate_linear_regression_trend(example_data_2)
    if trend2:
        print(f"Параметры тренда: {trend2}")
        print(f"Прогноз на 2014: {predict_value_from_trend(trend2, 2014)}")  # Ожидается ~11.0

    print("\nПример 3: Недостаточно данных")
    example_data_3 = [(2010, 10.0)]
    trend3 = calculate_linear_regression_trend(example_data_3)
    if trend3 is None:
        print("Недостаточно данных, тренд не рассчитан (ожидаемо).")

    print("\nПример 4: Горизонтальный тренд (все y одинаковы)")
    example_data_4 = [(2010, 10.0), (2011, 10.0), (2012, 10.0)]
    trend4 = calculate_linear_regression_trend(example_data_4)
    if trend4:
        print(f"Параметры тренда: {trend4}")  # Ожидается slope=0, intercept=10
        print(f"Прогноз на 2013: {predict_value_from_trend(trend4, 2013)}")  # Ожидается 10