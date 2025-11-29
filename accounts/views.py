from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.http import JsonResponse
from django.urls import reverse

from .forms import CustomUserCreationForm  # Импортируем нашу форму


def signup_view(request):
    if request.user.is_authenticated:
        return redirect('home')  # Если пользователь уже вошел, отправляем на главную

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # Автоматический вход после успешной регистрации

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':  # Если это AJAX запрос
                return JsonResponse({'status': 'success', 'redirect_url': reverse('home')})
            return redirect('home')  # Для обычной отправки формы
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'errors': form.errors.get_json_data(escape_html=True)},
                                    status=400)
            # Для обычной отправки, ошибки будут в form и отобразятся в шаблоне signup.html
    else:
        form = CustomUserCreationForm()


    return render(request, 'registration/signup.html', {'form': form})

