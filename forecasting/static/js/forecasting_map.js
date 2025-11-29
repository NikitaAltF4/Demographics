am5.ready(function() {

    // Create root element
    var root = am5.Root.new("amchartsMapContainer");

    // Set themes
    root.setThemes([
        am5themes_Animated.new(root)
    ]);

    // Create the map chart
    var chart = root.container.children.push(am5map.MapChart.new(root, {
        panX: "translateX",
        panY: "translateY",
        projection: am5map.geoMercator(),
        homeZoomLevel: 1,
        homeGeoPoint: { longitude: 95, latitude: 60 } // Центр России (примерно)
    }));

    // Create main polygon series for Russia
    var polygonSeries = chart.series.push(am5map.MapPolygonSeries.new(root, {
        geoJSON: am5geodata_russiaHigh,                 // Ваши геоданные
        geodataNames: am5geodata_russia_regions_lang_RU, // Ваш файл локализации для регионов РФ
        valueField: "id",                               // Поле в geoJSON для ID
        calculateAggregates: true
    }));

    polygonSeries.mapPolygons.template.setAll({
        tooltipText: "{name}",      // Имя из geodataNames
        interactive: true,          // Полигоны интерактивны
        fill: am5.color(0xcccccc),  // Цвет неактивных регионов
        stroke: am5.color(0xffffff),// Цвет границ
        strokeWidth: 0.5
    });

    polygonSeries.mapPolygons.template.states.create("hover", {
        fill: am5.color(0x999999)   // Цвет при наведении
    });

    polygonSeries.mapPolygons.template.states.create("active", {
        fill: am5.color(0xf27d79)
    });

    var selectedRegionsData = [];
    var allMapRegions = [];

    var selectedRegionsListEl = document.getElementById('selectedRegionsList');
    var selectedRegionIdsInputEl = document.getElementById('selectedRegionIdsInput');
    var allRegionsListEl = document.getElementById('allRegionsList');
    var regionSearchInputEl = document.getElementById('regionSearchInput');

    // Функция для обновления списка ВЫБРАННЫХ регионов под картой
    function updateSelectedRegionsDisplayOnPage() {
        if (!selectedRegionsListEl || !selectedRegionIdsInputEl) {
            console.error("Элементы для отображения выбранных регионов не найдены!");
            return;
        }

        selectedRegionsListEl.innerHTML = '';
        var regionGeoJsonIdsToSubmit = []; // Используем коды, которые приходят с карты

        if (selectedRegionsData.length === 0) {
            var li = document.createElement('li');
            li.textContent = 'Выбрана вся Россия';
            li.classList.add('text-muted');
            selectedRegionsListEl.appendChild(li);
            // Устанавливаем специальный код для "Всей России",
            // который соответствует значению в поле `map_code` для записи "Российская Федерация"
            selectedRegionIdsInputEl.value = 'RU-RF'; // <--- ИЗМЕНЕНИЕ ЗДЕСЬ
        } else {
            var sortedSelected = [...selectedRegionsData].sort((a, b) => a.name.localeCompare(b.name, 'ru'));
            sortedSelected.forEach(function(region) {
                var li = document.createElement('li');
                li.textContent = region.name;
                selectedRegionsListEl.appendChild(li);
                // region.id (или region.geoJsonId, как вы его храните в selectedRegionsData)
                // уже должен быть строковым кодом "RU-XXX"
                if (region.id) { // или region.geoJsonId, если так назвали свойство
                    regionGeoJsonIdsToSubmit.push(region.id); // или region.geoJsonId
                }
            });
            selectedRegionIdsInputEl.value = regionGeoJsonIdsToSubmit.join(',');
        }
        console.log("Updated selectedRegionIdsInput (Map Codes):", selectedRegionIdsInputEl.value);
    }

    // Функция для заполнения и обновления списка ВСЕХ регионов слева
    function populateAllRegionsList() {
        if (!allRegionsListEl) {
            console.error("Элемент списка всех регионов #allRegionsList не найден!");
            return;
        }
        allRegionsListEl.innerHTML = '';

        var searchTerm = "";
        if (regionSearchInputEl) {
             searchTerm = regionSearchInputEl.value.toLowerCase();
        }

        var regionsToDisplay = allMapRegions.filter(region =>
            region.name.toLowerCase().includes(searchTerm)
        );

        if (regionsToDisplay.length === 0) {
            var li = document.createElement('li');
            li.classList.add('list-group-item', 'text-muted');
            if (searchTerm) {
                li.textContent = 'Регионы не найдены';
            } else if (allMapRegions.length === 0) {
                 li.textContent = 'Нет данных о регионах';
            } else {
                 li.textContent = 'Поиск не дал результатов';
            }
            allRegionsListEl.appendChild(li);
            return;
        }

        regionsToDisplay.forEach(function(region) {
            var listItem = document.createElement('li');
            listItem.classList.add('list-group-item');
            listItem.textContent = region.name;
            listItem.dataset.regionId = region.id;

            if (selectedRegionsData.some(selRegion => selRegion.id === region.id)) {
                listItem.classList.add('active');
            }

            listItem.addEventListener('click', function() {
                handleRegionInteraction(region.id, region.name);
            });
            allRegionsListEl.appendChild(listItem);
        });
    }

    // Единая функция для обработки выбора/снятия выбора региона
    function handleRegionInteraction(regionId, regionName) {
        var mapPolygon = null;
        polygonSeries.mapPolygons.each(function(polygon) {
            if (polygon.dataItem && polygon.dataItem.get("id") === regionId) {
                mapPolygon = polygon;
            }
        });

        var listItemInAllList = null;
        if (allRegionsListEl) {
            listItemInAllList = allRegionsListEl.querySelector(`li[data-region-id="${regionId}"]`);
        }

        var index = selectedRegionsData.findIndex(r => r.id === regionId);

        if (index > -1) {
            selectedRegionsData.splice(index, 1);
            if (mapPolygon) {
                mapPolygon.set("active", false);
            }
            if (listItemInAllList) {
                listItemInAllList.classList.remove('active');
            }
        } else {
            selectedRegionsData.push({ id: regionId, name: regionName });
            if (mapPolygon) {
                mapPolygon.set("active", true);
            }
            if (listItemInAllList) {
                listItemInAllList.classList.add('active');
            }
        }
        updateSelectedRegionsDisplayOnPage();
    }

    // Event listener для клика по полигону на карте
    polygonSeries.mapPolygons.template.events.on("click", function (ev) {
        var dataItem = ev.target.dataItem;
        if (!dataItem) {
            return;
        }
        var regionId = dataItem.get("id");
        var regionName = dataItem.dataContext.name || regionId;
        handleRegionInteraction(regionId, regionName);
    });

    if (regionSearchInputEl) {
        regionSearchInputEl.addEventListener('input', function() {
            populateAllRegionsList();
        });
    } else {
        console.warn("Элемент поиска #regionSearchInput не найден!");
    }

    polygonSeries.events.on("datavalidated", function() {
        allMapRegions = [];

        if (typeof am5geodata_russiaHigh !== 'undefined' && am5geodata_russiaHigh.features) {
            am5geodata_russiaHigh.features.forEach(function(feature) {
                if (feature.properties && feature.properties.id) {
                    var regionId = feature.properties.id;
                    var regionName = (typeof am5geodata_russia_regions_lang_RU !== 'undefined' && am5geodata_russia_regions_lang_RU[regionId])
                                     ? am5geodata_russia_regions_lang_RU[regionId]
                                     : (feature.properties.name || regionId);
                    allMapRegions.push({ id: regionId, name: regionName });
                }
            });
        } else if (polygonSeries.data.length > 0) {
             polygonSeries.data.each(function(dataItem) {
                var id = dataItem.get("id");
                var name = dataItem.dataContext.name || id;
                if (id) {
                    allMapRegions.push({ id: id, name: name });
                }
            });
        }

        if (allMapRegions.length > 0) {
            allMapRegions.sort((a, b) => a.name.localeCompare(b.name, 'ru'));
            populateAllRegionsList();
        } else {
            if (allRegionsListEl) {
                allRegionsListEl.innerHTML = '<li class="list-group-item text-muted">Не удалось загрузить список регионов.</li>';
            }
            console.warn("Не удалось получить данные о регионах для списка (allMapRegions пуст).");
        }
        // Обновляем отображение выбранных регионов после загрузки данных карты
        // Это важно, если selectedRegionsData может быть предзаполнен
        updateSelectedRegionsDisplayOnPage();
    });

    chart.set("zoomControl", am5map.ZoomControl.new(root, {}));

    // Initial display update for selected regions list
    // Перенесено в 'datavalidated' для гарантии, что все загружено,
    // но также можно вызвать и здесь, если нет предзаполненных данных.
    // Если selectedRegionsData может быть не пустым при инициализации,
    // то этот вызов важен здесь.
    updateSelectedRegionsDisplayOnPage();

    chart.appear(1000, 100);

}); // end am5.ready()