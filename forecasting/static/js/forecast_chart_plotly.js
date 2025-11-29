// static/js/forecast_chart_plotly.js
document.addEventListener('DOMContentLoaded', function() {
    // Проверка глобальных переменных данных, определенных в HTML-шаблоне
    if (typeof allForecastData === 'undefined' || typeof availableMetricsRaw === 'undefined' || typeof isDetailedByAgeGlobal === 'undefined') {
        console.error("Data variables (allForecastData, availableMetricsRaw, isDetailedByAgeGlobal) are not defined globally in the HTML template before this script is loaded.");
        const chartContainerOnError = document.getElementById('plotlyChartContainer');
        if (chartContainerOnError) {
            chartContainerOnError.innerHTML = '<p class="text-center text-danger">Ошибка: Необходимые данные для графика не были загружены со страницы.</p>';
        }
        return; // Прерываем выполнение, если данных нет
    }

    // --- ОСНОВНЫЕ DOM-ЭЛЕМЕНТЫ УПРАВЛЕНИЯ ---
    const regionGroupSelect = document.getElementById('chartRegionGroupSelect');
    const mainTypeSelect = document.getElementById('chartMainTypeSelect');
    const renderChartButton = document.getElementById('renderChartButton');
    const chartContainer = document.getElementById('plotlyChartContainer');

    // --- КОНТРОЛЫ ДЛЯ ВРЕМЕННЫХ РЯДОВ / НАЛОЖЕНИЯ ---
    const tsLayeredControlsDiv = document.getElementById('timeSeriesLayeredControls');
    const tsGlobalChartTypeSelect = document.getElementById('tsGlobalChartTypeSelect');
    const tsBarModeSelect = document.getElementById('tsBarModeSelect');
    const barModeLabel = document.getElementById('barModeLabel');
    const layersContainer = document.getElementById('layersContainer');
    const addLayerButton = document.getElementById('addLayerButton');
    let layerCounter = 0; // Счетчик для уникальных ID слоев временных рядов

    // --- КОНТРОЛЫ ДЛЯ ПИРАМИД ---
    const pyramidControlsContainer = document.getElementById('pyramidControlsContainer');
    const additionalPyramidLayersContainer = document.getElementById('additionalPyramidLayersContainer');
    const addPyramidLayerButton = document.getElementById('addPyramidLayerButton');
    const removeLastPyramidLayerButton = document.getElementById('removeLastPyramidLayerButton');
    const pyramidNote = document.getElementById('pyramidNote');
    let pyramidLayerCounter = 0; // Счетчик для слоев пирамид (0 - основной, 1 - первый добавленный и т.д.)

    // Словарь для "человекочитаемых" названий метрик
    const metricLabels = {
        "urban_male": "Город (М)", "urban_female": "Город (Ж)", "urban_total": "Город (Всего)",
        "rural_male": "Село (М)", "rural_female": "Село (Ж)", "rural_total": "Село (Всего)",
        "total_male": "Итог (М)", "total_female": "Итог (Ж)", "total_total": "Итог (Всего)"
        // Добавьте сюда метки для ваших специфичных ключей рождаемости/смертности, если нужно
        // Например: "births_abs": "Число родившихся", "deaths_coeff": "Коэфф. смертности"
    };

    // --- УТИЛИТАРНЫЕ ФУНКЦИИ ---
    // Универсальная функция для заполнения <select> элемента
    function populateSelect(selectElement, optionsArray, useIndexAsValue = false, firstOption = null) {
        if (!selectElement) {
            console.warn("populateSelect: selectElement is null or undefined for options:", optionsArray);
            return;
        }
        selectElement.innerHTML = ''; // Очистить предыдущие опции
        if (firstOption) { // Добавить первую опцию, если предоставлена (может быть объектом {value, text} или строкой)
            if (typeof firstOption === 'object' && firstOption.value !== undefined && firstOption.text !== undefined){
                selectElement.add(new Option(firstOption.text, firstOption.value));
            } else if (typeof firstOption === 'string') {
                 selectElement.add(new Option(firstOption, "")); // Пустое значение для "выберите..."
            }
        }

        optionsArray.forEach((item, index) => {
            let value, text;
            if (typeof item === 'object' && item.value !== undefined && item.text !== undefined) {
                value = item.value;
                text = item.text;
            } else if (useIndexAsValue) {
                value = index.toString();
                text = typeof item === 'string' ? item : JSON.stringify(item); // Обеспечить, чтобы текст был строкой
            } else {
                value = item;
                text = typeof item === 'string' ? item : JSON.stringify(item);
            }
            selectElement.add(new Option(text, value));
        });
    }

    // Заполнение селектора возрастов (для временных рядов и, возможно, других типов)
    function populateDynamicAgeSelect(ageSelectElement, selectedGroupData) {
        if (!isDetailedByAgeGlobal || !ageSelectElement) {
            if(ageSelectElement) { ageSelectElement.innerHTML = ''; ageSelectElement.disabled = true; }
            return;
        }
        // Начальная опция
        const defaultAgeOption = { value: "total_for_group", text: "Сумма по возрастной группе" };

        if (!selectedGroupData || !selectedGroupData.data_by_year || !selectedGroupData.data_by_year.length === 0) {
            populateSelect(ageSelectElement, [], false, defaultAgeOption); // Только опция по умолчанию
            ageSelectElement.disabled = true;
            return;
        }

        const firstYearWithAgeRows = selectedGroupData.data_by_year.find(yd => yd.age_rows && yd.age_rows.length > 0);
        if (firstYearWithAgeRows && firstYearWithAgeRows.age_rows) {
             const ages = new Set();
             selectedGroupData.data_by_year.forEach(yearData => {
                if(yearData.age_rows) yearData.age_rows.forEach(ageRow => ages.add(ageRow.age_display));
             });

             const sortedAges = Array.from(ages).sort((a,b) => {
                let valA = parseInt(a.toString().replace('+', ''), 10);
                let valB = parseInt(b.toString().replace('+', ''), 10);
                if (a.toString().includes('+')) valA += 1000;
                if (b.toString().includes('+')) valB += 1000;
                return valA - valB;
             });
             populateSelect(ageSelectElement, sortedAges, false, defaultAgeOption);
             ageSelectElement.value = "total_for_group";
             ageSelectElement.disabled = false;
        } else {
            populateSelect(ageSelectElement, [], false, defaultAgeOption);
            ageSelectElement.disabled = true;
        }
    }

    // Заполнение селектора годов для конкретного слоя пирамиды
    function populatePyramidYears(pyramidYearSelectElement, selectedGroupData) {
        if (!isDetailedByAgeGlobal || !pyramidYearSelectElement || !selectedGroupData || !selectedGroupData.data_by_year) {
            if(pyramidYearSelectElement) pyramidYearSelectElement.innerHTML = '';
            return;
        }
        const years = selectedGroupData.data_by_year.map(item => item.year.toString());
        populateSelect(pyramidYearSelectElement, years);
        if (years.length > 0 && pyramidYearSelectElement.options.length > 0) { // Проверка что опции добавлены
            pyramidYearSelectElement.value = years[0];
        }
    }

    // --- ИНИЦИАЛИЗАЦИЯ ОБЩИХ СЕЛЕКТОРОВ ---
    if (allForecastData && allForecastData.length > 0) {
        populateSelect(regionGroupSelect, allForecastData.map(g => g.title), true); // true - используем индекс как value
    } else {
        console.warn("No forecast data available to populate region select. Charts might not work.");
        // Дизейблим все, если нет данных по группам
        if (mainTypeSelect) mainTypeSelect.disabled = true;
        if (renderChartButton) renderChartButton.disabled = true;
        if (chartContainer) chartContainer.innerHTML = '<p class="text-center">Нет данных для отображения.</p>';
        return; // Выходим, если основных данных нет
    }

    // --- ЛОГИКА ДЛЯ СЛОЕВ ВРЕМЕННЫХ РЯДОВ ---
    function addLayer() {
        // ... (Код функции addLayer из предыдущего ответа, он довольно большой)
        // Он создает HTML для нового слоя, заполняет селекторы и добавляет слушатели.
        // Важно, чтобы populateSelect и populateDynamicAgeSelect вызывались корректно.
        layerCounter++;
        const layerId = layerCounter;
        const layerDiv = document.createElement('div');
        layerDiv.classList.add('row', 'chart-controls', 'mb-2', 'border-bottom', 'pb-2', 'layer-control-group', 'align-items-end');
        layerDiv.setAttribute('data-layer-id', layerId);

        let ageSelectHTML = '';
        if (isDetailedByAgeGlobal) {
            ageSelectHTML = `
                <div class="col-md-4">
                    <label for="tsAgeSelect_${layerId}" class="form-label">Возраст (Слой ${layerId}):</label>
                    <select id="tsAgeSelect_${layerId}" class="form-select form-select-sm ts-age-select">
                        {# Опции будут добавлены populateDynamicAgeSelect #}
                    </select>
                </div>`;
        }

        layerDiv.innerHTML = `
            <div class="col-md-6">
                <label for="tsMetricSelect_${layerId}" class="form-label">Показатель (Слой ${layerId}):</label>
                <select id="tsMetricSelect_${layerId}" class="form-select form-select-sm ts-metric-select"></select>
            </div>
            ${ageSelectHTML}
            <div class="col-md-1">
                <button type="button" class="btn btn-sm btn-outline-danger remove-layer-button" data-remove-layer-id="${layerId}" title="Удалить слой ${layerId}">X</button>
            </div>
        `;
        layersContainer.appendChild(layerDiv);

        const newMetricSelect = document.getElementById(`tsMetricSelect_${layerId}`);
        const metricOptionsForLayer = availableMetricsRaw.map(key => ({
            value: key,
            text: metricLabels[key] || key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
        }));
        populateSelect(newMetricSelect, metricOptionsForLayer, false, "Выберите показатель...");

        if (isDetailedByAgeGlobal) {
            const newAgeSelect = document.getElementById(`tsAgeSelect_${layerId}`);
            const currentGroupIndex = parseInt(regionGroupSelect.value || 0);
            if (allForecastData[currentGroupIndex]) {
                populateDynamicAgeSelect(newAgeSelect, allForecastData[currentGroupIndex]);
            }
            if(newAgeSelect) newAgeSelect.addEventListener('change', renderSelectedChart);
        }
        if(newMetricSelect) newMetricSelect.addEventListener('change', renderSelectedChart);

        layerDiv.querySelector('.remove-layer-button').addEventListener('click', function() {
            layerDiv.remove();
            renderSelectedChart();
            // Если это был единственный слой, кнопка добавления должна стать основной
            if (layersContainer.children.length === 0 && addLayerButton) {
                 addLayerButton.classList.remove('btn-outline-secondary');
                 addLayerButton.classList.add('btn-outline-primary');
            }
        });
        // Меняем стиль кнопки "добавить" на менее заметный, если уже есть слои
        if (addLayerButton && layersContainer.children.length > 0) {
            addLayerButton.classList.remove('btn-outline-primary');
            addLayerButton.classList.add('btn-outline-secondary');
        }
    }

    if(addLayerButton) addLayerButton.addEventListener('click', addLayer);

    if (tsGlobalChartTypeSelect) {
        tsGlobalChartTypeSelect.addEventListener('change', function() {
            if (this.value === 'bar') {
                if(tsBarModeSelect) tsBarModeSelect.style.display = 'inline-block';
                if(barModeLabel) barModeLabel.style.display = 'inline-block';
            } else {
                if(tsBarModeSelect) tsBarModeSelect.style.display = 'none';
                if(barModeLabel) barModeLabel.style.display = 'none';
            }
            renderSelectedChart();
        });
    }
    if (tsBarModeSelect) tsBarModeSelect.addEventListener('change', renderSelectedChart);

    // --- ЛОГИКА ДЛЯ СЛОЕВ ПИРАМИД ---
    function initializePyramidControls(layerId, isCloningFromFirst = false) {
        console.log(`Initializing pyramid controls for layerId: ${layerId}, isCloningFromFirst: ${isCloningFromFirst}`);
        const prefix = `pyramid`; // Общий префикс для ID

        const regionSelect = document.getElementById(`${prefix}RegionSelect_${layerId}`);
        const yearSelect = document.getElementById(`${prefix}YearSelect_${layerId}`);
        const settlementSelect = document.getElementById(`${prefix}SettlementTypeSelect_${layerId}`);
        const maleColorInput = document.getElementById(`${prefix}MaleColor_${layerId}`);
        const femaleColorInput = document.getElementById(`${prefix}FemaleColor_${layerId}`);

        if (!regionSelect || !yearSelect || !settlementSelect || !maleColorInput || !femaleColorInput) {
            console.error(`One or more controls missing for pyramid layer ${layerId}. Cannot initialize.`);
            return;
        }

        if (isCloningFromFirst && layerId > 0) {
            // Для динамически добавляемых слоев, копируем опции и значения из первого (основного) слоя пирамиды
            // или из главного селектора регионов, если он актуальнее
            const sourceRegionSelect = document.getElementById(`${prefix}RegionSelect_0`) || regionGroupSelect;
            const sourceYearSelect = document.getElementById(`${prefix}YearSelect_0`); // Года будут зависеть от региона этого слоя
            const sourceSettlementSelect = document.getElementById(`${prefix}SettlementTypeSelect_0`);
            // Цвета можно оставить дефолтными для нового слоя или тоже клонировать/генерировать

            if (sourceRegionSelect) {
                populateSelect(regionSelect, Array.from(sourceRegionSelect.options).map(opt => ({ value: opt.value, text: opt.text })));
                regionSelect.value = sourceRegionSelect.value;
            } else { // Если даже основного селектора регионов нет, заполняем из allForecastData
                populateSelect(regionSelect, allForecastData.map(g => g.title), true);
            }

            // Заполняем года на основе текущего выбранного региона этого слоя
            const currentGroupIdxForLayer = parseInt(regionSelect.value || 0);
            if (allForecastData[currentGroupIdxForLayer]) {
                 populatePyramidYears(yearSelect, allForecastData[currentGroupIdxForLayer]);
            } else if (sourceYearSelect){ // Фоллбэк на года из первого слоя, если текущий регион невалиден
                 populateSelect(yearSelect, Array.from(sourceYearSelect.options).map(opt => opt.value));
                 yearSelect.value = sourceYearSelect.value;
            }


            if (sourceSettlementSelect) {
                populateSelect(settlementSelect, Array.from(sourceSettlementSelect.options).map(opt => ({ value: opt.value, text: opt.text })));
                settlementSelect.value = sourceSettlementSelect.value;
            }
            // Для цветов можно установить дефолтные, отличающиеся от первого слоя
            const defaultColors = [ // Палитра для новых слоев
                { male: "#1b9e77", female: "#d95f02" }, // темно-зеленый / оранжевый
                { male: "#7570b3", female: "#e7298a" }, // фиолетовый / розовый
                { male: "#e6ab02", female: "#a6761d" }  // темно-желтый / коричневый
            ];
            const colorSet = defaultColors[(layerId -1) % defaultColors.length]; // Циклически берем цвета
            maleColorInput.value = colorSet.male;
            femaleColorInput.value = colorSet.female;

        } else if (layerId === 0) { // Инициализация основного (нулевого) слоя пирамиды
            if (allForecastData && allForecastData.length > 0) {
                const regionTitlesForPyramid = allForecastData.map(g => g.title);
                console.log(`Pyramid layer ${layerId}: Populating region select with titles:`, regionTitlesForPyramid);
                populateSelect(regionSelect, regionTitlesForPyramid, true); // true = индекс как value
                if (regionSelect.options.length > 0) regionSelect.selectedIndex = 0;

                const initialGroupDataForPyramid = allForecastData[parseInt(regionSelect.value || 0)];
                if (initialGroupDataForPyramid) {
                    populatePyramidYears(yearSelect, initialGroupDataForPyramid);
                }
            } else {
                console.warn(`Pyramid layer ${layerId}: No allForecastData to populate region select.`);
            }
        }

        // Навешиваем обработчики событий на контролы этого слоя
        regionSelect.addEventListener('change', function() {
            const groupData = allForecastData[parseInt(this.value)];
            populatePyramidYears(yearSelect, groupData);
            renderSelectedChart();
        });
        yearSelect.addEventListener('change', renderSelectedChart);
        settlementSelect.addEventListener('change', renderSelectedChart);
        maleColorInput.addEventListener('change', renderSelectedChart);
        femaleColorInput.addEventListener('change', renderSelectedChart);
    }

    // Добавление нового слоя контролов для пирамиды
    if (addPyramidLayerButton) {
      addPyramidLayerButton.addEventListener('click', function() {
        if (!isDetailedByAgeGlobal) {
            alert("Для добавления пирамиды для сравнения необходима детализация прогноза по возрастам.");
            return;
        }

        pyramidLayerCounter++; // Это будет ID для нового слоя (1, 2, 3...)
        const newLayerId = pyramidLayerCounter;

        const layerDiv = document.createElement('div');
        layerDiv.classList.add('pyramid-layer-controls', 'mb-3', 'p-3', 'border', 'rounded', 'border-secondary');
        layerDiv.setAttribute('data-layer-id', newLayerId);

        // Генерируем HTML для нового слоя контролов
        layerDiv.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <h5>Пирамида ${newLayerId + 1} (Сравнение)</h5>
                <button type="button" class="btn-close remove-pyramid-layer-btn" aria-label="Удалить этот слой" data-remove-layer-id="${newLayerId}"></button>
            </div>
            <div class="row chart-controls">
                <div class="col-md-3">
                    <label for="pyramidRegionSelect_${newLayerId}" class="form-label">Группа регионов:</label>
                    <select id="pyramidRegionSelect_${newLayerId}" class="form-select form-select-sm pyramid-region-select"></select>
                </div>
                <div class="col-md-2">
                    <label for="pyramidYearSelect_${newLayerId}" class="form-label">Год:</label>
                    <select id="pyramidYearSelect_${newLayerId}" class="form-select form-select-sm pyramid-year-select"></select>
                </div>
                <div class="col-md-3">
                    <label for="pyramidSettlementTypeSelect_${newLayerId}" class="form-label">Тип поселения:</label>
                    <select id="pyramidSettlementTypeSelect_${newLayerId}" class="form-select form-select-sm pyramid-settlement-select">
                        <option value="total" selected>Все население</option>
                        <option value="urban">Городское</option>
                        <option value="rural">Сельское</option>
                    </select>
                </div>
                <div class="col-md-3">
                    <label class="form-label d-block">Цвета (М / Ж):</label>
                    <input type="color" id="pyramidMaleColor_${newLayerId}" class="form-control-sm pyramid-male-color" value="#66c2a5">
                     / 
                    <input type="color" id="pyramidFemaleColor_${newLayerId}" class="form-control-sm pyramid-female-color" value="#fc8d62">
                </div>
            </div>
        `;
        additionalPyramidLayersContainer.appendChild(layerDiv);
        initializePyramidControls(newLayerId, true); // Инициализируем новые контролы, клонируя опции

        if(removeLastPyramidLayerButton) removeLastPyramidLayerButton.style.display = 'inline-block';
        if(pyramidNote) pyramidNote.style.display = (pyramidLayerCounter > 0) ? 'block' : 'none';
        renderSelectedChart(); // Обновить график
      });
    }

    if (removeLastPyramidLayerButton) {
        removeLastPyramidLayerButton.addEventListener('click', function() {
            if (pyramidLayerCounter > 0) {
                const lastLayer = additionalPyramidLayersContainer.querySelector(`.pyramid-layer-controls[data-layer-id="${pyramidLayerCounter}"]`);
                if (lastLayer) lastLayer.remove();
                pyramidLayerCounter--;
            }
            if (pyramidLayerCounter === 0) {
                this.style.display = 'none'; // Скрыть кнопку удаления, если остался только основной слой
            }
            if(pyramidNote) pyramidNote.style.display = (pyramidLayerCounter > 0) ? 'block' : 'none';
            renderSelectedChart(); // Обновить график
        });
    }

    // Динамическое добавление обработчика для кнопок удаления слоев пирамид (делегирование событий не нужно, т.к. кнопка одна для последнего)
    // Но если бы у каждого слоя была своя кнопка удаления, нужно было бы делегирование или навешивать при создании
    additionalPyramidLayersContainer.addEventListener('click', function(event){
        if(event.target.classList.contains('remove-pyramid-layer-btn')) {
            const layerIdToRemove = event.target.getAttribute('data-remove-layer-id');
            const layerToRemove = additionalPyramidLayersContainer.querySelector(`.pyramid-layer-controls[data-layer-id="${layerIdToRemove}"]`);
            if(layerToRemove) {
                layerToRemove.remove();
                // Пересчитать pyramidLayerCounter не так просто, если удаляем не последний.
                // Проще всего реализовать удаление ТОЛЬКО ПОСЛЕДНЕГО слоя кнопкой removeLastPyramidLayerButton.
                // Если нужно удалять произвольный слой, потребуется переиндексация или другой подход.
                // Пока оставим удаление только последнего.
                // Для произвольного удаления, после remove(), нужно было бы актуализировать pyramidLayerCounter и видимость кнопки "Удалить последнюю".
                if (additionalPyramidLayersContainer.children.length === 0) {
                    if(removeLastPyramidLayerButton) removeLastPyramidLayerButton.style.display = 'none';
                    pyramidLayerCounter = 0; // Сброс, если удалили все дополнительные
                } else {
                    // Обновляем pyramidLayerCounter до максимального оставшегося data-layer-id
                    let maxId = 0;
                     additionalPyramidLayersContainer.querySelectorAll('.pyramid-layer-controls').forEach(div => {
                        const id = parseInt(div.getAttribute('data-layer-id'));
                        if (id > maxId) maxId = id;
                     });
                     pyramidLayerCounter = maxId;
                }


                if(pyramidNote) pyramidNote.style.display = (pyramidLayerCounter > 0) ? 'block' : 'none';
                renderSelectedChart();
            }
        }
    });


    // --- ОБНОВЛЕНИЕ ДИНАМИЧЕСКИХ СЕЛЕКТОРОВ ПРИ СМЕНЕ ГЛАВНОЙ ГРУППЫ РЕГИОНОВ ---
    regionGroupSelect.addEventListener('change', function() {
        // ... (код как был: обновление tsAgeSelect, pyramidYearSelect и т.д. для ВСЕХ слоев) ...
        const selectedGroupIndex = parseInt(this.value);
        const groupData = allForecastData[selectedGroupIndex];
        if (!groupData) return;

        document.querySelectorAll('.ts-age-select').forEach(as => {
            if (as) { populateDynamicAgeSelect(as, groupData); as.value = "total_for_group"; }
        });

        document.querySelectorAll('.pyramid-layer-controls').forEach(layerCtrl => {
            const layerId = layerCtrl.getAttribute('data-layer-id');
            const pyrRegSelect = document.getElementById(`pyramidRegionSelect_${layerId}`);
            const pyrYearSelect = document.getElementById(`pyramidYearSelect_${layerId}`);
            // НЕ меняем pyrRegSelect, если пользователь выбрал для слоя другой регион,
            // а обновляем только года для текущего выбранного региона этого слоя.
            // Но для первой пирамиды (layer 0) можно синхронизировать.
            if (pyrRegSelect && layerId === '0') { // Синхронизируем только основной (нулевой) слой пирамиды
                pyrRegSelect.value = selectedGroupIndex.toString();
                const currentPyramidGroupData = allForecastData[parseInt(pyrRegSelect.value)];
                if (currentPyramidGroupData && pyrYearSelect) {
                     populatePyramidYears(pyrYearSelect, currentPyramidGroupData);
                }
            } else if (pyrRegSelect && pyrYearSelect) { // Для остальных слоев просто обновляем года на основе их текущего выбора региона
                 const currentPyramidGroupDataForLayer = allForecastData[parseInt(pyrRegSelect.value)];
                 if (currentPyramidGroupDataForLayer) {
                    populatePyramidYears(pyrYearSelect, currentPyramidGroupDataForLayer);
                 }
            }
        });
        renderSelectedChart();
    });

    // --- ОСНОВНОЙ ПЕРЕКЛЮЧАТЕЛЬ ТИПОВ ГРАФИКОВ ---
    mainTypeSelect.addEventListener('change', function() {
        // Скрываем все специфичные контролы
        if(tsLayeredControlsDiv) tsLayeredControlsDiv.style.display = 'none';
        if(pyramidControlsContainer) pyramidControlsContainer.style.display = 'none';
        // if(crossControlsDiv) crossControlsDiv.style.display = 'none'; // Если вернете демо-крест

        // Показываем нужные
        const selectedType = this.value;
        if (selectedType === 'time_series' && tsLayeredControlsDiv) {
            tsLayeredControlsDiv.style.display = 'block';
        } else if (selectedType === 'pyramid' && pyramidControlsContainer && isDetailedByAgeGlobal) {
            pyramidControlsContainer.style.display = 'block';
        }
        // else if (selectedType === 'demographic_cross' && crossControlsDiv) {
        //    crossControlsDiv.style.display = 'flex';
        // }
        renderSelectedChart();
    });

    if (renderChartButton) {
        renderChartButton.addEventListener('click', renderSelectedChart);
    }

    // --- ГЛАВНАЯ ФУНКЦИЯ РЕНДЕРИНГА ---
    function renderSelectedChart() {
        Plotly.purge(chartContainer); // Очистка предыдущего графика
        const selectedChart = mainTypeSelect.value;
        console.log("Rendering chart type:", selectedChart);

        if (selectedChart === 'time_series') {
            drawTimeSeriesLayeredChart();
        } else if (selectedChart === 'pyramid' && isDetailedByAgeGlobal) {
            drawPyramidChart();
        } else if (selectedChart === 'pyramid' && !isDetailedByAgeGlobal) {
             chartContainer.innerHTML = '<p class="text-center text-warning">Для построения пирамиды необходима детализация прогноза по возрастам.</p>';
        } else {
            chartContainer.innerHTML = '<p class="text-center">Выберите тип визуализации для построения графика.</p>';
        }
    }

    // --- ФУНКЦИЯ ДЛЯ ИЗВЛЕЧЕНИЯ ЗНАЧЕНИЙ Y ---
    function getValuesForMetric(groupData, metricKey, selectedAgeForDetailed) {
        // ... (код из предыдущего ответа без изменений) ...
        let values = [];
        if (isDetailedByAgeGlobal && selectedAgeForDetailed !== "total_for_group") {
            values = groupData.data_by_year.map(yearItem => {
                const ageRow = yearItem.age_rows ? yearItem.age_rows.find(row => row.age_display === selectedAgeForDetailed) : null;
                return ageRow ? (ageRow[metricKey] || 0) : 0;
            });
        } else {
            if(isDetailedByAgeGlobal && selectedAgeForDetailed === "total_for_group"){
                 values = groupData.data_by_year.map(yearItem => {
                    if (!yearItem.age_rows) return 0;
                    return yearItem.age_rows.reduce((sum, ageRow) => sum + ( (ageRow && ageRow[metricKey]) || 0), 0);
                 });
            } else {
                values = groupData.data_by_year.map(yearItem => (yearItem && yearItem[metricKey]) || 0);
            }
        }
        return values;
    }

    // --- ФУНКЦИЯ ОТРИСОВКИ ВРЕМЕННЫХ РЯДОВ (СЛОИ) ---
    function drawTimeSeriesLayeredChart() {
        // ... (код из предыдущего ответа - без изменений, но он использует addLayerButton, layersContainer и т.д.) ...
        const selectedGroupIndex = parseInt(regionGroupSelect.value);
        const groupData = allForecastData[selectedGroupIndex];
        const globalChartType = tsGlobalChartTypeSelect.value;
        const barMode = (globalChartType === 'bar') ? tsBarModeSelect.value : null;

        if (!groupData || !groupData.data_by_year || groupData.data_by_year.length === 0) {
            chartContainer.innerHTML = '<p class="text-center">Нет данных для выбранной группы регионов.</p>'; return;
        }
        const years = groupData.data_by_year.map(item => item.year);
        const traces = [];

        document.querySelectorAll('#layersContainer .layer-control-group').forEach(layerDiv => {
            const layerId = layerDiv.getAttribute('data-layer-id');
            const metricSelectElement = document.getElementById(`tsMetricSelect_${layerId}`);
            const ageSelectElement = document.getElementById(`tsAgeSelect_${layerId}`);

            if (!metricSelectElement || !metricSelectElement.value) return; // Пропускаем, если метрика не выбрана

            const selectedMetricKey = metricSelectElement.value;
            const selectedAge = (ageSelectElement && !ageSelectElement.disabled) ? ageSelectElement.value : "total_for_group";

            const values = getValuesForMetric(groupData, selectedMetricKey, selectedAge);
            const traceName = (metricLabels[selectedMetricKey] || selectedMetricKey) +
                              (isDetailedByAgeGlobal && selectedAge !== "total_for_group" && ageSelectElement && !ageSelectElement.disabled ? ` (Возраст: ${selectedAge})` : '');
            const trace = { x: years, y: values, name: traceName };

            switch (globalChartType) {
                case 'lines+markers': trace.type = 'scatter'; trace.mode = 'lines+markers'; break;
                case 'lines': trace.type = 'scatter'; trace.mode = 'lines'; break;
                case 'bar': trace.type = 'bar'; delete trace.mode; break;
                case 'markers': trace.type = 'scatter'; trace.mode = 'markers'; break;
                default: trace.type = 'scatter'; trace.mode = 'lines+markers';
            }
            traces.push(trace);
        });

        if (traces.length === 0) {
            chartContainer.innerHTML = '<p class="text-center">Добавьте хотя бы один показатель (слой) для построения графика временного ряда.</p>'; return;
        }

        const layout = {
            title: `Данные по: ${groupData.title}`,
            xaxis: { title: 'Год', automargin: true },
            yaxis: { title: 'Численность', automargin: true },
            margin: { l: 70, r: 30, t: 70, b: 50 },
            legend: { traceorder: 'normal' }
        };
        if (globalChartType === 'bar' && traces.length > 1 && barMode) {
             layout.barmode = barMode;
        } else {
            delete layout.barmode;
        }

        Plotly.newPlot(chartContainer, traces, layout, {responsive: true});
    }

    // --- ФУНКЦИЯ ОТРИСОВКИ ПИРАМИД (с наложением) ---
    function drawPyramidChart() {
        // ... (код из предыдущего ответа, который собирает данные со ВСЕХ '.pyramid-layer-controls')
        if (!isDetailedByAgeGlobal) {
            chartContainer.innerHTML = '<p class="text-center text-warning">Для построения пирамиды необходима детализация прогноза по возрастам.</p>';
            return;
        }
        Plotly.purge(chartContainer);
        const finalTraces = [];
        const allLayersData = []; // Для сбора данных перед созданием трейсов

        document.querySelectorAll('.pyramid-layer-controls').forEach((layerDiv, layerIndex) => {
            const layerId = layerDiv.getAttribute('data-layer-id');
            const regionSel = document.getElementById(`pyramidRegionSelect_${layerId}`);
            const yearSel = document.getElementById(`pyramidYearSelect_${layerId}`);
            const settlementSel = document.getElementById(`pyramidSettlementTypeSelect_${layerId}`);
            const maleColorInput = document.getElementById(`pyramidMaleColor_${layerId}`);
            const femaleColorInput = document.getElementById(`pyramidFemaleColor_${layerId}`);

            if(!regionSel || !yearSel || !settlementSel || !maleColorInput || !femaleColorInput){
                console.warn(`Skipping pyramid layer ${layerId} due to missing controls.`);
                return;
            }

            const selectedGroupIndex = parseInt(regionSel.value);
            const selectedYear = parseInt(yearSel.value);
            const settlementType = settlementSel.value; // 'total', 'urban', 'rural'
            const maleColor = maleColorInput.value;
            const femaleColor = femaleColorInput.value;

            const groupData = allForecastData[selectedGroupIndex];
            if (!groupData) { console.warn(`No group data for index ${selectedGroupIndex}`); return;}

            const yearData = groupData.data_by_year.find(item => item.year === selectedYear);
            if (!yearData || !yearData.age_rows) {
                console.warn(`No age_rows data for group ${groupData.title}, year ${selectedYear}`); return;
            }

            let currentAgeLabels = [];
            let currentMaleValues = [];
            let currentFemaleValues = [];

            yearData.age_rows.forEach(row => {
                currentAgeLabels.push(row.age_display);
                let malePop = 0, femalePop = 0;
                // Адаптируйте под вашу структуру данных (total_male/female или сумма urban+rural)
                if (settlementType === 'urban') {
                    malePop = row.urban_male || 0; femalePop = row.urban_female || 0;
                } else if (settlementType === 'rural') {
                    malePop = row.rural_male || 0; femalePop = row.rural_female || 0;
                } else { // total
                    malePop = (row.total_male !== undefined) ? (row.total_male || 0) : ((row.urban_male || 0) + (row.rural_male || 0));
                    femalePop = (row.total_female !== undefined) ? (row.total_female || 0) : ((row.urban_female || 0) + (row.rural_female || 0));
                }
                currentMaleValues.push(-malePop);
                currentFemaleValues.push(femalePop);
            });

            allLayersData.push({
                ageLabels: currentAgeLabels, // Важно: для правильного наложения все пирамиды должны иметь один и тот же набор и порядок ageLabels
                maleValues: currentMaleValues,
                femaleValues: currentFemaleValues,
                maleColor: maleColor,
                femaleColor: femaleColor,
                legendSuffix: `(${groupData.title.substring(0,10)}... ${selectedYear} ${settlementType})`,
                opacity: (layerIndex === 0) ? 0.8 : 0.55 // Основная чуть менее прозрачна
            });
        });

        if (allLayersData.length === 0) {
            chartContainer.innerHTML = '<p class="text-center">Не выбраны данные для построения пирамид.</p>'; return;
        }

        // Используем ageLabels от первого слоя как основные для оси Y
        const yAxisLabels = allLayersData[0].ageLabels.slice().sort((a,b) => { // Сортируем, если нужно
            let valA = parseInt(a.toString().replace('+', ''),10); let valB = parseInt(b.toString().replace('+', ''),10);
            if (a.toString().includes('+')) valA += 1000; if (b.toString().includes('+')) valB += 1000;
            return valA - valB;
        });
        let maxAbsXValueOverall = 0;

        allLayersData.forEach(layerData => {
            // Находим максимальное абсолютное значение для всех слоев для масштабирования оси X
            const maxMale = Math.max(...layerData.maleValues.map(Math.abs));
            const maxFemale = Math.max(...layerData.femaleValues);
            if (maxMale > maxAbsXValueOverall) maxAbsXValueOverall = maxMale;
            if (maxFemale > maxAbsXValueOverall) maxAbsXValueOverall = maxFemale;

            // Важно: если наборы ageLabels для разных слоев различаются, нужно их синхронизировать.
            // Здесь предполагается, что они совпадают после сортировки yAxisLabels.
            // Если нет - данные для недостающих возрастов в одном из слоев будут 0.
            // Это сложная синхронизация, для простоты предполагаем, что набор возрастов общий.

            finalTraces.push({
                y: yAxisLabels, // Используем общий набор меток оси Y
                x: layerData.maleValues, // Здесь должны быть значения, соответствующие yAxisLabels
                name: `Мужчины ${layerData.legendSuffix}`, type: 'bar', orientation: 'h',
                marker: {color: layerData.maleColor, opacity: layerData.opacity}, hoverinfo: 'y+x'
            });
            finalTraces.push({
                y: yAxisLabels,
                x: layerData.femaleValues,
                name: `Женщины ${layerData.legendSuffix}`, type: 'bar', orientation: 'h',
                marker: {color: layerData.femaleColor, opacity: layerData.opacity}, hoverinfo: 'y+x'
            });
        });

        if (finalTraces.length === 0) { /*...*/ return; }

        const layout = {
            title: 'Возрастно-половые пирамиды',
            yaxis: { title: 'Возраст', automargin: true, categoryorder: 'array', categoryarray: yAxisLabels.slice().reverse() },
            xaxis: { title: 'Численность', automargin: true, range: [-maxAbsXValueOverall*1.1, maxAbsXValueOverall*1.1] },
            barmode: 'overlay', // Ключ к наложению!
            bargap: 0.1, // Расстояние между барами ОДНОГО трейса (если их несколько на одной Y-позиции)
            bargroupgap: 0.05, // Расстояние между группами баров (для разных Y-позиций)
            legend: { x: 0.5, y: -0.25, xanchor:'center', yanchor: 'top', orientation: "h", tracegroupgap: 10 },
            margin: { l: 70, r: 30, t: 70, b: 120 } // Увеличил отступ снизу для легенды
        };
        Plotly.newPlot(chartContainer, finalTraces, layout, {responsive: true});
    }


    // --- ИНИЦИАЛИЗАЦИЯ ПРИ ЗАГРУЗКЕ СТРАНИЦЫ ---
    function initializePage() {
        if (!allForecastData || allForecastData.length === 0) {
            // Обработка случая, когда нет данных вообще
            if(chartContainer) chartContainer.innerHTML = '<p class="text-center">Нет данных для визуализации.</p>';
            if(mainTypeSelect) mainTypeSelect.disabled = true;
            // ... дизейблим все остальные контролы ...
            return;
        }

        // Инициализация общих селекторов
        populateSelect(regionGroupSelect, allForecastData.map(g => g.title), true); // Используем индекс как value
        if(regionGroupSelect.options.length > 0) regionGroupSelect.selectedIndex = 0;

        // Инициализация контролов первого слоя пирамиды (если он есть в HTML)
        if(isDetailedByAgeGlobal && document.getElementById('pyramidRegionSelect_0')) {
           initializePyramidControls(0, true);
        } else if (isDetailedByAgeGlobal && addPyramidLayerButton) {
            // Если isDetailed, но первого слоя нет в HTML, то либо его надо создать, либо дизейблить addPyramidLayerButton.
            // Либо addPyramidLayerButton будет создавать самый первый слой.
            // Текущая логика предполагает, что первый слой пирамиды есть в HTML.
        } else {
            if(pyramidControlsContainer) pyramidControlsContainer.style.display = 'none';
            if(mainTypeSelect) {
                const pyramidOpt = mainTypeSelect.querySelector('option[value="pyramid"]');
                if(pyramidOpt) pyramidOpt.disabled = true;
            }
            if(addPyramidLayerButton) addPyramidLayerButton.style.display = 'none';
            if(removeLastPyramidLayerButton) removeLastPyramidLayerButton.style.display = 'none';
            if(pyramidNote) pyramidNote.style.display = 'none';
        }


        // Изначальное отображение контролов для временного ряда
        mainTypeSelect.value = 'time_series';
        if(tsLayeredControlsDiv) tsLayeredControlsDiv.style.display = 'block';
        if(pyramidControlsContainer) pyramidControlsContainer.style.display = 'none';

        // Добавляем первый слой для временных рядов, если есть метрики
        if (availableMetricsRaw && availableMetricsRaw.length > 0) {
            if (layersContainer && layersContainer.children.length === 0) { // Проверяем, что контейнер есть и пуст
                addLayer();
            }
            renderSelectedChart(); // Первоначальная отрисовка
        } else {
            if (tsLayeredControlsDiv) tsLayeredControlsDiv.innerHTML = '<p class="text-muted">Нет доступных показателей для временного ряда.</p>';
            // Если нет метрик, может, показать какой-то другой график по умолчанию или сообщение
            if (mainTypeSelect.value === 'time_series' && chartContainer) {
                 chartContainer.innerHTML = '<p class="text-center">Нет доступных показателей для графика.</p>';
            }
        }
    }

    initializePage();
});