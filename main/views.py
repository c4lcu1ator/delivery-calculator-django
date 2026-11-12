from django.shortcuts import render

from .forms import DeliveryForm


def delivery_view(request):
    """Главная страница: форма заявки и результат расчёта."""
    form = DeliveryForm(request.POST or None)
    result = None

    if request.method == 'POST' and form.is_valid():
        result = form.calculate()

    return render(request, 'demo/delivery.html', {'form': form, 'result': result})
