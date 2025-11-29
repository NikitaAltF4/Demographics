document.addEventListener('DOMContentLoaded', function () {
    const ageRangeSliderEl = document.getElementById('ageRangeSliderNoui');
    const ageFromInput = document.getElementById('ageFromInputNoui'); // name="target_age_start"
    const ageToInput = document.getElementById('ageToInputNoui');     // name="target_age_end"

    // Скрытое поле для типа возрастной группы (specific_range или all_ages)
    const targetAgeGroupTypeInput = document.getElementById('selectedAgeRangeInputNoui'); // name="target_age_group_type"

    const ageIconDisplays = document.querySelectorAll('.age-scaled-icon-display');
    const ageGroupIconsContainer = document.querySelector('.age-group-scaled-icons');

    if (!ageRangeSliderEl || !ageFromInput || !ageToInput || !targetAgeGroupTypeInput) {
        console.warn("Не все HTML-элементы для выбора возрастных групп найдены. Функционал может быть ограничен.");
        return;
    }

    const MIN_AGE = parseInt(ageFromInput.min) || 0;
    const MAX_AGE = parseInt(ageToInput.max) || 100;

    // --- 1. Инициализация noUiSlider ---
    noUiSlider.create(ageRangeSliderEl, {
        start: [
            parseInt(ageFromInput.value) || MIN_AGE,
            parseInt(ageToInput.value) || MAX_AGE
        ],
        connect: true,
        step: 1,
        margin: 0,
        range: {
            'min': MIN_AGE,
            'max': MAX_AGE
        },
        tooltips: [true, true],
        format: {
            to: function (value) { return parseInt(value); },
            from: function (value) { return parseInt(value); }
        }
    });

    // --- 2. Синхронизация ширины слайдера (если используется) ---
    function syncSliderWidth() {
        if (ageGroupIconsContainer && ageRangeSliderEl.noUiSlider) {
            const containerWidth = ageGroupIconsContainer.offsetWidth;
            if (containerWidth > 0) {
                const controlsContainer = ageRangeSliderEl.closest('.age-range-controls-noui');
                if (controlsContainer) {
                    controlsContainer.style.maxWidth = `${containerWidth}px`;
                }
            }
        }
    }
    syncSliderWidth();
    window.addEventListener('resize', syncSliderWidth);


    // --- 3. Обновление иконок и инпутов при изменении слайдера ---
    ageRangeSliderEl.noUiSlider.on('update', function (values, handle) {
        const valueFrom = parseInt(values[0]);
        const valueTo = parseInt(values[1]);

        ageFromInput.value = valueFrom;
        ageToInput.value = valueTo;
        updateAgeIconHighlights(valueFrom, valueTo);

        // Так как слайдер используется, устанавливаем тип диапазона
        if (targetAgeGroupTypeInput) {
            targetAgeGroupTypeInput.value = 'specific_range';
        }
    });

    // --- 4. Обновление слайдера при изменении инпутов ---
    function updateSliderFromInputs() {
        let fromVal = parseInt(ageFromInput.value);
        let toVal = parseInt(ageToInput.value);

        if (isNaN(fromVal) || fromVal < MIN_AGE) fromVal = MIN_AGE;
        if (fromVal > MAX_AGE) fromVal = MAX_AGE;
        if (isNaN(toVal) || toVal < MIN_AGE) toVal = MIN_AGE;
        if (toVal > MAX_AGE) toVal = MAX_AGE;
        if (fromVal > toVal) fromVal = toVal; // "От" не может быть больше "До"

        ageFromInput.value = fromVal; // Обновить инпут на случай коррекции
        ageToInput.value = toVal;   // Обновить инпут на случай коррекции

        ageRangeSliderEl.noUiSlider.set([fromVal, toVal]);

        // Также устанавливаем тип диапазона при ручном вводе
        if (targetAgeGroupTypeInput) {
            targetAgeGroupTypeInput.value = 'specific_range';
        }
        // updateAgeIconHighlights(fromVal, toVal); // Вызовется из 'update' слайдера
    }

    ageFromInput.addEventListener('change', updateSliderFromInputs);
    ageToInput.addEventListener('change', updateSliderFromInputs);
    ageFromInput.addEventListener('keydown', function(e) {if (e.key === 'Enter') { this.blur(); updateSliderFromInputs();}});
    ageToInput.addEventListener('keydown', function(e) {if (e.key === 'Enter') { this.blur(); updateSliderFromInputs();}});


    // --- 5. Функция подсветки иконок ---
    function updateAgeIconHighlights(currentFromAge, currentToAge) {
        if (!ageIconDisplays || ageIconDisplays.length === 0) return;
        ageIconDisplays.forEach(iconDisplay => {
            const iconMinAge = parseInt(iconDisplay.dataset.minAge, 10);
            const iconMaxAge = parseInt(iconDisplay.dataset.maxAge, 10);
            iconDisplay.classList.toggle('highlighted',
                currentFromAge <= iconMaxAge && currentToAge >= iconMinAge
            );
        });
    }


    const initialFrom = parseInt(ageFromInput.value) || MIN_AGE;
    const initialTo = parseInt(ageToInput.value) || MAX_AGE;

    if(initialFrom === MIN_AGE && initialTo === MAX_AGE && targetAgeGroupTypeInput){

    } else if (targetAgeGroupTypeInput) {
         targetAgeGroupTypeInput.value = 'specific_range';
    }

    ageRangeSliderEl.noUiSlider.set([initialFrom, initialTo]); // Обновляем слайдер по инпутам

    if (targetAgeGroupTypeInput) { // Изначально ставим 'all_ages', если инпуты 0-100
        if (initialFrom === MIN_AGE && initialTo === MAX_AGE) {
            targetAgeGroupTypeInput.value = 'all_ages';
        } else {
            targetAgeGroupTypeInput.value = 'specific_range';
        }
    }

});