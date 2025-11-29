document.addEventListener('DOMContentLoaded', function() {
    // --- Логика для ВЫБОРА ПОЛА ---
    const genderMaleOption = document.getElementById('genderMaleOption');
    const genderFemaleOption = document.getElementById('genderFemaleOption');

    const maleCheckbox = document.getElementById('genderMale');
    const femaleCheckbox = document.getElementById('genderFemale');
    const genderAllCheckbox = document.getElementById('genderAll');
    const selectedGendersInput = document.getElementById('selectedGendersInput');

    if (!genderMaleOption || !genderFemaleOption || !maleCheckbox || !femaleCheckbox || !genderAllCheckbox) {
        console.error("Не все элементы для выбора пола найдены. Проверьте HTML ID.");
        // return; // Не прерываем, если другие секции могут работать
    }

    function updateGenderVisualState() {
        if (!maleCheckbox || !femaleCheckbox) return; // Доп. проверка

        if (maleCheckbox.checked) {
            if (genderMaleOption) {
                genderMaleOption.classList.add('active');
                genderMaleOption.setAttribute('aria-pressed', 'true');
            }
        } else {
            if (genderMaleOption) {
                genderMaleOption.classList.remove('active');
                genderMaleOption.setAttribute('aria-pressed', 'false');
            }
        }

        if (femaleCheckbox.checked) {
            if (genderFemaleOption) {
                genderFemaleOption.classList.add('active');
                genderFemaleOption.setAttribute('aria-pressed', 'true');
            }
        } else {
            if (genderFemaleOption) {
                genderFemaleOption.classList.remove('active');
                genderFemaleOption.setAttribute('aria-pressed', 'false');
            }
        }

        if (genderAllCheckbox) {
            genderAllCheckbox.checked = maleCheckbox.checked && femaleCheckbox.checked;
        }

        if (selectedGendersInput) {
            let selectedValues = [];
            if (genderAllCheckbox && genderAllCheckbox.checked) { // Если выбраны оба, отправляем "all"
                selectedValues.push('all');
            } else {
                if (maleCheckbox.checked) {
                    selectedValues.push('male');
                }
                if (femaleCheckbox.checked) {
                    selectedValues.push('female');
                }
            }
            selectedGendersInput.value = selectedValues.join(',');
            // console.log("Selected genders for form:", selectedGendersInput.value);
        }
    }

    function handleGenderOptionToggle(clickedGenderCheckbox) {
        if (!maleCheckbox || !femaleCheckbox) return; // Доп. проверка

        clickedGenderCheckbox.checked = !clickedGenderCheckbox.checked;

        if (!maleCheckbox.checked && !femaleCheckbox.checked) {
            clickedGenderCheckbox.checked = true; // Хотя бы один должен быть выбран
        }
        updateGenderVisualState();
    }

    if (genderMaleOption) {
        genderMaleOption.addEventListener('click', function() {
            handleGenderOptionToggle(maleCheckbox);
        });
        genderMaleOption.addEventListener('keydown', function(event) {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                handleGenderOptionToggle(maleCheckbox);
            }
        });
    }

    if (genderFemaleOption) {
        genderFemaleOption.addEventListener('click', function() {
            handleGenderOptionToggle(femaleCheckbox);
        });
        genderFemaleOption.addEventListener('keydown', function(event) {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                handleGenderOptionToggle(femaleCheckbox);
            }
        });
    }

    // Инициализация состояния для Пола
    if (maleCheckbox && femaleCheckbox) { // Убедимся, что элементы существуют перед вызовом
      updateGenderVisualState();
    }
});