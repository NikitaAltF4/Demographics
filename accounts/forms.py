from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True, help_text='Обязательное поле. Введите корректный email.')
    first_name = forms.CharField(max_length=30, required=False, help_text='Необязательное поле.')
    last_name = forms.CharField(max_length=150, required=False, help_text='Необязательное поле.')

    class Meta(UserCreationForm.Meta):
        model = User # Используем стандартную модель User
        fields = UserCreationForm.Meta.fields + ('email', 'first_name', 'last_name',)
