// Инициализация Feather Icons
if (typeof feather !== 'undefined') {
    feather.replace();
} else {
    console.warn('Feather Icons library (feather) не найдена.');
}

// Код для управления сайдбаром и collapse-элементами
document.addEventListener('DOMContentLoaded', function () {
    const sidebarLinks = document.querySelectorAll('#sidebarMenu .nav-link[data-bs-toggle="collapse"]');
    const contentSections = document.querySelectorAll('.forecast-content-section.collapse');
    const migrationCheckbox = document.getElementById('includeMigration');
    const migrationScenarioBlock = document.getElementById('migrationScenarioBlock');

    if (migrationCheckbox && migrationScenarioBlock) {
        migrationCheckbox.addEventListener('change', function() {
            migrationScenarioBlock.style.display = this.checked ? 'block' : 'none';
        });
    }

    sidebarLinks.forEach(link => {
        const targetId = link.getAttribute('data-bs-target');
        const targetSection = document.querySelector(targetId);

        if (targetSection) {
            // Управляем aria-expanded и классом active при показе/скрытии Bootstrap Collapse
            targetSection.addEventListener('show.bs.collapse', function () {
                link.classList.add('active');
                link.setAttribute('aria-expanded', 'true');
            });
            targetSection.addEventListener('hide.bs.collapse', function () {
                link.classList.remove('active');
                link.setAttribute('aria-expanded', 'false');
            });

            // Обработчик клика для скрытия других секций
            link.addEventListener('click', function (event) {
                sidebarLinks.forEach(l => {
                    if (l !== this) {
                        l.classList.remove('active');
                        l.setAttribute('aria-expanded', 'false');
                        // Также скрываем связанные collapse-элементы для неактивных ссылок
                        const otherTargetId = l.getAttribute('data-bs-target');
                        const otherTargetSection = document.querySelector(otherTargetId);
                        if (otherTargetSection && otherTargetSection.classList.contains('show')) {
                             bootstrap.Collapse.getOrCreateInstance(otherTargetSection).hide();
                        }
                    }
                });
                this.classList.add('active');
                this.setAttribute('aria-expanded', 'true');
                // Bootstrap сам покажет целевую секцию по data-bs-target
            });
        }
    });

    // Активация первой видимой секции или первой ссылки по умолчанию
    const regionsContentSection = document.getElementById('regionsContent');
    let defaultSectionShown = false;

    if (regionsContentSection && regionsContentSection.classList.contains('show')) {
         const regionLink = document.querySelector('#sidebarMenu .nav-link[data-bs-target="#regionsContent"]');
         if (regionLink) {
            regionLink.classList.add('active');
            regionLink.setAttribute('aria-expanded', 'true');
            defaultSectionShown = true;
         }
    }

    if (!defaultSectionShown && sidebarLinks.length > 0) {
        // Если ни одна секция не открыта по умолчанию (например, нет .show на regionsContent), открываем первую из сайдбара
        const firstLink = sidebarLinks[0];
        const firstTargetId = firstLink.getAttribute('data-bs-target');
        const firstTargetSection = document.querySelector(firstTargetId);
        if (firstTargetSection) {
            firstLink.classList.add('active');
            firstLink.setAttribute('aria-expanded', 'true');
            if (typeof bootstrap !== 'undefined' && bootstrap.Collapse) { // Проверка на существование bootstrap
                 bootstrap.Collapse.getOrCreateInstance(firstTargetSection).show();
            } else {
                console.warn('Bootstrap Collapse component не найден.');
            }
        }
    }
});