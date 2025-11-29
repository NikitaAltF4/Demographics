document.addEventListener('DOMContentLoaded', function() {
    const settlementUrbanOption = document.getElementById('settlementUrbanOption');
    const settlementRuralOption = document.getElementById('settlementRuralOption');

    const urbanCheckbox = document.getElementById('settlementUrban');
    const ruralCheckbox = document.getElementById('settlementRural');
    const allCheckbox = document.getElementById('settlementAll'); // Используется для определения состояния "Все"
    const selectedTypesInput = document.getElementById('selectedSettlementTypesInput'); // Скрытое поле для отправки

    // Проверка на существование элементов, чтобы избежать ошибок, если разметка изменится
    if (!settlementUrbanOption || !settlementRuralOption || !urbanCheckbox || !ruralCheckbox || !allCheckbox) {
        console.error("Не все элементы для выбора типа поселения найдены. Проверьте HTML ID.");
        return; // Прерываем выполнение, если что-то не найдено
    }

    function updateVisualState() {
        // Обновляем визуальное состояние "кнопок" (div.settlement-option)
        if (urbanCheckbox.checked) {
            settlementUrbanOption.classList.add('active');
            settlementUrbanOption.setAttribute('aria-pressed', 'true');
        } else {
            settlementUrbanOption.classList.remove('active');
            settlementUrbanOption.setAttribute('aria-pressed', 'false');
        }

        if (ruralCheckbox.checked) {
            settlementRuralOption.classList.add('active');
            settlementRuralOption.setAttribute('aria-pressed', 'true');
        } else {
            settlementRuralOption.classList.remove('active');
            settlementRuralOption.setAttribute('aria-pressed', 'false');
        }


        allCheckbox.checked = urbanCheckbox.checked && ruralCheckbox.checked;

        // Обновляем значение скрытого input для отправки на сервер (опционально)
        if (selectedTypesInput) {
            let selectedValues = [];
            if (allCheckbox.checked) {
                selectedValues.push('all'); // Если оба, отправляем "all"
            } else {
                if (urbanCheckbox.checked) {
                    selectedValues.push('urban');
                }
                if (ruralCheckbox.checked) {
                    selectedValues.push('rural');
                }
            }
            selectedTypesInput.value = selectedValues.join(','); // Например "urban", "rural", "urban,rural", или "all"
            // console.log("Selected settlement types for form:", selectedTypesInput.value);
        }
    }

    function handleOptionToggle(clickedOptionCheckbox) {
        // 1. Переключаем состояние чекбокса, соответствующего кликнутой опции
        clickedOptionCheckbox.checked = !clickedOptionCheckbox.checked;


        if (!urbanCheckbox.checked && !ruralCheckbox.checked) {
            clickedOptionCheckbox.checked = true; // Возвращаем его в отмеченное состояние
        }

        // 3. Обновляем визуальное состояние и скрытые поля
        updateVisualState();
    }

    // Навешиваем обработчики на визуальные "кнопки"
    settlementUrbanOption.addEventListener('click', function() {
        handleOptionToggle(urbanCheckbox);
    });
    // Для доступности: обработка нажатия Enter/Space, когда "кнопка" в фокусе
    settlementUrbanOption.addEventListener('keydown', function(event) {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault(); // Предотвращаем стандартное действие (например, прокрутку при Space)
            handleOptionToggle(urbanCheckbox);
        }
    });


    settlementRuralOption.addEventListener('click', function() {
        handleOptionToggle(ruralCheckbox);
    });
    settlementRuralOption.addEventListener('keydown', function(event) {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            handleOptionToggle(ruralCheckbox);
        }
    });


    updateVisualState();
});