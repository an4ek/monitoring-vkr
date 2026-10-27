import { useLocation, useNavigate } from 'react-router'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Form, Input } from 'antd'
import { login } from '../api/auth.ts'

type Fields = { username: string; password: string }

// Страница входа: логин и пароль выдаёт администратор системы
export default function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()

  const signIn = useMutation({
    mutationFn: ({ username, password }: Fields) => login(username, password),
    onSuccess: (me) => {
      queryClient.clear() // данные прошлого пользователя не показываем
      queryClient.setQueryData(['me'], me)
      navigate((location.state as { from?: string } | null)?.from ?? '/incidents', { replace: true })
    },
  })

  return (
    <div className="login">
      <Card title="Вход в систему" className="login__card">
        <Form<Fields> layout="vertical" onFinish={(values) => signIn.mutate(values)} requiredMark={false}>
          <Form.Item label="Логин" name="username" rules={[{ required: true, message: 'Введите логин' }]}>
            <Input autoComplete="username" autoFocus />
          </Form.Item>
          <Form.Item label="Пароль" name="password" rules={[{ required: true, message: 'Введите пароль' }]}>
            <Input.Password autoComplete="current-password" />
          </Form.Item>
          {signIn.isError && <Alert type="error" title={signIn.error.message} style={{ marginBottom: 16 }} />}
          <Button type="primary" htmlType="submit" block loading={signIn.isPending}>
            Войти
          </Button>
        </Form>
        {/* Подсказка видна только при разработке, в собранной версии ее нет */}
        {import.meta.env.DEV && (
          <p className="hint" style={{ marginTop: 16 }}>
            Тестовые учётные записи (пароль demo12345): ivanov, petrova — инженеры; orlova — руководитель; admin —
            администратор.
          </p>
        )}
      </Card>
    </div>
  )
}
