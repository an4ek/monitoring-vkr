import { Link } from 'react-router'

export default function NotFoundPage() {
  return (
    <>
      <h1>Страница не найдена</h1>
      <p className="hint">
        <Link to="/incidents">Вернуться к инцидентам</Link>
      </p>
    </>
  )
}
