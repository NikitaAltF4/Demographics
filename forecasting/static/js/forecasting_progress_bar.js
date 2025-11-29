// forecasting_progress_bar.js
document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('demographicForecastForm');
    const loadingOverlay = document.getElementById('loadingOverlay');
    const progressBar = document.getElementById('progressBar');
    const progressTextElement = document.querySelector('#loadingOverlay .loading-text');
    let progressIntervalId;
    let currentForecastTaskId = null;

    const apiUrlInput = document.getElementById('forecastProgressApiUrl');
    if (!apiUrlInput) {
        console.error("CRITICAL: Input with ID 'forecastProgressApiUrl' not found in DOM!");
    }

    const progressApiUrl = apiUrlInput ? apiUrlInput.value : '/SOME_INVALID_URL_SEE_CONSOLE_ERROR/';
    console.log("Progress API URL (from DOMContentLoaded):", progressApiUrl);

    if (form && loadingOverlay && progressBar) {
        form.addEventListener('submit', function(event) {
            event.preventDefault();
            console.log("Form submit event triggered.");

            if (currentForecastTaskId) {
                console.warn("A forecast is already in progress:", currentForecastTaskId);
                return;
            }

            loadingOverlay.style.display = 'block';
            progressBar.style.width = '0%';
            progressBar.textContent = '0%';
            if (progressTextElement) progressTextElement.textContent = 'Отправка запроса...';

            const formData = new FormData(form);
            console.log("Form action URL for POST:", form.action);

            fetch(form.action, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': formData.get('csrfmiddlewaretoken')
                }
            })
            .then(response => {
                console.log("Initial POST response status:", response.status);
                if (!response.ok) {
                    // Пытаемся получить JSON с ошибкой, если сервер его прислал
                    return response.json().then(errData => {
                        // Используем errData.message или стандартное сообщение
                        throw new Error( (errData && errData.message) ? errData.message : `Ошибка сервера: ${response.status}`);
                    }).catch(() => { // Если ответ не JSON или другая ошибка парсинга
                        throw new Error(`Ошибка сервера: ${response.status} (ответ не JSON)`);
                    });
                }
                return response.json();
            })
            .then(data => { // data - это ответ от ForecastView.post
                console.log("Initial POST response data:", data);
                if (data.task_id && (data.status === 'processing_initiated' || data.status === 'processing_complete')) {
                    currentForecastTaskId = data.task_id;
                    console.log("Forecast task started with ID:", currentForecastTaskId);
                    if (progressTextElement) progressTextElement.textContent = 'Расчет запущен, ожидание прогресса...';
                    pollProgress(currentForecastTaskId); // Первый вызов pollProgress
                } else if (data.status === 'error') {
                    handleForecastError(data.message || "Ошибка при запуске прогноза на сервере.");
                } else {
                    // Это может случиться, если data не содержит task_id или status, как ожидалось
                    console.error("Unexpected data structure from initial POST:", data);
                    handleForecastError("Неожиданный ответ от сервера при запуске прогноза (неверная структура).");
                }
            })
            // !!!!! УДАЛЕН ЛИШНИЙ БЛОК .THEN(DATA => {...}) КОТОРЫЙ БЫЛ ЗДЕСЬ !!!!!
            .catch(error => {
                console.error('Ошибка при отправке формы прогноза или в цепочке .then:', error);
                handleForecastError(`Ошибка обработки ответа сервера: ${error.message}`);
            });
        });
    } else {
        if (!form) console.error("Form #demographicForecastForm not found!");
        if (!loadingOverlay) console.error("Element #loadingOverlay not found!");
        if (!progressBar) console.error("Element #progressBar not found!");
    }

    function pollProgress(taskIdArgument) { // Используем taskIdArgument для ясности
        if (!currentForecastTaskId || currentForecastTaskId !== taskIdArgument) {
            console.warn(`pollProgress: Task ID mismatch or task cleared. Polling for ${taskIdArgument}, current is ${currentForecastTaskId}. Halting.`);
            if (progressIntervalId) clearInterval(progressIntervalId);
            return;
        }
        console.log(`Polling progress for task: ${taskIdArgument}`);

        // Проверка, что progressApiUrl корректно определен
        if (!progressApiUrl || progressApiUrl === '/SOME_INVALID_URL_SEE_CONSOLE_ERROR/') {
            console.error("Cannot poll progress: progressApiUrl is not correctly configured.");
            handleForecastError("Ошибка конфигурации: не удалось определить URL для API прогресса.");
            return;
        }
        const pollingUrl = `${progressApiUrl.endsWith('/') ? progressApiUrl : progressApiUrl + '/'}?task_id=${taskIdArgument}`;
        console.log("Polling URL:", pollingUrl);

        fetch(pollingUrl)
        .then(response => {
            console.log(`Progress API response status for task ${taskIdArgument}:`, response.status);
            if (!response.ok) {
                if (response.status === 404) {
                     return response.json().then(errData => { // Пытаемся получить JSON даже для 404
                        throw new Error( (errData && errData.message) ? errData.message : "Задача прогноза не найдена (404).");
                    }).catch(() => {
                        throw new Error("Задача прогноза не найдена (404, ответ не JSON).");
                    });
                }
                 // Для других ошибок сервера при опросе
                return response.json().then(errData => {
                    throw new Error( (errData && errData.message) ? errData.message : `Ошибка при проверке прогресса: ${response.status}`);
                }).catch(() => {
                     throw new Error(`Ошибка при проверке прогресса: ${response.status} (ответ не JSON).`);
                });
            }
            return response.json();
        })
        .then(data => { // data - это ответ от ForecastProgressView
            console.log(`Progress API data for task ${taskIdArgument}:`, data);
            // ---- НОВЫЕ ЛОГИ ДЛЯ АНАЛИЗА ----
            console.log(` JS received from poll: task_id=${data.task_id}, status=${data.status}, progress=${data.progress}, completed_configs=${data.completed_configurations}, total_configs=${data.total_configurations}`);
            // ---- КОНЕЦ НОВЫХ ЛОГОВ ----

            if (data.task_id !== currentForecastTaskId) { // Важная проверка, если задачи могли смениться
                console.warn(`Received progress data for task ${data.task_id}, but current task is ${currentForecastTaskId}. Ignoring.`);
                return;
            }

            // Обновление progressBar и progressTextElement - это происходит до проверки на completed
            console.log(`Updating progress bar (from poll data): value=${data.progress}, text=${Math.round(data.progress)}%`);
            progressBar.style.width = (data.progress || 0) + '%'; // Защита от undefined/null
            progressBar.textContent = Math.round(data.progress || 0) + '%'; // Защита

            if (progressTextElement) {
                if (data.status === 'running' || data.status === 'starting' || data.status === 'queued') {
                    progressTextElement.textContent = `Выполнено процессов: ${data.completed_configurations || 0} из ${data.total_configurations || 'N/A'} `;
                } else if (data.status === 'completed') {
                     progressTextElement.textContent = 'Прогноз готов! Загрузка результатов...';
                } else if (data.status === 'error') {
                    progressTextElement.textContent = `Ошибка: ${data.message || 'Неизвестная ошибка вычисления'}`;
                } else {
                    progressTextElement.textContent = `Статус: ${data.status || 'неизвестен'}`;
                }
            }

            // Теперь проверяем статус
            console.log(`Checking status for task ${taskIdArgument}: Current status is '${data.status}'`);

            if (data.status === 'completed') {
                console.log(`Task ${taskIdArgument} is COMPLETED. Preparing to write results.`);
                if (progressIntervalId) clearInterval(progressIntervalId);

                console.log(`Task ${taskIdArgument} html_result present:`, !!data.html_result);
                if (data.html_result && typeof data.html_result === 'string') {
                    console.log(`Task ${taskIdArgument}: html_result length: ${data.html_result.length}`);
                    setTimeout(function() { // Даем браузеру шанс перерисовать 100%
                        console.log(`Task ${taskIdArgument}: Attempting document.write().`);
                        try {
                            document.open();
                            document.write(data.html_result);
                            document.close();
                            console.log(`Task ${taskIdArgument}: document.write() finished.`);
                            if (typeof feather !== 'undefined') {
                                feather.replace(); // Повторная инициализация иконок
                            }
                        } catch (e) {
                            console.error(`Task ${taskIdArgument}: Error during document.write():`, e);
                            handleForecastError("Ошибка при отображении результатов: " + e.message);
                        }
                    }, 50);
                } else {
                    console.error(`Task ${taskIdArgument} COMPLETED but html_result is missing or not a string:`, data.html_result);
                    handleForecastError("Прогноз завершен, но результаты не были получены (данные неполные).");
                }
                currentForecastTaskId = null; // Сбрасываем ID текущей задачи
            } else if (data.status === 'error') {
                console.error(`Task ${taskIdArgument} reported ERROR:`, data.message);
                if (progressIntervalId) clearInterval(progressIntervalId);
                handleForecastError(data.message || "Произошла ошибка при обработке прогноза на сервере.");
            } else if (data.status === 'running' || data.status === 'starting' || data.status === 'queued') {
                console.log(`Task ${taskIdArgument} is still ${data.status}. Will poll again.`);
                if (progressIntervalId) clearInterval(progressIntervalId);
                progressIntervalId = setTimeout(() => pollProgress(taskIdArgument), 200); // Используем аргумент функции
            } else if (data.status === 'not_found') {
                 console.warn(`Task ${taskIdArgument} reported NOT_FOUND.`);
                 if (progressIntervalId) clearInterval(progressIntervalId);
                 handleForecastError(data.message || "Задача прогнозирования не найдена (возможно, устарела).");
            } else {
                console.warn(`Task ${taskIdArgument} has UNKNOWN status: '${data.status}'. Stopping polling.`);
                if (progressIntervalId) clearInterval(progressIntervalId);
                // Можно решить, показывать ли ошибку или просто остановить опрос
                // handleForecastError(`Неизвестный статус задачи: ${data.status}`);
            }
        })
        .catch(error => {
            console.error(`Ошибка при опросе прогресса для задачи ${taskIdArgument}:`, error);
            if (progressTextElement) progressTextElement.textContent = 'Ошибка связи при проверке статуса...';
            if (progressIntervalId) clearInterval(progressIntervalId);
            // Повторная попытка через больший интервал
            progressIntervalId = setTimeout(() => pollProgress(taskIdArgument), 5000); // Используем аргумент функции
        });
    }

    function handleForecastError(message) {
        console.error("handleForecastError called with message:", message);
        if (progressIntervalId) clearInterval(progressIntervalId);
        currentForecastTaskId = null;
        if (loadingOverlay) loadingOverlay.style.display = 'none';
        // progressBar и progressTextElement уже должны быть объявлены выше,
        // но для безопасности можно добавить проверки, если они используются
        if (progressBar) {
            progressBar.style.width = '0%';
            progressBar.textContent = '0%';
        }
        if (progressTextElement) progressTextElement.textContent = 'Идет расчет прогноза, пожалуйста, подождите';

        alert(`Ошибка прогнозирования: ${message}`);
    }

    window.addEventListener('pageshow', function(event) {
        const overlayStillVisible = loadingOverlay && loadingOverlay.style.display === 'block';
        const noActiveTask = !currentForecastTaskId;
        if (overlayStillVisible && noActiveTask) {
            console.log("Pageshow: Resetting UI as overlay is visible but no task is active.");
            if (loadingOverlay) loadingOverlay.style.display = 'none';
            if (progressBar) {
                 progressBar.style.width = '0%';
                 progressBar.textContent = '0%';
            }
            if (progressTextElement) progressTextElement.textContent = 'Идет расчет прогноза, пожалуйста, подождите';
        }
    });
});