document.addEventListener('DOMContentLoaded', function () {
    const histDataEndYearSliderEl = document.getElementById('histDataEndYearSliderNoui');
    const histDataEndYearInputEl = document.getElementById('historicalDataEndYearInput');

    const forecastEndYearSliderEl = document.getElementById('forecastEndYearSliderNoui');
    const forecastEndYearInputEl = document.getElementById('forecastEndYearInput');

    const calculatedForecastStartYearHiddenInput = document.getElementById('calculatedForecastStartYearInput');

    const yearIconDisplays = document.querySelectorAll('.year-scaled-icon-display'); // Получаем иконки

    if (!histDataEndYearSliderEl || !histDataEndYearInputEl ||
        !forecastEndYearSliderEl || !forecastEndYearInputEl ||
        !calculatedForecastStartYearHiddenInput) {
        console.warn("Один или несколько HTML-элементов для управления периодом не найдены.");
        return;
    }

    const MIN_HIST_YEAR = parseInt(histDataEndYearInputEl.min) || 2012;
    const MAX_HIST_YEAR = parseInt(histDataEndYearInputEl.max) || 2022;
    const GLOBAL_MAX_FORECAST_END_YEAR = parseInt(forecastEndYearInputEl.max) || 2050;
    let currentMinForecastEndRange;

    // --- ФУНКЦИЯ ПОДСВЕТКИ ИКОНОК ПЕРИОДА ---
    function updateYearIconHighlights(forecastStart, forecastEnd) {
        if (!yearIconDisplays || yearIconDisplays.length === 0) return;

        const start = parseInt(forecastStart);
        const end = parseInt(forecastEnd);

        if (isNaN(start) || isNaN(end)) return;

        yearIconDisplays.forEach(iconDisplay => {
            const iconMinYear = parseInt(iconDisplay.dataset.minYear);
            const iconMaxYear = parseInt(iconDisplay.dataset.maxYear);

            if (isNaN(iconMinYear) || isNaN(iconMaxYear)) return;

            // Проверяем пересечение диапазонов:
            // (StartA <= EndB) and (EndA >= StartB)
            if (start <= iconMaxYear && end >= iconMinYear) {
                iconDisplay.classList.add('highlighted');
            } else {
                iconDisplay.classList.remove('highlighted');
            }
        });
    }

    // --- Инициализация слайдера для ГОДА ПОСЛЕДНИХ ИСТОРИЧЕСКИХ ДАННЫХ (БАЗЫ) ---
    noUiSlider.create(histDataEndYearSliderEl, {
        start: [parseInt(histDataEndYearInputEl.value) || MAX_HIST_YEAR],
        step: 1,
        connect: 'lower',
        range: { 'min': MIN_HIST_YEAR, 'max': MAX_HIST_YEAR },
        tooltips: true,
        format: { to: v => parseInt(v), from: v => parseInt(v) }
    });

    // --- Инициализация слайдера для КОНЕЧНОГО ГОДА ПРОГНОЗА ---
    noUiSlider.create(forecastEndYearSliderEl, {
        start: [parseInt(forecastEndYearInputEl.value) || ((parseInt(histDataEndYearInputEl.value) || MAX_HIST_YEAR) + 6)],
        step: 1,
        connect: 'lower',
        range: {
            'min': (parseInt(histDataEndYearInputEl.value) || MAX_HIST_YEAR) + 1,
            'max': GLOBAL_MAX_FORECAST_END_YEAR
        },
        tooltips: true,
        format: { to: v => parseInt(v), from: v => parseInt(v) }
    });

    // --- Функция обновления зависимых контролов ---
    function updateDependentControls(selectedHistoricalEndYear) {
        const calculatedForecastStartYear = selectedHistoricalEndYear + 1;
        calculatedForecastStartYearHiddenInput.value = calculatedForecastStartYear;
        currentMinForecastEndRange = calculatedForecastStartYear;

        forecastEndYearSliderEl.noUiSlider.updateOptions({
            range: {
                'min': currentMinForecastEndRange,
                'max': GLOBAL_MAX_FORECAST_END_YEAR
            }
        });

        let currentForecastEndValue = parseInt(forecastEndYearInputEl.value);
        let currentSliderEndValue = parseInt(forecastEndYearSliderEl.noUiSlider.get());

        if (isNaN(currentForecastEndValue) || currentForecastEndValue < currentMinForecastEndRange) {
            currentForecastEndValue = Math.min(currentMinForecastEndRange + 5, GLOBAL_MAX_FORECAST_END_YEAR);
            forecastEndYearInputEl.value = currentForecastEndValue;
        }
         // Если текущее значение слайдера меньше нового минимума, устанавливаем его на новый минимум
        if (currentSliderEndValue < currentMinForecastEndRange) {
             forecastEndYearSliderEl.noUiSlider.set(currentMinForecastEndRange);
        }
        // Если значение инпута было изменено и оно валидно, но отличается от слайдера (или слайдер стал невалиден)
        // устанавливаем слайдер по инпуту (если инпут валиден для нового диапазона)
        else if (currentForecastEndValue >= currentMinForecastEndRange && currentSliderEndValue !== currentForecastEndValue) {
            forecastEndYearSliderEl.noUiSlider.set(currentForecastEndValue);
        }


        // Вызываем подсветку иконок
        updateYearIconHighlights(calculatedForecastStartYear, parseInt(forecastEndYearInputEl.value));
    }

    // --- Связываем слайдер и инпут для базового года ---
    histDataEndYearSliderEl.noUiSlider.on('update', function (values, handle) {
        const val = parseInt(values[0]);
        if (histDataEndYearInputEl.value !== String(val)) { // Обновляем инпут только если значение изменилось
            histDataEndYearInputEl.value = val;
        }
        updateDependentControls(val);
    });

    histDataEndYearInputEl.addEventListener('change', function () {
        let year = parseInt(this.value);
        if (isNaN(year) || year < MIN_HIST_YEAR) year = MIN_HIST_YEAR;
        if (year > MAX_HIST_YEAR) year = MAX_HIST_YEAR;
        this.value = year;
        histDataEndYearSliderEl.noUiSlider.set(year);
    });
    histDataEndYearInputEl.addEventListener('input', function() {
        let year = parseInt(this.value);
        if (!isNaN(year) && year >= MIN_HIST_YEAR && year <= MAX_HIST_YEAR) {
             //histDataEndYearSliderEl.noUiSlider.set(year, false); // false, чтобы не вызывать 'update' СРАЗУ
             //updateDependentControls(year); // вызываем обновление иконок и зависимого слайдера
        }
    });


    // --- Связываем слайдер и инпут для конечного года прогноза ---
    forecastEndYearSliderEl.noUiSlider.on('update', function (values, handle) {
        const endVal = parseInt(values[0]);
        if (forecastEndYearInputEl.value !== String(endVal)){
            forecastEndYearInputEl.value = endVal;
        }
        updateYearIconHighlights(parseInt(calculatedForecastStartYearHiddenInput.value), endVal);
    });

    forecastEndYearInputEl.addEventListener('change', function () {
        let year = parseInt(this.value);
        const minAllowed = currentMinForecastEndRange || (parseInt(histDataEndYearInputEl.value) + 1);
        const maxAllowed = GLOBAL_MAX_FORECAST_END_YEAR;

        if (isNaN(year) || year < minAllowed) year = minAllowed;
        if (year > maxAllowed) year = maxAllowed;
        this.value = year;
        forecastEndYearSliderEl.noUiSlider.set(year);
        // updateYearIconHighlights(parseInt(calculatedForecastStartYearHiddenInput.value), year); // Вызовется из 'update' слайдера
    });
    forecastEndYearInputEl.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            this.blur();
            // Искусственно вызываем 'change', чтобы обновить слайдер, если значение валидно
            const event = new Event('change', { bubbles: true, cancelable: true });
            this.dispatchEvent(event);
        }
    });


    // --- Первоначальная настройка ---
    const initialHistYear = parseInt(histDataEndYearInputEl.value) || MAX_HIST_YEAR;
    const initialForecastEndYear = parseInt(forecastEndYearInputEl.value) || (initialHistYear + 5);

    // Сначала устанавливаем значение для базового года (это вызовет 'update' и updateDependentControls)
    histDataEndYearSliderEl.noUiSlider.set(initialHistYear);

    // Убедимся, что второй слайдер и инпут также установлены корректно после первого updateDependentControls
    // Это нужно, если начальное значение forecastEndYearInputEl было меньше нового минимума
    // updateDependentControls позаботится об этом, но можем еще раз установить здесь.
    let finalInitialEndYear = parseInt(forecastEndYearInputEl.value); // Берем уже скорректированное значение
    if (isNaN(finalInitialEndYear) || finalInitialEndYear < (initialHistYear + 1)){
        finalInitialEndYear = initialHistYear + 1 + 5; // Дефолтный +5 лет к вычисленному началу
        if(finalInitialEndYear > GLOBAL_MAX_FORECAST_END_YEAR) finalInitialEndYear = GLOBAL_MAX_FORECAST_END_YEAR;
        forecastEndYearInputEl.value = finalInitialEndYear;
    }
    forecastEndYearSliderEl.noUiSlider.set(finalInitialEndYear);

    // Финальный вызов для подсветки иконок с актуальными значениями
    updateYearIconHighlights(parseInt(calculatedForecastStartYearHiddenInput.value), finalInitialEndYear);

    if (typeof feather !== 'undefined') {
        feather.replace();
    }
});