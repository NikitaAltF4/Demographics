document.addEventListener('DOMContentLoaded', function () {
    const lottieAnimations = {}; // Объект для хранения загруженных Lottie-анимаций

    // 1. Загружаем все большие Lottie-анимации
    document.querySelectorAll('.lottie-feature-animation').forEach(container => {
        const containerId = container.id;
        const animationPath = container.dataset.animationPath;

        if (!containerId) {
            console.warn('Lottie feature animation container is missing an ID.', container);
            return;
        }
        if (!animationPath) {
            console.warn(`data-animation-path not found for Lottie container: ${containerId}`, container);
            return;
        }

        const anim = lottie.loadAnimation({
            container: container,
            renderer: 'svg',
            loop: false,
            autoplay: false,
            path: animationPath
        });
        lottieAnimations[containerId] = anim; // Сохраняем анимацию по ее ID
    });

    // 2. Настраиваем управление для каждой ссылки-стрелки
    document.querySelectorAll('.feature-arrow-link').forEach(arrowLink => {
        const controlledLottieId = arrowLink.dataset.controlsLottieId;
        if (!controlledLottieId) {
            console.warn('feature-arrow-link is missing data-controls-lottie-id attribute.', arrowLink);
            return;
        }

        const targetAnimation = lottieAnimations[controlledLottieId];
        if (!targetAnimation) {
            console.warn(`Lottie animation with ID "${controlledLottieId}" not found or not loaded.`, arrowLink);
            return;
        }

        arrowLink.addEventListener('mouseenter', () => {
            targetAnimation.setDirection(1); // Вперед
            targetAnimation.play();
        });

        arrowLink.addEventListener('mouseleave', () => {
            // Проиграть в обратную сторону:
            targetAnimation.setDirection(-1); // Назад
            targetAnimation.play();

            // Или сбросить на начало:
            // targetAnimation.goToAndStop(0, true);
        });
    });
});