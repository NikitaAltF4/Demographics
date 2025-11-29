import logging
from typing import List, Dict, Any, Optional, Union, Tuple  # <--- ДОБАВЛЕН Tuple


from data_collector.db_connector import DBConnector

logger = logging.getLogger(__name__)

# --- Константы для упрощения работы с типами поселений и полами ---
SETTLEMENT_TYPE_TOTAL_ID = 1
SETTLEMENT_TYPE_URBAN_ID = 2
SETTLEMENT_TYPE_RURAL_ID = 3

SEX_TOTAL_CODE = 'A'
SEX_MALE_CODE = 'M'
SEX_FEMALE_CODE = 'F'


# --------------------------------------------------------------------

class DBDataProvider:
    """
    Предоставляет методы для загрузки демографических данных из базы данных.
    """

    def __init__(self):
        self.db_connector = DBConnector()

    def _execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """
        Выполняет SQL-запрос и возвращает результаты в виде списка словарей.
        """
        conn = None
        try:
            conn = self.db_connector.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params or ())
            results = cursor.fetchall()
            cursor.close()
            return results
        except Exception as e:
            logger.error(f"Ошибка при выполнении SQL-запроса: {query} с параметрами {params}. Ошибка: {e}",
                         exc_info=True)
            raise
        finally:
            # DBConnector должен сам управлять своим соединением
            pass

    def get_initial_population(
            self,
            year: int,
            region_ids: List[int],
            settlement_type_id: int,
            sex_code: str
    ) -> Dict[int, Dict[str, int]]:
        placeholders_region = ', '.join(['%s'] * len(region_ids))

        query = f"""
            SELECT age, sex, SUM(population) as total_population
            FROM population
            WHERE year = %s
              AND reg IN ({placeholders_region})
              AND settlement_type_id = %s
        """
        params_list = [year] + region_ids + [settlement_type_id]

        if sex_code != SEX_TOTAL_CODE:
            query += " AND sex = %s"
            params_list.append(sex_code)

        query += " GROUP BY age, sex ORDER BY age, sex;"
        params = tuple(params_list)

        logger.debug(f"Запрос get_initial_population: {query} с параметрами {params}")
        raw_results = self._execute_query(query, params)

        population_data = {}
        for row in raw_results:
            age = int(row['age'])
            sex = row['sex']
            pop = int(row['total_population'])
            if age not in population_data:
                population_data[age] = {}
            population_data[age][sex] = population_data[age].get(sex, 0) + pop

        return population_data

    def get_historical_birth_rates_data(
            self,
            start_year: int,
            end_year: int,
            region_ids: List[int],
            settlement_type_id: int,
    ) -> Dict[int, Dict[int, float]]:
        placeholders_region = ', '.join(['%s'] * len(region_ids))
        query = f"""
            SELECT year, age as mother_age, SUM(birth_rate) as total_births
            FROM birth_rate
            WHERE year BETWEEN %s AND %s
              AND reg IN ({placeholders_region})
              AND settlement_type_id = %s
            GROUP BY year, mother_age
            ORDER BY mother_age, year;
        """
        params = tuple([start_year, end_year] + region_ids + [settlement_type_id])
        logger.debug(f"Запрос get_historical_birth_rates_data: {query} с параметрами {params}")
        raw_results = self._execute_query(query, params)

        birth_data = {}
        for row in raw_results:
            year = int(row['year'])
            mother_age = int(row['mother_age'])
            births = float(row['total_births'])
            if mother_age not in birth_data:
                birth_data[mother_age] = {}
            birth_data[mother_age][year] = births
        return birth_data

    def get_historical_female_population_for_birth_rates(
            self,
            start_year: int,
            end_year: int,
            region_ids: List[int],
            settlement_type_id: int,
    ) -> Dict[int, Dict[int, int]]:
        placeholders_region = ', '.join(['%s'] * len(region_ids))
        query = f"""
            SELECT year, age, SUM(population) as total_population
            FROM population
            WHERE year BETWEEN %s AND %s
              AND reg IN ({placeholders_region})
              AND settlement_type_id = %s
              AND sex = %s 
            GROUP BY year, age
            ORDER BY age, year;
        """
        params = tuple([start_year, end_year] + region_ids + [settlement_type_id, SEX_FEMALE_CODE])
        logger.debug(f"Запрос get_historical_female_population_for_birth_rates: {query} с параметрами {params}")
        raw_results = self._execute_query(query, params)

        female_pop_data = {}
        for row in raw_results:
            year = int(row['year'])
            age = int(row['age'])
            pop = int(row['total_population'])
            if age not in female_pop_data:
                female_pop_data[age] = {}
            female_pop_data[age][year] = pop
        return female_pop_data

    def get_historical_death_counts_data(
            self,
            start_year: int,
            end_year: int,
            region_ids: List[int],
            settlement_type_id: int,
            sex_code: str
    ) -> Dict[str, Dict[int, Dict[int, float]]]:
        placeholders_region = ', '.join(['%s'] * len(region_ids))
        query = f"""
            SELECT year, sex, age, SUM(death_rate) as total_deaths
            FROM death_rate
            WHERE year BETWEEN %s AND %s
              AND reg IN ({placeholders_region})
              AND settlement_type_id = %s
        """
        params_list = [start_year, end_year] + region_ids + [settlement_type_id]

        if sex_code != SEX_TOTAL_CODE:
            query += " AND sex = %s"
            params_list.append(sex_code)

        query += " GROUP BY year, sex, age ORDER BY sex, age, year;"
        params = tuple(params_list)
        logger.debug(f"Запрос get_historical_death_counts_data: {query} с параметрами {params}")
        raw_results = self._execute_query(query, params)

        death_data = {}
        for row in raw_results:
            year = int(row['year'])
            sex = row['sex']
            age = int(row['age'])
            deaths = float(row['total_deaths'])
            if sex not in death_data:
                death_data[sex] = {}
            if age not in death_data[sex]:
                death_data[sex][age] = {}
            death_data[sex][age][year] = deaths
        return death_data

    def get_historical_population_for_death_rates(
            self,
            start_year: int,
            end_year: int,
            region_ids: List[int],
            settlement_type_id: int,
            sex_code: str
    ) -> Dict[str, Dict[int, Dict[int, int]]]:
        placeholders_region = ', '.join(['%s'] * len(region_ids))
        query = f"""
            SELECT year, sex, age, SUM(population) as total_population
            FROM population
            WHERE year BETWEEN %s AND %s
              AND reg IN ({placeholders_region})
              AND settlement_type_id = %s
        """
        params_list = [start_year, end_year] + region_ids + [settlement_type_id]

        if sex_code != SEX_TOTAL_CODE:
            query += " AND sex = %s"
            params_list.append(sex_code)

        query += " GROUP BY year, sex, age ORDER BY sex, age, year;"
        params = tuple(params_list)
        logger.debug(f"Запрос get_historical_population_for_death_rates: {query} с параметрами {params}")
        raw_results = self._execute_query(query, params)

        pop_data = {}
        for row in raw_results:
            year = int(row['year'])
            sex = row['sex']
            age = int(row['age'])
            pop = int(row['total_population'])
            if sex not in pop_data:
                pop_data[sex] = {}
            if age not in pop_data[sex]:
                pop_data[sex][age] = {}
            pop_data[sex][age][year] = pop
        return pop_data

    def get_historical_migration_saldo(
            self,
            start_year: int,
            end_year: int,
            region_ids: List[int],
            settlement_type_id: int,
            sex_code: str
    ) -> Dict[str, Dict[Tuple[int, int], Dict[int, int]]]:  # {sex: {(age_start, age_end): {year: saldo}}}
        placeholders_region = ', '.join(['%s'] * len(region_ids))
        query = f"""
            SELECT year, sex, age_group_start, age_group_end, SUM(migration_saldo) as total_saldo
            FROM migration_saldo
            WHERE year BETWEEN %s AND %s
              AND region_id IN ({placeholders_region}) 
              AND settlement_type_id = %s
        """
        params_list = [start_year, end_year] + region_ids + [settlement_type_id]

        if sex_code != SEX_TOTAL_CODE:
            query += " AND sex = %s"
            params_list.append(sex_code)

        query += " GROUP BY year, sex, age_group_start, age_group_end ORDER BY sex, age_group_start, year;"
        params = tuple(params_list)
        logger.debug(f"Запрос get_historical_migration_saldo: {query} с параметрами {params}")
        raw_results = self._execute_query(query, params)

        migration_data = {}
        for row in raw_results:
            year = int(row['year'])
            sex = row['sex']
            age_start = int(row['age_group_start'])
            age_end = int(row['age_group_end']) if row['age_group_end'] is not None else age_start
            saldo = int(row['total_saldo'])

            if sex not in migration_data:
                migration_data[sex] = {}

            age_key = (age_start, age_end)
            if age_key not in migration_data[sex]:
                migration_data[sex][age_key] = {}
            migration_data[sex][age_key][year] = saldo
        return migration_data


if __name__ == '__main__':
    provider = DBDataProvider()
    print("Пример: get_initial_population")
    try:
        initial_pop = provider.get_initial_population(
            year=2022,
            region_ids=[2],
            settlement_type_id=SETTLEMENT_TYPE_TOTAL_ID,
            sex_code=SEX_TOTAL_CODE
        )
        if initial_pop:
            print(f"Получено {len(initial_pop)} возрастных групп для исходного населения.")
            for age, data in list(initial_pop.items())[:3]:
                print(f"  Возраст {age}: {data}")
        else:
            print("Исходное население не найдено.")
    except Exception as e:
        print(f"Ошибка при получении исходного населения: {e}")

    print("\nПример: get_historical_birth_rates_data")
    try:
        birth_data = provider.get_historical_birth_rates_data(
            start_year=2020,
            end_year=2022,
            region_ids=[2],
            settlement_type_id=SETTLEMENT_TYPE_TOTAL_ID
        )
        if birth_data:
            print(f"Получено {len(birth_data)} возрастных групп матерей для данных о рождаемости.")
            for age, data_by_year in list(birth_data.items())[:2]:
                print(f"  Возраст матери {age}: {data_by_year}")
        else:
            print("Данные о рождаемости не найдены.")
    except Exception as e:
        print(f"Ошибка при получении данных о рождаемости: {e}")