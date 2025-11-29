document.addEventListener('DOMContentLoaded', function () {
    // ... (код для слайдеров остается без изменений) ...

    function setupConditionalInputToggle(options) {
        const { radioGroupName, conditions } = options;
        const radios = document.querySelectorAll(`input[name="${radioGroupName}"]`);
        // Скрытые поля, куда будет записываться итоговый процент
        const finalManualPercInput = document.getElementById(options.finalManualPercInputId);


        if (!radios || radios.length === 0) {
            console.warn(`Радиокнопки с именем "${radioGroupName}" не найдены.`);
            return;
        }

        function toggleInputsAndSetFinalValue() {
            let finalPercentageValue = null; // Для итогового скрытого поля

            radios.forEach(radio => {
                const condition = conditions.find(c => c.radioId === radio.id);
                if (condition) {
                    const container = document.getElementById(condition.containerId);
                    if (container) {
                        if (radio.checked) {
                            container.classList.remove('d-none');
                            // Если это поле для ввода процента, берем его значение
                            const percentageInput = container.querySelector('input[type="number"]');
                            if (percentageInput) {
                                const rawValue = parseFloat(percentageInput.value);
                                if (!isNaN(rawValue)) {
                                    // Определяем, положительное или отрицательное значение
                                    if (condition.isNegativeTrend) {
                                        finalPercentageValue = -Math.abs(rawValue); // Убеждаемся, что оно отрицательное
                                    } else {
                                        finalPercentageValue = Math.abs(rawValue); // Убеждаемся, что оно положительное
                                    }
                                }
                            }
                        } else {
                            container.classList.add('d-none');

                        }
                    }
                } else {

                }
            });


            if (finalManualPercInput) {
                if (finalPercentageValue !== null) {
                    finalManualPercInput.value = finalPercentageValue.toFixed(1); // Округляем до одного знака после запятой
                } else {

                    finalManualPercInput.value = '';
                }
            }
        }

        radios.forEach(radio => {
            radio.addEventListener('change', toggleInputsAndSetFinalValue);
            // Также добавим слушатель на поля ввода процентов, чтобы обновлять итоговое скрытое поле
            const condition = conditions.find(c => c.radioId === radio.id);
            if (condition) {
                const container = document.getElementById(condition.containerId);
                if (container) {
                    const percentageInput = container.querySelector('input[type="number"]');
                    if (percentageInput) {
                        percentageInput.addEventListener('input', toggleInputsAndSetFinalValue);
                        percentageInput.addEventListener('change', toggleInputsAndSetFinalValue); // На случай если 'input' не сработает
                    }
                }
            }
        });
        toggleInputsAndSetFinalValue(); // Вызов для установки начального состояния
    }

    // Настройка для секции "Коэффициенты рождаемости"
    setupConditionalInputToggle({
        radioGroupName: 'birth_rate_scenario',
        finalManualPercInputId: 'finalBirthRateManualPerc', // ID скрытого поля
        conditions: [
            // value у этих радиокнопок "{{ scenarios.manual_percent }}", поэтому ориентируемся на ID
            { radioId: 'fertilityManualPositive', containerId: 'fertilityPositiveTrendContainer', isNegativeTrend: false },
            { radioId: 'fertilityManualNegative', containerId: 'fertilityNegativeTrendContainer', isNegativeTrend: true  }
        ]
    });

    // Настройка для секции "Коэффициенты смертности (Мужчины)"
    setupConditionalInputToggle({
        radioGroupName: 'death_rate_scenario_male',
        finalManualPercInputId: 'finalDeathRateManualPercMale',
        conditions: [
            { radioId: 'mortalityManualPositiveMale', containerId: 'mortalityPositiveTrendMaleContainer', isNegativeTrend: false }, // Улучшение = положительный процент в форме, но для смертности это СНИЖЕНИЕ
            { radioId: 'mortalityManualNegativeMale', containerId: 'mortalityNegativeTrendMaleContainer', isNegativeTrend: true }  // Ухудшение = отрицательный процент в форме, но для смертности это РОСТ

        ]
    });
    // Переделка для смертности с учетом знака
     function setupMortalityToggle(options) {
        const { radioGroupName, conditions, finalManualPercInputId } = options;
        const radios = document.querySelectorAll(`input[name="${radioGroupName}"]`);
        const finalManualPercInput = document.getElementById(finalManualPercInputId);

        if (!radios || radios.length === 0) return;

        function toggleAndSet() {
            let finalPercentageValue = null;
            radios.forEach(radio => {
                const condition = conditions.find(c => c.radioId === radio.id);
                if (condition) {
                    const container = document.getElementById(condition.containerId);
                    if (container) {
                        if (radio.checked) {
                            container.classList.remove('d-none');
                            const percentageInput = container.querySelector('input[type="number"]');
                            if (percentageInput) {
                                const rawValue = parseFloat(percentageInput.value);
                                if (!isNaN(rawValue)) {
                                    // Для смертности:
                                    // "Улучшение (снижение)" -> итоговый процент ОТРИЦАТЕЛЬНЫЙ
                                    // "Ухудшение (рост)" -> итоговый процент ПОЛОЖИТЕЛЬНЫЙ
                                    if (condition.trendType === 'improvement') { // Улучшение
                                        finalPercentageValue = -Math.abs(rawValue);
                                    } else if (condition.trendType === 'worsening') { // Ухудшение
                                        finalPercentageValue = Math.abs(rawValue);
                                    }
                                }
                            }
                        } else {
                            container.classList.add('d-none');
                        }
                    }
                }
            });
            if (finalManualPercInput) {
                finalManualPercInput.value = (finalPercentageValue !== null) ? finalPercentageValue.toFixed(1) : '';
            }
        }
        radios.forEach(radio => {
            radio.addEventListener('change', toggleAndSet);
            const condition = conditions.find(c => c.radioId === radio.id);
            if (condition) {
                const input = document.getElementById(condition.containerId)?.querySelector('input[type="number"]');
                if (input) input.addEventListener('input', toggleAndSet);
                if (input) input.addEventListener('change', toggleAndSet);
            }
        });
        toggleAndSet();
    }

    setupMortalityToggle({
        radioGroupName: 'death_rate_scenario_male',
        finalManualPercInputId: 'finalDeathRateManualPercMale',
        conditions: [
            { radioId: 'mortalityManualPositiveMale', containerId: 'mortalityPositiveTrendMaleContainer', trendType: 'improvement' }, // Улучшение
            { radioId: 'mortalityManualNegativeMale', containerId: 'mortalityNegativeTrendMaleContainer', trendType: 'worsening'  }  // Ухудшение
        ]
    });

    setupMortalityToggle({
        radioGroupName: 'death_rate_scenario_female',
        finalManualPercInputId: 'finalDeathRateManualPercFemale',
        conditions: [
            { radioId: 'mortalityManualPositiveFemale', containerId: 'mortalityPositiveTrendFemaleContainer', trendType: 'improvement' },
            { radioId: 'mortalityManualNegativeFemale', containerId: 'mortalityNegativeTrendFemaleContainer', trendType: 'worsening'  }
        ]
    });


    // Настройка для секции "Миграция"
    setupConditionalInputToggle({ // Используем старую функцию, т.к. миграция проще (рост/снижение сальдо)
        radioGroupName: 'migration_scenario',
        finalManualPercInputId: 'finalMigrationManualPerc',
        conditions: [
            { radioId: 'migrationManualPositive', containerId: 'migrationPositiveTrendContainer', isNegativeTrend: false },
            { radioId: 'migrationManualNegative', containerId: 'migrationNegativeTrendContainer', isNegativeTrend: true }
        ]
    });


    // --- Логика для общего переключателя секции "Международная миграция" ---
    const includeMigrationCheckbox = document.getElementById('includeMigration');
    const migrationDetailsDiv = document.getElementById('migrationDetails');

    if (includeMigrationCheckbox && migrationDetailsDiv) {
        var bsMigrationCollapse = new bootstrap.Collapse(migrationDetailsDiv, { toggle: false });
        function toggleMigrationDetailsSection() {
            if (includeMigrationCheckbox.checked) bsMigrationCollapse.show();
            else bsMigrationCollapse.hide();
        }
        includeMigrationCheckbox.addEventListener('change', toggleMigrationDetailsSection);
        toggleMigrationDetailsSection();
    }


    // Обработка отправки формы
    const form = document.getElementById('demographicForm'); // Убедитесь, что у вашей <form> есть id="demographicForm"
    if (form) {
        form.addEventListener('submit', function(event) {
            event.preventDefault();
            console.log('Форма отправлена (демо). Собираем данные...');
            // const formData = new FormData(form); // FormData может быть неполной для скрытых полей
            const data = {};

            // Получаем данные из формы
            data.fertilityScenario = document.querySelector('input[name="fertilityScenario"]:checked')?.value;
            data.mortalityScenario = document.querySelector('input[name="mortalityScenario"]:checked')?.value;

            // Чекбоксы
            data.include_migration = document.getElementById('includeMigration').checked;
            data.detailed_age_forecast = document.getElementById('detailedAgeForecast').checked; // Предполагается, что есть такой чекбокс

            // Собираем данные для процентов, если выбраны соответствующие тенденции
            if (data.fertilityScenario === 'positive_trend') {
                data.fertility_positive_trend_percentage = form.elements.fertility_positive_trend_percentage.value;
            }
            if (data.fertilityScenario === 'negative_trend') {
                data.fertility_negative_trend_percentage = form.elements.fertility_negative_trend_percentage.value;
            }

            if (data.mortalityScenario === 'positive_trend') {
                data.mortality_positive_trend_percentage = form.elements.mortality_positive_trend_percentage.value;
            }
            if (data.mortalityScenario === 'negative_trend') {
                data.mortality_negative_trend_percentage = form.elements.mortality_negative_trend_percentage.value;
            }

            if (data.include_migration) {
                data.migrationScenario = document.querySelector('input[name="migrationScenario"]:checked')?.value;
                if (data.migrationScenario === 'fixed') { // Добавлена проверка для 'fixed'
                    data.net_migration_value = form.elements.net_migration_value.value;
                }
                if (data.migrationScenario === 'positive_trend') {
                    data.migration_positive_trend_percentage = form.elements.migration_positive_trend_percentage.value;
                }
                if (data.migrationScenario === 'negative_trend') {
                    data.migration_negative_trend_percentage = form.elements.migration_negative_trend_percentage.value;
                }
            } else {
                delete data.migrationScenario;
                delete data.net_migration_value; // Удаляем и это поле
                delete data.migration_positive_trend_percentage;
                delete data.migration_negative_trend_percentage;
            }

            console.log('Собранные данные:', data);
            alert('Данные формы выведены в консоль (нажмите F12).');
        });
    }
});