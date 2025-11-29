document.addEventListener('DOMContentLoaded', function () {
    if (typeof feather !== 'undefined') {
        try {
            feather.replace({ width: '1em', height: '1em', 'stroke-width': 2 });
        } catch(e) {
            console.warn("Feather icons could not be replaced on history page.", e);
        }
    }

    // Обработчики для кнопок экспорта в истории
    document.querySelectorAll('.export-csv-history-link').forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const forecastId = this.dataset.forecastId;
            if (forecastId) {
                // Предполагается, что у вас есть URL с именем 'export_forecast' в приложении 'forecasting'
                // и он принимает forecast_run_id и format
                // Если ваш URL настроен иначе, адаптируйте эту строку
                window.location.href = `/forecast/export/${forecastId}/csv/`;
            } else {
                console.error("Не удалось получить ID прогноза для экспорта CSV");
                alert("Не удалось экспортировать: ID прогноза не найден.");
            }
        });
    });

    document.querySelectorAll('.export-xlsx-history-link').forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const forecastId = this.dataset.forecastId;
            if (forecastId) {
                window.location.href = `/forecast/export/${forecastId}/xlsx/`;
            } else {
                console.error("Не удалось получить ID прогноза для экспорта XLSX");
                alert("Не удалось экспортировать: ID прогноза не найден.");
            }
        });
    });

});