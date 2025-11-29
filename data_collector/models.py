from django.db import models

class Region(models.Model):
    # Django автоматически создаст поле id (AutoField, primary_key=True),
    # если вы не определите другое первичное поле.
    # Ваше поле `id` int(11) NOT NULL в дампе будет соответствовать этому.

    code = models.CharField(
        max_length=10,
        unique=True, # Вы указали в дампе, что это поле у вас было, но не уникальное. Если оно ДОЛЖНО быть уникальным, оставьте. Иначе уберите unique=True
        help_text="Основной код региона (например, RF-1100)"
    )
    name = models.CharField(
        max_length=255,
        help_text="Наименование региона"
    )
    country_id = models.IntegerField( # В вашем дампе это просто int.
                                     # В идеальном Django мире это был бы ForeignKey на модель Country,
                                     # но для простоты пока оставим как IntegerField, если модели Country нет.
        help_text="ID страны (если используется для связи)"
    )
    okato_code = models.CharField(
        max_length=20,
        null=True,
        blank=True, # blank=True позволяет оставлять поле пустым в админке/формах
        help_text="Код ОКАТО/ОКТМО"
    )
    map_code = models.CharField( # Наше новое поле для кодов карты
        max_length=15,
        unique=True,  # Коды карты должны быть уникальны
        null=True,    # Может быть не для всех регионов есть код карты
        blank=True,
        help_text="Код региона как в geoJSON/картах AmCharts (например, RU-AD, RU-RF)"
    )

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'regions' # Явно указываем Django, с какой таблицей работать
        verbose_name = 'Регион'
        verbose_name_plural = 'Регионы'
        ordering = ['name'] # Сортировка по умолчанию в админке и при запросах без order_by