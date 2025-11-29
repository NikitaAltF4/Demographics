document.addEventListener('DOMContentLoaded', () => {
    const sidebarLinks = document.querySelectorAll('.sidebar-nav .nav-pills .nav-link[href^="#"]');
    const contentSections = document.querySelectorAll('.main-content-column .content-section');
    const mainContentColumn = document.querySelector('.main-content-column'); // Для возможного сброса прокрутки

    function showSection(sectionIdToShow) {
        // Скрываем все секции контента
        contentSections.forEach(section => {
            section.style.display = 'none';
        });

        // Показываем нужную секцию
        const targetSection = document.getElementById(sectionIdToShow);
        if (targetSection) {
            targetSection.style.display = 'block';
             // При переключении секций, прокрутим mainContentColumn вверх, чтобы видеть начало секции
            if (mainContentColumn) {
                mainContentColumn.scrollTop = 0;
            }
        } else {
            console.warn(`Секция с ID "${sectionIdToShow}" не найдена.`);
        }

        // Обновляем активную ссылку в сайдбаре
        sidebarLinks.forEach(link => {
            link.classList.remove('active');
            // Проверяем, что href не пустой и действительно соответствует sectionIdToShow
            const linkHref = link.getAttribute('href');
            if (linkHref && linkHref === `#${sectionIdToShow}`) {
                link.classList.add('active');
            }
        });
    }

    sidebarLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            const targetIdAttribute = this.getAttribute('href');
            if (targetIdAttribute && targetIdAttribute.startsWith('#')) {
                e.preventDefault(); // Отменяем стандартный переход по якорю для навигации по секциям
                const sectionId = targetIdAttribute.substring(1); // Убираем #

                showSection(sectionId);
            }
        });
    });

    // --- Инициализация при загрузке страницы ---
    let initialSectionId = '';
    if (window.location.hash && window.location.hash.length > 1) {
        const hashId = window.location.hash.substring(1);
        if (document.getElementById(hashId) && Array.from(contentSections).some(s => s.id === hashId)) {
            initialSectionId = hashId;
        }
    }

    if (!initialSectionId && sidebarLinks.length > 0) {
        const firstLinkHref = sidebarLinks[0].getAttribute('href');
        if (firstLinkHref && firstLinkHref.startsWith('#')) {
            initialSectionId = firstLinkHref.substring(1);
        }
    }

    if (initialSectionId) {
        showSection(initialSectionId);
    } else if (contentSections.length > 0) {
        contentSections[0].style.display = 'block';
        console.warn("Не удалось определить начальную активную секцию из ссылок сайдбара, показана первая секция по умолчанию.");
        if (sidebarLinks.length > 0) {
            sidebarLinks[0].classList.add('active');
        }
    }


    // --- Инициализация Feather Icons ---
    if (typeof feather !== 'undefined') {
        try {
            feather.replace();
        } catch (e) {
            console.warn("Feather icons could not be replaced (tab-like behavior).", e);
        }
    }

});