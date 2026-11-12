"""Форма заявки на доставку и расчёт её стоимости."""

from decimal import Decimal, ROUND_HALF_UP

from django import forms

# Базовая ставка и цена за каждый килограмм, ₽
BASE_RATE = Decimal('300')
PRICE_PER_KG = Decimal('30')

# Наценка по типу доставки
DELIVERY_COEFFICIENTS = {
    'standard': Decimal('1.0'),
    'express': Decimal('1.5'),
    'same_day': Decimal('2.0'),
}

# Известные промокоды: код -> скидка в процентах
PROMO_CODES = {
    'SALE5': Decimal('5'),
    'SALE10': Decimal('10'),
    'SALE15': Decimal('15'),
}

MAX_EXPRESS_WEIGHT = Decimal('20')


def money(value):
    """Округление денежной суммы до 2 знаков (банковское округление)."""
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class DeliveryForm(forms.Form):
    sender_name = forms.CharField(
        label='ФИО отправителя',
        min_length=3,
        max_length=150,
        error_messages={'required': 'Укажите ФИО отправителя.'},
        widget=forms.TextInput(
            attrs={'placeholder': 'Иванов Иван Иванович', 'autocomplete': 'name'}
        ),
    )
    phone = forms.CharField(
        label='Телефон',
        max_length=20,
        error_messages={'required': 'Укажите номер телефона.'},
        widget=forms.TextInput(
            attrs={'placeholder': '+7 (999) 123-45-67', 'autocomplete': 'tel'}
        ),
    )
    city_from = forms.CharField(
        label='Город отправки',
        max_length=100,
        error_messages={'required': 'Укажите город отправки.'},
        widget=forms.TextInput(attrs={'placeholder': 'Москва'}),
    )
    city_to = forms.CharField(
        label='Город получения',
        max_length=100,
        error_messages={'required': 'Укажите город получения.'},
        widget=forms.TextInput(attrs={'placeholder': 'Казань'}),
    )
    weight = forms.DecimalField(
        label='Вес, кг',
        min_value=Decimal('0.1'),
        max_value=Decimal('100'),
        max_digits=5,
        decimal_places=2,
        error_messages={
            'required': 'Укажите вес посылки.',
            'invalid': 'Введите корректный вес в килограммах.',
            'min_value': 'Вес должен быть не меньше 0,1 кг.',
            'max_value': 'Вес не может превышать 100 кг.',
        },
        widget=forms.NumberInput(
            attrs={'placeholder': '1.5', 'step': '0.01', 'min': '0.1', 'max': '100'}
        ),
    )
    delivery_type = forms.ChoiceField(
        label='Тип доставки',
        choices=[
            ('standard', 'Стандартная (×1.0)'),
            ('express', 'Экспресс (×1.5)'),
            ('same_day', 'В день заказа (×2.0)'),
        ],
        error_messages={'required': 'Выберите тип доставки.'},
    )
    promo_code = forms.CharField(
        label='Промокод',
        required=False,
        max_length=30,
        help_text='Необязательно. Попробуйте SALE5, SALE10 или SALE15.',
        widget=forms.TextInput(attrs={'placeholder': 'SALE10', 'autocomplete': 'off'}),
    )
    agree = forms.BooleanField(
        label='Согласен с условиями доставки',
        error_messages={'required': 'Для отправки заявки нужно согласие с условиями.'},
    )

    def clean_sender_name(self):
        return self.cleaned_data['sender_name'].strip()

    def clean_phone(self):
        """Оставляем только цифры и проверяем российский формат."""
        raw = self.cleaned_data['phone']
        digits = ''.join(ch for ch in raw if ch.isdigit())

        if len(digits) == 11 and digits[0] in ('7', '8'):
            return '+7' + digits[1:]
        if len(digits) == 10:
            return '+7' + digits

        raise forms.ValidationError(
            'Телефон должен содержать 11 цифр, например +7 (999) 123-45-67.'
        )

    def clean_city_from(self):
        return self.cleaned_data['city_from'].strip()

    def clean_city_to(self):
        return self.cleaned_data['city_to'].strip()

    def clean_promo_code(self):
        """Проверка промокода: пустой — допустим, неизвестный — ошибка."""
        code = (self.cleaned_data.get('promo_code') or '').strip().upper()
        if not code:
            return ''
        if code not in PROMO_CODES:
            raise forms.ValidationError(
                'Неизвестный промокод. Доступны: ' + ', '.join(sorted(PROMO_CODES)) + '.'
            )
        return code

    def clean(self):
        cleaned_data = super().clean()
        city_from = cleaned_data.get('city_from')
        city_to = cleaned_data.get('city_to')
        weight = cleaned_data.get('weight')
        delivery_type = cleaned_data.get('delivery_type')

        # Города отправки и получения не должны совпадать
        if city_from and city_to:
            if city_from.strip().lower() == city_to.strip().lower():
                self.add_error(
                    'city_to', 'Город получения должен отличаться от города отправки.'
                )

        # Экспресс-доставка ограничена по весу
        if (
            delivery_type == 'express'
            and weight is not None
            and weight > MAX_EXPRESS_WEIGHT
        ):
            self.add_error(
                'weight',
                f'Для экспресс-доставки вес не может превышать '
                f'{MAX_EXPRESS_WEIGHT:g} кг.',
            )

        return cleaned_data

    def calculate(self):
        """Стоимость доставки с разбивкой по составляющим.

        Возвращает словарь с базовой ставкой, надбавкой за вес,
        коэффициентом типа доставки, скидкой и итоговой суммой.
        Ожидает, что форма уже прошла валидацию (is_valid() == True).
        """
        if not self.is_valid():
            raise ValueError('Нельзя рассчитать стоимость невалидной формы.')

        data = self.cleaned_data
        weight = data['weight']
        delivery_type = data['delivery_type']
        coefficient = DELIVERY_COEFFICIENTS[delivery_type]

        weight_extra = PRICE_PER_KG * weight
        before_coefficient = BASE_RATE + weight_extra
        before_discount = money(before_coefficient * coefficient)

        promo = data.get('promo_code') or ''
        discount_percent = PROMO_CODES.get(promo, Decimal('0'))
        discount_amount = money(before_discount * discount_percent / Decimal('100'))
        total = money(before_discount - discount_amount)

        return {
            'base_rate': money(BASE_RATE),
            'weight': weight,
            'weight_extra': money(weight_extra),
            'coefficient': coefficient,
            'before_discount': before_discount,
            'promo_code': promo,
            'discount_percent': discount_percent,
            'discount_amount': discount_amount,
            'total': total,
        }
