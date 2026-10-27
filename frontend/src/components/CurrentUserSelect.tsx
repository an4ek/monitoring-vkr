import { Select } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { fetchPeople } from '../api/catalog.ts'
import { setCurrentUser, useCurrentUser } from '../hooks/useCurrentUser.ts'

// Выбор «кто я» в шапке — временная замена входа в систему.
// Нужен, чтобы в истории инцидента было видно, кто взял его в работу и кто закрыл.
export default function CurrentUserSelect() {
  const people = useQuery({ queryKey: ['people'], queryFn: fetchPeople })
  const currentId = useCurrentUser()

  return (
    <Select<number>
      style={{ width: 220 }}
      placeholder="Кто вы?"
      loading={people.isPending}
      value={currentId ?? undefined}
      onChange={setCurrentUser}
      options={(people.data ?? []).map((person) => ({ value: person.id, label: person.full_name }))}
    />
  )
}
