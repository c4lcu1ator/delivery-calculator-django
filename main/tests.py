from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from .forms import DeliveryForm

VALID_DATA = {
    'sender_name': 'Иванов Иван Иванович',
    'phone': '+7 (999) 123-45-67',
    'city_from': 'Москва',
    'city_to': 'Казань',
    'weight': '1',
    'delivery_type': 'standard',
    'promo_code': '',
    'agree': 'on',
}


def make_form(**overrides):
    data = {**VALID_DATA, **overrides}
    return DeliveryForm(data=data)


class DeliveryCalculationTests(TestCase):
    def test_standard_delivery(self):
        result = make_form(weight='1').calculate()
        self.assertEqual(result['total'], Decimal('330.00'))

    def test_express_delivery(self):
        # (300 + 30 * 10) * 1.5 = 900
        result = make_form(weight='10', delivery_type='express').calculate()
        self.assertEqual(result['total'], Decimal('900.00'))

    def test_same_day_delivery(self):
        # (300 + 30 * 5) * 2 = 900
        result = make_form(weight='5', delivery_type='same_day').calculate()
        self.assertEqual(result['total'], Decimal('900.00'))

    def test_fractional_weight_is_rounded(self):
        # (300 + 30 * 0.1) = 303 -> standard
        result = make_form(weight='0.1').calculate()
        self.assertEqual(result['total'], Decimal('303.00'))

    def test_min_weight_rounding_to_two_places(self):
        # (300 + 30 * 0.33) * 1.5 = 464.85
        result = make_form(weight='0.33', delivery_type='express').calculate()
        self.assertEqual(result['total'], Decimal('464.85'))


class PromoCodeTests(TestCase):
    def test_promo_code_is_normalized(self):
        form = make_form(promo_code=' sale10 ')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['promo_code'], 'SALE10')

    def test_promo_code_applies_discount(self):
        # 330 − 10% = 297
        result = make_form(promo_code='SALE10').calculate()
        self.assertEqual(result['discount_percent'], Decimal('10'))
        self.assertEqual(result['discount_amount'], Decimal('33.00'))
        self.assertEqual(result['total'], Decimal('297.00'))

    def test_fifteen_percent_discount(self):
        result = make_form(promo_code='SALE15').calculate()
        self.assertEqual(result['total'], Decimal('280.50'))

    def test_unknown_promo_code_is_rejected(self):
        form = make_form(promo_code='FREEDELIVERY')
        self.assertFalse(form.is_valid())
        self.assertIn('promo_code', form.errors)

    def test_empty_promo_code_is_allowed(self):
        form = make_form(promo_code='')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['promo_code'], '')


class ValidationTests(TestCase):
    def test_weight_below_minimum(self):
        form = make_form(weight='0.05')
        self.assertFalse(form.is_valid())
        self.assertIn('weight', form.errors)

    def test_weight_above_maximum(self):
        form = make_form(weight='150')
        self.assertFalse(form.is_valid())
        self.assertIn('weight', form.errors)

    def test_cities_must_differ(self):
        form = make_form(city_from='Москва', city_to='  москва ')
        self.assertFalse(form.is_valid())
        self.assertIn('city_to', form.errors)

    def test_express_weight_limit(self):
        form = make_form(weight='21', delivery_type='express')
        self.assertFalse(form.is_valid())
        self.assertIn('weight', form.errors)

    def test_express_weight_on_the_limit_is_allowed(self):
        form = make_form(weight='20', delivery_type='express')
        self.assertTrue(form.is_valid(), form.errors)

    def test_same_day_has_no_extra_weight_limit(self):
        form = make_form(weight='99', delivery_type='same_day')
        self.assertTrue(form.is_valid(), form.errors)

    def test_agreement_is_required(self):
        data = {k: v for k, v in VALID_DATA.items() if k != 'agree'}
        form = DeliveryForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('agree', form.errors)

    def test_phone_is_normalized(self):
        form = make_form(phone='8 999 123 45 67')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['phone'], '+79991234567')

    def test_invalid_phone_is_rejected(self):
        form = make_form(phone='12345')
        self.assertFalse(form.is_valid())
        self.assertIn('phone', form.errors)


class DeliveryViewTests(TestCase):
    def test_get_renders_empty_form(self):
        response = self.client.get(reverse('main:delivery'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Калькулятор доставки')
        self.assertContains(response, 'csrfmiddlewaretoken')

    def test_valid_post_shows_result(self):
        response = self.client.post(reverse('main:delivery'), VALID_DATA)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Результат расчёта')
        # При LANGUAGE_CODE='ru-ru' числа выводятся с запятой
        self.assertContains(response, '330,00')

    def test_invalid_post_keeps_entered_values(self):
        data = {**VALID_DATA, 'weight': '0.05', 'sender_name': 'Петров Пётр Петрович'}
        response = self.client.post(reverse('main:delivery'), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Петров Пётр Петрович')
        self.assertContains(response, 'Вес должен быть не меньше')
        self.assertNotContains(response, 'Результат расчёта')
