"""Проверки входа. Запуск: python manage.py test accounts"""
from unittest import mock

from django.core.management import call_command
from django.test import Client, TestCase, override_settings


# Быстрый хеш паролей только для проверок, чтобы тесты не шли минуту
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class LoginTests(TestCase):
    def setUp(self):
        with mock.patch('sys.stdout'):
            call_command('demo_reset')
        # Клиент с проверкой CSRF, как настоящий браузер
        self.browser = Client(enforce_csrf_checks=True)

    def csrf(self):
        self.browser.get('/api/auth/csrf/')
        return self.browser.cookies['csrftoken'].value

    def test_login_logout(self):
        token = self.csrf()
        wrong = self.browser.post('/api/auth/login/', {'username': 'ivanov', 'password': 'x'},
                                  content_type='application/json', headers={'X-CSRFToken': token})
        self.assertEqual(wrong.status_code, 400)
        ok = self.browser.post('/api/auth/login/', {'username': 'ivanov', 'password': 'demo12345'},
                               content_type='application/json', headers={'X-CSRFToken': token})
        self.assertEqual(ok.json()['role'], 'engineer')
        self.assertEqual(self.browser.get('/api/auth/me/').json()['full_name'], 'Иванов Сергей')

        token = self.browser.cookies['csrftoken'].value  # после входа токен меняется
        # Без CSRF-токена изменяющий запрос не проходит
        self.assertEqual(self.browser.post('/api/incidents/1/take/').status_code, 403)
        self.assertEqual(self.browser.post('/api/incidents/1/take/', headers={'X-CSRFToken': token}).status_code, 200)

        self.browser.post('/api/auth/logout/', headers={'X-CSRFToken': token})
        self.assertEqual(self.browser.get('/api/auth/me/').status_code, 403)

    def test_login_requires_csrf(self):
        response = self.browser.post('/api/auth/login/', {'username': 'ivanov', 'password': 'demo12345'},
                                     content_type='application/json')
        self.assertEqual(response.status_code, 403)
