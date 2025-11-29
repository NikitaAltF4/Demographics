// static/js/auth_modals.js
document.addEventListener('DOMContentLoaded', function() {
    // --- ИНИЦИАЛИЗАЦИЯ МОДАЛЬНЫХ ОКОН BOOTSTRAP ---
    const loginModalElement = document.getElementById('loginModal');
    const signupModalElement = document.getElementById('signupModal');

    let loginModalInstance, signupModalInstance;

    if (loginModalElement) {
        loginModalInstance = new bootstrap.Modal(loginModalElement);
    }
    if (signupModalElement) {
        signupModalInstance = new bootstrap.Modal(signupModalElement);
    }

    // --- ОБРАБОТЧИКИ ДЛЯ ОТКРЫТИЯ МОДАЛЬНЫХ ОКОН ---
    // (Bootstrap обычно сам обрабатывает data-bs-toggle и data-bs-target,
    // но если нужны кастомные триггеры или поведение, можно добавить)
    // Например, если ссылки в шапке не имеют этих атрибутов:
    /*
    document.getElementById('openLoginModalButton')?.addEventListener('click', (e) => {
        e.preventDefault();
        if (loginModalInstance) loginModalInstance.show();
    });
    document.getElementById('openSignupModalButton')?.addEventListener('click', (e) => {
        e.preventDefault();
        if (signupModalInstance) signupModalInstance.show();
    });
    */


    // --- AJAX ДЛЯ ФОРМЫ ВХОДА ---
    const loginForm = document.getElementById('loginModalForm');
    const loginErrorAlert = document.getElementById('loginErrorAlert'); // Элемент для отображения ошибок

    if (loginForm && loginErrorAlert) {
        loginForm.addEventListener('submit', function(e) {
            e.preventDefault(); // Предотвращаем стандартную отправку
            loginErrorAlert.style.display = 'none'; // Скрыть предыдущие ошибки
            loginErrorAlert.textContent = ''; // Очистить текст

            const formData = new FormData(loginForm);
            const submitButton = loginForm.querySelector('button[type="submit"]');
            if (submitButton) submitButton.disabled = true; // Дизейблим кнопку на время запроса

            fetch(loginForm.action, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': formData.get('csrfmiddlewaretoken'),
                    'X-Requested-With': 'XMLHttpRequest' // Чтобы сервер знал, что это AJAX
                }
            })
            .then(response => {
                if (submitButton) submitButton.disabled = false; // Включаем кнопку обратно

                if (response.ok && response.redirected) {
                    window.location.href = response.url; // Успешный вход и редирект
                } else if (response.ok && response.url.includes(loginForm.action)) {
                    // Сервер вернул 200, но не редирект - значит, ошибки в форме
                    loginErrorAlert.textContent = "Неверное имя пользователя или пароль.";
                    loginErrorAlert.style.display = 'block';
                    // Можно попробовать распарсить HTML и найти form.errors, но это сложнее
                    // Для простоты - общее сообщение.
                } else if (!response.ok) {
                    loginErrorAlert.textContent = `Ошибка сервера: ${response.status}. Пожалуйста, попробуйте позже.`;
                    loginErrorAlert.style.display = 'block';
                    // throw new Error(`Login server error: ${response.status}`); // Для отладки можно раскомментировать
                } else {
                    // Неожиданный успешный ответ без редиректа (маловероятно для Django login view)
                    loginErrorAlert.textContent = "Произошла неожиданная ошибка при входе.";
                    loginErrorAlert.style.display = 'block';
                }
            })
            .catch(error => {
                if (submitButton) submitButton.disabled = false;
                console.error('Login AJAX error:', error);
                loginErrorAlert.textContent = "Ошибка сети или внутренняя ошибка при входе. Пожалуйста, попробуйте снова.";
                loginErrorAlert.style.display = 'block';
            });
        });
    } else {
        if (!loginForm) console.warn("Элемент формы входа #loginModalForm не найден.");
        if (!loginErrorAlert) console.warn("Элемент #loginErrorAlert для ошибок входа не найден.");
    }

    // --- AJAX ДЛЯ ФОРМЫ РЕГИСТРАЦИИ ---
    const signupForm = document.getElementById('signupModalForm');
    const signupAlertsContainer = document.getElementById('signupAlerts'); // div для сообщений/ошибок

    if (signupForm && signupAlertsContainer) {
        signupForm.addEventListener('submit', function(e) {
            e.preventDefault();
            signupAlertsContainer.innerHTML = ''; // Очистить предыдущие сообщения
            const submitButton = signupForm.querySelector('button[type="submit"]');
            if (submitButton) submitButton.disabled = true;

            const formData = new FormData(signupForm);

            fetch(signupForm.action, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': formData.get('csrfmiddlewaretoken'),
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => {
                if (submitButton) submitButton.disabled = false;
                return response.json().then(data => ({ status: response.status, ok: response.ok, redirected: response.redirected, url: response.url, data }));
            })
            .then(({ status, ok, redirected, url, data }) => { // Деструктуризация объекта
                if (ok && redirected) { // Для Django <=4.x signup при успехе может делать редирект
                    window.location.href = url;
                } else if (ok && data && data.status === 'success' && data.redirect_url) { // Если view вернула JSON с redirect_url
                    window.location.href = data.redirect_url;
                } else if (data && data.errors) { // Если view вернула JSON с ошибками
                    Object.keys(data.errors).forEach(field => {
                        const fieldErrors = data.errors[field];
                        fieldErrors.forEach(error => {
                            const alertDiv = document.createElement('div');
                            alertDiv.className = 'alert alert-warning alert-sm p-2'; // Меньше padding
                            let fieldLabel = field;
                            if (field === '__all__') fieldLabel = 'Общие ошибки';
                            else {
                                const labelEl = signupForm.querySelector(`label[for="signup${field.charAt(0).toUpperCase() + field.slice(1)}"]`);
                                if (labelEl) fieldLabel = labelEl.textContent.replace(':','');
                            }
                            alertDiv.innerHTML = `<strong>${fieldLabel}:</strong> ${error.message}`;
                            signupAlertsContainer.appendChild(alertDiv);
                        });
                    });
                } else if (ok && url.includes(signupForm.action)) {
                     // Старый фоллбэк: форма вернулась (200 OK, не AJAX), значит есть ошибки рендера на стороне Django
                    const alertDiv = document.createElement('div');
                    alertDiv.className = 'alert alert-warning';
                    alertDiv.textContent = 'Пожалуйста, проверьте форму на наличие ошибок и попробуйте снова.';
                    signupAlertsContainer.appendChild(alertDiv);
                     console.warn("Signup form seems to have re-rendered by Django, check server response for embedded errors or use JSON error response.");
                } else if (!ok) { // Другие HTTP ошибки
                    const errorMsg = (data && data.message) ? data.message : `Ошибка сервера: ${status}`;
                    throw new Error(errorMsg);
                } else {
                    // Неожиданный успешный ответ
                     const alertDiv = document.createElement('div');
                    alertDiv.className = 'alert alert-info';
                    alertDiv.textContent = 'Ответ от сервера получен, но результат неясен.';
                    signupAlertsContainer.appendChild(alertDiv);
                }
            })
            .catch(error => {
                if (submitButton) submitButton.disabled = false;
                console.error('Signup AJAX error or processing error:', error);
                const alertDiv = document.createElement('div');
                alertDiv.className = 'alert alert-danger';
                alertDiv.textContent = `Ошибка регистрации: ${error.message}. Пожалуйста, попробуйте позже.`;
                signupAlertsContainer.appendChild(alertDiv);
            });
        });
    } else {
        if (!signupForm) console.warn("Элемент формы регистрации #signupModalForm не найден.");
        if (!signupAlertsContainer) console.warn("Элемент #signupAlerts для сообщений регистрации не найден.");
    }

    // Ссылка "Забыли пароль?" из модального окна входа
    const forgotPasswordLink = document.getElementById('forgotPasswordLinkFromLogin');
    if (forgotPasswordLink && loginModalInstance) { // Проверяем loginModalInstance
        forgotPasswordLink.addEventListener('click', function(e){
            e.preventDefault();
            loginModalInstance.hide();
            // URL для сброса пароля должен быть определен в ваших Django urls.py
            // и выведен в шаблон (если он динамический) или захардкожен, если всегда одинаков.
            // Для стандартного Django auth это {% url 'password_reset' %}
            // Если этот скрипт в static, он не может напрямую использовать {% url %}.
            // Поэтому либо URL должен быть в data-атрибуте, либо он известен.
            // Для Django это обычно /accounts/password_reset/
            window.location.href = "/accounts/password_reset/";
        });
    }
});