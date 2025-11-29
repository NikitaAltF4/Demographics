// static/js/forecasting_form_handler.js
document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('demographicForecastForm');

    if (form) {
        form.addEventListener('submit', function(event) {
            console.log('Обработчик SUBMIT формы (forecasting_form_handler.js): подготовка данных...');

            // --- 1. Регионы ---
            const regionIdsInput = document.getElementById('selectedRegionIdsInput'); // name="region_ids"
            if (regionIdsInput) {
                // Проверка на пустое значение, если необходимо, но обычно карта устанавливает RU-RF по умолчанию
                if (!regionIdsInput.value || regionIdsInput.value.trim() === "") {
                    console.warn("selectedRegionIdsInput пустое. Убедитесь, что значение устанавливается картой или имеет дефолт в HTML.");
                    // Если нужно принудительно: regionIdsInput.value = "RU-RF";
                }
                console.log("Передача -> Регионы (Map Codes):", regionIdsInput.value);
            } else {
                console.error("Скрытое поле для ID регионов (selectedRegionIdsInput) не найдено!");
            }

            // --- 2. Тип поселения ---
            const urbanCb = document.getElementById('settlementUrban');
            const ruralCb = document.getElementById('settlementRural');
            const finalSettlementInput = document.getElementById('finalSettlementTypeId'); // name="settlement_type_id"

            if (urbanCb && ruralCb && finalSettlementInput) {
                let finalSettlementId = '1'; // ID=1 (Total) по умолчанию (соответствует вашему views.py)
                if (urbanCb.checked && !ruralCb.checked) finalSettlementId = '2'; // ID=2 (Urban)
                else if (!urbanCb.checked && ruralCb.checked) finalSettlementId = '3'; // ID=3 (Rural)
                finalSettlementInput.value = finalSettlementId;
                console.log("Передача -> Тип поселения (ID):", finalSettlementInput.value);
            } else {
                console.warn("Элементы для типа поселения (settlementUrban, settlementRural, finalSettlementTypeId) не найдены полностью.");
            }

            // --- 3. Пол ---
            const maleCb = document.getElementById('genderMale');
            const femaleCb = document.getElementById('genderFemale');
            const finalSexInput = document.getElementById('finalSexCodeTarget'); // name="sex_code_target"

            if (maleCb && femaleCb && finalSexInput) {
                let finalSexCode = 'A'; // Код 'A' (Оба) по умолчанию (соответствует вашему views.py)
                if (maleCb.checked && !femaleCb.checked) finalSexCode = 'M';
                else if (!maleCb.checked && femaleCb.checked) finalSexCode = 'F';
                finalSexInput.value = finalSexCode;
                console.log("Передача -> Целевой пол (Код):", finalSexInput.value);
            } else {
                console.warn("Элементы для выбора пола (genderMale, genderFemale, finalSexCodeTarget) не найдены полностью.");
            }

            // --- 4. Возрастные группы ---
            // name="target_age_start", name="target_age_end", name="target_age_group_type"
            const ageFromInputEl = document.getElementById('ageFromInputNoui');
            const ageToInputEl = document.getElementById('ageToInputNoui');
            const targetAgeGroupTypeInputEl = document.getElementById('selectedAgeRangeInputNoui'); // Этот input name="target_age_group_type"

            if (ageFromInputEl && ageToInputEl && targetAgeGroupTypeInputEl) {
                console.log(`Считано -> Возраст от: ${ageFromInputEl.value}, до: ${ageToInputEl.value}, тип группы: ${targetAgeGroupTypeInputEl.value}`);

            } else {
                 console.warn("Одно или несколько полей для возрастных групп (ageFromInputNoui, ageToInputNoui, selectedAgeRangeInputNoui) не найдены.");
            }


            // --- 5. Период прогнозирования ---

            const histEndYearInput = document.getElementById('historicalDataEndYearInput');
            const forecastEndYearInput = document.getElementById('forecastEndYearInput');
            const calculatedStartYearInput = document.getElementById('calculatedForecastStartYearInput'); // name="forecast_start_year"

            if (histEndYearInput && forecastEndYearInput && calculatedStartYearInput) {
                 console.log(`Считано -> Год конца ист. данных: ${histEndYearInput.value}`);
                 console.log(`Считано -> Год начала прогноза (скрытое поле): ${calculatedStartYearInput.value}`);
                 console.log(`Считано -> Год конца прогноза: ${forecastEndYearInput.value}`);
            } else {
                console.warn("Одно или несколько полей для периода прогнозирования (historicalDataEndYearInput, forecastEndYearInput, calculatedForecastStartYearInput) не найдены.");
            }


            // --- 6. Сценарии и проценты ---


            function setFinalManualPercentage(scenarioRadioGroupName, positivePercInputName, negativePercInputName, finalHiddenInputName) {
                const selectedScenarioRadio = form.querySelector(`input[name="${scenarioRadioGroupName}"]:checked`);
                const finalHiddenInput = form.elements[finalHiddenInputName];

                if (!selectedScenarioRadio) {
                    // console.warn(`(setFinalManualPercentage) Не найдена выбранная радиокнопка для группы "${scenarioRadioGroupName}"`);
                    if (finalHiddenInput) finalHiddenInput.value = '';
                    return;
                }
                if (!finalHiddenInput) {
                    // console.warn(`(setFinalManualPercentage) Не найдено скрытое поле для результата "${finalHiddenInputName}"`);
                    return;
                }

                finalHiddenInput.value = '';

                if (typeof djangoScenarioValues !== 'undefined' && djangoScenarioValues.manual_percent) {
                    if (selectedScenarioRadio.value === djangoScenarioValues.manual_percent) {
                        let percentageStr = '';
                        let isNegative = false;

                        const selectedRadioId = selectedScenarioRadio.id;
                        // Ваши input'ы для процентов имеют name, а не id, к которым легко обратиться,
                        // поэтому доступ через form.elements[name]
                        const positiveInput = form.elements[positivePercInputName];
                        const negativeInput = form.elements[negativePercInputName];

                        if (positiveInput && selectedRadioId.toLowerCase().includes('positive')) {
                            percentageStr = positiveInput.value;
                        } else if (negativeInput && selectedRadioId.toLowerCase().includes('negative')) {
                            percentageStr = negativeInput.value;
                            isNegative = true;
                        } else {
                             // console.warn(`Для ${scenarioRadioGroupName} (ID радио: ${selectedRadioId}) не найдено активное поле ввода % ('positive'/'negative' в ID не найдено).`);
                        }

                        if (percentageStr && percentageStr.trim() !== '') {
                            let percValue = parseFloat(percentageStr.replace(',', '.'));
                            if (!isNaN(percValue)) {
                                finalHiddenInput.value = isNegative ? -Math.abs(percValue) : Math.abs(percValue);
                            } else {
                                // console.warn(`Не удалось преобразовать процент '${percentageStr}' в число для ${finalHiddenInputName}`);
                            }
                        }
                    }
                } else {
                    console.error("JS Объект 'djangoScenarioValues' или его ключ 'manual_percent' не определен. Проверьте HTML-шаблон forecasting_parameters.html.");
                }
                console.log(`Установлено для отправки -> ${finalHiddenInputName}:`, finalHiddenInput.value || "'' (пусто)");
            }

            if (typeof djangoScenarioValues === 'undefined' || !djangoScenarioValues.manual_percent) {
                console.error("CRITICAL: JavaScript объект 'djangoScenarioValues' не определен или не содержит ключ 'manual_percent'. Убедитесь, что он передается из Django в HTML forecasting_parameters.html в теге <script> ПЕРЕД этим скриптом.");
            } else {
                setFinalManualPercentage(
                    'birth_rate_scenario',
                    'birth_rate_manual_perc_positive_input',
                    'birth_rate_manual_perc_negative_input',
                    'birth_rate_manual_change_percent'
                );
                setFinalManualPercentage(
                    'death_rate_scenario_male',
                    'death_rate_manual_perc_male_positive_input',
                    'death_rate_manual_perc_male_negative_input',
                    'death_rate_manual_change_percent_male'
                );
                setFinalManualPercentage(
                    'death_rate_scenario_female',
                    'death_rate_manual_perc_female_positive_input',
                    'death_rate_manual_perc_female_negative_input',
                    'death_rate_manual_change_percent_female'
                );

                const includeMigrationCb = document.getElementById('includeMigration'); // name="include_migration"
                const finalMigrationPercHiddenInput = form.elements['migration_manual_change_percent']; // name="migration_manual_change_percent"

                if (includeMigrationCb && finalMigrationPercHiddenInput) {
                    if (includeMigrationCb.checked) {
                        setFinalManualPercentage(
                            'migration_scenario',
                            'migration_manual_perc_positive_input',
                            'migration_manual_perc_negative_input',
                            'migration_manual_change_percent'
                        );
                    } else {
                        finalMigrationPercHiddenInput.value = '';
                        console.log(`Установлено для отправки -> migration_manual_change_percent: '' (миграция выключена)`);
                    }
                } else {
                    console.warn("Элементы 'includeMigration' или скрытое поле 'migration_manual_change_percent' не найдены.");
                }
            }

            const detailedAgeForecastCb = document.getElementById('detailedAgeForecast'); // name="output_detailed_by_age"
            if (detailedAgeForecastCb) {
                 console.log("Значение чекбокса 'Детализация по возрастам' (будет отправлено как есть):", detailedAgeForecastCb.checked);
            } else {
                 console.warn("Чекбокс 'detailedAgeForecast' не найден.");
            }

            console.log("Форма подготовлена. Стандартная отправка будет выполнена браузером.");
            // event.preventDefault() здесь НЕТ, поэтому форма отправится обычным образом.
            // Если этот скрипт используется вместе с forecasting_progress_bar.js,
            // то forecasting_progress_bar.js должен вызывать event.preventDefault() для AJAX-отправки.
            // Если это ЕДИНСТВЕННЫЙ обработчик submit, и он должен только подготовить данные,
            // то отсутствие preventDefault() корректно.

        });
    } else {
        console.error("Форма #demographicForecastForm не найдена на странице! Обработчик forecasting_form_handler.js не будет работать.");
    }
});