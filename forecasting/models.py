from django.db import models
from django.conf import settings  # Для AUTH_USER_MODEL
from django.urls import reverse  # Для генерации URL
import uuid


class ForecastRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,  # Если пользователя удалят, прогнозы останутся "анонимными"
        null=True,
        blank=True,
        related_name='forecast_runs'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Время запуска")

    # Название, которое пользователь может дать своему прогнозу (необязательно)
    custom_title = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Название прогноза (польз.)"
    )

    # Входные параметры, которые были использованы (словарь base_forecast_params_no_combination_specifics)
    input_parameters_json = models.JSONField(verbose_name="Входные параметры (JSON)")

    # Если вы будете хранить полный HTML или JSON результатов в файле:
    results_file_path = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        verbose_name="Путь к файлу результатов (относительно MEDIA_ROOT)"
    )


    warnings_json = models.JSONField(default=list, blank=True, verbose_name="Предупреждения")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Запуск прогноза"
        verbose_name_plural = "Запуски прогнозов"

    def __str__(self):
        user_str = self.user.username if self.user else "Аноним"
        title_str = f" «{self.custom_title}»" if self.custom_title else ""
        return f"Прогноз {title_str} от {self.created_at.strftime('%d.%m.%Y %H:%M')} ({user_str})"

    def get_absolute_url(self):

        return "#"  # Заглушка

    def get_results_display_url(self):

        return None