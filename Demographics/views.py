from django.shortcuts import render

def home_view(request):
    """
    Отображает главную страницу сайта.
    """
    context = {
        'page_title': 'Демографическое прогнозирование', # Пример передачи данных в шаблон
    }
    return render(request, 'home.html', context)


def method_age_shift_info_view(request):
    """
    Отображает страницу с информацией о методе передвижки возрастов.
    """
    return render(request, 'metodologiya.html')



def detalniy_analiz_info_view(request):
    """
    Отображает страницу с информацией о методе передвижки возрастов.
    """
    return render(request, 'detalniy_analiz.html')


def primenenie_view(request):
    """
    Отображает страницу с информацией о методе передвижки возрастов.
    """
    return render(request, 'primenenie.html')